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
PRIVATE_ROOT = WORKSPACE / ".agent-token-manager/acp1-3c-natural-qualification-20260818-live"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import freeze_acp1_3c_registry as freezer  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp13cFrozenRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_3c_frozen_registry_spec.json")
        cls.result = load("acp1_3c_results.json")
        cls.registry = load("acp1_3c_candidate_registry.json")
        cls.index = load("acp1_3c_frozen_registry_index.json")
        cls.manifest = load("acp1_3c_frozen_experiment_manifest.json")

    def test_all_process_gates_and_eighty_native_runs_are_frozen(self) -> None:
        self.assertEqual(self.result["run_count"], 80)
        self.assertEqual(set(self.result["gates"].values()), {True})
        self.assertEqual(self.index["status"], "complete_under_frozen_experiment_scope")
        self.assertTrue(self.index["policy"]["native_only"])
        self.assertFalse(self.index["policy"]["intervention_executed"])

    def test_registry_classification_and_acp13d_allowlist_are_exact(self) -> None:
        self.assertEqual(self.registry["summary"], {
            "case_count": 4, "qualified_count": 2, "diagnostic_only_count": 1, "rejected_count": 1,
        })
        qualified = [row["case_id"] for row in self.registry["cases"] if row["status"] == "qualified"]
        self.assertEqual(qualified, ["natural_signature_limit_v1", "natural_command_shape_v1"])
        self.assertEqual(self.index["qualified_case_ids"], qualified)
        self.assertTrue(all(row["eligible_for_acp1_3d"] == (row["status"] == "qualified") for row in self.registry["cases"]))

    def test_private_inventory_reconstructs_without_path_disclosure(self) -> None:
        inventory = freezer.private_inventory(PRIVATE_ROOT)
        digest = hashlib.sha256(freezer.canonical_bytes(inventory)).hexdigest()
        self.assertEqual(inventory["run_count"], 80)
        self.assertEqual(digest, self.spec["private_source"]["inventory_sha256"])
        self.assertEqual(digest, self.index["source_private_artifact"]["inventory_sha256"])
        self.assertFalse(self.index["source_private_artifact"]["paths_persisted"])

    def test_manifest_and_index_bind_every_artifact(self) -> None:
        index_path = RESOURCES / "acp1_3c_frozen_registry_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["visibility"], "private")
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["sha256"], sha256(PRIVATE_ROOT / freezer.INVENTORY_NAME))
        for artifact in self.index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(artifact["sha256"], sha256(path))

    def test_public_outputs_are_body_free_and_make_no_intervention_claim(self) -> None:
        serialized = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_3c_results.json", "acp1_3c_candidate_registry.json",
            "acp1_3c_frozen_registry_index.json", "acp1_3c_frozen_experiment_manifest.json",
        )).lower()
        for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "avoidable_tokens", "potential_savings"):
            self.assertNotIn(prohibited, serialized)
        self.assertFalse(self.registry["consumer_policy"]["intervention_or_savings_claim"])
        self.assertEqual(self.registry["qualification_scope"], "native_only_no_intervention")

    def test_upstream_and_online_frozen_hashes_remain_unchanged(self) -> None:
        expected = {
            "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
            "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
            "resources/acp1_3a_frozen_baseline_index.json": "0715444a6d373727298b968ac6294ba57c1e794cf1e814b87359d2262c51b110",
            "resources/acp1_3b_frozen_feasibility_index.json": "6397007ce8fdb2229b45490249be70ad4017adf0df41388135d71be04bb10fc3",
            "resources/acp1_3b_frozen_experiment_manifest.json": "3cecfb99652eeabcfd0709aa5df7b8f55400ce9179bd33dedbc1239887467a87",
        }
        for path, expected_hash in expected.items():
            self.assertEqual(sha256(ROOT / path), expected_hash)


if __name__ == "__main__":
    unittest.main()
