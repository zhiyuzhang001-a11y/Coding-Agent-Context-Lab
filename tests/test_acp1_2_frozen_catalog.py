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

import run_acp1_2_frozen_catalog as baseline  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp12FrozenCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_2_frozen_catalog_spec.json")
        cls.catalog = load("acp1_2_frozen_catalog.json")
        cls.index = load("acp1_2_frozen_catalog_index.json")
        cls.manifest = load("acp1_2_frozen_experiment_manifest.json")

    def test_all_gates_pass_under_frozen_scope(self) -> None:
        self.assertEqual(self.index["status"], "complete_under_frozen_experiment_scope")
        self.assertEqual(set(self.index["gates"].values()), {True})
        self.assertEqual(self.index["upstream_baseline_id"], "acp1-1-co1-4-within-session-repetition-v1")
        self.assertEqual(self.index["governance"]["admission_status"], "active")

    def test_frozen_catalog_reproduces_byte_for_byte(self) -> None:
        first = baseline._build(self.spec, ROOT)
        second = baseline._build(self.spec, ROOT)
        self.assertEqual(first[1:], second[1:])
        self.assertEqual(first[1], (RESOURCES / "acp1_2_frozen_catalog.json").read_bytes())
        self.assertEqual(first[2], (RESOURCES / "acp1_2_frozen_catalog.md").read_bytes())
        self.assertEqual(first[3], (RESOURCES / "acp1_2_frozen_catalog.txt").read_bytes())
        self.assertTrue(baseline._expected(self.spec, first[0]))

    def test_manifest_binds_index_and_index_binds_artifacts(self) -> None:
        index_path = RESOURCES / "acp1_2_frozen_catalog_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["status"], "not_produced")
        for name, artifact in self.index["artifacts"].items():
            with self.subTest(artifact=name):
                path = ROOT / artifact["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(artifact["sha256"], sha256(path))

    def test_catalog_has_five_high_cost_candidates_and_no_other_types(self) -> None:
        summary = self.catalog["candidate_summary"]
        self.assertEqual(summary["candidate_count"], 5)
        self.assertEqual(summary["candidate_type_counts"], {
            "high_cost_call_candidate": 5,
            "cost_concentration_candidate": 0,
            "repeated_or_overlapping_evidence_candidate": 0,
        })
        self.assertEqual(summary["unique_target_observed_exposure_tokens"], 10735)
        self.assertEqual(summary["unique_target_observed_share"], 0.608180839612)

    def test_every_candidate_remains_unknown_untested_and_blocked(self) -> None:
        for candidate in self.catalog["hypothesis_candidates"]:
            self.assertEqual(candidate["necessity_status"], "unknown")
            self.assertEqual(candidate["causal_status"], "untested")
            self.assertEqual(candidate["validation_feasibility"]["status"], "blocked")
        self.assertFalse(self.catalog["policy"]["necessity_verdict_produced"])
        self.assertFalse(self.catalog["policy"]["causal_claim_produced"])
        self.assertFalse(self.catalog["policy"]["avoidable_or_savings_estimate_produced"])
        self.assertFalse(self.catalog["policy"]["intervention_executed"])

    def test_schema_privacy_and_no_forbidden_estimate(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        jsonschema.validate(self.catalog, load("acp1_2_hypothesis_catalog_schema.json"))
        content = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_2_frozen_catalog.json", "acp1_2_frozen_catalog.md", "acp1_2_frozen_catalog.txt",
        )).lower()
        self.assertNotIn("/users/", content)
        for forbidden in ("wasted_tokens", "avoidable_tokens", "potential_savings", "savings_ratio"):
            self.assertNotIn(forbidden, content)

    def test_all_prior_and_online_frozen_hashes_remain_unchanged(self) -> None:
        expected = {
            "resources/acp1_0_frozen_baseline_index.json": "598bf7ea4ee98f17de483b5f818c68d9ea95f5fc444736f1bac1efa34b65a186",
            "resources/acp1_1_frozen_baseline_index.json": "034630b6a8474f1b6d0e7f245fa60098edab0a393642c97762b426123cb43fb9",
            "resources/acp1_1_frozen_experiment_manifest.json": "79f6add0c42cbc357e308d0c317d933c98ffca4ee09602d544af32d08735364a",
            "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
            "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
        }
        for path, expected_hash in expected.items():
            self.assertEqual(sha256(ROOT / path), expected_hash)


if __name__ == "__main__":
    unittest.main()
