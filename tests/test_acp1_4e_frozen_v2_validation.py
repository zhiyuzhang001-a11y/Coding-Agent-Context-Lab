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
QUALIFICATION_ROOT = WORKSPACE / ".agent-token-manager/acp1-4e-qualification-live-20260819"
PILOT_ROOT = WORKSPACE / ".agent-token-manager/acp1-4e-pilot-live-20260819"
FORMAL_ROOT = WORKSPACE / ".agent-token-manager/acp1-4e-formal-live-20260819"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import freeze_acp1_4e_v2_validation as freezer  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp14eFrozenV2ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_4e_frozen_v2_validation_spec.json")
        cls.offline = load("acp1_4e_offline_preflight.json")
        cls.registry = load("acp1_4e_candidate_registry.json")
        cls.pilot = load("acp1_4e_pilot_results.json")
        cls.formal = load("acp1_4e_results.json")
        cls.index = load("acp1_4e_frozen_v2_validation_index.json")
        cls.manifest = load("acp1_4e_frozen_experiment_manifest.json")

    def test_offline_and_qualification_gates_pass_without_replacement(self) -> None:
        self.assertEqual(self.offline["status"], "pass")
        self.assertEqual(self.offline["agent_run_count"], 0)
        self.assertEqual(self.registry["funnel"], {"proposed": 3, "qualified": 3, "diagnostic_only": 0, "rejected": 0})
        self.assertTrue(self.registry["formal_eligibility_gate"])

    def test_pilot_is_excluded_and_all_cases_activate(self) -> None:
        self.assertEqual(self.pilot["run_count"], 6)
        self.assertFalse(self.pilot["included_in_formal_statistics"])
        self.assertEqual(self.pilot["status"], "pass")
        self.assertTrue(all(row["evidence_reduction_ratio"] >= 0.35 for row in self.pilot["cases"]))

    def test_formal_resolves_all_three_activation_blockers(self) -> None:
        self.assertEqual(self.formal["summary"], self.spec["expected"]["formal_summary"])
        self.assertEqual(self.formal["run_count"], 60)
        for row in self.formal["cases"]:
            self.assertEqual(row["verdict"], "PASS")
            self.assertTrue(all(row["gates"].values()))
            self.assertGreaterEqual(row["activation"]["evidence_reduction_ratio"]["median"], 0.35)
            self.assertEqual(row["counts"]["control_correct"], 10)
            self.assertEqual(row["counts"]["treatment_correct"], 10)

    def test_no_behavioral_compensation_signal(self) -> None:
        for row in self.formal["cases"]:
            self.assertEqual(row["behavior"]["tool_call_delta"]["median"], 0)
            self.assertEqual(row["behavior"]["cycle_delta"]["median"], 0)
            self.assertEqual(row["behavior"]["novel_treatment_compensation_path_count"], 0)
            self.assertEqual(row["counts"]["treatment_only_failures"], 0)

    def test_private_inventory_binds_ninety_six_runs(self) -> None:
        inventory = freezer.private_inventory(QUALIFICATION_ROOT, PILOT_ROOT, FORMAL_ROOT)
        digest = hashlib.sha256(freezer.canonical_bytes(inventory)).hexdigest()
        self.assertEqual(inventory["run_count"], 96)
        self.assertEqual([row["run_count"] for row in inventory["phases"]], [30, 6, 60])
        self.assertEqual(digest, self.spec["private_source"]["inventory_sha256"])
        self.assertEqual(digest, self.index["private_source"]["inventory_sha256"])

    def test_manifest_index_and_component_hashes_are_bound(self) -> None:
        index_path = RESOURCES / "acp1_4e_frozen_v2_validation_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["visibility"], "private")
        for artifact in self.index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(artifact["sha256"], sha256(path))

    def test_public_artifacts_preserve_privacy_and_no_overclaim(self) -> None:
        serialized = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_4e_offline_preflight.json", "acp1_4e_qualification_results.json", "acp1_4e_candidate_registry.json",
            "acp1_4e_pilot_results.json", "acp1_4e_results.json", "acp1_4e_frozen_v2_validation_index.json",
            "acp1_4e_frozen_experiment_manifest.json",
        )).casefold()
        for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "potential_savings"):
            self.assertNotIn(prohibited, serialized)
        self.assertFalse(self.index["policy"]["production_slicing_or_replacement"])
        self.assertFalse(self.index["policy"]["real_time_recommendation"])
        self.assertFalse(self.index["policy"]["global_generalization_claim"])
        self.assertFalse(self.index["policy"]["global_savings_claim"])


if __name__ == "__main__":
    unittest.main()
