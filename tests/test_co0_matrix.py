from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


matrix = load_module("run_co0_matrix", SCRIPTS / "run_co0_matrix.py")


def result(
    *,
    correct: bool = True,
    visible: int = 100,
    total: int = 1000,
    retries: int = 0,
    replacement: bool = True,
    canary: bool = False,
    code_mode: bool = False,
) -> dict:
    return {
        "status": "completed",
        "correct": correct,
        "transcript_available": True,
        "replacement_visible": replacement,
        "canary_visible": canary,
        "code_mode_used": code_mode,
        "model_visible_tool_output_tokens": visible,
        "same_intent_retries": retries,
        "compensation_tool_calls": retries,
        "usage": {"total_tokens": total},
        "model_visible_tool_output_sha256": "same",
    }


class Co0MatrixTests(unittest.TestCase):
    def test_interface_summary_requires_supported_code_mode_and_passthrough_equality(self) -> None:
        results = {(name, "co"): result() for name in matrix.SUPPORTED_NAMES}
        results[("code_mode", "co")] = result(code_mode=True)
        results[("passthrough", "native")] = result(replacement=False, canary=True)
        results[("passthrough", "co")] = result(replacement=False, canary=True)
        results[("fail_open", "co")] = {
            **result(replacement=False, canary=True),
            "optimizer_statuses": ["fallback_optimizer_error"],
        }
        self.assertEqual(matrix.interface_summary(results)["status"], "passed")
        results[("code_mode", "co")]["code_mode_used"] = False
        self.assertEqual(matrix.interface_summary(results)["status"], "failed")

    def test_economic_summary_counts_retries_inside_co_visible_total_once(self) -> None:
        results = {}
        for name in matrix.SUPPORTED_NAMES:
            results[(name, "native")] = result(visible=300, total=1200)
            results[(name, "co")] = result(visible=100, total=900, retries=1)
        summary = matrix.economic_summary(results)
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["aggregate_net_visible_context_saving"], 800)
        self.assertEqual(summary["median_same_intent_retries"], 1)
        self.assertEqual(summary["median_co_native_total_ratio"], 0.75)

    def test_economic_summary_rejects_visible_saving_with_full_session_regression(self) -> None:
        results = {}
        for name in matrix.SUPPORTED_NAMES:
            results[(name, "native")] = result(visible=300, total=1000)
            results[(name, "co")] = result(visible=100, total=1300)
        summary = matrix.economic_summary(results)
        self.assertEqual(summary["status"], "failed")
        self.assertTrue(summary["checks"]["aggregate_net_visible_saving_positive"])
        self.assertFalse(summary["checks"]["median_total_ratio_at_most_one"])


if __name__ == "__main__":
    unittest.main()
