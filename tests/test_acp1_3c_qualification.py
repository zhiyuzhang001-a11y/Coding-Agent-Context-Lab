from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_acp1_3c_qualification as qualification  # noqa: E402


class Acp13cQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_path = RESOURCES / "acp1_3c_natural_cases.json"
        cls.fixture = qualification.load_fixture(cls.fixture_path)
        cls.case = cls.fixture["cases"][0]

    def run_row(self, repetition: int, *, correct: bool = True, recurred: bool = True, ambiguous: bool = False, path: str = "path-a") -> dict:
        return {
            "run_id": f"sample-{repetition}", "case_id": self.case["case_id"], "repetition": repetition,
            "status": "completed", "correct": correct, "usage": {"total_tokens": 10000 + repetition},
            "model_cycles": 2, "tool_call_count": 1, "candidate_recurred": recurred,
            "candidate_ambiguous": ambiguous, "candidate_match_count": 2 if ambiguous else int(recurred),
            "candidate_visible_estimated_tokens": 1200 if recurred else None,
            "path_signature_sha256": path, "hook_or_collector_used": False,
        }

    def test_fixture_freezes_four_natural_native_only_cases(self) -> None:
        self.assertEqual(len(self.fixture["cases"]), 4)
        self.assertEqual(self.fixture["repetitions_per_case"], 20)
        self.assertTrue(self.fixture["policy"]["native_only"])
        self.assertFalse(self.fixture["policy"]["intervention"])
        self.assertEqual(self.fixture["thresholds"]["correct"], 19)
        self.assertEqual(self.fixture["thresholds"]["candidate_recurrence"], 16)
        self.assertEqual(self.fixture["thresholds"]["dominant_path_frequency"], 16)

    def test_candidate_identity_requires_terms_size_and_success(self) -> None:
        command = "rg -n signature_from_content plugins/agent-token-manager/scripts/smart_read.py"
        self.assertTrue(qualification.candidate_match({"command": command, "output": "x" * 4000}, self.case, 4000))
        self.assertFalse(qualification.candidate_match({"command": command, "output": "x" * 3999}, self.case, 4000))
        self.assertFalse(qualification.candidate_match({"command": "rg -n other smart_read.py", "output": "x" * 5000}, self.case, 4000))
        self.assertFalse(qualification.candidate_match({"command": command, "output": "Script failed" + "x" * 5000}, self.case, 4000))

    def test_multiple_candidate_matches_are_ambiguous_not_selected(self) -> None:
        call = {"tool_name": "exec", "command": "rg signature_from_content smart_read.py", "output": "x" * 4000}
        analyzed = qualification.analyze_calls([call, call], self.case, 4000)
        self.assertEqual(analyzed["candidate_match_count"], 2)
        self.assertTrue(analyzed["candidate_ambiguous"])
        self.assertFalse(analyzed["candidate_recurred"])
        self.assertIsNone(analyzed["candidate_result_sha256"])
        self.assertEqual({row["candidate_relation"] for row in analyzed["path_signature"]}, {"ambiguous"})

    def test_qualified_requires_nineteen_correct_sixteen_recurrences_and_dominant_path(self) -> None:
        runs = [self.run_row(index, correct=index <= 19, recurred=index <= 16, path="path-a" if index <= 16 else f"path-{index}") for index in range(1, 21)]
        summary = qualification.summarize_case(self.fixture, self.case, runs)
        self.assertEqual(summary["status"], "qualified")
        self.assertTrue(summary["eligible_for_acp1_3d"])

    def test_unstable_path_is_diagnostic_but_low_recurrence_is_rejected(self) -> None:
        unstable = [self.run_row(index, path=f"path-{index % 3}") for index in range(1, 21)]
        self.assertEqual(qualification.summarize_case(self.fixture, self.case, unstable)["status"], "diagnostic_only")
        low_recurrence = [self.run_row(index, recurred=index <= 15) for index in range(1, 21)]
        self.assertEqual(qualification.summarize_case(self.fixture, self.case, low_recurrence)["status"], "rejected")

    def test_public_compaction_excludes_prompt_answer_command_and_result_body(self) -> None:
        private = self.run_row(1)
        private.update({"final_text": "secret", "expected": "secret", "command": "private", "output": "private"})
        compact = qualification.compact_run(private)
        serialized = json.dumps(compact).lower()
        for prohibited in ("final_text", "expected", "command", "output", "secret", "/users/"):
            self.assertNotIn(prohibited, serialized)

    def test_runner_has_no_collector_optimizer_or_online_hook_dependency(self) -> None:
        source = (SCRIPTS / "run_acp1_3c_qualification.py").read_text(encoding="utf-8")
        for prohibited in ("import acp_collector", "import context_optimizer_hook", "decision:block"):
            self.assertNotIn(prohibited, source)
        self.assertIn("verify_frozen_integrity(plugin)", source)


if __name__ == "__main__":
    unittest.main()
