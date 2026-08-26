from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
SCRIPTS = ROOT / "scripts"
EXPERIMENT = REPOSITORY / "experiments/co1-hook-only/plugins/hook-only-cost-probe/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path); assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


runner = load_module("run_co1_4_replace_probe_tests", SCRIPTS / "run_co1_4_replace_probe.py")


class Co14ReplaceProbeTests(unittest.TestCase):
    def test_manifest_has_four_balanced_command_shapes(self) -> None:
        manifest = runner.load_manifest(ROOT / "resources/co1_4_replace_cases.json")
        self.assertEqual(len(manifest["cases"]), 4)
        self.assertEqual(manifest["plugin_commit"], "920a033")
        self.assertEqual(sum("&&" in case["command"] for case in manifest["cases"]), 2)

    def test_host_canary_hook_replaces_without_parsing_command(self) -> None:
        if not EXPERIMENT.is_dir():
            self.skipTest("repository-only Hook experiment is not packaged")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = {
                "tool_name": "Bash", "tool_use_id": "probe-1", "cwd": str(root),
                "tool_input": {"command": "arbitrary && pipeline | shape"},
                "tool_response": {"output": "RAW_HOST_PAYLOAD"},
            }
            environment = dict(os.environ, CO11_HOOK_MODE="host-canary", CO11_DATA=str(root))
            result = subprocess.run(
                [sys.executable, str(EXPERIMENT / "hook_probe.py")], input=json.dumps(event),
                text=True, capture_output=True, env=environment, check=False,
            )
            record = json.loads((root / "hook-probe.jsonl").read_text().strip())
        self.assertEqual(result.returncode, 0)
        self.assertIn("CO14_HOST_CANARY", result.stdout)
        self.assertIn("RAW_HOST_PAYLOAD", result.stdout)
        self.assertEqual(record["decision"], "block")
        self.assertNotIn("RAW_HOST_PAYLOAD", json.dumps(record))

    def test_summary_requires_canary_correctness_raw_preservation_and_cycle_neutrality(self) -> None:
        manifest = runner.load_manifest(ROOT / "resources/co1_4_replace_cases.json")
        results = {}
        for case in manifest["cases"]:
            results[(case["id"], "observe")] = {
                "correct": True, "canary_visible": False, "model_cycles": 2,
                "tool_call_count": 1, "hook_decisions": ["none"],
            }
            results[(case["id"], "canary")] = {
                "correct": True, "canary_visible": True, "raw_result_preserved": True,
                "success_semantics_preserved": True,
                "model_cycles": 2, "tool_call_count": 1, "hook_decisions": ["block"],
            }
        self.assertEqual(runner.summarize(manifest["cases"], results)["status"], "passed")
        first = manifest["cases"][0]["id"]
        results[(first, "observe")]["correct"] = False
        self.assertEqual(runner.summarize(manifest["cases"], results)["status"], "passed")
        results[(first, "observe")]["correct"] = True
        results[(first, "canary")]["correct"] = False
        self.assertEqual(runner.summarize(manifest["cases"], results)["status"], "failed")
        results[(first, "canary")]["correct"] = True
        results[(first, "canary")]["success_semantics_preserved"] = False
        self.assertEqual(runner.summarize(manifest["cases"], results)["status"], "failed")
        results[(first, "canary")]["success_semantics_preserved"] = True
        results[(manifest["cases"][0]["id"], "canary")]["model_cycles"] = 3
        self.assertEqual(runner.summarize(manifest["cases"], results)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
