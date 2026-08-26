from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path); assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


probe = load_module("run_co1_4_host_probe_tests", SCRIPTS / "run_co1_4_host_probe.py")


class Co14HostProbeTests(unittest.TestCase):
    def test_unwrap_and_family_do_not_require_full_shell_parser(self) -> None:
        wrapped = '/bin/zsh -lc "rg -n needle file.py && sed -n \'1,20p\' file.py"'
        command = probe.unwrap_cli_command(wrapped)
        self.assertEqual(command, "rg -n needle file.py && sed -n '1,20p' file.py")
        self.assertEqual(probe.command_family(command), "compound_shell")
        self.assertTrue(probe.code_bearing(command))

    def test_summary_uses_call_and_visible_token_weighted_coverage(self) -> None:
        calls = [
            {"family": "rg", "code_bearing": True, "model_visible_tokens": 900,
             "hook_observed": True, "command_correlated": True, "raw_present_in_model_visible": True,
             "hook_tool_name": "Bash"},
            {"family": "sed", "code_bearing": True, "model_visible_tokens": 100,
             "hook_observed": False, "command_correlated": True, "raw_present_in_model_visible": True,
             "hook_tool_name": None},
        ]
        result = probe.summarize([{"run_id": "one", "calls": calls}])
        self.assertEqual(result["call_coverage"], 0.5)
        self.assertEqual(result["weighted_coverage"], 0.9)
        self.assertEqual(result["status"], "failed")

    def test_observe_pass_requires_end_to_end_correlation(self) -> None:
        calls = []
        for family in ("rg", "sed"):
            calls.append({"family": family, "code_bearing": True, "model_visible_tokens": 100,
                          "hook_observed": True, "command_correlated": True,
                          "raw_present_in_model_visible": True, "hook_tool_name": "Bash"})
        result = probe.summarize([{"run_id": "one", "calls": calls}])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["end_to_end_correlation"], 1.0)


if __name__ == "__main__":
    unittest.main()
