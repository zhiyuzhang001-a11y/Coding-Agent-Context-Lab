from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_acp1_4f_native_qualification.py"
CONTRACT = ROOT / "resources/acp1_4f_frozen_contract.json"
INDEX = ROOT / "resources/acp1_4f_f0_frozen_index.json"


def load_runner():
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location("run_acp1_4f_native_qualification", RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Acp14fNativeQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner()
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_refrozen_contract_has_explicit_identity_for_all_cases(self) -> None:
        value = self.runner.load_contract(ROOT, CONTRACT, INDEX)
        self.assertEqual(value["experiment_id"], "acp1-4f-combined-prospective-generalization-v2.1")
        self.assertEqual(value["candidate_identity"]["method"], "family_request_shape_and_success-v1")
        self.assertTrue(all(row.get("candidate_identity") for row in value["cases"]))
        self.assertFalse(value["execution"]["builder_enabled_during_native"])

    def test_candidate_matching_is_family_specific_and_success_preserving(self) -> None:
        cases = {row["case_id"]: row for row in self.contract["cases"]}
        good = [
            ({"command": "sed -n '1,80p' alpha_service/settings.py", "output": "MAX_RETRIES = 7\n"}, cases["f_read_alpha_retry_v1"]),
            ({"command": "rg -n maintenance alpha_service", "output": "routes.py:maintenance restricted\n"}, cases["f_search_alpha_maintenance_status_v1"]),
            ({"command": "cd beta_cli && python3 verify_manifest.py", "output": '{"summary":{"command_count":5}}\n'}, cases["f_bash_beta_command_count_v1"]),
        ]
        for call, case in good:
            with self.subTest(case=case["case_id"]):
                self.assertTrue(self.runner.candidate_match(call, case, 16))
        failed = {"command": "rg -n maintenance alpha_service", "output": "Script failed: 1\n"}
        self.assertFalse(self.runner.candidate_match(failed, cases["f_search_alpha_maintenance_status_v1"], 16))

    def test_path_signature_is_deterministic_and_multiple_matches_are_ambiguous(self) -> None:
        case = next(row for row in self.contract["cases"] if row["case_id"] == "f_read_alpha_retry_v1")
        calls = [
            {"tool_name": "Bash", "command": "cat alpha_service/settings.py", "output": "MAX_RETRIES = 7\n"},
            {"tool_name": "Bash", "command": "sed -n '1,20p' alpha_service/settings.py", "output": "MAX_RETRIES = 7\n"},
        ]
        first = self.runner.analyze_calls(calls, case, 16)
        second = self.runner.analyze_calls(calls, case, 16)
        self.assertEqual(first, second)
        self.assertTrue(first["candidate_ambiguous"])
        self.assertFalse(first["candidate_recurred"])

    def test_synthetic_complete_runs_apply_native_coverage_gate(self) -> None:
        runs = []
        for case in self.contract["cases"]:
            for repetition in range(1, 11):
                runs.append({
                    "run_id": f"{case['case_id']}-{repetition}", "case_id": case["case_id"], "repetition": repetition,
                    "status": "completed", "correct": True, "usage": {"total_tokens": 1000}, "model_cycles": 2,
                    "tool_call_count": 1, "candidate_match_count": 1, "candidate_recurred": True,
                    "candidate_ambiguous": False, "candidate_visible_estimated_tokens": 100,
                    "path_signature_sha256": "stable", "hook_or_collector_used": False, "treatment_builder_used": False,
                })
        with tempfile.TemporaryDirectory() as temporary:
            runner_copy = Path(temporary) / "runner.py"
            runner_copy.write_bytes(RUNNER.read_bytes())
            result, registry = self.runner.build_outputs(self.contract, CONTRACT, runner_copy, runs, {"version": "test"})
        self.assertEqual(result["run_count"], 120)
        self.assertTrue(registry["native_coverage_gate"])
        self.assertEqual(registry["summary"]["qualified_by_family"], {"read": 4, "search": 4, "bash": 4})
        self.assertTrue(registry["consumer_policy"]["f2_must_consume_all_ten_native_observations"])

    def test_public_compaction_excludes_answers_commands_and_result_bodies(self) -> None:
        compact = self.runner.compact_run({
            "run_id": "private", "case_id": "c", "repetition": 1, "status": "completed", "correct": True,
            "usage": {"total_tokens": 20}, "final_text": "secret", "expected": "secret",
            "command": "private command", "candidate_result": "private output",
        })
        serialized = json.dumps(compact, sort_keys=True)
        for prohibited in ("secret", "private command", "private output", "final_text", "expected"):
            self.assertNotIn(prohibited, serialized)

    def test_runner_is_native_only_and_does_not_import_builder(self) -> None:
        source = RUNNER.read_text(encoding="utf-8").casefold()
        self.assertNotIn("acp1_4f_treatment_contract", source)
        self.assertNotIn("build_treatment(", source)
        self.assertIn('"treatment_builder_used": false', source)
        self.assertIn('"hook_or_collector_used": false', source)


if __name__ == "__main__":
    unittest.main()

