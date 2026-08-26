from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_module("validate_benchmark_registry_tests", SCRIPTS / "validate_benchmark_registry.py")


class AcpBenchmarkRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads((RESOURCES / "acp0h_benchmark_registry.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((RESOURCES / "acp0h_benchmark_registry_schema.json").read_text(encoding="utf-8"))

    def test_current_registry_preserves_all_cases_and_expected_classification(self) -> None:
        result = validator.validate_registry(self.registry, ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["case_count"], 12)
        self.assertEqual(result["historical_migration_case_count"], 11)
        self.assertEqual(result["prospective_native_case_count"], 1)
        self.assertEqual(result["formal_baseline_input_count"], 1)
        self.assertEqual(result["active_formal_baseline_input_count"], 1)
        self.assertEqual(result["role_counts"], {
            "coverage_probe": 2,
            "failure_injection": 1,
            "stable_gate": 8,
            "stochastic_diagnostic": 1,
        })
        self.assertEqual(result["admission_counts"], {"active": 11, "diagnostic_only": 1})

    def test_stochastic_case_is_diagnostic_only_and_never_absolute_gate(self) -> None:
        case = next(case for case in self.registry["cases"] if case["case_id"] == "single_file_range_count")
        self.assertEqual(case["benchmark_role"], "stochastic_diagnostic")
        self.assertEqual(case["admission_status"], "diagnostic_only")
        self.assertEqual(case["native_calibration"]["repetitions"], 20)
        self.assertEqual(case["native_calibration"]["correct"], 14)
        self.assertIn("distribution_parity", case["allowed_gate_usage"])
        self.assertNotIn("absolute_correctness", case["allowed_gate_usage"])
        self.assertNotIn("cost_neutrality", case["allowed_gate_usage"])

    def test_historical_exception_is_narrow_and_new_case_threshold_is_stricter(self) -> None:
        policy = self.registry["governance_policy"]
        self.assertEqual(policy["migration_exception"]["applies_only_to_registry_version"], "1.0.0")
        self.assertEqual(policy["migration_exception"]["minimum_repetitions"], 5)
        self.assertTrue(policy["migration_exception"]["requires_perfect_native_record"])
        self.assertEqual(policy["new_stable_minimum_repetitions"], 20)
        self.assertEqual(policy["new_stable_minimum_correct"], 19)

    def test_registry_rejects_gate_leak_unqualified_admission_and_case_deletion(self) -> None:
        stochastic_leak = copy.deepcopy(self.registry)
        stochastic = next(case for case in stochastic_leak["cases"] if case["case_id"] == "single_file_range_count")
        stochastic["allowed_gate_usage"].append("absolute_correctness")
        with self.assertRaises(validator.RegistryError):
            validator.validate_registry(stochastic_leak, ROOT)

        weak_history = copy.deepcopy(self.registry)
        weak_history["cases"][0]["native_calibration"]["correct"] = 4
        with self.assertRaises(validator.RegistryError):
            validator.validate_registry(weak_history, ROOT)

        pending_admitted = copy.deepcopy(self.registry)
        pending_admitted["cases"][0]["ground_truth"]["audit_status"] = "pending"
        with self.assertRaises(validator.RegistryError):
            validator.validate_registry(pending_admitted, ROOT)

        deleted = copy.deepcopy(self.registry)
        deleted["cases"].pop()
        with self.assertRaises(validator.RegistryError):
            validator.validate_registry(deleted, ROOT)

    def test_new_stable_case_requires_prospective_20_run_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            temp_resources = temp_root / "resources"
            temp_resources.mkdir()
            for name in (
                "acp0_4a_results.json", "acp0_4b_native_calibration_results.json",
                "acp0_co1_4_replay_fixture.json",
            ):
                shutil.copy2(RESOURCES / name, temp_resources / name)
            fixture = json.loads((RESOURCES / "acp0_4_cases.json").read_text(encoding="utf-8"))
            new_source = {
                "id": "prospective_stable_case",
                "category": "single_file_location",
                "question": "Synthetic prospective governance case.",
                "expected": "PASS",
                "order": ["off", "on"],
            }
            fixture["cases"].append(new_source)
            fixture_path = temp_resources / "acp0_4_cases.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            registry = copy.deepcopy(self.registry)
            registry["source_fixture"]["sha256"] = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
            evidence = temp_resources / "acp0_4b_native_calibration_results.json"
            registry["cases"].append({
                "case_id": "prospective_stable_case", "version": 1,
                "purpose": "Prospective stable admission test.", "benchmark_role": "stable_gate",
                "ground_truth": {
                    "audit_status": "audited_unambiguous", "source_pointer": "resources/acp0_4_cases.json#/cases/12",
                    "question_sha256": validator.sha256_text(new_source["question"]),
                    "expected_answer_sha256": validator.sha256_text(new_source["expected"]),
                },
                "native_calibration": {
                    "status": "qualified_stable", "basis": "prospective_native_calibration",
                    "repetitions": 20, "correct": 19,
                    "evidence_path": "resources/acp0_4b_native_calibration_results.json",
                    "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                },
                "admission_status": "active", "introduced_at": "2026-08-18", "supersedes": None,
                "retired_reason": None,
                "oracle_and_scorer_version": "strip-outer-whitespace-exact-final-text-v1",
                "expected_coverage_path": "local_tool_evidence",
                "allowed_gate_usage": ["absolute_correctness", "cost_neutrality", "path_neutrality", "host_transparency", "collector_coverage"],
            })
            self.assertTrue(validator.validate_registry(registry, temp_root)["valid"])
            registry["cases"][-1]["native_calibration"]["repetitions"] = 5
            registry["cases"][-1]["native_calibration"]["correct"] = 5
            with self.assertRaises(validator.RegistryError):
                validator.validate_registry(registry, temp_root)

    def test_validation_is_deterministic_read_only_and_privacy_safe(self) -> None:
        registry = copy.deepcopy(self.registry)
        before = copy.deepcopy(registry)
        first = validator.validate_registry(registry, ROOT)
        second = validator.validate_registry(copy.deepcopy(registry), ROOT)
        self.assertEqual(validator.canonical_bytes(first), validator.canonical_bytes(second))
        self.assertEqual(registry, before)
        serialized = json.dumps(self.registry, ensure_ascii=False)
        self.assertNotIn("question\"", serialized)
        self.assertNotIn("expected\"", serialized)
        self.assertNotIn("/Users/", serialized)

    def test_registry_schema_validates(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        jsonschema.Draft202012Validator.check_schema(self.schema)
        jsonschema.validate(self.registry, self.schema)

    def test_formal_baseline_input_is_active_hash_qualified_coverage_probe(self) -> None:
        item = self.registry["formal_baseline_inputs"][0]
        self.assertEqual(item["input_id"], "co1_4_observe_replay")
        self.assertEqual(item["version"], 1)
        self.assertEqual(item["benchmark_role"], "coverage_probe")
        self.assertEqual(item["qualification_status"], "qualified_measurement_fixture")
        self.assertEqual(item["admission_status"], "active")
        drifted = copy.deepcopy(self.registry)
        drifted["formal_baseline_inputs"][0]["fixture_sha256"] = "0" * 64
        with self.assertRaises(validator.RegistryError):
            validator.validate_registry(drifted, ROOT)


if __name__ == "__main__":
    unittest.main()
