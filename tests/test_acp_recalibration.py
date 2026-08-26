from __future__ import annotations

import copy
import importlib.util
import json
import sys
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


recalibration = load_module("decide_recalibration_tests", SCRIPTS / "decide_recalibration.py")


class AcpRecalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy_path = RESOURCES / "acp0h_recalibration_policy.json"
        cls.policy = recalibration.load_policy(cls.policy_path)
        cls.matrix = json.loads((RESOURCES / "acp0h_recalibration_change_matrix.json").read_text(encoding="utf-8"))
        cls.state_schema = json.loads((RESOURCES / "acp0h_calibration_state_schema.json").read_text(encoding="utf-8"))
        cls.decision_schema = json.loads((RESOURCES / "acp0h_recalibration_decision_schema.json").read_text(encoding="utf-8"))

    def test_synthetic_change_matrix_covers_every_trigger_and_precedence(self) -> None:
        base = self.matrix["state_defaults"]
        seen_changed_fields: set[str] = set()
        for case in self.matrix["cases"]:
            current = copy.deepcopy(base)
            current.update(case["changes"])
            decision = recalibration.decide(base, current, self.policy)
            self.assertEqual(decision["required_mode"], case["expected_mode"], case["case_id"])
            self.assertEqual(decision["recalibration_required"], bool(case["changes"]), case["case_id"])
            seen_changed_fields.update(case["changes"])
            if case["expected_mode"] == "none":
                self.assertEqual(decision["required_suites"], [])
            elif case["expected_mode"] == "smoke":
                self.assertEqual(decision["required_suites"], ["smoke-calibration-v1"])
            else:
                self.assertEqual(
                    decision["required_suites"],
                    ["smoke-calibration-v1", "paired-no-interference-v1"],
                )
        tracked = set(self.policy["smoke_fields"]) | set(self.policy["full_paired_fields"])
        self.assertEqual(seen_changed_fields, tracked)

    def test_reason_codes_are_explicit_sorted_and_retain_all_changes(self) -> None:
        previous = self.matrix["state_defaults"]
        current = copy.deepcopy(previous)
        current["renderer_sha256"] = "unknown"
        current["host_binary_sha256"] = "unknown"
        decision = recalibration.decide(previous, current, self.policy)
        self.assertEqual(decision["required_mode"], "full_paired")
        self.assertEqual(
            decision["reasons"],
            [
                {"field": "host_binary_sha256", "reason_code": "host_binary_sha256_changed", "required_mode": "full_paired"},
                {"field": "renderer_sha256", "reason_code": "renderer_sha256_changed", "required_mode": "smoke"},
            ],
        )

    def test_unknown_transitions_trigger_and_unchanged_unknown_does_not(self) -> None:
        previous = copy.deepcopy(self.matrix["state_defaults"])
        previous["host_binary_sha256"] = "unknown"
        same = recalibration.decide(previous, copy.deepcopy(previous), self.policy)
        self.assertEqual(same["required_mode"], "none")
        current = copy.deepcopy(previous)
        current["host_binary_sha256"] = "0" * 64
        changed = recalibration.decide(previous, current, self.policy)
        self.assertEqual(changed["required_mode"], "full_paired")
        self.assertEqual(changed["reasons"][0]["reason_code"], "host_binary_sha256_changed")

    def test_decision_is_deterministic_and_does_not_modify_states(self) -> None:
        previous = copy.deepcopy(self.matrix["state_defaults"])
        current = copy.deepcopy(previous)
        current["fixture_sha256"] = "unknown"
        previous_before = copy.deepcopy(previous)
        current_before = copy.deepcopy(current)
        first = recalibration.decide(previous, current, self.policy)
        second = recalibration.decide(copy.deepcopy(previous), copy.deepcopy(current), self.policy)
        self.assertEqual(recalibration.canonical_bytes(first), recalibration.canonical_bytes(second))
        self.assertEqual(previous, previous_before)
        self.assertEqual(current, current_before)

    def test_closed_state_rejects_missing_extra_and_invalid_digest(self) -> None:
        base = self.matrix["state_defaults"]
        extra = copy.deepcopy(base)
        extra["SECRET_TOKEN"] = "private"
        with self.assertRaises(recalibration.RecalibrationError):
            recalibration.decide(base, extra, self.policy)
        missing = copy.deepcopy(base)
        del missing["renderer_sha256"]
        with self.assertRaises(recalibration.RecalibrationError):
            recalibration.decide(base, missing, self.policy)
        invalid = copy.deepcopy(base)
        invalid["fixture_sha256"] = "/private/local/path"
        with self.assertRaises(recalibration.RecalibrationError):
            recalibration.decide(base, invalid, self.policy)

    def test_policy_separates_cheap_and_expensive_suites(self) -> None:
        self.assertTrue(self.policy["full_paired_suite"]["includes_smoke_suite"])
        self.assertIn("fixture_replay", self.policy["smoke_suite"]["checks"])
        self.assertIn("fail_open", self.policy["smoke_suite"]["checks"])
        self.assertIn("cost_neutrality", self.policy["full_paired_suite"]["checks"])
        self.assertIn("correctness_parity", self.policy["full_paired_suite"]["checks"])
        self.assertNotIn("renderer_sha256", self.policy["full_paired_fields"])
        self.assertIn("collector_sha256", self.policy["full_paired_fields"])

    def test_calibration_state_is_derived_from_manifest_and_closed_supplement(self) -> None:
        base = self.matrix["state_defaults"]
        environment_fields = {
            "codex_version", "host_binary_sha256", "model_identifier", "hook_api_version",
            "os", "architecture", "config_digest", "sandbox_digest",
            "environment_allowlist_digest", "collector_sha256", "normalizer_sha256",
            "reporter_sha256",
        }
        manifest = {
            "schema_id": "experiment-manifest-v1",
            "environment": {field: base[field] for field in environment_fields},
            "artifacts": {"fixture": {"status": "produced", "sha256": base["fixture_sha256"]}},
        }
        supplemental = {field: base[field] for field in recalibration.SUPPLEMENTAL_FIELDS}
        state = recalibration.state_from_manifest(manifest, supplemental, self.policy)
        self.assertEqual(state, base)
        serialized = json.dumps(state, sort_keys=True)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("/private/", serialized)
        self.assertNotIn("SECRET_TOKEN", serialized)
        invalid = copy.deepcopy(supplemental)
        invalid["SECRET_TOKEN"] = "private"
        with self.assertRaises(recalibration.RecalibrationError):
            recalibration.state_from_manifest(manifest, invalid, self.policy)

    def test_schemas_validate_matrix_states_and_decisions(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        jsonschema.Draft202012Validator.check_schema(self.state_schema)
        jsonschema.Draft202012Validator.check_schema(self.decision_schema)
        base = self.matrix["state_defaults"]
        jsonschema.validate(base, self.state_schema)
        for case in self.matrix["cases"]:
            current = copy.deepcopy(base)
            current.update(case["changes"])
            jsonschema.validate(current, self.state_schema)
            jsonschema.validate(recalibration.decide(base, current, self.policy), self.decision_schema)


if __name__ == "__main__":
    unittest.main()
