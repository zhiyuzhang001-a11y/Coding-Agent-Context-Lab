from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_module("run_acp0_4b_tests", SCRIPTS / "run_acp0_4b.py")


class Acp04bTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = json.loads((ROOT / "resources" / "acp0_4b_correctness_spec.json").read_text(encoding="utf-8"))
        cls.inherited = {
            "status": "inconclusive",
            "cost_neutrality": {"pooled_gate_pass": True},
            "path_neutrality": {"any_preregistered_systematic_signal": False},
            "hard_checks": {"host_hard_gates_pass": True},
        }

    @staticmethod
    def row(arm="off", answer="7", status="completed"):
        return {
            "repetition": 1, "arm": arm, "status": status, "answer": answer,
            "correct": answer == "7" and status == "completed",
            "answer_shape": "correct" if answer == "7" else "other_integer",
            "tool_calls": 1, "model_cycles": 2, "total_tokens": 100,
            "collector_events": 1 if arm == "on" else 0, "collector_invoked_tool": False,
        }

    def test_specification_and_thresholds_are_preregistered(self) -> None:
        self.assertEqual(self.spec["specification_audit"]["status"], "unambiguous_existing_case")
        self.assertEqual(self.spec["native_calibration"]["repetitions"], 20)
        self.assertEqual(self.spec["native_calibration"]["empirically_stable_minimum_correct"], 19)
        self.assertEqual(self.spec["prospective_correctness"]["stochastic_minimum_accuracy_delta"], -0.1)
        self.assertFalse(self.spec["prospective_correctness"]["runs_enter_cost_or_path_gate"])

    def test_answer_shapes_are_observational_and_deterministic(self) -> None:
        expected = self.spec["expected"]
        cases = {
            "7": "correct", "6": "off_by_one_like", "8": "off_by_one_like",
            "5": "first_cluster_only_like", "10": "endpoint_like", "42": "other_integer",
            "seven": "malformed_or_missing", "": "malformed_or_missing",
        }
        for answer, category in cases.items():
            with self.subTest(answer=answer):
                self.assertEqual(runner.answer_shape({"status": "completed", "final_text": answer}, expected), category)
        self.assertEqual(runner.answer_shape({"status": "failed", "final_text": "7"}, expected), "execution_failure")

    def test_native_classification_boundary_is_frozen(self) -> None:
        stable = [self.row(answer="7") for _ in range(19)] + [self.row(answer="8")]
        diagnostic = [self.row(answer="7") for _ in range(18)] + [self.row(answer="8") for _ in range(2)]
        self.assertEqual(runner.baseline_summary(self.spec, stable)["classification"], "empirically_stable_gate")
        self.assertEqual(runner.baseline_summary(self.spec, diagnostic)["classification"], "stochastic_diagnostic")

    def test_frozen_baseline_must_reproduce_preregistered_classification(self) -> None:
        baseline = {
            "schema_id": runner.BASELINE_SCHEMA_ID, "case_id": self.spec["case_id"],
            "expected": self.spec["expected"], "run_count": 20, "correct_count": 14,
            "classification": "stochastic_diagnostic", "all_runs_included": True,
        }
        runner.validate_frozen_baseline(self.spec, baseline)
        baseline["classification"] = "empirically_stable_gate"
        with self.assertRaises(RuntimeError):
            runner.validate_frozen_baseline(self.spec, baseline)

    def test_stochastic_gate_accepts_frozen_minus_point_one_boundary(self) -> None:
        baseline = {"classification": "stochastic_diagnostic"}
        off = [self.row("off", "7") for _ in range(15)] + [self.row("off", "8") for _ in range(5)]
        on = [self.row("on", "7") for _ in range(13)] + [self.row("on", "8") for _ in range(7)]
        result = runner.paired_summary(self.spec, baseline, off + on, {"status": "passed"}, self.inherited)
        self.assertAlmostEqual(result["accuracy_delta_on_minus_off"], -0.1)
        self.assertTrue(result["hard_checks"]["prospective_correctness_criterion_pass"])
        self.assertEqual(result["acp0_graduation"], "pass")

    def test_stable_gate_requires_nineteen_and_not_below_off(self) -> None:
        baseline = {"classification": "empirically_stable_gate"}
        off = [self.row("off", "7") for _ in range(20)]
        on = [self.row("on", "7") for _ in range(19)] + [self.row("on", "8")]
        result = runner.paired_summary(self.spec, baseline, off + on, {"status": "passed"}, self.inherited)
        self.assertFalse(result["hard_checks"]["prospective_correctness_criterion_pass"])
        self.assertEqual(result["acp0_graduation"], "fail")

    def test_inherited_cost_failure_cannot_be_overridden(self) -> None:
        inherited = json.loads(json.dumps(self.inherited))
        inherited["cost_neutrality"]["pooled_gate_pass"] = False
        rows = [self.row("off", "7") for _ in range(20)] + [self.row("on", "7") for _ in range(20)]
        result = runner.paired_summary(
            self.spec, {"classification": "empirically_stable_gate"}, rows, {"status": "passed"}, inherited,
        )
        self.assertFalse(result["inherited_checks"]["acp0_4a_cost_gate_pass"])
        self.assertEqual(result["acp0_graduation"], "fail")


if __name__ == "__main__":
    unittest.main()
