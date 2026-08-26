from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load_module("run_co1_gate2_tests", ROOT / "scripts" / "run_co1_gate2.py")
optimizer = load_module("context_optimizer_hook_gate2_tests", ROOT / "scripts" / "context_optimizer_hook.py")


class Co1Gate2Tests(unittest.TestCase):
    def test_frozen_manifest_has_four_activated_and_two_fail_open_cases(self) -> None:
        manifest = runner.load_manifest(ROOT / "resources" / "co1_gate2_cases.json")
        self.assertEqual(len(manifest["cases"]), 6)
        self.assertEqual(sum(bool(case["activated"]) for case in manifest["cases"]), 4)
        for case in manifest["cases"]:
            start, end = runner.marker_range(ROOT / "resources" / "co1_gate2_fixture.py", case["id"])
            self.assertLess(start, end)

    def test_transcript_calls_pair_commands_and_outputs(self) -> None:
        events = [
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "1", "name": "exec_command", "arguments": json.dumps({"cmd": "sed -n '1,4p' file.py"})}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "1", "output": "visible"}},
        ]
        self.assertEqual(
            runner.transcript_calls(events),
            [{"call_id": "1", "tool_name": "exec_command", "command": "sed -n '1,4p' file.py", "output": "visible"}],
        )

    def test_code_mode_custom_exec_extracts_nested_shell_command_and_text_blocks(self) -> None:
        command = "sed -n '1,4p' file.py"
        code = (
            'const r = await tools.exec_command({"cmd":"sed -n \'1,4p\' file.py",'
            '"workdir":"/tmp/worktree"});\ntext(r.output);'
        )
        events = [
            {"type": "response_item", "payload": {"type": "custom_tool_call", "call_id": "1", "name": "exec", "input": code}},
            {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "1", "output": [{"type": "input_text", "text": "header\n"}, {"type": "input_text", "text": "body"}]}},
        ]
        calls = runner.transcript_calls(events)
        self.assertEqual(calls[0]["command"], command)
        self.assertEqual(calls[0]["output"], "header\nbody")

    def test_code_mode_custom_exec_accepts_current_unquoted_js_keys(self) -> None:
        code = (
            'const r = await tools.exec_command({cmd:"rg -n \\\"needle\\\" file.py && '
            'sed -n \'1,20p\' file.py",workdir:"/tmp/worktree",yield_time_ms:10000}); '
            'text(r.output);'
        )
        arguments = runner.custom_exec_arguments(code)
        self.assertEqual(arguments["cmd"], 'rg -n "needle" file.py && sed -n \'1,20p\' file.py')

    def test_attribution_separates_retry_compensation_test_and_other(self) -> None:
        initial = "sed -n '1,4p' file.py"
        calls = [
            {"call_id": "1", "command": initial, "output": "a"},
            {"call_id": "2", "command": initial, "output": "b"},
            {"call_id": "3", "command": "rg LIMIT file.py", "output": "c"},
            {"call_id": "4", "command": "python3 fixture_test.py", "output": "ok"},
        ]
        categories = [item["category"] for item in runner.attribute_calls(calls, initial, "file.py")]
        self.assertEqual(
            categories,
            ["initial_activated_read", "same_intent_retry", "adjacent_context_compensation", "test_or_build"],
        )

    def test_summary_applies_compensation_aware_gates_and_fail_open_reasons(self) -> None:
        manifest = runner.load_manifest(ROOT / "resources" / "co1_gate2_cases.json")
        results = {}
        for case in manifest["cases"]:
            common = {
                "correct": True, "same_intent_retries": 0, "compensation_reads": 0,
                "usage": {"total_tokens": 1000}, "visible_output_sha256": "same",
                "optimizer_reasons": [case.get("expected_fail_open_reason", "syntax_unique_range")],
            }
            if case["activated"]:
                results[(case["id"], "native")] = {
                    **common, "read_visible_tokens": 1000, "canary_visible": True, "replacement_visible": False,
                }
                results[(case["id"], "co")] = {
                    **common, "read_visible_tokens": 400, "canary_visible": False,
                    "replacement_visible": True, "usage": {"total_tokens": 900},
                }
            else:
                results[(case["id"], "native")] = {
                    **common, "read_visible_tokens": 500, "canary_visible": True, "replacement_visible": False,
                }
                results[(case["id"], "co")] = {
                    **common, "read_visible_tokens": 500, "canary_visible": True, "replacement_visible": False,
                }
        summary = runner.summarize(manifest["cases"], results)
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["median_net_saving_percent"], 60.0)

    def test_fixture_routes_four_slices_and_two_expected_fail_open_reasons(self) -> None:
        manifest = runner.load_manifest(ROOT / "resources" / "co1_gate2_cases.json")
        fixture = Path(manifest["fixture"]).resolve()
        lines = fixture.read_text(encoding="utf-8").splitlines(keepends=True)
        for case in manifest["cases"]:
            with self.subTest(case=case["id"]):
                start, end = runner.marker_range(fixture, case["id"])
                raw = "".join(lines[start - 1 : end])
                command = f"sed -n '{start},{end}p' {fixture}"
                event = {
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "tool_response": {"output": raw},
                    "cwd": str(Path.cwd()),
                }
                record, decision = optimizer.evaluate_event(
                    event,
                    mode="enforce",
                    min_chars=128,
                    visible_chars=256,
                    syntax_mode="enforce",
                    syntax_budget_chars=int(manifest["syntax_budget_chars"]),
                )
                if case["activated"]:
                    self.assertEqual(record["status"], "optimized")
                    self.assertEqual(record["optimizer_strategy"], "python_syntax_slice")
                    self.assertIsNotNone(decision)
                    self.assertNotIn(case["canary"], decision["reason"])
                else:
                    self.assertEqual(record["reason"], case["expected_fail_open_reason"])
                    self.assertIsNone(decision)


if __name__ == "__main__":
    unittest.main()
