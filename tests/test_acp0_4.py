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


runner = load_module("run_acp0_4_tests", SCRIPTS / "run_acp0_4.py")


class Acp04Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest_path = ROOT / "resources" / "acp0_4_cases.json"
        cls.manifest = runner.load_manifest(cls.manifest_path)
        cls.contract = json.loads((ROOT / "resources" / "acp0_contract.json").read_text(encoding="utf-8"))

    def test_manifest_has_twelve_balanced_representative_pairs(self) -> None:
        cases = self.manifest["cases"]
        self.assertEqual(len(cases), 12)
        self.assertEqual(sum(case["order"] == ["off", "on"] for case in cases), 6)
        self.assertEqual(sum(case["order"] == ["on", "off"] for case in cases), 6)
        self.assertTrue(runner.REQUIRED_CATEGORIES.issubset({case["category"] for case in cases}))
        self.assertEqual(self.manifest["token_ratio_ceiling"], 1.02)

    def test_host_probes_preserve_hash_emit_nothing_and_fail_open(self) -> None:
        collector = ROOT / self.contract["acp0_1_collector_audit"]["collector_path"]
        with tempfile.TemporaryDirectory() as directory:
            result = runner.run_host_probes(collector, Path(directory))
        self.assertEqual(result["status"], "passed")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual({case["case"] for case in result["cases"]}, {
            "controlled_success", "unknown_tool", "missing_metadata", "malformed_json", "audit_unwritable",
        })

    def results(self, *, token_ratio: float = 1.0, cycle_delta: int = 0, call_delta: int = 0):
        values = {}
        for index, case in enumerate(self.manifest["cases"]):
            off_tokens = 1000 + index
            base = {
                "status": "completed", "correct": True, "usage": {"total_tokens": off_tokens}, "model_cycles": 2,
                "tool_call_count": 2, "tool_request_hashes": ["a"], "tool_result_hashes": ["b"],
                "collector_invoked_tool": False, "collector_event_count": 0, "collector_total_duration_ms": 0,
            }
            values[(case["id"], "off")] = dict(base)
            values[(case["id"], "on")] = {
                **base, "usage": {"total_tokens": int(off_tokens * token_ratio)},
                "model_cycles": 2 + cycle_delta, "tool_call_count": 2 + call_delta,
                "collector_event_count": 2, "collector_total_duration_ms": 1.25,
            }
        return values

    @staticmethod
    def host_pass():
        return {"status": "passed", "checks": {"all": True}, "cases": []}

    def test_summary_passes_neutral_pairs_and_keeps_sequence_observational(self) -> None:
        result = runner.summarize(self.manifest, self.results(), self.host_pass())
        self.assertEqual(result["verdict"], "pass")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["aggregate"]["pair_count"], 12)
        self.assertEqual(result["aggregate"]["collector_event_count"], 24)
        self.assertTrue(result["interpretation"]["sequence_equality_is_observational_not_a_hard_gate"])

    def test_correctness_host_and_profiler_originated_calls_are_hard_failures(self) -> None:
        values = self.results()
        first = self.manifest["cases"][0]["id"]
        values[(first, "on")]["correct"] = False
        self.assertEqual(runner.summarize(self.manifest, values, self.host_pass())["verdict"], "fail")
        values = self.results()
        values[(first, "on")]["collector_invoked_tool"] = True
        self.assertEqual(runner.summarize(self.manifest, values, self.host_pass())["verdict"], "fail")
        values = self.results()
        values[(first, "on")]["collector_event_count"] = 0
        self.assertEqual(runner.summarize(self.manifest, values, self.host_pass())["verdict"], "fail")
        self.assertEqual(runner.summarize(self.manifest, self.results(), {"status": "failed"})["verdict"], "fail")

    def test_systematic_cycle_call_or_token_increase_fails(self) -> None:
        self.assertEqual(runner.summarize(
            self.manifest, self.results(cycle_delta=1), self.host_pass()
        )["verdict"], "fail")
        self.assertEqual(runner.summarize(
            self.manifest, self.results(call_delta=1), self.host_pass()
        )["verdict"], "fail")
        result = runner.summarize(self.manifest, self.results(token_ratio=1.03), self.host_pass())
        self.assertEqual(result["verdict"], "fail")
        self.assertFalse(result["checks"]["median_token_ratio_within_ceiling"])

    def test_online_manifest_contains_only_collector(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        serialized = json.dumps(hooks)
        self.assertIn("acp_collector.py", serialized)
        for forbidden in ("context_optimizer", "acp_normalizer", "acp_reporter", "replacement", "slicing"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
