from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
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


runner = load_module("run_acp0_4a_tests", SCRIPTS / "run_acp0_4a.py")


class Acp04aTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((ROOT / "resources" / "acp0_4_cases.json").read_text(encoding="utf-8"))

    @staticmethod
    def host_pass():
        return {"status": "passed", "checks": {"all": True}, "cases": []}

    def fake_runs(self, *, on_ratio: float = 1.0, on_call_delta: int = 0, on_cycle_delta: int = 0):
        runs = []
        for repetition in range(1, runner.REPETITIONS + 1):
            for case_index, case in enumerate(self.manifest["cases"]):
                for arm in ("off", "on"):
                    calls = 1 + (on_call_delta if arm == "on" else 0)
                    cycles = 2 + (on_cycle_delta if arm == "on" else 0)
                    tokens = 1000 + case_index * 10 + repetition
                    if arm == "on":
                        tokens = int(tokens * on_ratio)
                    runs.append({
                        "base_case_id": case["id"], "repetition": repetition, "arm": arm,
                        "status": "completed", "correct": True, "usage": {"total_tokens": tokens},
                        "model_cycles": cycles, "tool_call_count": calls,
                        "tool_families": ["exec"] * calls,
                        "collector_event_count": calls if arm == "on" else 0,
                        "collector_total_duration_ms": 0.1 if arm == "on" else 0,
                        "collector_invoked_tool": False,
                    })
        return runs

    def test_schedule_is_fixed_complete_and_balanced(self) -> None:
        schedule = runner.run_schedule(self.manifest["cases"])
        self.assertEqual(len(schedule), 120)
        for case in self.manifest["cases"]:
            for arm in ("off", "on"):
                self.assertEqual(sum(item[1]["id"] == case["id"] and item[2] == arm for item in schedule), 5)

    def test_distribution_has_frozen_robust_statistics(self) -> None:
        result = runner.describe([1, 2, 100])
        self.assertEqual(set(result), {"count", "mean", "median", "min", "max", "mad"})
        self.assertEqual(result["median"], 2)
        self.assertEqual(result["mad"], 1)

    def test_neutral_repetitions_pass_with_likely_stochastic_attribution(self) -> None:
        result = runner.summarize(self.manifest, self.fake_runs(), self.host_pass())
        self.assertEqual(result["graduation_verdict"], "pass")
        self.assertEqual(result["attribution_conclusion"], "likely_stochastic")
        self.assertEqual(result["overall"]["run_count"], 120)
        self.assertEqual(result["conditional_cost"]["coverage"], 1.0)
        self.assertTrue(all(result["hard_checks"].values()))
        self.assertFalse(any(result["path_signals"].values()))

    def test_cost_gate_cannot_be_replaced_by_conditional_analysis(self) -> None:
        result = runner.summarize(self.manifest, self.fake_runs(on_ratio=1.03), self.host_pass())
        self.assertEqual(result["attribution_conclusion"], "likely_stochastic")
        self.assertEqual(result["graduation_verdict"], "fail")
        self.assertGreater(result["overall"]["pooled_token_ratio"], 1.02)

    def test_systematic_path_shift_fails_even_when_tokens_do_not(self) -> None:
        result = runner.summarize(
            self.manifest, self.fake_runs(on_call_delta=1, on_cycle_delta=1), self.host_pass()
        )
        self.assertEqual(result["attribution_conclusion"], "possible_systematic_effect")
        self.assertEqual(result["graduation_verdict"], "fail")
        self.assertTrue(result["path_signals"]["mean_tool_call_delta_at_least_0_25"])
        self.assertTrue(result["path_signals"]["mean_model_cycle_delta_at_least_0_25"])

    def test_missing_run_is_not_silently_excluded(self) -> None:
        result = runner.summarize(self.manifest, self.fake_runs()[:-1], self.host_pass())
        self.assertEqual(result["attribution_conclusion"], "inconclusive")
        self.assertEqual(result["graduation_verdict"], "fail")
        self.assertFalse(result["hard_checks"]["all_120_runs_present"])
        self.assertFalse(result["no_cherry_picking"]["all_scheduled_runs_included"])

    def test_path_signature_contains_no_command_or_result_identity(self) -> None:
        signature = json.loads(runner.path_signature({
            "tool_call_count": 1, "model_cycles": 2, "tool_families": ["exec"],
            "command": "PRIVATE", "result_hash": "PRIVATE",
        }))
        self.assertEqual(set(signature), {"tool_entry", "tool_call_count", "model_cycle_count", "tool_family_sequence"})

    def test_resumed_preflight_discards_prior_probe_events(self) -> None:
        calls = []
        original = runner.base.run_host_probes
        try:
            def fake_probe(_collector, workspace):
                calls.append(workspace.exists())
                return self.host_pass()

            runner.base.run_host_probes = fake_probe
            with tempfile.TemporaryDirectory() as temp:
                workspace = Path(temp) / "host-probes"
                workspace.mkdir()
                (workspace / "stale-event.jsonl").write_text("stale\n", encoding="utf-8")
                self.assertEqual(runner.fresh_host_probes(Path("collector"), workspace)["status"], "passed")
                self.assertEqual(calls, [False])
        finally:
            runner.base.run_host_probes = original

    def test_existing_repetition_restores_base_case_identity(self) -> None:
        case = self.manifest["cases"][0]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.json"
            path.write_text(json.dumps({
                "case_id": f"{case['id']}__r03", "arm": "on", "expected": case["expected"],
            }), encoding="utf-8")
            result = runner.load_existing_result(path, case, 3, "on")
        self.assertEqual(result["base_case_id"], case["id"])
        self.assertEqual(result["repetition"], 3)


if __name__ == "__main__":
    unittest.main()
