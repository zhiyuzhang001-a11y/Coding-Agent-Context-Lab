from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import runpy
import subprocess
import sys
import tomllib
import unittest
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
CONTRACT_PATH = RESOURCES / "acp1_4f_frozen_contract.json"
ORACLE_PATH = RESOURCES / "acp1_4f_oracle_registry.json"
INDEX_PATH = RESOURCES / "acp1_4f_f0_frozen_index.json"
BUILDER_PATH = ROOT / "scripts/acp1_4f_treatment_contract.py"
VERIFIER_PATH = ROOT / "scripts/verify_acp1_4f_f0.py"
SUBJECTS = RESOURCES / "acp1_4f_subjects"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_builder():
    spec = importlib.util.spec_from_file_location("acp1_4f_treatment_contract", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tree_hash(root: Path) -> str:
    rows = [
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
    return hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()


class Acp14fF0ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load(CONTRACT_PATH)
        cls.oracle = load(ORACLE_PATH)
        cls.index = load(INDEX_PATH)
        cls.builder = load_builder()

    def test_fixed_sampling_frame_has_twelve_fresh_cross_context_cases(self) -> None:
        cases = self.contract["cases"]
        self.assertEqual(len(cases), 12)
        self.assertEqual(Counter(row["family"] for row in cases), {"read": 4, "search": 4, "bash": 4})
        contexts = defaultdict(set)
        for row in cases:
            contexts[row["family"]].add(row["project_form"])
            self.assertTrue(row["case_id"].startswith("f_"))
        self.assertGreaterEqual(len({row["project_form"] for row in cases}), 3)
        self.assertTrue(all(len(values) >= 2 for values in contexts.values()))
        self.assertFalse(self.contract["sampling"]["replacement_allowed"])
        self.assertFalse(self.contract["sampling"]["historical_primary_cases_allowed"])

    def test_subject_snapshots_are_hash_bound(self) -> None:
        for row in self.contract["cases"]:
            path = ROOT / row["subject_path"]
            self.assertTrue(path.exists())
            if "subject_sha256" in row:
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["subject_sha256"])
            else:
                self.assertEqual(tree_hash(path), row["subject_tree_sha256"])

    def test_oracle_registry_is_complete_and_physically_separate(self) -> None:
        case_ids = {row["case_id"] for row in self.contract["cases"]}
        self.assertEqual(set(self.oracle["cases"]), case_ids)
        serialized_cases = json.dumps(self.contract["cases"], sort_keys=True).casefold()
        self.assertNotIn('"expected"', serialized_cases)
        self.assertNotIn('"scorer"', serialized_cases)
        self.assertEqual(self.oracle["visibility"], "outer_harness_only_never_builder_input")

    def test_ground_truth_matches_frozen_subjects(self) -> None:
        alpha_settings = runpy.run_path(str(SUBJECTS / "alpha_service/settings.py"))
        alpha_routes = runpy.run_path(str(SUBJECTS / "alpha_service/routes.py"))["ROUTES"]
        beta_config = load(SUBJECTS / "beta_cli/config.json")
        beta_commands = runpy.run_path(str(SUBJECTS / "beta_cli/commands.py"))["COMMANDS"]
        with (SUBJECTS / "gamma_pipeline/pipeline.toml").open("rb") as handle:
            gamma_pipeline = tomllib.load(handle)
        gamma_regions = load(SUBJECTS / "gamma_pipeline/regions.json")
        expected = {
            "f_read_alpha_retry_v1": str(alpha_settings["MAX_RETRIES"]),
            "f_read_alpha_maintenance_method_v1": next(row["method"] for row in alpha_routes if row["name"] == "maintenance"),
            "f_read_beta_result_limit_v1": str(beta_config["output"]["result_limit"]),
            "f_read_gamma_batch_size_v1": str(gamma_pipeline["batch_size"]),
            "f_search_alpha_maintenance_status_v1": next(row["status"] for row in alpha_routes if row["name"] == "maintenance"),
            "f_search_beta_archive_category_v1": beta_commands["archive"]["category"],
            "f_search_beta_default_color_v1": beta_config["output"]["color"],
            "f_search_gamma_production_retention_v1": str(gamma_regions["production"]["retention_days"]),
        }
        commands = {
            "f_bash_alpha_failed_checks_v1": ("alpha_service", "status_report.py", "failed"),
            "f_bash_beta_command_count_v1": ("beta_cli", "verify_manifest.py", "command_count"),
            "f_bash_gamma_valid_shards_v1": ("gamma_pipeline", "validate_pipeline.py", "valid_shards"),
            "f_bash_gamma_total_stages_v1": ("gamma_pipeline", "pipeline_summary.py", "total_stages"),
        }
        for case_id, (project, script, key) in commands.items():
            completed = subprocess.run(
                [sys.executable, script], cwd=SUBJECTS / project, check=True, text=True, capture_output=True
            )
            expected[case_id] = str(json.loads(completed.stdout)["summary"][key])
        self.assertEqual({key: value["expected"] for key, value in self.oracle["cases"].items()}, expected)

    def test_builder_input_surface_is_exact_and_rejects_nested_oracles(self) -> None:
        self.assertEqual(tuple(self.builder.ALLOWED_FIELDS), tuple(self.contract["builder_contract"]["allowed_input_fields"]))
        base = {
            "tool_family": "read",
            "request_shape": {"anchors": ["LIMIT"]},
            "requested_path_identity": "path-hash",
            "requested_range": None,
            "query_shape": {},
            "command_shape": {},
            "structural_result": [{"kind": "line", "text": "LIMIT = 4"}],
            "frozen_template_params": {},
        }
        with self.assertRaises(TypeError):
            self.builder.TreatmentBuilderInput(**base, case_id="hidden")
        for key in self.contract["builder_contract"]["prohibited_input_keys"]:
            poisoned = dict(base)
            poisoned["request_shape"] = {"nested": {key: "hidden"}}
            with self.subTest(key=key), self.assertRaises(self.builder.ContractViolation):
                self.builder.TreatmentBuilderInput(**poisoned)

    def test_builder_has_no_registry_or_file_access_and_no_case_literals(self) -> None:
        tree = ast.parse(BUILDER_PATH.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(imported.isdisjoint({"json", "pathlib", "subprocess"}))
        source = BUILDER_PATH.read_text(encoding="utf-8")
        for case_id in self.oracle["cases"]:
            self.assertNotIn(case_id, source)

    def test_templates_are_deterministic_and_preserve_unknowns(self) -> None:
        read_value = self.builder.TreatmentBuilderInput(
            "read", {"anchors": ["LIMIT"]}, "p1", None, {}, {},
            [
                {"kind": "header", "text": "header"},
                {"kind": "line", "text": "noise"},
                {"kind": "line", "text": "LIMIT = 4"},
                {"kind": "line", "text": "tail"},
                {"kind": "line", "text": "more"},
                {"kind": "line", "text": "far"},
            ],
            {"context_before": 0, "context_after": 1},
        )
        self.assertEqual(self.builder.build_treatment(read_value), self.builder.build_treatment(read_value))
        self.assertEqual(self.builder.build_treatment(read_value).disposition, "projected")

        search_value = self.builder.TreatmentBuilderInput(
            "search", {}, None, None, {"term": "x"}, {},
            [
                {"path_identity": "b", "structural_key": "k", "ordinal": 2, "text": "third"},
                {"path_identity": "a", "structural_key": "k", "ordinal": 1, "text": "first"},
                {"path_identity": "a", "structural_key": "k", "ordinal": 3, "text": "second"},
            ],
            {"first_n_per_group": 1},
        )
        search_output = self.builder.build_treatment(search_value)
        self.assertEqual([row["text"] for row in search_output.records], ["first", "third"])

        bash_value = self.builder.TreatmentBuilderInput(
            "bash", {}, None, None, {}, {"format": "free_text"},
            [{"kind": "log", "text": "opaque output"}], {},
        )
        self.assertEqual(self.builder.build_treatment(bash_value).disposition, "passthrough")

    def test_gates_budget_and_frozen_product_boundaries(self) -> None:
        self.assertEqual(self.contract["formal_admission"], {
            "native_qualified_and_offline_eligible_required": True,
            "minimum_cases": 9,
            "minimum_cases_per_family": 3,
        })
        self.assertEqual(self.contract["overall"]["pass_rate_denominator"], "all_formal_admitted_cases")
        self.assertTrue(self.contract["overall"]["inconclusive_in_denominator"])
        self.assertEqual(self.contract["run_budget"]["primary_agent_run_hard_max"], 366)
        self.assertEqual(self.contract["status"], "f0_frozen_agent_runs_not_started")
        self.assertFalse(any(self.contract["policy"].values()))
        self.assertEqual(self.contract["builder_contract"]["violation_policy"], "invalidate_experiment_version_restart_without_run_reuse")

    def test_frozen_index_verifies_without_agent_runs(self) -> None:
        spec = importlib.util.spec_from_file_location("verify_acp1_4f_f0", VERIFIER_PATH)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        result = verifier.verify(ROOT, INDEX_PATH)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["agent_run_count"], 0)
        self.assertFalse(self.index["agent_runs_authorized"])
        self.assertEqual(self.index["verdict"], "READY_FOR_NATIVE_QUALIFICATION")


if __name__ == "__main__":
    unittest.main()
