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
SCRIPTS = REPOSITORY / "experiments" / "co1-hook-only" / "plugins" / "hook-only-cost-probe" / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


EXPERIMENT_AVAILABLE = SCRIPTS.is_dir()
if EXPERIMENT_AVAILABLE and str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
gate = load_module("compensation_risk_gate_tests", SCRIPTS / "compensation_risk_gate.py") if EXPERIMENT_AVAILABLE else None


@unittest.skipUnless(EXPERIMENT_AVAILABLE, "repository-only CO-1.2 experiment is not packaged")
class CompensationRiskGateTests(unittest.TestCase):
    def decision(self, source: str, *, raw_padding: int = 2400, intent: str | None = None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.py"
            path.write_text(source, encoding="utf-8")
            lines = source.splitlines()
            return gate.evaluate(path, 1, len(lines), source + ("# raw-only padding\n" * raw_padding), task_intent=intent)

    def test_self_contained_function_and_pure_method_activate(self) -> None:
        function = self.decision("def clean(value: str) -> str:\n    return value.strip().lower()\n")
        method = self.decision("class Pure:\n    def add(self, value: int) -> int:\n        return value + 1\n")
        for decision in (function, method):
            self.assertTrue(decision.activate_slice)
            self.assertEqual(decision.reason, "low_compensation_risk")
            self.assertIsNotNone(decision.replacement)
            self.assertGreaterEqual(decision.details["estimated_saving_tokens"], 200)
            self.assertGreaterEqual(decision.details["estimated_saving_ratio"], 0.4)

    def test_module_constant_and_external_helper_are_distinct(self) -> None:
        constant = self.decision("LIMIT = 7\ndef calculate(value: int) -> int:\n    return value * LIMIT\n")
        helper = self.decision("def helper(value: int) -> int:\n    return value + 1\ndef calculate(value: int) -> int:\n    return helper(value)\n")
        self.assertEqual(constant.reason, "external_dependency_risk")
        self.assertEqual(constant.details["risk_evidence"], ["LIMIT"])
        self.assertEqual(helper.reason, "analysis_uncertain")
        # A range spanning both sibling functions is rejected before dependency scoring.
        self.assertEqual(helper.details["risk_evidence"], ["non_unique_target"])

    def test_external_helper_with_unique_range_is_detected(self) -> None:
        source = "def helper(value: int) -> int:\n    return value + 1\n\ndef calculate(value: int) -> int:\n    return helper(value)\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.py"; path.write_text(source, encoding="utf-8")
            decision = gate.evaluate(path, 4, 5, source + ("# padding\n" * 2400))
        self.assertEqual(decision.reason, "external_helper_risk")
        self.assertEqual(decision.details["risk_evidence"], ["helper"])

    def test_external_import_is_detected_as_dependency(self) -> None:
        source = "import math\n\ndef round_up(value: float) -> int:\n    return math.ceil(value)\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.py"; path.write_text(source, encoding="utf-8")
            decision = gate.evaluate(path, 3, 4, source + ("# raw-only canary\n" * 2400))
        self.assertEqual(decision.reason, "external_dependency_risk")
        self.assertEqual(decision.details["risk_evidence"], ["math"])
        self.assertIsNone(decision.replacement)

    def test_class_field_and_sibling_method_are_distinct(self) -> None:
        state = self.decision("class Service:\n    def run(self, value: int) -> int:\n        return value * self.multiplier\n")
        sibling = self.decision("class Service:\n    def run(self, value: int) -> int:\n        return self.normalize(value)\n")
        self.assertEqual(state.reason, "class_state_risk")
        self.assertEqual(state.details["risk_evidence"], ["multiplier"])
        self.assertEqual(sibling.reason, "sibling_method_risk")
        self.assertEqual(sibling.details["risk_evidence"], ["normalize"])

    def test_dynamic_task_intent_low_saving_and_ambiguity_fail_open(self) -> None:
        dynamic = self.decision("def read(obj):\n    return getattr(obj, 'value')\n")
        intent = self.decision("def clean(value):\n    return value.strip()\n", intent="edit")
        low = self.decision("def clean(value):\n    return value.strip()\n", raw_padding=0)
        ambiguous = self.decision("def left():\n    return 1\ndef right():\n    return 2\n")
        self.assertEqual(dynamic.reason, "dynamic_semantics_risk")
        self.assertEqual(intent.reason, "task_intent_risk")
        self.assertEqual(low.reason, "insufficient_expected_saving")
        self.assertEqual(ambiguous.reason, "analysis_uncertain")
        for decision in (dynamic, intent, low, ambiguous):
            self.assertFalse(decision.activate_slice)
            self.assertIsNone(decision.replacement)

    def test_real_hook_blocks_only_low_risk_slice_and_logs_high_risk_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            low = root / "low.py"; low.write_text("def clean(value):\n    return value.strip()\n", encoding="utf-8")
            high = root / "high.py"; high.write_text("LIMIT = 7\ndef calc(value):\n    return value * LIMIT\n", encoding="utf-8")
            environment = dict(os.environ)
            environment.update({"CO11_HOOK_MODE": "gated", "CO11_DATA": str(root / "data")})
            outputs = []
            for path, start, end in ((low, 1, 2), (high, 2, 3)):
                event = {
                    "tool_name": "Bash", "cwd": str(root),
                    "tool_input": {"command": f"sed -n '{start},{end}p' {path}"},
                    "tool_response": {"output": path.read_text() + ("# raw-only padding\n" * 2400)},
                }
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / "hook_probe.py")], input=json.dumps(event),
                    text=True, capture_output=True, env=environment, check=False,
                )
                self.assertEqual(result.returncode, 0)
                outputs.append(result.stdout)
            records = [json.loads(line) for line in (root / "data" / "hook-probe.jsonl").read_text().splitlines()]
        self.assertIn('"decision":"block"', outputs[0])
        self.assertNotIn("raw-only padding", outputs[0])
        self.assertEqual(outputs[1], "")
        self.assertTrue(records[0]["activate_slice"])
        self.assertEqual(records[1]["reason"], "external_dependency_risk")


if __name__ == "__main__":
    unittest.main()
