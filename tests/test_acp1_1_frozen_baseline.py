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

import run_acp1_1_frozen_baseline as baseline  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp11FrozenBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_1_frozen_baseline_spec.json")
        cls.analysis = load("acp1_1_frozen_analysis.json")
        cls.index = load("acp1_1_frozen_baseline_index.json")
        cls.manifest = load("acp1_1_frozen_experiment_manifest.json")

    def test_all_gates_pass_under_frozen_scope(self) -> None:
        self.assertEqual(self.index["status"], "complete_under_frozen_experiment_scope")
        self.assertEqual(set(self.index["gates"].values()), {True})
        self.assertEqual(self.index["upstream_baseline_id"], "acp1-0-co1-4-cost-attribution-v1")
        self.assertEqual(self.index["governance"]["admission_status"], "active")

    def test_frozen_pipeline_reproduces_outputs_byte_for_byte(self) -> None:
        first = baseline._build(self.spec, ROOT)
        second = baseline._build(self.spec, ROOT)
        self.assertEqual(first[1:], second[1:])
        self.assertEqual(first[1], (RESOURCES / "acp1_1_frozen_analysis.json").read_bytes())
        self.assertEqual(first[2], (RESOURCES / "acp1_1_frozen_analysis.md").read_bytes())
        self.assertEqual(first[3], (RESOURCES / "acp1_1_frozen_analysis.txt").read_bytes())
        self.assertTrue(baseline._expected(self.spec, first[0]))

    def test_manifest_binds_index_and_index_binds_artifacts(self) -> None:
        index_path = RESOURCES / "acp1_1_frozen_baseline_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["status"], "not_produced")
        for name, artifact in self.index["artifacts"].items():
            with self.subTest(artifact=name):
                path = ROOT / artifact["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(artifact["sha256"], sha256(path))

    def test_baseline_distinguishes_cross_session_fact_from_within_session_relation(self) -> None:
        snapshot = self.index["measurement_snapshot"]
        self.assertEqual(snapshot["acp1_0_cross_session_exact_repeat_volume"], 5288)
        self.assertEqual(snapshot["relation_count"], 0)
        self.assertEqual(snapshot["unique_repeated_observation_tokens"], 0)
        self.assertEqual(self.analysis["source_and_scope"]["relation_scope"], "within_session")
        self.assertFalse(self.analysis["source_and_scope"]["cross_session_relations_created"])

    def test_unknown_path_range_cycle_and_content_are_not_coerced(self) -> None:
        coverage = self.analysis["denominator_and_coverage"]
        unknowns = self.analysis["unknowns"]
        self.assertEqual(coverage["relation_order_coverage_status"], "complete")
        self.assertEqual(coverage["path_identity_coverage_status"], "unknown")
        self.assertEqual(coverage["explicit_range_coverage_status"], "unknown")
        self.assertEqual(coverage["cycle_coverage_status"], "unknown")
        self.assertEqual(unknowns["content_stability_state"], "unknown")

    def test_schema_privacy_and_no_diagnosis(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        schema = load("acp1_1_repeated_evidence_schema.json")
        jsonschema.validate(self.analysis, schema)
        content = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_1_frozen_analysis.json", "acp1_1_frozen_analysis.md", "acp1_1_frozen_analysis.txt",
        )).lower()
        self.assertNotIn("/users/", content)
        for forbidden in ("wasted_tokens", "avoidable_tokens", "potential_savings", "optimization_opportunity"):
            self.assertNotIn(forbidden, content)

    def test_acp1_0_and_online_frozen_hashes_remain_unchanged(self) -> None:
        expected = {
            "resources/acp1_0_frozen_baseline_index.json": "598bf7ea4ee98f17de483b5f818c68d9ea95f5fc444736f1bac1efa34b65a186",
            "resources/acp1_0_frozen_experiment_manifest.json": "b44a0eae1ad88ca36d3280f73dad37e517ac3c2302db94a443bd44ee6c4e113f",
            "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
            "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
        }
        for path, digest in expected.items():
            self.assertEqual(sha256(ROOT / path), digest)


if __name__ == "__main__":
    unittest.main()
