from __future__ import annotations

import importlib.util
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


optimizer = load_module("context_optimizer_hook", ROOT / "scripts" / "context_optimizer_hook.py")


def event(command: str, output: str = "small") -> dict[str, object]:
    return {
        "session_id": "co0-session",
        "turn_id": "co0-turn",
        "tool_use_id": "co0-tool",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"output": output},
        "cwd": "/repo",
    }


class ContextOptimizerHookTests(unittest.TestCase):
    def test_strict_whitelist_accepts_only_simple_shapes(self) -> None:
        accepted = {
            "cat source.py": "cat",
            "cat -- source.py": "cat",
            "sed -n '20,80p' source.py": "sed_range",
            "rg 'needle' src": "rg",
            "python3 scripts/smart_read.py source.py --symbol Service.run": "known_symbol",
        }
        for command, expected in accepted.items():
            with self.subTest(command=command):
                self.assertEqual(optimizer.classify_command("Bash", {"command": command})[0], expected)

        rejected = [
            "cat source.py | head",
            "cat *.py",
            "sed -n '80,20p' source.py",
            "rg -n needle src",
            "rg needle src > matches.txt",
            "python3 tests/test_all.py",
            "make test",
            "cat $(find . -name source.py)",
        ]
        for command in rejected:
            with self.subTest(command=command):
                self.assertIsNone(optimizer.classify_command("Bash", {"command": command})[0])

    def test_enforced_large_read_replaces_raw_canary_payload(self) -> None:
        canary = "CO0_RAW_PAYLOAD_CANARY_7C91"
        original = "useful first line\n" + ("middle filler\n" * 300) + canary + "\nprivate tail"
        with mock.patch.dict(os.environ, {"AGENT_TOKEN_MANAGER_CO0_CANARY": canary}, clear=False):
            record, decision = optimizer.evaluate_event(
                event("cat source.py", original), mode="enforce", min_chars=128, visible_chars=512
            )
        self.assertEqual(record["status"], "optimized")
        self.assertTrue(record["canary_in_original"])
        self.assertFalse(record["canary_in_replacement"])
        self.assertIsNotNone(decision)
        replacement = decision["reason"]
        self.assertEqual(decision["decision"], "block")
        self.assertIn("useful first line", replacement)
        self.assertNotIn(canary, replacement)
        self.assertLess(len(replacement), len(original))

    def test_default_observe_mode_never_replaces_output(self) -> None:
        record, decision = optimizer.evaluate_event(event("cat source.py", "x" * 9000), mode="observe")
        self.assertEqual(record["status"], "passthrough_observe")
        self.assertIsNone(decision)

    def test_unsupported_and_small_results_passthrough(self) -> None:
        unsupported, unsupported_decision = optimizer.evaluate_event(
            event("pytest -q", "x" * 9000), mode="enforce", min_chars=128
        )
        small, small_decision = optimizer.evaluate_event(
            event("rg needle src", "one match"), mode="enforce", min_chars=128
        )
        self.assertEqual(unsupported["status"], "passthrough_unsupported")
        self.assertEqual(small["status"], "passthrough_not_beneficial")
        self.assertIsNone(unsupported_decision)
        self.assertIsNone(small_decision)

    def test_injected_error_and_timeout_fail_open(self) -> None:
        original = "x" * 9000
        error, error_decision = optimizer.evaluate_event(
            event("cat source.py", original), mode="enforce", min_chars=128, force_failure="error"
        )
        timeout, timeout_decision = optimizer.evaluate_event(
            event("cat source.py", original), mode="enforce", min_chars=128, force_failure="timeout"
        )
        self.assertEqual(error["status"], "fallback_optimizer_error")
        self.assertEqual(timeout["status"], "fallback_budget_or_timeout")
        self.assertEqual(error["fallback_reason"], "injected_optimizer_error")
        self.assertEqual(timeout["fallback_reason"], "injected_timeout")
        self.assertIsNone(error_decision)
        self.assertIsNone(timeout_decision)

    def test_environment_injection_requires_explicit_test_mode(self) -> None:
        original = "x" * 9000
        variables = {"AGENT_TOKEN_MANAGER_CO0_INJECT_FAILURE": "error"}
        with mock.patch.dict(os.environ, variables, clear=False):
            optimized, decision = optimizer.evaluate_event(
                event("cat source.py", original), mode="enforce", min_chars=128
            )
        self.assertEqual(optimized["status"], "optimized")
        self.assertIsNotNone(decision)
        variables["AGENT_TOKEN_MANAGER_CO0_TEST_MODE"] = "1"
        with mock.patch.dict(os.environ, variables, clear=False):
            fallback, fallback_decision = optimizer.evaluate_event(
                event("cat source.py", original), mode="enforce", min_chars=128
            )
        self.assertEqual(fallback["status"], "fallback_optimizer_error")
        self.assertIsNone(fallback_decision)

    def test_log_is_private_and_contains_observable_state(self) -> None:
        secret = "SECRET SOURCE BODY"
        record, _ = optimizer.evaluate_event(
            event("cat source.py", secret * 500), mode="enforce", min_chars=128, visible_chars=512
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context-optimizer.jsonl"
            optimizer.append_record(path, record)
            serialized = path.read_text(encoding="utf-8")
            parsed = json.loads(serialized)
            mode = path.stat().st_mode & 0o777
        self.assertEqual(parsed["status"], "optimized")
        self.assertNotIn(secret, serialized)
        self.assertEqual(mode, 0o600)

    def test_frozen_optimizer_is_not_registered_in_acp_hook_chain(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        post_hooks = hooks["hooks"]["PostToolUse"]
        commands = [hook["command"] for entry in post_hooks for hook in entry["hooks"]]
        self.assertTrue(any("acp_collector.py" in command for command in commands))
        self.assertFalse(any("context_optimizer_hook.py" in command for command in commands))

    def test_cli_emits_hook_decision_and_private_record(self) -> None:
        canary = "CO0_SUBPROCESS_CANARY_91D2"
        raw = "visible locator\n" + ("filler\n" * 500) + canary
        payload = event("rg needle src", raw)
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            environment.update(
                {
                    "AGENT_TOKEN_MANAGER_DATA": directory,
                    "AGENT_TOKEN_MANAGER_CO0_MODE": "enforce",
                    "AGENT_TOKEN_MANAGER_CO0_MIN_CHARS": "128",
                    "AGENT_TOKEN_MANAGER_CO0_VISIBLE_CHARS": "512",
                    "AGENT_TOKEN_MANAGER_CO0_CANARY": canary,
                }
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "context_optimizer_hook.py")],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
            decision = json.loads(result.stdout)
            record = json.loads((Path(directory) / "context-optimizer.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(decision["decision"], "block")
        self.assertNotIn(canary, decision["reason"])
        self.assertEqual(record["status"], "optimized")
        self.assertEqual(record["mode"], "enforce")
        self.assertTrue(record["canary_in_original"])
        self.assertFalse(record["canary_in_replacement"])


if __name__ == "__main__":
    unittest.main()
