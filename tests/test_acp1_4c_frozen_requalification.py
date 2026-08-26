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
QUALIFICATION_ROOT = WORKSPACE / ".agent-token-manager/acp1-4c-qualification-live-20260819"
PILOT_ROOT = WORKSPACE / ".agent-token-manager/acp1-4c-pilot-live-20260819"
FORMAL_ROOT = WORKSPACE / ".agent-token-manager/acp1-4c-formal-live-20260819"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import freeze_acp1_4c_bash_requalification as freezer  # noqa: E402


def load(name: str) -> dict:
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp14cFrozenRequalificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = load("acp1_4c_frozen_requalification_spec.json")
        cls.audit = load("acp1_4c_bash_audit.json")
        cls.registry = load("acp1_4c_bash_v2_registry.json")
        cls.formal = load("acp1_4c_results.json")
        cls.index = load("acp1_4c_frozen_requalification_index.json")
        cls.manifest = load("acp1_4c_frozen_experiment_manifest.json")

    def test_old_bash_history_is_preserved_and_not_rescored(self) -> None:
        self.assertEqual(self.audit["conclusion"], "benchmark_invalid_for_bash_qualification_not_treatment_failure")
        self.assertFalse(self.audit["history_policy"]["old_results_rescored"])
        self.assertEqual(sha256(RESOURCES / "acp1_4_frozen_generalization_index.json"), self.spec["components"]["upstream_index"]["sha256"])
        self.assertFalse(self.index["policy"]["old_acp1_4_history_changed"])

    def test_v2_funnel_qualifies_two_and_preserves_rejection(self) -> None:
        self.assertEqual(self.registry["funnel"], {"proposed": 3, "qualified": 2, "diagnostic_only": 0, "rejected": 1})
        self.assertTrue(self.registry["formal_eligibility_gate"])
        rejected = [row for row in self.registry["cases"] if row["status"] == "rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["native_calibration"]["candidate_recurrence"], 0)

    def test_bash_formal_cases_both_pass_without_behavior_failure(self) -> None:
        bash = [row for row in self.formal["cases"] if row["family"] == "bash"]
        self.assertEqual(len(bash), 2)
        self.assertTrue(all(row["verdict"] == "PASS" for row in bash))
        for row in bash:
            self.assertEqual(row["counts"]["control_correct"], 10)
            self.assertEqual(row["counts"]["treatment_correct"], 10)
            self.assertTrue(all(row["gates"][key] for key in (
                "g3_correctness", "g4_tool_path", "g5_cycle", "g6_success_semantics", "g7_outcome_completeness",
            )))

    def test_combined_verdict_preserves_activation_inconclusives(self) -> None:
        self.assertEqual(self.formal["funnel"], self.spec["expected"]["formal_funnel"])
        self.assertEqual(self.formal["generalization"]["verdict"], "INSUFFICIENT_COVERAGE")
        inconclusive = [row for row in self.formal["cases"] if row["verdict"] == "INCONCLUSIVE"]
        self.assertEqual(len(inconclusive), 3)
        self.assertTrue(all(not row["gates"]["g2_activation"] for row in inconclusive))
        self.assertTrue(all(all(row["gates"][key] for key in (
            "g3_correctness", "g4_tool_path", "g5_cycle", "g6_success_semantics", "g7_outcome_completeness",
        )) for row in self.formal["cases"]))

    def test_private_inventory_reconstructs_one_hundred_ninety_four_runs(self) -> None:
        inventory = freezer.private_inventory(QUALIFICATION_ROOT, PILOT_ROOT, FORMAL_ROOT)
        digest = hashlib.sha256(freezer.canonical_bytes(inventory)).hexdigest()
        self.assertEqual(inventory["run_count"], 194)
        self.assertEqual([row["run_count"] for row in inventory["phases"]], [30, 4, 160])
        self.assertEqual(digest, self.spec["private_source"]["inventory_sha256"])
        self.assertEqual(digest, self.index["source_private_artifact"]["inventory_sha256"])

    def test_manifest_index_and_component_hashes_are_bound(self) -> None:
        index_path = RESOURCES / "acp1_4c_frozen_requalification_index.json"
        self.assertEqual(self.manifest["artifacts"]["public_compact_result"]["sha256"], sha256(index_path))
        self.assertEqual(self.manifest["artifacts"]["raw_private_artifact"]["visibility"], "private")
        for artifact in self.index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(artifact["sha256"], sha256(path))

    def test_public_artifacts_preserve_privacy_and_no_overclaim(self) -> None:
        serialized = "\n".join((RESOURCES / name).read_text(encoding="utf-8") for name in (
            "acp1_4c_bash_audit.json", "acp1_4c_qualification_results.json", "acp1_4c_bash_v2_registry.json",
            "acp1_4c_pilot_results.json", "acp1_4c_results.json", "acp1_4c_frozen_requalification_index.json",
            "acp1_4c_frozen_experiment_manifest.json",
        )).lower()
        for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "potential_savings"):
            self.assertNotIn(prohibited, serialized)
        self.assertFalse(self.index["policy"]["production_slicing_or_replacement"])
        self.assertFalse(self.index["policy"]["real_time_recommendation"])
        self.assertFalse(self.index["policy"]["global_savings_claim"])


if __name__ == "__main__":
    unittest.main()
