from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load_module("run_co1_3_ab_tests", SCRIPTS / "run_co1_3_ab.py")


class Co13AbTests(unittest.TestCase):
    def manifest(self):
        return runner.load_manifest(ROOT / "resources/co1_3_cases.json")

    def test_manifest_freezes_twelve_balanced_natural_tasks(self) -> None:
        manifest = self.manifest()
        self.assertEqual(manifest["subject_commit"], "b506818")
        prompts = [runner.build_prompt(case) for case in manifest["cases"]]
        self.assertTrue(all("Begin by running" not in prompt for prompt in prompts))
        self.assertEqual(sum(case["order"] == ["native", "co"] for case in manifest["cases"]), 6)
        self.assertEqual(sum(case["order"] == ["co", "native"] for case in manifest["cases"]), 6)

    def test_offline_expected_classification_matches_frozen_gate(self) -> None:
        experiment = REPOSITORY / "experiments/co1-hook-only/plugins/hook-only-cost-probe"
        if not experiment.is_dir():
            self.skipTest("repository-only frozen Hook experiment is not packaged")
        rows = runner.preflight(REPOSITORY, self.manifest())
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(row["passed"] for row in rows), json.dumps(rows, indent=2))
        self.assertTrue(all(row["activate_slice"] for row in rows[:6]))
        self.assertTrue(all(not row["activate_slice"] for row in rows[6:]))

    def fake_results(self, *, co_ratio: float, cycle_delta: int = 0, recovery: int = 0):
        manifest = self.manifest()
        results = {}
        for case in manifest["cases"]:
            hit = case["cohort"] == "expected_hit"
            results[(case["id"], "native")] = {
                "correct": True, "usage": {"total_tokens": 1000}, "model_visible_code_tokens": 200,
                "model_cycles": 2, "tool_call_count": 2, "exact_read_retries": 0,
            }
            results[(case["id"], "co")] = {
                "correct": True, "usage": {"total_tokens": int(1000 * co_ratio)},
                "model_visible_code_tokens": 100 if hit else 200,
                "model_cycles": 2 + cycle_delta, "tool_call_count": 2, "exact_read_retries": 0,
                "recovery_reads_after_activation": recovery if hit else 0,
                "gate_activations": 1 if hit else 0, "gate_reasons": ["low_compensation_risk" if hit else case["expected_gate_reason"]],
                "package_visible": hit,
            }
        return manifest, results

    def test_summary_freezes_strong_weak_and_fail_verdicts(self) -> None:
        manifest, results = self.fake_results(co_ratio=0.90)
        self.assertEqual(runner.summarize(manifest["cases"], results)["verdict"], "strong_pass")
        manifest, results = self.fake_results(co_ratio=0.98)
        self.assertEqual(runner.summarize(manifest["cases"], results)["verdict"], "weak_signal")
        manifest, results = self.fake_results(co_ratio=0.90, cycle_delta=1, recovery=1)
        self.assertEqual(runner.summarize(manifest["cases"], results)["verdict"], "fail")

    def test_zero_actual_activation_is_fail_even_when_total_tokens_are_lower(self) -> None:
        manifest, results = self.fake_results(co_ratio=0.90)
        for case in manifest["cases"]:
            results[(case["id"], "co")]["gate_activations"] = 0
            results[(case["id"], "co")]["package_visible"] = False
        summary = runner.summarize(manifest["cases"], results)
        self.assertFalse(summary["checks"]["actual_activation_nonzero"])
        self.assertEqual(summary["verdict"], "fail")


if __name__ == "__main__":
    unittest.main()
