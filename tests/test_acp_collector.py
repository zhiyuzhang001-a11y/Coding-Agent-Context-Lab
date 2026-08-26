from __future__ import annotations

import importlib.util
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load_module("acp_collector_tests", ROOT / "scripts" / "acp_collector.py")
replay = load_module("replay_acp0_fixture_tests", ROOT / "scripts" / "replay_acp0_fixture.py")


def sample_event() -> dict[str, object]:
    return {
        "session_id": "RAW-SESSION-SECRET",
        "turn_id": "RAW-TURN-SECRET",
        "tool_use_id": "RAW-TOOL-SECRET",
        "tool_name": "Bash",
        "tool_input": {"command": "sed -n '10,20p' src/private_auth.py"},
        "tool_response": {"output": "PRIVATE SOURCE BODY", "exit_code": 0},
        "cwd": "/private/repository",
    }


class AcpCollectorTests(unittest.TestCase):
    def test_manifest_executes_only_the_acp_collector(self) -> None:
        manifest = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        hooks = manifest["hooks"]["PostToolUse"]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["matcher"], "*")
        commands = [hook["command"] for entry in hooks for hook in entry["hooks"]]
        self.assertEqual(len(commands), 1)
        self.assertIn("acp_collector.py", commands[0])
        self.assertNotIn("optimizer", commands[0])
        self.assertNotIn("audit_tool_output.py", commands[0])

    def test_record_uses_closed_allowlist_and_does_not_persist_private_inputs(self) -> None:
        event = sample_event()
        original = copy.deepcopy(event)
        record = collector.build_record(
            event, b"k" * 32,
            timestamp="2026-08-17T00:00:00+00:00", nonce="fixed",
        )
        contract = json.loads((ROOT / "resources" / "acp0_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(set(record), set(contract["privacy_schema"]["allowed_event_fields"]))
        serialized = json.dumps(record, ensure_ascii=False)
        for private in (
            "RAW-SESSION-SECRET", "RAW-TURN-SECRET", "RAW-TOOL-SECRET",
            "PRIVATE SOURCE BODY", "private_auth.py", "/private/repository", "sed -n",
        ):
            self.assertNotIn(private, serialized)
        self.assertEqual(record["result_status"], "success")
        self.assertEqual(record["command_shape"], "sed")
        self.assertEqual(record["coverage_state"], "observed_not_matched")
        self.assertEqual(len(record["explicit_ranges"]), 1)
        self.assertEqual(event, original)
        self.assertEqual(record["output_sha256"], hashlib.sha256(b"PRIVATE SOURCE BODY").hexdigest())

    def test_pseudonyms_are_stable_within_secret_and_change_with_secret(self) -> None:
        first = collector.build_record(sample_event(), b"a" * 32, timestamp="t", nonce="n")
        second = collector.build_record(sample_event(), b"a" * 32, timestamp="t", nonce="n")
        third = collector.build_record(sample_event(), b"b" * 32, timestamp="t", nonce="n")
        self.assertEqual(first["session_id_hash"], second["session_id_hash"])
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertNotEqual(first["session_id_hash"], third["session_id_hash"])
        self.assertNotEqual(first["explicit_ranges"], third["explicit_ranges"])

    def test_missing_session_is_honestly_unmatched_and_event_scoped(self) -> None:
        event = sample_event()
        del event["session_id"]
        first = collector.build_record(event, b"k" * 32, timestamp="t", nonce="one")
        second = collector.build_record(event, b"k" * 32, timestamp="t", nonce="two")
        self.assertNotEqual(first["session_id_hash"], second["session_id_hash"])
        self.assertEqual(first["coverage_reason"], "missing_session_metadata")

    def test_external_paths_are_not_persisted_or_hashed(self) -> None:
        event = sample_event()
        event["tool_name"] = "read_file"
        event["tool_input"] = {"path": "/outside/secret.py"}
        record = collector.build_record(event, b"k" * 32, timestamp="t", nonce="n")
        self.assertEqual(record["path_hashes"], [])
        self.assertNotIn("outside", json.dumps(record))

    def test_unknown_and_unsupported_tools_remain_nonfatal_unknowns(self) -> None:
        unknown = sample_event()
        unknown["tool_name"] = "custom_tool"
        unsupported = sample_event()
        unsupported["tool_name"] = "mcp__private__read"
        first = collector.build_record(unknown, b"k" * 32, timestamp="t", nonce="n")
        second = collector.build_record(unsupported, b"k" * 32, timestamp="t", nonce="n")
        self.assertEqual(first["tool_family"], "other")
        self.assertEqual(second["coverage_state"], "unsupported_tool_path")

    def test_private_files_use_mode_0600(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "acp"
            secret = collector.load_or_create_secret(data_dir)
            collector.append_record(data_dir / "events.jsonl", collector.build_record(sample_event(), secret))
            self.assertEqual((data_dir / "collector-secret.key").stat().st_mode & 0o777, 0o600)
            self.assertEqual((data_dir / "events.jsonl").stat().st_mode & 0o777, 0o600)

    def test_cli_emits_nothing_and_failures_are_fail_open(self) -> None:
        script = ROOT / "scripts" / "acp_collector.py"
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            environment["AGENT_TOKEN_MANAGER_DATA"] = directory
            success = subprocess.run(
                [sys.executable, str(script)], input=json.dumps(sample_event()), text=True,
                capture_output=True, check=False, env=environment,
            )
            malformed = subprocess.run(
                [sys.executable, str(script)], input="{not-json", text=True,
                capture_output=True, check=False, env=environment,
            )
            blocked_path = Path(directory) / "not-a-directory"
            blocked_path.write_text("x", encoding="utf-8")
            environment["AGENT_TOKEN_MANAGER_DATA"] = str(blocked_path)
            unwritable = subprocess.run(
                [sys.executable, str(script)], input=json.dumps(sample_event()), text=True,
                capture_output=True, check=False, env=environment,
            )
        for result in (success, malformed, unwritable):
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

    def test_injected_append_and_serialization_failures_do_not_escape_main(self) -> None:
        payload = json.dumps(sample_event())
        with mock.patch.object(sys, "stdin", __import__("io").StringIO(payload)), mock.patch.object(
            collector, "append_record", side_effect=OSError("injected")
        ):
            self.assertEqual(collector.main(), 0)
        with mock.patch.object(sys, "stdin", __import__("io").StringIO(payload)), mock.patch.object(
            collector, "build_record", side_effect=TypeError("serialization injected")
        ):
            self.assertEqual(collector.main(), 0)

    def test_replay_is_byte_stable_and_matches_frozen_baseline(self) -> None:
        fixture = json.loads((ROOT / "resources" / "acp0_co1_4_replay_fixture.json").read_text(encoding="utf-8"))
        first = replay.render_summary(fixture)
        second = replay.render_summary(fixture)
        self.assertEqual(first, second)
        summary = json.loads(first)
        self.assertEqual(summary["session_count"], 12)
        self.assertEqual(summary["event_count"], 16)
        self.assertEqual(summary["estimated_model_visible_tokens"], 17651)
        self.assertEqual(summary["matched_event_count"], 16)
        self.assertEqual(summary["call_coverage"], 1.0)
        self.assertEqual(summary["model_visible_token_weighted_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
