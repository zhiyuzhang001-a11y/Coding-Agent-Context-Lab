from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from m2e_events import evaluate_treatment, parse_codex_jsonl, summarize_usage
from run_m2e_calibration import balanced_schedule, codex_command, load_manifest


def token_event(input_tokens: int, output_tokens: int, cached: int, reasoning: int) -> dict:
    return {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached,
                    "cache_write_input_tokens": 0,
                    "output_tokens": output_tokens,
                    "reasoning_output_tokens": reasoning,
                    "total_tokens": input_tokens + output_tokens,
                }
            },
        },
    }


class M2eEventTests(unittest.TestCase):
    def test_final_cumulative_usage_is_selected_not_summed(self) -> None:
        usage = summarize_usage(
            [token_event(100, 10, 20, 2), token_event(250, 30, 100, 5)]
        )
        self.assertEqual(usage["status"], "valid")
        self.assertEqual(usage["candidate_count"], 2)
        self.assertEqual(usage["input_tokens"], 250)
        self.assertEqual(usage["output_tokens"], 30)
        self.assertEqual(usage["total_tokens"], 280)

    def test_exec_usage_derives_total_without_adding_subsets(self) -> None:
        usage = summarize_usage(
            [
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 200,
                        "cached_input_tokens": 120,
                        "output_tokens": 40,
                        "reasoning_output_tokens": 10,
                    },
                }
            ]
        )
        self.assertEqual(usage["total_tokens"], 240)
        self.assertTrue(usage["total_derived"])

    def test_usage_rejects_double_counted_total(self) -> None:
        event = token_event(100, 20, 10, 5)
        event["payload"]["info"]["total_token_usage"]["total_tokens"] = 135
        self.assertEqual(summarize_usage([event])["status"], "invalid")

    def test_treatment_ignores_skill_catalog_but_observes_command(self) -> None:
        catalog = {
            "type": "response_item",
            "payload": {"type": "message", "content": "budgeted-code-reading"},
        }
        command = {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "python3 scripts/task_navigator.py next . --task-id t",
                "output": "{}",
            },
        }
        self.assertTrue(evaluate_treatment([catalog], "native")["compliant"])
        self.assertFalse(evaluate_treatment([catalog, command], "native")["compliant"])
        self.assertTrue(evaluate_treatment([catalog, command], "m2d")["compliant"])

    def test_native_ignores_marker_text_in_command_output(self) -> None:
        command = {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "rg -n privacy .",
                "aggregated_output": "scripts/task_navigator.py",
                "exit_code": 0,
                "status": "completed",
            },
        }
        self.assertTrue(evaluate_treatment([command], "native")["compliant"])

    def test_m2d_rejects_failed_or_unwritable_manager_commands(self) -> None:
        command = {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "python3 scripts/task_navigator.py start . --task x",
                "aggregated_output": "PermissionError: cache_status=write_failed",
                "exit_code": 1,
                "status": "completed",
            },
        }
        treatment = evaluate_treatment([command], "m2d")
        self.assertFalse(treatment["compliant"])
        self.assertEqual(treatment["smart_command_failures"], 1)
        self.assertEqual(treatment["manager_write_failures"], 1)

    def test_jsonl_parser_reports_duplicate_outputs(self) -> None:
        events = [
            token_event(100, 20, 10, 5),
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "sed -n 1,20p source.py",
                    "output": "same",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "sed -n 1,20p source.py",
                    "output": "same",
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
            parsed = parse_codex_jsonl(path, "native")
        self.assertEqual(parsed["tools"]["duplicate_result_count"], 1)
        self.assertGreater(parsed["tools"]["estimated_read_result_tokens"], 0)

    def test_started_command_is_not_counted_as_completed_or_duplicate(self) -> None:
        events = [
            token_event(100, 20, 10, 5),
            {
                "type": "item.started",
                "item": {
                    "type": "command_execution",
                    "command": "sed -n 1,20p source.py",
                    "aggregated_output": "",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "sed -n 1,20p source.py",
                    "aggregated_output": "evidence",
                    "exit_code": 0,
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.jsonl"
            path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
            parsed = parse_codex_jsonl(path, "native")
        self.assertEqual(parsed["tools"]["command_calls"], 1)
        self.assertEqual(parsed["tools"]["completed_output_events"], 1)
        self.assertEqual(parsed["tools"]["duplicate_result_count"], 0)


class M2eManifestTests(unittest.TestCase):
    def test_calibration_manifest_and_balanced_order(self) -> None:
        manifest = load_manifest(PLUGIN / "resources" / "m2e_calibration_cases.json")
        self.assertTrue(
            all("code-navigation capability" not in case["prompt"] for case in manifest["cases"])
        )
        schedule = balanced_schedule(manifest["cases"], 2)
        self.assertEqual(len(schedule), 8)
        for case in manifest["cases"]:
            per_case = [(arm, repetition) for item, arm, repetition in schedule if item is case]
            self.assertEqual({arm for arm, _ in per_case}, {"native", "m2d"})
            self.assertNotEqual(per_case[0][0], per_case[2][0])
        second_pair = balanced_schedule([manifest["cases"][0]], 1, repetition_start=2)
        self.assertEqual([(arm, repetition) for _, arm, repetition in second_pair], [("m2d", 2), ("native", 2)])

    def test_arm_command_does_not_depend_on_plugin_config_override(self) -> None:
        manifest = load_manifest(PLUGIN / "resources" / "m2e_calibration_cases.json")
        case = manifest["cases"][0]
        command = codex_command(
            "codex",
            "native",
            case,
            Path("/worktree"),
            Path("/schema.json"),
            Path("/last.json"),
            "gpt-5.6-sol",
            "medium",
            Path("/manager-data"),
        )
        self.assertNotIn("agent-token-manager@personal", " ".join(command))
        self.assertIn("/manager-data", command)
        self.assertNotIn("--sandbox", command)
        self.assertIn("--approve-for-me", command)

    def test_edit_fixture_starts_with_the_expected_empty_input_bug(self) -> None:
        path = PLUGIN / "resources" / "m2e_calibration_fixture" / "audit_report.py"
        spec = importlib.util.spec_from_file_location("m2e_fixture_audit", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(ZeroDivisionError):
            module.summarize_audit([])


if __name__ == "__main__":
    unittest.main()
