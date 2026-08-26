from __future__ import annotations

import importlib.util
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


gate = load_module("run_co0_gate", ROOT / "scripts" / "run_co0_gate.py")


class Co0GateTests(unittest.TestCase):
    def test_fixture_canary_extracts_only_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.txt"
            fixture.write_text("header\nSECRET_TOKEN: unique-value\ntail\n", encoding="utf-8")
            self.assertEqual(gate.fixture_canary(fixture), "unique-value")

    def test_fixture_canary_requires_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture.txt"
            fixture.write_text("no marker\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                gate.fixture_canary(fixture)

    def test_model_tool_outputs_ignores_raw_exec_ui_event(self) -> None:
        events = [
            {
                "type": "event_msg",
                "payload": {"type": "exec_command_end", "output": "RAW CANARY"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": "[Smart Read CO-0 optimized result]",
                },
            },
        ]
        self.assertEqual(gate.model_tool_outputs(events), ["[Smart Read CO-0 optimized result]"])


if __name__ == "__main__":
    unittest.main()
