from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_m2e_cost_attribution import (
    analyze_run,
    command_operations,
    completed_commands,
    payload_bucket,
    select_latest_successful,
)


class M2eCostAttributionTests(unittest.TestCase):
    def test_compound_navigator_commands_preserve_each_invocation(self) -> None:
        command = (
            'python3 navigation_map.py index .; '
            'python3 task_navigator.py start . --task "find target"'
        )
        operations = command_operations(command)
        self.assertEqual(operations, ["index", "start"])
        self.assertEqual(payload_bucket(operations), "compound")

    def test_expand_payload_is_source_evidence(self) -> None:
        operations = command_operations("python3 task_navigator.py expand . --marker-id abc")
        self.assertEqual(operations, ["expand"])
        self.assertEqual(payload_bucket(operations), "source_evidence")

    def test_completed_commands_exclude_started_events(self) -> None:
        events = [
            {
                "type": "item.started",
                "item": {"type": "command_execution", "command": "rg x", "aggregated_output": ""},
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": "rg x",
                    "aggregated_output": "one",
                },
            },
        ]
        self.assertEqual(completed_commands(events), [(1, "rg x", "one")])

    def test_latest_successful_summary_is_selected_per_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for batch, total, success in (
                ("20260101T000000Z", 100, True),
                ("20260102T000000Z", 200, True),
                ("20260103T000000Z", 300, False),
            ):
                run = root / batch / "case-r1-native"
                run.mkdir(parents=True)
                (run / "summary.json").write_text(
                    json.dumps(
                        {
                            "case_id": "case",
                            "repetition": 1,
                            "arm": "native",
                            "success": success,
                            "events": {"usage": {"total_tokens": total}},
                        }
                    ),
                    encoding="utf-8",
                )
            selected = select_latest_successful(root)
        self.assertEqual(len(selected), 1)
        self.assertIn("20260102T000000Z", str(selected[0]))

    def test_trace_keeps_hashes_and_evidence_flags_not_output_body(self) -> None:
        secret = "SECRET_SOURCE_BODY expected.py target_symbol"
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            run.mkdir()
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "sed -n 1,20p expected.py",
                        "aggregated_output": secret,
                    },
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 100, "output_tokens": 20},
                },
            ]
            (run / "codex.jsonl").write_text(
                "\n".join(json.dumps(event) for event in events) + "\n",
                encoding="utf-8",
            )
            summary = run / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "run_id": "case-r1-native",
                        "case_id": "case",
                        "kind": "locate",
                        "arm": "native",
                        "repetition": 1,
                        "success": True,
                        "raw_artifacts": {"directory": str(run)},
                    }
                ),
                encoding="utf-8",
            )
            result = analyze_run(
                summary,
                {"case": {"paths": ["expected.py"], "symbols": ["target_symbol"]}},
            )
        encoded = json.dumps(result)
        self.assertNotIn(secret, encoded)
        self.assertTrue(result["trace"][0]["effective_evidence"])
        self.assertEqual(len(result["trace"][0]["output_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
