from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path); assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


pilot = load_module("run_co1_1_pilot_tests", ROOT / "scripts" / "run_co1_1_pilot.py")


class Co11PilotTests(unittest.TestCase):
    def test_probe_plugin_has_no_context_injection_components(self) -> None:
        plugin = REPOSITORY / "experiments" / "co1-hook-only" / "plugins" / "hook-only-cost-probe"
        if not plugin.exists():
            self.skipTest("repository-only Hook probe is not packaged in the installed product plugin")
        manifest = (plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        self.assertIn('"defaultPrompt": []', manifest)
        for name in ("skills", ".mcp.json", ".app.json"):
            self.assertFalse((plugin / name).exists())
        self.assertTrue((plugin / "hooks" / "hooks.json").is_file())

    def test_summary_isolates_observe_and_rewrite_deltas(self) -> None:
        totals = {"native": [1000, 1010], "observe": [1020, 1030], "rewrite": [1100, 1110]}
        results = []
        for repetition in (1, 2):
            for arm in pilot.ARMS:
                results.append({"arm": arm, "repetition": repetition, "status": "completed", "correct": True,
                                "usage": {"total_tokens": totals[arm][repetition - 1]}, "tool_call_count": 1,
                                "model_cycles": 2, "canary_visible": True,
                                "hook_decisions": [] if arm == "native" else ["none" if arm == "observe" else "block"]})
        summary = pilot.summarize(results)
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["median_observe_minus_native"], 20)
        self.assertEqual(summary["median_rewrite_minus_observe"], 80)


if __name__ == "__main__":
    unittest.main()
