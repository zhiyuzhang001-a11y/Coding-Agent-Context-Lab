from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load_module("audit_tool_output", ROOT / "scripts" / "audit_tool_output.py")
report = load_module("report_audit", ROOT / "scripts" / "report_audit.py")


class AuditTests(unittest.TestCase):
    def test_record_keeps_metadata_but_not_response_content(self) -> None:
        secret_source = "def login(password):\n    return password == 'secret'\n"
        event = {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "tool_name": "Bash",
            "tool_input": {"cmd": "sed -n 1,80p src/auth.py", "workdir": "/repo"},
            "tool_response": {"output": secret_source},
        }
        record = audit.build_record(event)
        serialized = json.dumps(record)
        self.assertTrue(record["read_like"])
        self.assertEqual(record["explicit_paths"], ["/repo"])
        self.assertGreater(record["estimated_response_tokens"], 0)
        self.assertEqual(record["token_count_method"], "chars_div_4_v1")
        self.assertFalse(record["large_read_candidate"])
        self.assertNotIn(secret_source, serialized)
        self.assertNotIn("password", serialized)

    def test_append_and_report_detect_duplicate_results(self) -> None:
        event = {
            "tool_name": "read_file",
            "tool_input": {"path": "src/auth.py"},
            "tool_response": "same output",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            record = audit.build_record(event)
            audit.append_record(path, record)
            audit.append_record(path, record)
            summary = report.summarize(report.load_records(path))
        self.assertEqual(summary["tool_calls"], 2)
        self.assertEqual(summary["repeated_identical_results"], 1)
        self.assertEqual(summary["read_share_percent"], 100.0)

    def test_smart_read_python_command_counts_as_read(self) -> None:
        tool_input = {
            "cmd": "/usr/bin/python3 scripts/smart_read.py src/auth.py --budget 700"
        }
        self.assertTrue(audit.is_read_like("Bash", tool_input))

    def test_task_navigator_command_counts_as_read(self) -> None:
        tool_input = {
            "cmd": "python3 scripts/task_navigator.py expand . --task-id t --marker-id m"
        }
        self.assertTrue(audit.is_read_like("exec_command", tool_input))

    def test_compact_navigator_command_counts_as_read(self) -> None:
        tool_input = {
            "cmd": "python3 scripts/compact_navigator.py navigate . --task investigate --request-id r1"
        }
        self.assertTrue(audit.is_read_like("exec_command", tool_input))

    def test_large_read_candidate_is_reported(self) -> None:
        event = {
            "tool_name": "read_file",
            "tool_input": {"path": "large.py"},
            "tool_response": "x" * 9000,
        }
        record = audit.build_record(event)
        summary = report.summarize([record])
        self.assertTrue(record["large_read_candidate"])
        self.assertEqual(summary["large_read_candidates"], 1)
        self.assertEqual(summary["large_read_candidate_tokens"], 2250)
        self.assertEqual(summary["largest_read_result_tokens"], 2250)

    def test_manager_metadata_is_whitelisted_and_reported(self) -> None:
        response = {
            "output": json.dumps(
                {
                    "cache_status": "hit",
                    "estimated_output_tokens": 321,
                    "route": {
                        "mode": "symbol",
                        "reason": "named_symbols",
                        "source_estimated_tokens": 5000,
                        "direct_max_tokens": 800,
                    },
                    "regions": [{"content": "TOP SECRET SOURCE"}],
                }
            )
        }
        record = audit.build_record(
            {
                "tool_name": "Bash",
                "tool_input": {"cmd": "python3 scripts/context_router.py source.py"},
                "tool_response": response,
            }
        )
        serialized = json.dumps(record)
        self.assertEqual(record["manager_read"]["cache_status"], "hit")
        self.assertEqual(record["manager_read"]["route_reason"], "named_symbols")
        self.assertTrue(record["read_like"])
        self.assertNotIn("TOP SECRET SOURCE", serialized)
        summary = report.summarize([record])
        self.assertEqual(summary["manager_reads"], 1)
        self.assertEqual(summary["cache_statuses"], {"hit": 1})
        self.assertEqual(summary["route_reasons"], {"named_symbols": 1})

    def test_serena_bundle_metadata_and_tool_are_read_like(self) -> None:
        response = json.dumps(
            {
                "backend": "serena",
                "backend_calls": 2,
                "estimated_output_tokens": 450,
                "target": [{"body": "PRIVATE SOURCE"}],
            }
        )
        record = audit.build_record(
            {
                "tool_name": "mcp__serena_context_adapter__context_bundle",
                "tool_input": {"name_path": "Service/run"},
                "tool_response": response,
            }
        )
        self.assertTrue(record["read_like"])
        self.assertEqual(record["manager_read"]["backend"], "serena")
        self.assertEqual(record["manager_read"]["backend_calls"], 2)
        self.assertNotIn("PRIVATE SOURCE", json.dumps(record))

    def test_read_pipeline_counts_as_read(self) -> None:
        tool_input = {"cmd": "nl -ba src/auth.py | sed -n '1,200p'"}
        self.assertTrue(audit.is_read_like("Bash", tool_input))


if __name__ == "__main__":
    unittest.main()
