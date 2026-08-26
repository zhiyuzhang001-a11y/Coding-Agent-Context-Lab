from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
RESOURCES = ROOT / "resources"
INDEX = RESOURCES / "acp1_4f_f1_frozen_early_stop_index.json"
RESULT = RESOURCES / "acp1_4f_f1_early_stop.json"
PRIVATE = WORKSPACE / ".agent-token-manager/acp1-4f-native-v21-20260819"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Acp14fF1EarlyStopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = load(INDEX)
        cls.result = load(RESULT)

    def test_artifact_chain_is_frozen(self) -> None:
        for artifact in self.index["artifacts"].values():
            path = ROOT / artifact["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(sha256(path), artifact["sha256"])

    def test_private_completed_inventory_reconstructs_exactly(self) -> None:
        paths = sorted(PRIVATE.glob("*/result.json"))
        rows = [load(path) for path in paths]
        inventory = {
            "schema_version": 1,
            "logical_id": "acp1-4f-native-v21-early-stop-20260819",
            "completed_run_count": len(paths),
            "runs": [{"run_id": row["run_id"], "sha256": sha256(path)} for path, row in zip(paths, rows)],
        }
        digest = hashlib.sha256((json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
        self.assertEqual(len(paths), 54)
        self.assertEqual(digest, self.index["private_source"]["completed_result_inventory_sha256"])

    def test_coverage_impossibility_and_early_stop_are_not_rewritten(self) -> None:
        coverage = self.result["coverage_impossibility"]
        self.assertFalse(coverage["native_coverage_gate_can_still_pass"])
        self.assertLess(coverage["read_maximum_possible_qualified"], coverage["minimum_formal_admitted_per_family"])
        self.assertLess(coverage["search_maximum_possible_qualified"], coverage["minimum_formal_admitted_per_family"])
        self.assertEqual(self.result["verdict"], "INSUFFICIENT_NATIVE_COVERAGE")
        self.assertEqual((self.result["completed_run_count"], self.result["interrupted_run_count"]), (54, 1))
        self.assertFalse(self.index["next_phase"]["v2_1_resume_allowed"])

    def test_all_completed_correct_runs_and_failures_are_classification_not_correctness(self) -> None:
        self.assertEqual(sum(row["completed"] for row in self.result["case_observations"]), 54)
        self.assertEqual(sum(row["correct"] for row in self.result["case_observations"]), 54)
        statuses = {row["case_id"]: row["status"] for row in self.result["case_observations"]}
        self.assertEqual(sum(value == "qualified" for value in statuses.values()), 1)
        self.assertIn("diagnostic_only", statuses.values())
        self.assertIn("rejected", statuses.values())
        self.assertIn("early_rejected", statuses.values())

    def test_builder_intervention_and_downstream_phases_remain_disabled(self) -> None:
        policy = self.result["policy"]
        self.assertFalse(policy["treatment_builder_used"])
        self.assertFalse(policy["collector_or_hook_used"])
        self.assertFalse(policy["intervention_used"])
        self.assertFalse(policy["f2_authorized"])
        self.assertFalse(policy["pilot_or_formal_authorized"])

    def test_public_artifacts_are_body_free_and_make_no_savings_claim(self) -> None:
        serialized = RESULT.read_text(encoding="utf-8").casefold() + INDEX.read_text(encoding="utf-8").casefold()
        for prohibited in ("final_text", "tool_response", "expected\"", "/users/", "wasted_tokens", "potential_savings"):
            self.assertNotIn(prohibited, serialized)


if __name__ == "__main__":
    unittest.main()

