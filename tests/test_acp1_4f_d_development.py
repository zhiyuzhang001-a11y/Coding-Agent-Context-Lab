from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
CONTRACT = ROOT / "resources/acp1_4f_d_development_contract.json"
SCHEMA = ROOT / "resources/acp1_4f_d_registry_schema.json"
FIXTURE = ROOT / "resources/acp1_4f_d_offline_fixture.json"
POOL = ROOT / "resources/acp1_4f_d_case_pool.json"
ORACLE = ROOT / "resources/acp1_4f_d_oracle_registry.json"
SUBJECTS = ROOT / "resources/acp1_4f_d_subjects"
SCREEN_REGISTRY = ROOT / "resources/acp1_4f_d_development_registry.json"
EXTENSION_CONTRACT = ROOT / "resources/acp1_4f_d_extension_contract.json"
EXTENSION_INDEX = ROOT / "resources/acp1_4f_d_extension_authorization_index.json"
EXTENSION_REGISTRY = ROOT / "resources/acp1_4f_d_extension_registry.json"
FINAL_INDEX = ROOT / "resources/acp1_4f_d_frozen_final_index.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Acp14fDDevelopmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("run_acp1_4f_d_development", SCRIPTS / "run_acp1_4f_d_development.py")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.pool = json.loads(POOL.read_text(encoding="utf-8"))
        cls.oracle = json.loads(ORACLE.read_text(encoding="utf-8"))

    @staticmethod
    def command_event(command: str, output: str, exit_code: int = 0) -> dict:
        return {"type": "item.completed", "item": {"type": "command_execution", "command": command, "aggregated_output": output, "exit_code": exit_code}}

    def test_contract_keeps_v3_and_interventions_blocked(self) -> None:
        self.assertEqual(self.contract["upstream"]["v3_status"], "BLOCKED_BY_BENCHMARK_DEVELOPMENT")
        self.assertEqual(self.contract["scope"]["r1_s1_b1_status"], "frozen")
        self.assertFalse(self.contract["scope"]["intervention_enabled"])
        self.assertTrue(self.contract["authorization"]["screen_runs_authorized"])
        self.assertFalse(self.contract["authorization"]["extension_runs_authorized"])
        self.assertEqual(self.contract["execution"]["screen_run_count"], 72)
        self.assertEqual(self.contract["execution"]["hard_agent_run_cap"], 240)

    def test_observed_family_is_not_forced_to_intended_form(self) -> None:
        case = self.fixture["cases"][0]
        output = "fixture_project/config.py:10:deployment_state = ready\n" + ("context\n" * 120)
        analysis = self.runner.analyze_exec_events(
            [self.command_event("/bin/zsh -lc 'rg -n deployment_state fixture_project'", output)], case, self.contract
        )
        self.assertEqual(case["intended_evidence_form"], "read_like")
        self.assertEqual(analysis["evidence_family"], "search_like")
        self.assertEqual(analysis["carrier"], "bash_rg")
        self.assertTrue(analysis["meaningful_evidence"])

    def test_structured_json_uses_request_field_without_oracle(self) -> None:
        case = self.fixture["cases"][1]
        output = '{"summary_status":"pass","rows":[' + ("{\"name\":\"check\",\"ok\":true}," * 40) + '{}]}'
        analysis = self.runner.analyze_exec_events(
            [self.command_event("python fixture_project/validate.py --json", output)], case, self.contract
        )
        self.assertEqual(analysis["evidence_family"], "structured_bash_like")
        self.assertEqual(analysis["carrier"], "bash_json")
        self.assertTrue(analysis["evidence_opportunity_identified"])

    def test_read_intent_can_be_observed_through_search_carrier(self) -> None:
        case = {
            "request_identity": {"subject_scopes": ["project/config.py"], "request_anchors": ["LIMIT"], "query_terms": [], "structural_fields": []}
        }
        output = "project/config.py:10:LIMIT = 55\n" + ("project/config.py:11:context\n" * 80)
        analysis = self.runner.analyze_exec_events(
            [self.command_event("rg -n LIMIT project/config.py", output)], case, self.contract
        )
        self.assertEqual(analysis["evidence_family"], "search_like")
        self.assertTrue(analysis["evidence_opportunity_identified"])

    def test_ambiguous_opportunities_trigger_structural_futility(self) -> None:
        case = self.fixture["cases"][0]
        output = "fixture_project/config.py:10:deployment_state = ready\n" + ("context\n" * 120)
        event = self.command_event("rg -n deployment_state fixture_project", output)
        analysis = self.runner.analyze_exec_events([event, event], case, self.contract)
        run = {"correct": True, **analysis}
        reasons = self.runner.futility_reasons([run], 10, self.contract["final_case_gates"], False)
        self.assertIn("F_AMBIGUOUS_IDENTITY", reasons)

    def test_screen_futility_uses_maximum_achievable_counts(self) -> None:
        base = {
            "correct": True,
            "measurement_unknown": False,
            "truncation_observed": False,
            "ambiguous_identity": False,
            "evidence_opportunity_identified": False,
            "compatible_carrier_identified": False,
            "meaningful_evidence": False,
            "evidence_family": None,
        }
        reasons = self.runner.futility_reasons([dict(base) for _ in range(3)], 10, self.contract["final_case_gates"], False)
        self.assertIn("F_EVIDENCE_NOT_IDENTIFIABLE", reasons)
        self.assertIn("F_NO_COMPATIBLE_CARRIER", reasons)
        self.assertIn("F_INTERVENTION_NOT_MEANINGFUL", reasons)

    def test_registry_schema_contains_programmatic_formal_inputs(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        case = schema["$defs"]["case"]
        self.assertFalse(case["additionalProperties"])
        for field in ("design", "tool_family", "evidence_family", "carrier", "identity", "measurement", "qualification", "status"):
            self.assertIn(field, case["required"])

    def test_runner_does_not_import_or_enable_treatment_builder(self) -> None:
        source = (SCRIPTS / "run_acp1_4f_d_development.py").read_text(encoding="utf-8")
        self.assertNotIn("acp1_4f_treatment_contract", source)
        self.assertIn('"treatment_builder_used": False', source)
        self.assertIn('"intervention_used": False', source)

    def test_pool_has_twenty_four_new_balanced_design_targets(self) -> None:
        cases = self.pool["cases"]
        self.assertEqual(len(cases), 24)
        self.assertEqual(len({case["case_id"] for case in cases}), 24)
        self.assertEqual({case["intended_evidence_form"] for case in cases}, {"read_like", "search_like", "structured_bash_like"})
        self.assertEqual(
            {family: sum(case["intended_evidence_form"] == family for case in cases) for family in {case["intended_evidence_form"] for case in cases}},
            {"read_like": 8, "search_like": 8, "structured_bash_like": 8},
        )
        self.assertEqual(len({case["project_form"] for case in cases}), 4)
        self.assertFalse(any(case["case_id"].startswith("f_") for case in cases))

    def test_pool_subjects_and_oracles_are_complete_and_prompt_hidden(self) -> None:
        cases = self.pool["cases"]
        self.assertEqual(set(self.oracle["cases"]), {case["case_id"] for case in cases})
        for case in cases:
            subject = SUBJECTS / case["subject_path"]
            self.assertTrue(subject.exists())
            if case["intended_evidence_form"] != "search_like":
                self.assertTrue(subject.is_file())
            expected = self.oracle["cases"][case["case_id"]]["expected"]
            self.assertFalse(self.runner.prompt_inferable(case, {"expected": expected}))

    def test_structured_subjects_emit_large_parseable_reports(self) -> None:
        scripts = {
            "delta_web/validate_service.py": ("summary_status", "review", "failing_check_count", 2),
            "epsilon_cli/verify_manifest.py": ("manifest_status", "attention", "invalid_entry_count", 3),
            "zeta_jobs/validate_jobs.py": ("pipeline_status", "quarantine", "invalid_shard_count", 4),
            "eta_library/audit_library.py": ("catalog_status", "partial", "unindexed_collection_count", 2),
        }
        for relative, (status_key, status, count_key, count) in scripts.items():
            completed = subprocess.run([sys.executable, str(SUBJECTS / relative), "--json"], text=True, capture_output=True, check=True)
            report = json.loads(completed.stdout)
            self.assertEqual(report[status_key], status)
            self.assertEqual(report[count_key], count)
            self.assertGreaterEqual((len(completed.stdout) + 3) // 4, self.contract["measurement"]["minimum_meaningful_evidence_tokens"])

    def test_offline_check_has_zero_agent_runs_and_expected_budget(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_acp1_4f_d_development.py"), "--stage", "offline-check"],
            cwd=ROOT.parents[1], text=True, capture_output=True, check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["case_count"], 24)
        self.assertEqual(result["screen_run_count"], 72)
        self.assertEqual(result["hard_agent_run_cap"], 240)

    def test_frozen_protocol_and_subject_inventory_verify(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "verify_acp1_4f_d_protocol.py")],
            cwd=ROOT.parents[1], text=True, capture_output=True, check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["case_count"], 24)
        self.assertEqual(result["agent_run_count_at_freeze"], 0)

    def test_extension_contract_changes_only_phase_authorization(self) -> None:
        base = json.loads(CONTRACT.read_text(encoding="utf-8"))
        extension = json.loads(EXTENSION_CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(extension["status"], "screen_complete_extension_authorized")
        self.assertTrue(extension["authorization"]["extension_runs_authorized"])
        base.pop("status")
        extension.pop("status")
        base_auth = base.pop("authorization")
        extension_auth = extension.pop("authorization")
        self.assertEqual(base, extension)
        self.assertEqual({key: value for key, value in base_auth.items() if key != "extension_runs_authorized"}, {key: value for key, value in extension_auth.items() if key != "extension_runs_authorized"})

    def test_extension_admission_is_exactly_programmatic_screen_admission(self) -> None:
        registry = json.loads(SCREEN_REGISTRY.read_text(encoding="utf-8"))
        index = json.loads(EXTENSION_INDEX.read_text(encoding="utf-8"))
        admitted = [case["case_id"] for case in registry["cases"] if case["status"]["state"] == "screen_admitted"]
        self.assertEqual(admitted, index["admission"]["case_ids"])
        self.assertEqual(index["admission"]["case_count"], 7)
        for artifact in index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(self.runner.sha256_file(path), artifact["sha256"])

    def test_frozen_final_index_matches_registry_and_artifacts(self) -> None:
        registry = json.loads(EXTENSION_REGISTRY.read_text(encoding="utf-8"))
        index = json.loads(FINAL_INDEX.read_text(encoding="utf-8"))
        self.assertEqual(registry["status"], "complete")
        self.assertEqual(registry["verdict"], "BENCHMARK_SEMANTICS_NOT_SUPPORTED")
        self.assertEqual(index["verdict"], registry["verdict"])
        self.assertEqual(index["agent_run_count"], registry["agent_run_count"])
        self.assertEqual(index["outcome"]["qualified_case_count"], sum(case["status"]["state"] == "qualified" for case in registry["cases"]))
        for artifact in index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(self.runner.sha256_file(path), artifact["sha256"])

    def test_final_verdict_is_supported_by_observed_families(self) -> None:
        registry = json.loads(EXTENSION_REGISTRY.read_text(encoding="utf-8"))
        index = json.loads(FINAL_INDEX.read_text(encoding="utf-8"))
        counts = {}
        for case in registry["cases"]:
            if case["status"]["state"] == "qualified":
                family = case["evidence_family"]["dominant_family"]
                counts[family] = counts.get(family, 0) + 1
        expected = {"search_like": 4, "read_like": 0, "structured_bash_like": 0}
        self.assertEqual(index["outcome"]["qualified_cases_by_observed_family"], expected)
        self.assertEqual(counts, {"search_like": 4})
        self.assertEqual(index["decision"]["supported_observed_family_count"], 1)
        self.assertFalse(index["decision"]["v3_authorized"])
        self.assertTrue(index["decision"]["r1_s1_b1_frozen"])

    def test_public_final_artifacts_do_not_persist_private_paths_or_run_ids(self) -> None:
        registry_text = EXTENSION_REGISTRY.read_text(encoding="utf-8")
        index_text = FINAL_INDEX.read_text(encoding="utf-8")
        self.assertNotIn(".agent-token-manager", registry_text)
        self.assertNotIn(".agent-token-manager", index_text)
        self.assertNotIn("__r01-native", registry_text)
        self.assertNotIn("__r01-native", index_text)
        self.assertFalse(json.loads(index_text)["private_source"]["paths_persisted_publicly"])


if __name__ == "__main__":
    unittest.main()
