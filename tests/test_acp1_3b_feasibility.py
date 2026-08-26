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

import run_acp1_3b_feasibility as feasibility  # noqa: E402


class Acp13bFeasibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = feasibility.load_spec(RESOURCES / "acp1_3b_experiment_spec.json")

    def row(self, phase: str, repetition: int, arm: str, *, correct: bool = True) -> dict:
        visible = 2400 if arm == "control" else 1200
        return {
            "run_id": f"{phase}__r{repetition:02d}-{arm}", "phase": phase, "repetition": repetition, "arm": arm,
            "status": "completed", "correct": correct, "usage": {"total_tokens": 30000 if arm == "control" else 29000},
            "model_cycles": 2, "tool_call_count": 1, "exact_target_call_count": 1,
            "target_request_sha256": "a" * 64, "target_result_sha256": ("b" if arm == "control" else "c") * 64,
            "target_result_chars": visible * 4, "target_visible_estimated_tokens": visible,
            "target_contains_expected_evidence": True, "target_success_semantics": True,
            "payload_sha256": ("d" if arm == "control" else "e") * 64, "payload_chars": visible * 4,
            "prompt_sha256": "f" * 64, "hook_or_replacement_used": False,
        }

    def test_payload_is_deterministic_subset_and_activation_exceeds_frozen_threshold(self) -> None:
        control = feasibility.evidence_payload(self.spec, "control")
        treatment = feasibility.evidence_payload(self.spec, "treatment")
        self.assertEqual(control, feasibility.evidence_payload(self.spec, "control"))
        self.assertTrue(control.startswith(treatment))
        self.assertIn(self.spec["payload"]["target_line"], treatment)
        metadata = {arm: feasibility.payload_metadata(self.spec, arm) for arm in feasibility.ARMS}
        reduction = 1 - metadata["treatment"]["visible_estimated_tokens"] / metadata["control"]["visible_estimated_tokens"]
        self.assertGreaterEqual(reduction, self.spec["payload"]["minimum_visible_estimate_reduction_ratio"])

    def test_offline_canary_preserves_normal_success_without_hook(self) -> None:
        canary = feasibility.offline_canary(self.spec)
        self.assertEqual(canary["status"], "passed")
        self.assertTrue(canary["normal_exit_both_arms"])
        self.assertTrue(canary["source_payload_only_intervention"])
        self.assertFalse(canary["hook_or_replacement_used"])

    def test_qualification_requires_preregistered_nineteen_of_twenty(self) -> None:
        runs = [self.row("qualification", repetition, "control", correct=repetition != 20) for repetition in range(1, 21)]
        summary = feasibility.qualification_summary(self.spec, runs)
        self.assertEqual(summary["status"], "pass")
        runs[18]["correct"] = False
        self.assertEqual(feasibility.qualification_summary(self.spec, runs)["status"], "fail")

    def test_paired_mechanism_gate_is_not_cost_or_correctness_improvement_gate(self) -> None:
        canary = feasibility.offline_canary(self.spec)
        runs = [self.row("paired", repetition, arm, correct=not (arm == "treatment" and repetition == 5)) for repetition in range(1, 6) for arm in feasibility.ARMS]
        summary = feasibility.paired_summary(self.spec, runs, canary)
        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["arms"]["control"]["correct_count"], 5)
        self.assertEqual(summary["arms"]["treatment"]["correct_count"], 4)
        self.assertEqual(summary["correctness_effect_status"], "observed_not_causal_generalization")
        self.assertEqual(summary["cost_effect_status"], "observed_not_avoidable_estimate")

    def test_public_result_contains_no_prompt_answer_or_tool_body(self) -> None:
        canary = feasibility.offline_canary(self.spec)
        qualification_runs = [self.row("qualification", repetition, "control") for repetition in range(1, 21)]
        paired_runs = [self.row("paired", repetition, arm) for repetition in range(1, 6) for arm in feasibility.ARMS]
        public = feasibility.build_public_result(
            self.spec, canary, feasibility.qualification_summary(self.spec, qualification_runs),
            feasibility.paired_summary(self.spec, paired_runs, canary),
        )
        serialized = json.dumps(public, ensure_ascii=False).lower()
        self.assertNotIn(self.spec["question"].lower(), serialized)
        self.assertNotIn(self.spec["expected"].lower(), serialized)
        self.assertNotIn(self.spec["payload"]["target_line"].lower(), serialized)
        self.assertFalse(public["conclusions"]["general_savings_claim"])
        self.assertEqual(public["conclusions"]["historical_candidate_validation"], "not_performed")

    def test_runner_has_no_online_collector_or_optimizer_dependency(self) -> None:
        source = (SCRIPTS / "run_acp1_3b_feasibility.py").read_text(encoding="utf-8")
        self.assertNotIn("import acp_collector", source)
        self.assertNotIn("import context_optimizer_hook", source)
        self.assertNotIn("decision:block", source)


if __name__ == "__main__":
    unittest.main()
