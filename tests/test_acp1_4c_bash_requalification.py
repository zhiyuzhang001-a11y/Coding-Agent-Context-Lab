from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_acp1_4c_bash_requalification as runner  # noqa: E402


class Acp14cBashRequalificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec_path = RESOURCES / "acp1_4c_experiment_spec.json"
        cls.spec = runner.load_spec(cls.spec_path, ROOT)

    def test_v1_audit_preserves_history_and_identifies_both_failure_modes(self) -> None:
        audit = json.loads((RESOURCES / "acp1_4c_bash_audit.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["conclusion"], "benchmark_invalid_for_bash_qualification_not_treatment_failure")
        self.assertEqual(set(audit["failure_categories"]), {
            "trailing_period_became_unittest_argv", "read_only_sandbox_has_no_writable_tempdir",
        })
        self.assertTrue(audit["history_policy"]["old_cases_preserved"])
        self.assertFalse(audit["history_policy"]["old_results_rescored"])
        self.assertFalse(audit["history_policy"]["acp1_4_verdict_changed"])

    def test_sampling_frame_is_three_bash_v2_cases(self) -> None:
        self.assertEqual(len(self.spec["cases"]), 3)
        self.assertTrue(all(row["family"] == "bash" and row["case_version"] == 2 for row in self.spec["cases"]))
        self.assertEqual(self.spec["qualification"]["qualified_case_min_for_formal"], 2)
        self.assertEqual({row["treatment"]["method"] for row in self.spec["cases"]}, {
            "json-list-prefix-projection-v1", "json-object-key-projection-v1", "hashed-nontarget-match-ablation-v1",
        })

    def test_commands_are_unambiguous_read_only_and_period_free(self) -> None:
        for case in self.spec["cases"]:
            command = case["command"]
            self.assertTrue(command.startswith("python3 "))
            self.assertFalse(command.endswith(" ."))
            self.assertNotIn("unittest", command)
            self.assertNotIn("tempfile", command)
            self.assertNotIn(">", command)

    def test_control_commands_succeed_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            subject = Path(name) / "subject"
            runner.base.qualification.materialize_subject(WORKSPACE, self.spec["subject_commit"], subject)
            for case in self.spec["cases"]:
                completed = subprocess.run(shlex.split(case["command"]), cwd=subject, text=True, capture_output=True, timeout=20)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertGreaterEqual(len(completed.stdout), case["minimum_result_chars"])

    def test_treatments_are_deterministic_preserve_answer_and_activate(self) -> None:
        for case in self.spec["cases"]:
            with tempfile.TemporaryDirectory() as control_name, tempfile.TemporaryDirectory() as first_name, tempfile.TemporaryDirectory() as second_name:
                control, first, second = Path(control_name) / "subject", Path(first_name) / "subject", Path(second_name) / "subject"
                for subject in (control, first, second):
                    runner.base.qualification.materialize_subject(WORKSPACE, self.spec["subject_commit"], subject)
                left = runner.apply_treatment(first, case)
                right = runner.apply_treatment(second, case)
                self.assertEqual(left, right)
                before = subprocess.run(shlex.split(case["command"]), cwd=control, text=True, capture_output=True, check=True).stdout
                after = subprocess.run(shlex.split(case["command"]), cwd=first, text=True, capture_output=True, check=True).stdout
                self.assertNotEqual(before, after)
                self.assertGreaterEqual((len(before) - len(after)) / len(before), self.spec["formal"]["minimum_evidence_reduction_ratio"])
                self.assertIn(case["expected"], after)

    def test_public_compaction_remains_body_free(self) -> None:
        compact = runner.base.compact({"run_id": "x", "case_id": "x", "family": "bash", "final_text": "secret", "expected": "secret", "usage": {}, "treatment": {}})
        serialized = json.dumps(compact)
        self.assertNotIn("final_text", serialized)
        self.assertNotIn("expected", serialized)
        self.assertNotIn("secret", serialized)


if __name__ == "__main__":
    unittest.main()
