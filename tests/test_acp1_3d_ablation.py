from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_acp1_3d_ablation as ablation  # noqa: E402


class Acp13dAblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec_path = RESOURCES / "acp1_3d_experiment_spec.json"
        cls.spec = ablation.load_spec(cls.spec_path, ROOT)

    def test_only_upstream_qualified_cases_are_admitted(self) -> None:
        self.assertEqual([row["case_id"] for row in self.spec["cases"]], [
            "natural_signature_limit_v1", "natural_command_shape_v1",
        ])
        self.assertFalse(self.spec["policy"]["production_slicing_or_replacement"])
        self.assertFalse(self.spec["policy"]["collector_or_hook_mutation"])

    def test_prefix_projection_is_deterministic_and_preserves_first_hundred_lines(self) -> None:
        case = self.spec["cases"][0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / case["treatment"]["target"]
            target.parent.mkdir(parents=True)
            original = "".join(f"line-{index}\n" for index in range(1, 151))
            target.write_text(original, encoding="utf-8")
            metadata = ablation.apply_treatment(root, case)
            self.assertEqual(target.read_text(encoding="utf-8"), "".join(f"line-{index}\n" for index in range(1, 101)))
            self.assertEqual(metadata["changed_line_count"], 50)
            self.assertNotEqual(metadata["source_before_sha256"], metadata["source_after_sha256"])

    def test_hashed_projection_is_deterministic_and_preserves_target_file(self) -> None:
        case = self.spec["cases"][1]
        snapshots = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / case["treatment"]["preserved_target"]
                target.parent.mkdir(parents=True)
                target.write_text("def command_shape():\n    return 'rg'\n", encoding="utf-8")
                other = root / "notes.txt"
                other.write_text("".join(f"CO-1 Gate 2 command_shape line {index}\n" for index in range(40)), encoding="utf-8")
                metadata = ablation.apply_treatment(root, case)
                snapshots.append((metadata, target.read_text(encoding="utf-8"), other.read_text(encoding="utf-8")))
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(snapshots[0][1], "def command_shape():\n    return 'rg'\n")
        self.assertGreater(snapshots[0][0]["changed_line_count"], 0)

    def test_logical_identity_has_no_treatment_size_floor(self) -> None:
        case = self.spec["cases"][0]
        call = {"tool_name": "exec", "command": "rg signature_from_content smart_read.py", "output": "small success"}
        analyzed = ablation.analyze_calls([call], case)
        self.assertTrue(analyzed["candidate_recurred"])
        self.assertEqual(analyzed["candidate_visible_estimated_tokens"], 4)
        self.assertTrue(analyzed["candidate_success_semantics"])

    def synthetic_runs(self, case: dict, *, treatment_wrong: int = 0) -> list[dict]:
        rows = []
        for block in range(1, 21):
            for arm in ("control", "treatment"):
                wrong = arm == "treatment" and block <= treatment_wrong
                rows.append({
                    "case_id": case["case_id"], "case_version": 1, "block": block, "arm": arm,
                    "status": "completed", "correct": not wrong, "usage": {"total_tokens": 10000 if arm == "control" else 9000},
                    "model_cycles": 2, "tool_call_count": 1, "candidate_recurred": True,
                    "candidate_ambiguous": False, "candidate_success_semantics": True,
                    "candidate_visible_estimated_tokens": 2000 if arm == "control" else 1000,
                    "candidate_result_sha256": "control" if arm == "control" else "treatment",
                    "path_signature_sha256": case["upstream_dominant_path_sha256"],
                    "hook_or_collector_used": False,
                })
        return rows

    def test_behavior_preserving_ablation_passes_but_cost_claim_stays_scoped(self) -> None:
        case = self.spec["cases"][0]
        summary = ablation.formal_case_summary(self.spec, case, self.synthetic_runs(case))
        self.assertEqual(summary["verdict"], "PASS")
        self.assertEqual(summary["session_cost"]["effect"], "observed_reduction")
        self.assertTrue(summary["claim_scope"]["potentially_avoidable_observed_evidence_supported"])
        self.assertFalse(summary["claim_scope"]["end_to_end_savings_claim"])

    def test_two_new_treatment_errors_fail_strict_correctness_gate(self) -> None:
        case = self.spec["cases"][0]
        summary = ablation.formal_case_summary(self.spec, case, self.synthetic_runs(case, treatment_wrong=2))
        self.assertEqual(summary["verdict"], "FAIL")
        self.assertFalse(summary["gates"]["g3_correctness"])
        self.assertEqual(summary["session_cost"]["effect"], "not_interpretable")

    def test_public_run_excludes_prompt_answer_command_and_tool_body(self) -> None:
        run = self.synthetic_runs(self.spec["cases"][0])[0]
        run.update({"final_text": "private-answer", "expected": "private-answer", "command": "private-command", "output": "private-output"})
        serialized = json.dumps(ablation.compact_run(run)).lower()
        for prohibited in ("final_text", "expected", "private-answer", "private-command", "private-output", "/users/"):
            self.assertNotIn(prohibited, serialized)


if __name__ == "__main__":
    unittest.main()
