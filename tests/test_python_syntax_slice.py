from __future__ import annotations

import importlib.util
import sys
import tempfile
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


slicer = load_module("python_syntax_slice_tests", ROOT / "scripts" / "python_syntax_slice.py")
optimizer = load_module("context_optimizer_hook_co1_tests", ROOT / "scripts" / "context_optimizer_hook.py")


SOURCE = '''from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from framework import decorate

UNRELATED = "do not include this region"


@decorate("worker")
async def worker(
    callback: Callable[[str], Awaitable[int]],
    retries: int = 2,
) -> Awaitable[int]:
    """Run every callback attempt."""
    total = 0
    for attempt in range(retries):
        total += await callback(str(attempt))
    return total


class Service(BaseService):
    """Service docs outside a method slice."""

    @decorate("run")
    def run(self, value: str = "x") -> str:
        """Return a complete transformed value."""
        prepared = value.strip()
        if not prepared:
            return "empty"
        return prepared.upper()

    async def stop(self) -> None:
        await self.close()


def tail() -> str:
    return os.getcwd()
'''


def line_of(text: str, needle: str) -> int:
    return next(index for index, line in enumerate(text.splitlines(), start=1) if needle in line)


def hook_event(command: str, output: str, cwd: str) -> dict[str, object]:
    return {
        "session_id": "co1-session",
        "turn_id": "co1-turn",
        "tool_use_id": "co1-tool",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"output": output},
        "cwd": cwd,
    }


class PythonSyntaxSliceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.path = self.root / "large.py"
        self.path.write_text(SOURCE, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_async_function_preserves_complete_unit_and_direct_support_imports(self) -> None:
        result = slicer.build_slice(self.path, symbol="worker", budget_chars=8000)
        self.assertIsNotNone(result.replacement)
        replacement = result.replacement or ""
        self.assertIn("from __future__ import annotations", replacement)
        self.assertIn("from collections.abc import Awaitable, Callable", replacement)
        self.assertIn("from framework import decorate", replacement)
        self.assertNotIn("import os", replacement)
        self.assertIn('@decorate("worker")', replacement)
        self.assertIn('"""Run every callback attempt."""', replacement)
        self.assertIn("total += await callback", replacement)
        self.assertIn("return total", replacement)
        self.assertNotIn("UNRELATED =", replacement)
        self.assertEqual(result.metadata["syntax_kind"], "async_function")

    def test_method_includes_class_header_and_complete_body_not_sibling(self) -> None:
        result = slicer.build_slice(self.path, symbol="Service.run", budget_chars=8000)
        replacement = result.replacement or ""
        self.assertIn("class Service(BaseService):", replacement)
        self.assertIn('@decorate("run")', replacement)
        self.assertIn('"""Return a complete transformed value."""', replacement)
        self.assertIn("return prepared.upper()", replacement)
        self.assertNotIn("async def stop", replacement)
        self.assertNotIn("Service docs outside", replacement)
        self.assertEqual(result.metadata["syntax_enclosing_class"], "Service")

    def test_class_and_async_method_are_supported(self) -> None:
        class_result = slicer.build_slice(self.path, symbol="Service", budget_chars=8000)
        method_result = slicer.build_slice(self.path, symbol="Service.stop", budget_chars=8000)
        self.assertIn("async def stop", class_result.replacement or "")
        self.assertIn("await self.close()", method_result.replacement or "")
        self.assertEqual(class_result.metadata["syntax_kind"], "class")
        self.assertEqual(method_result.metadata["syntax_kind"], "async_method")

    def test_unique_sed_range_selects_method_and_cross_sibling_range_is_ambiguous(self) -> None:
        run_line = line_of(SOURCE, "prepared =")
        stop_line = line_of(SOURCE, "async def stop")
        selected = slicer.build_slice(self.path, start_line=run_line, end_line=run_line + 1, budget_chars=8000)
        ambiguous = slicer.build_slice(
            self.path,
            start_line=line_of(SOURCE, "def run"),
            end_line=stop_line,
            budget_chars=8000,
        )
        self.assertEqual(selected.metadata["syntax_symbol"], "Service.run")
        self.assertIsNone(ambiguous.replacement)
        self.assertEqual(ambiguous.reason, "syntax_range_ambiguous")

    def test_duplicate_bare_symbol_parse_error_and_over_budget_fail_open(self) -> None:
        duplicate = self.root / "duplicate.py"
        duplicate.write_text("class A:\n    def run(self):\n        pass\nclass B:\n    def run(self):\n        pass\n", encoding="utf-8")
        broken = self.root / "broken.py"
        broken.write_text("def broken(:\n", encoding="utf-8")
        ambiguous = slicer.build_slice(duplicate, symbol="run", budget_chars=8000)
        syntax_error = slicer.build_slice(broken, symbol="broken", budget_chars=8000)
        over_budget = slicer.build_slice(self.path, symbol="Service", budget_chars=256)
        self.assertEqual(ambiguous.reason, "syntax_symbol_ambiguous")
        self.assertEqual(syntax_error.reason, "syntax_parse_error")
        self.assertEqual(over_budget.reason, "syntax_slice_over_budget")
        self.assertGreater(over_budget.metadata["syntax_required_chars"], 256)
        self.assertIsNone(ambiguous.replacement)
        self.assertIsNone(syntax_error.replacement)
        self.assertIsNone(over_budget.replacement)

    def test_hook_known_symbol_replaces_large_raw_payload_with_syntax_package(self) -> None:
        raw = "raw canary should disappear\n" + ("filler\n" * 2000)
        command = f"python3 scripts/smart_read.py {self.path} --symbol Service.run --budget 900"
        record, decision = optimizer.evaluate_event(
            hook_event(command, raw, str(self.root)),
            mode="enforce",
            min_chars=128,
            syntax_mode="enforce",
            syntax_budget_chars=8000,
        )
        self.assertEqual(record["status"], "optimized")
        self.assertEqual(record["optimizer_strategy"], "python_syntax_slice")
        self.assertEqual(record["syntax_symbol"], "Service.run")
        self.assertEqual(decision["decision"], "block")
        self.assertIn("complete_syntax_unit: true", decision["reason"])
        self.assertNotIn("raw canary should disappear", decision["reason"])

    def test_hook_sed_ambiguity_and_over_budget_return_native(self) -> None:
        raw = "native output\n" + ("x" * 8000)
        start = line_of(SOURCE, "def run")
        end = line_of(SOURCE, "async def stop")
        ambiguous, ambiguous_decision = optimizer.evaluate_event(
            hook_event(f"sed -n '{start},{end}p' {self.path}", raw, str(self.root)),
            mode="enforce",
            min_chars=128,
            syntax_mode="enforce",
            syntax_budget_chars=8000,
        )
        over_budget, budget_decision = optimizer.evaluate_event(
            hook_event(
                f"sed -n '{line_of(SOURCE, 'prepared =')},{line_of(SOURCE, 'return prepared.upper')}p' {self.path}",
                raw,
                str(self.root),
            ),
            mode="enforce",
            min_chars=128,
            syntax_mode="enforce",
            syntax_budget_chars=256,
        )
        self.assertEqual(ambiguous["reason"], "syntax_range_ambiguous")
        self.assertIsNone(ambiguous_decision)
        self.assertEqual(over_budget["status"], "fallback_budget_or_timeout")
        self.assertEqual(over_budget["reason"], "syntax_slice_over_budget")
        self.assertIsNone(budget_decision)

    def test_bare_cat_does_not_trigger_syntax_guessing(self) -> None:
        raw = "first line\n" + ("large body\n" * 1000)
        record, decision = optimizer.evaluate_event(
            hook_event(f"cat {self.path}", raw, str(self.root)),
            mode="enforce",
            min_chars=128,
            visible_chars=512,
            syntax_mode="enforce",
        )
        self.assertEqual(record["status"], "optimized")
        self.assertNotIn("optimizer_strategy", record)
        self.assertIn("CO-0 optimized result", decision["reason"])


if __name__ == "__main__":
    unittest.main()
