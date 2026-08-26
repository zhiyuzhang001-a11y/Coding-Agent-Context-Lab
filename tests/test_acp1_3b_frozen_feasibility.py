from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
PRIVATE_ROOT = WORKSPACE / ".agent-token-manager/acp1-3b-controlled-evidence-20260818-live"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import freeze_acp1_3b_feasibility as freezer  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp13bFrozenFeasibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_3b_frozen_feasibility_spec.json")
        cls.result = load("acp1_3b_results.json")
        cls.index = load("acp1_3b_frozen_feasibility_index.json")
        cls.manifest = load("acp1_3b_frozen_experiment_manifest.json")

    def test_frozen_scope_and_all_preregistered_gates_pass(self) -> None:
        self.assertEqual(self.index["status"], "complete_under_synthetic_frozen_experiment_scope")
        self.assertEqual(set(self.index["gates"].values()), {True})
        self.assertEqual(self.result["replay_qualification"]["correct_count"], 20)
        self.assertEqual(self.result["paired_feasibility"]["arms"]["control"]["correct_count"], 5)
        self.assertEqual(self.result["paired_feasibility"]["arms"]["treatment"]["correct_count"], 5)

    def test_private_chain_reconstructs_without_persisting_path(self) -> None:
        inventory = freezer.private_inventory(PRIVATE_ROOT)
        digest = hashlib.sha256(freezer.canonical_bytes(inventory)).hexdigest()
        self.assertEqual(inventory["run_count"], 30)
        self.assertEqual(digest, self.spec["private_source"]["inventory_sha256"])
        self.assertEqual(digest, self.index["source_private_artifact"]["inventory_sha256"])
        self.assertFalse(self.index["source_private_artifact"]["paths_persisted"])
        self.assertNotIn(str(PRIVATE_ROOT).lower(), json.dumps(self.index).lower())

    def test_manifest_binds_public_index_and_private_inventory(self) -> None:
        index_path = RESOURCES / "acp1_3b_frozen_feasibility_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["visibility"], "private")
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["sha256"], sha256(PRIVATE_ROOT / freezer.INVENTORY_NAME))
        self.assertTrue(all("path" not in row for row in self.manifest["artifacts"].values()))

    def test_public_artifacts_are_hash_bound_and_privacy_safe(self) -> None:
        for name, artifact in self.index["artifacts"].items():
            with self.subTest(artifact=name):
                path = ROOT / artifact["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(artifact["sha256"], sha256(path))
        serialized = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_3b_results.json", "acp1_3b_frozen_feasibility_index.json", "acp1_3b_frozen_experiment_manifest.json",
        )).lower()
        for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "avoidable_tokens", "potential_savings"):
            self.assertNotIn(prohibited, serialized)

    def test_scope_does_not_overclaim_candidate_or_product_validation(self) -> None:
        self.assertEqual(self.index["scope"]["historical_high_cost_candidates"], "not_validated")
        self.assertEqual(self.index["scope"]["production_host_intervention"], "blocked")
        self.assertFalse(self.index["scope"]["avoidable_or_savings_claim"])
        self.assertEqual(self.result["conclusions"]["historical_candidate_validation"], "not_performed")
        self.assertFalse(self.result["conclusions"]["general_savings_claim"])

    def test_all_online_and_upstream_frozen_hashes_remain_unchanged(self) -> None:
        expected = {
            "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
            "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
            "resources/acp1_2_frozen_catalog_index.json": "e9aa0310cbf6eea4dc33bfe9ba3c8987097919e0956fbc8f801885d30dd24975",
            "resources/acp1_3a_frozen_baseline_index.json": "0715444a6d373727298b968ac6294ba57c1e794cf1e814b87359d2262c51b110",
            "resources/acp1_3a_frozen_experiment_manifest.json": "0bee7c218d1bbfe893473327ad577701536b588db5c607f8bb6c7810dcc33720",
        }
        for path, expected_hash in expected.items():
            self.assertEqual(sha256(ROOT / path), expected_hash)


if __name__ == "__main__":
    unittest.main()
