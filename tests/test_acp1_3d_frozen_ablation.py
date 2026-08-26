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
PILOT_ROOT = WORKSPACE / ".agent-token-manager/acp1-3d-pilot-20260818"
FORMAL_ROOT = WORKSPACE / ".agent-token-manager/acp1-3d-formal-20260818"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import freeze_acp1_3d_ablation as freezer  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp13dFrozenAblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_3d_frozen_ablation_spec.json")
        cls.pilot = load("acp1_3d_pilot_results.json")
        cls.result = load("acp1_3d_results.json")
        cls.index = load("acp1_3d_frozen_ablation_index.json")
        cls.manifest = load("acp1_3d_frozen_experiment_manifest.json")

    def test_pilot_and_formal_counts_are_separate_and_complete(self) -> None:
        self.assertEqual(self.pilot["run_count"], 4)
        self.assertFalse(self.pilot["included_in_formal_statistics"])
        self.assertEqual(self.result["run_count"], 80)
        self.assertEqual(self.result["summary"], {
            "case_count": 2, "pass_count": 2, "fail_count": 0, "inconclusive_count": 0,
        })
        self.assertEqual(self.index["status"], "complete_under_frozen_experiment_scope")

    def test_only_qualified_cases_entered_formal_experiment(self) -> None:
        self.assertEqual([row["case_id"] for row in self.result["cases"]], [
            "natural_signature_limit_v1", "natural_command_shape_v1",
        ])
        self.assertEqual([row["verdict"] for row in self.result["cases"]], ["PASS", "PASS"])
        self.assertTrue(all(set(row["gates"].values()) == {True} for row in self.result["cases"]))

    def test_behavior_and_activation_snapshots_are_frozen(self) -> None:
        first, second = self.result["cases"]
        self.assertEqual((first["counts"]["control_correct"], first["counts"]["treatment_correct"]), (20, 20))
        self.assertEqual((second["counts"]["control_correct"], second["counts"]["treatment_correct"]), (20, 20))
        self.assertAlmostEqual(first["activation"]["evidence_reduction_ratio"]["median"], 0.626099706744868)
        self.assertAlmostEqual(second["activation"]["evidence_reduction_ratio"]["median"], 0.49696233292831105)
        self.assertEqual(first["behavior"]["tool_call_delta"]["median"], 0)
        self.assertEqual(second["behavior"]["cycle_delta"]["median"], 0)

    def test_session_cost_is_descriptive_and_claim_scope_is_narrow(self) -> None:
        self.assertEqual([row["session_cost"]["effect"] for row in self.result["cases"]], [
            "observed_reduction", "observed_reduction",
        ])
        self.assertFalse(self.result["policy"]["global_savings_claim"])
        self.assertFalse(self.result["policy"]["production_slicing_or_replacement"])
        self.assertTrue(self.result["policy"]["experimental_harness_only"])
        self.assertFalse(self.index["policy"]["historical_candidates_validated"])

    def test_private_inventory_reconstructs_without_path_disclosure(self) -> None:
        inventory = freezer.private_inventory(PILOT_ROOT, FORMAL_ROOT)
        digest = hashlib.sha256(freezer.canonical_bytes(inventory)).hexdigest()
        self.assertEqual(inventory["run_count"], 84)
        self.assertEqual([row["run_count"] for row in inventory["phases"]], [4, 80])
        self.assertEqual(digest, self.spec["private_source"]["inventory_sha256"])
        self.assertEqual(digest, self.index["source_private_artifact"]["inventory_sha256"])
        self.assertFalse(self.index["source_private_artifact"]["paths_persisted"])

    def test_manifest_and_index_bind_every_artifact(self) -> None:
        index_path = RESOURCES / "acp1_3d_frozen_ablation_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["visibility"], "private")
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["sha256"], sha256(FORMAL_ROOT / freezer.INVENTORY_NAME))
        for artifact in self.index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(artifact["sha256"], sha256(path))

    def test_public_outputs_are_private_body_free(self) -> None:
        serialized = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_3d_pilot_results.json", "acp1_3d_results.json",
            "acp1_3d_frozen_ablation_index.json", "acp1_3d_frozen_experiment_manifest.json",
        )).lower()
        for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "potential_savings"):
            self.assertNotIn(prohibited, serialized)

    def test_upstream_and_online_frozen_hashes_remain_unchanged(self) -> None:
        expected = {
            "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
            "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
            "resources/acp1_3c_candidate_registry.json": "b618e64409b5e3e9d75b9b2a412b6bbd58c486a363afa4f58968e8a17f58f0f8",
            "resources/acp1_3c_frozen_registry_index.json": "a4c599bd1084429a16cd6977d5128d1031d1fbaa03b907d26b329cbf1ce59090",
            "resources/acp1_3c_frozen_experiment_manifest.json": "ddf15adaa883a16e192d7c4e2a53ba3a7a7ba3d51ceb43b029d98a0ebac4a45c",
        }
        for path, expected_hash in expected.items():
            self.assertEqual(sha256(ROOT / path), expected_hash)


if __name__ == "__main__":
    unittest.main()
