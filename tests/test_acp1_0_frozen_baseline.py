from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_acp1_0_frozen_baseline as baseline  # noqa: E402
import validate_benchmark_registry  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp10FrozenBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_0_frozen_baseline_spec.json")
        cls.index = load("acp1_0_frozen_baseline_index.json")
        cls.manifest = load("acp1_0_frozen_experiment_manifest.json")
        cls.attribution = load("acp1_0_frozen_attribution.json")

    def test_all_five_gates_pass_under_explicit_frozen_scope(self) -> None:
        self.assertEqual(self.index["status"], "complete_under_frozen_experiment_scope")
        self.assertEqual(set(self.index["gates"].values()), {True})
        self.assertFalse(self.index["experiment_scope"]["derivation_model_invocation_used"])
        self.assertEqual(self.index["experiment_scope"]["source_observation_model_identifier"], "unknown")
        self.assertIn("source_observation.model_identifier", self.index["experiment_scope"]["declared_unknowns"])

    def test_manifest_binds_index_and_index_binds_every_listed_artifact(self) -> None:
        index_path = RESOURCES / "acp1_0_frozen_baseline_index.json"
        public_result = self.manifest["artifacts"]["public_compact_result"]
        self.assertEqual(public_result["status"], "produced")
        self.assertEqual(public_result["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["status"], "not_produced")
        for name, artifact in self.index["artifacts"].items():
            with self.subTest(artifact=name):
                path = ROOT / artifact["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(artifact["sha256"], sha256(path))

    def test_governed_input_is_active_and_hash_qualified(self) -> None:
        registry = load("acp0h_benchmark_registry.json")
        result = validate_benchmark_registry.validate_registry(registry, ROOT)
        governed = next(
            item for item in registry["formal_baseline_inputs"]
            if item["input_id"] == self.index["governance"]["formal_input_id"]
        )
        self.assertTrue(result["valid"])
        self.assertEqual(governed["admission_status"], "active")
        self.assertEqual(governed["fixture_sha256"], self.index["artifacts"]["fixture"]["sha256"])
        self.assertEqual(self.index["governance"]["registry_sha256"], sha256(RESOURCES / "acp0h_benchmark_registry.json"))

    def test_frozen_pipeline_reproduces_canonical_outputs_byte_for_byte(self) -> None:
        first = baseline._pipeline_bytes(self.spec, ROOT)
        second = baseline._pipeline_bytes(self.spec, ROOT)
        for name, payload in first["outputs"].items():
            with self.subTest(output=name):
                self.assertEqual(payload, second["outputs"][name])
                self.assertEqual(payload, (RESOURCES / baseline.OUTPUT_NAMES[name]).read_bytes())
        self.assertTrue(baseline._measurement_gate(self.spec, first))
        self.assertTrue(baseline._privacy_gate(self.spec, first["outputs"]))

    def test_measurement_snapshot_and_unknown_semantics_are_frozen(self) -> None:
        snapshot = self.index["measurement_snapshot"]
        self.assertEqual(snapshot["sessions"], 12)
        self.assertEqual(snapshot["observed_calls"], 16)
        self.assertEqual(snapshot["observed_matched_visible_estimated_tokens"], 17651)
        self.assertEqual(snapshot["coverage_status"], "complete")
        self.assertEqual(snapshot["unknown_count"], 0)
        self.assertEqual(snapshot["exact_repeat_group_observation_visible_tokens"], 5288)
        self.assertEqual(self.attribution["cycle_structure_or_unknown"]["status"], "unknown")
        self.assertEqual(self.attribution["scope_and_denominators"]["session_total_tokens"]["status"], "unknown")

    def test_outputs_remain_privacy_safe_and_diagnosis_free(self) -> None:
        names = (
            "acp1_0_frozen_normalized_batch.json",
            "acp1_0_frozen_coverage_ledger.json",
            "acp1_0_frozen_fact_report.json",
            "acp1_0_frozen_attribution.json",
            "acp1_0_frozen_attribution.md",
            "acp1_0_frozen_attribution.txt",
        )
        content = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in names)
        for forbidden in ("/Users/", "tool_response", "SYNTHETIC_PRIVATE_BODY", 'raw_session_id"'):
            self.assertNotIn(forbidden, content)
        lowered = content.lower()
        for forbidden in ("wasted_tokens", "avoidable_tokens", "optimization_opportunity", "potential savings"):
            self.assertNotIn(forbidden, lowered)
        self.assertTrue(self.index["policy"]["fact_only"])
        self.assertTrue(self.index["policy"]["no_diagnosis"])
        self.assertTrue(self.index["policy"]["no_online_effect"])

    def test_frozen_json_artifacts_validate_against_existing_schemas(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        attribution_schema = load("acp1_0_attribution_schema.json")
        manifest_schema = load("acp0h_experiment_manifest_schema.json")
        jsonschema.validate(self.attribution, attribution_schema)
        jsonschema.validate(self.manifest, manifest_schema)


if __name__ == "__main__":
    unittest.main()
