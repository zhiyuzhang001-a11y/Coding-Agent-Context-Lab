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
QUALIFICATION_ROOT = WORKSPACE / ".agent-token-manager/acp1-4-qualification-live-20260818"
PILOT_ROOT = WORKSPACE / ".agent-token-manager/acp1-4-pilot-live-20260818"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import freeze_acp1_4_generalization as freezer  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp14FrozenGeneralizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_4_frozen_generalization_spec.json")
        cls.qualification = load("acp1_4a_results.json")
        cls.registry = load("acp1_4a_candidate_registry.json")
        cls.pilot = load("acp1_4b_pilot_results.json")
        cls.index = load("acp1_4_frozen_generalization_index.json")
        cls.manifest = load("acp1_4_frozen_experiment_manifest.json")

    def test_complete_funnel_is_frozen_without_replacement(self) -> None:
        self.assertEqual(self.qualification["run_count"], 80)
        self.assertEqual(self.registry["funnel"], {"proposed": 8, "qualified": 6, "diagnostic_only": 0, "rejected": 2})
        self.assertFalse(self.registry["formal_coverage_gate"])
        self.assertFalse(self.index["policy"]["failed_cases_replaced"])

    def test_family_coverage_failure_is_explicit(self) -> None:
        self.assertEqual(self.registry["family_coverage"], {
            "read": {"proposed": 3, "qualified": 3},
            "search": {"proposed": 3, "qualified": 3},
            "bash": {"proposed": 2, "qualified": 0},
        })
        self.assertEqual(self.index["generalization_verdict"], "INSUFFICIENT_COVERAGE")
        self.assertEqual(self.index["status"], "stopped_insufficient_coverage_under_frozen_scope")

    def test_bash_native_failures_remain_rejected(self) -> None:
        bash = [row for row in self.registry["cases"] if row["family"] == "bash"]
        self.assertEqual(len(bash), 2)
        self.assertTrue(all(row["status"] == "rejected" for row in bash))
        self.assertTrue(all(row["native_calibration"]["correct"] == 0 for row in bash))
        self.assertTrue(all(row["native_calibration"]["candidate_recurrence"] == 5 for row in bash))

    def test_family_pilot_does_not_enter_formal_statistics(self) -> None:
        self.assertEqual(self.pilot["run_count"], 4)
        self.assertFalse(self.pilot["included_in_formal_statistics"])
        self.assertEqual(self.pilot["status"], "inconclusive_plumbing")
        self.assertFalse((RESOURCES / "acp1_4b_results.json").exists())
        self.assertFalse(self.index["policy"]["formal_started"])

    def test_private_inventory_reconstructs_eighty_four_valid_runs(self) -> None:
        inventory = freezer.private_inventory(QUALIFICATION_ROOT, PILOT_ROOT)
        digest = hashlib.sha256(freezer.canonical_bytes(inventory)).hexdigest()
        self.assertEqual(inventory["run_count"], 84)
        self.assertEqual([row["run_count"] for row in inventory["phases"]], [80, 4])
        self.assertEqual(digest, self.spec["private_source"]["inventory_sha256"])
        self.assertEqual(digest, self.index["source_private_artifact"]["inventory_sha256"])

    def test_manifest_index_and_component_hashes_are_bound(self) -> None:
        index_path = RESOURCES / "acp1_4_frozen_generalization_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["visibility"], "private")
        for artifact in self.index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(artifact["sha256"], sha256(path))

    def test_public_artifacts_preserve_privacy_and_no_savings_claim(self) -> None:
        serialized = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_4a_results.json", "acp1_4a_candidate_registry.json", "acp1_4b_pilot_results.json",
            "acp1_4_frozen_generalization_index.json", "acp1_4_frozen_experiment_manifest.json",
        )).lower()
        for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "potential_savings"):
            self.assertNotIn(prohibited, serialized)
        self.assertFalse(self.index["policy"]["production_slicing_or_replacement"])
        self.assertFalse(self.index["policy"]["global_savings_claim"])


if __name__ == "__main__":
    unittest.main()
