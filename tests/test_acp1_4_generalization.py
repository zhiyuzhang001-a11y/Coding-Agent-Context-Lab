from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
SCRIPTS = ROOT / "scripts"
RESOURCES = ROOT / "resources"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_acp1_4_generalization as runner  # noqa: E402


class Acp14GeneralizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec_path = RESOURCES / "acp1_4_experiment_spec.json"
        cls.spec = runner.load_spec(cls.spec_path, ROOT)

    def test_sampling_frame_and_family_coverage_are_frozen(self) -> None:
        self.assertEqual(len(self.spec["cases"]), 8)
        self.assertEqual(Counter(row["family"] for row in self.spec["cases"]), Counter({"read": 3, "search": 3, "bash": 2}))
        self.assertEqual(self.spec["generalization"]["qualified_case_min"], 6)
        self.assertEqual(self.spec["generalization"]["qualified_per_family_min"], 2)

    def test_treatments_and_thresholds_are_preregistered(self) -> None:
        self.assertEqual({row["treatment"]["method"] for row in self.spec["cases"]}, {
            "prefix-source-projection-v1", "hashed-nontarget-match-ablation-v1", "python-unittest-method-subset-v1",
        })
        self.assertEqual(self.spec["formal"]["minimum_evidence_reduction_ratio"], 0.35)
        self.assertEqual(self.spec["formal"]["blocks_per_case"], 10)
        self.assertFalse(self.spec["policy"]["production_slicing_or_replacement"])
        self.assertFalse(self.spec["policy"]["global_savings_claim"])

    def test_public_compaction_excludes_prompt_answer_and_tool_body(self) -> None:
        compact = runner.compact({
            "run_id": "secret", "case_id": "x", "family": "read", "final_text": "answer", "expected": "answer",
            "tool_result": "body", "usage": {"total_tokens": 3}, "treatment": {"method": "x"},
        })
        serialized = json.dumps(compact)
        for prohibited in ("final_text", "expected", "tool_result", "body", "answer"):
            self.assertNotIn(prohibited, serialized)

    def test_all_treatments_are_deterministic_and_change_subject(self) -> None:
        with tempfile.TemporaryDirectory() as first_name, tempfile.TemporaryDirectory() as second_name:
            first, second = Path(first_name) / "subject", Path(second_name) / "subject"
            runner.qualification.materialize_subject(WORKSPACE, self.spec["subject_commit"], first)
            runner.qualification.materialize_subject(WORKSPACE, self.spec["subject_commit"], second)
            for case in self.spec["cases"]:
                left = runner.apply_treatment(first, case)
                right = runner.apply_treatment(second, case)
                self.assertEqual(left, right)
                self.assertGreater(left["changed_line_count"], 0)

    def test_read_treatments_preserve_ground_truth_lines(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            subject = Path(name) / "subject"
            runner.qualification.materialize_subject(WORKSPACE, self.spec["subject_commit"], subject)
            for case in [row for row in self.spec["cases"] if row["family"] == "read"]:
                runner.apply_treatment(subject, case)
            self.assertIn("SCHEMA_VERSION = 1", (subject / "plugins/agent-token-manager/scripts/navigation_contract.py").read_text())
            self.assertIn("DEFAULT_DIRECT_MAX_TOKENS = 800", (subject / "plugins/agent-token-manager/scripts/context_router.py").read_text())
            self.assertIn('DATABASE_NAME = "navigation-v1.sqlite3"', (subject / "plugins/agent-token-manager/scripts/workspace_data.py").read_text())

    def test_search_treatments_preserve_target_and_reduce_other_matches(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            subject = Path(name) / "subject"
            runner.qualification.materialize_subject(WORKSPACE, self.spec["subject_commit"], subject)
            for case in [row for row in self.spec["cases"] if row["family"] == "search"]:
                preserved = subject / case["treatment"]["preserved_target"]
                before = preserved.read_bytes()
                meta = runner.apply_treatment(subject, case)
                self.assertEqual(preserved.read_bytes(), before)
                self.assertGreater(meta["changed_line_count"], 0)

    def test_bash_subset_treatments_remain_valid_python_and_remove_methods(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            subject = Path(name) / "subject"
            runner.qualification.materialize_subject(WORKSPACE, self.spec["subject_commit"], subject)
            for case in [row for row in self.spec["cases"] if row["family"] == "bash"]:
                meta = runner.apply_treatment(subject, case)
                self.assertGreater(meta["removed_test_method_count"], 0)
                target = subject / case["treatment"]["target"]
                completed = subprocess.run([sys.executable, "-m", "py_compile", str(target)], capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_generalization_verdict_does_not_use_session_ratio(self) -> None:
        registry = {"formal_coverage_gate": True}
        rows = []
        for family in ("read", "search", "bash"):
            rows.extend({"case_id": f"{family}-{index}", "family": family, "verdict": "PASS"} for index in range(2))
        verdict = runner.generalization_summary(self.spec, rows, registry, True)
        self.assertEqual(verdict["verdict"], "SUPPORTED_WITH_BOUNDARIES")
        self.assertNotIn("session", json.dumps(verdict).lower())


if __name__ == "__main__":
    unittest.main()
