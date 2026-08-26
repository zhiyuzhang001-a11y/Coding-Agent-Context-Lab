from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


attributor_tests = load_module("acp_attributor_fixture_for_renderer", TESTS / "test_acp_attributor.py")
renderer = load_module("acp_attribution_renderer_tests", SCRIPTS / "acp_attribution_renderer.py")


class AcpAttributionRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        attributor_tests.AcpAttributorTests.setUpClass()
        cls.fixture = attributor_tests.AcpAttributorTests()

    def attribution(self, kind: str = "complete") -> dict:
        report = self.fixture.report(kind)
        return attributor_tests.attributor.build_attribution(report)

    def test_markdown_has_required_cost_map_sections_and_traceability(self) -> None:
        data = self.attribution()
        output = renderer.render_markdown(data)
        for heading in (
            "Session Summary", "Cost Concentration", "Tool-family Map", "Top Calls",
            "Repetition Facts", "Coverage / Unknown", "Traceability",
        ):
            self.assertIn(heading, output)
        self.assertIn(data["schema_id"], output)
        self.assertIn(data["generator_version"], output)
        self.assertIn(renderer.attribution_sha256(data), output)
        self.assertIn(data["source_fact_report_sha256"], output)
        self.assertIn("0.139085604215", output)
        self.assertIn("5288", output)

    def test_cli_text_is_compact_and_uses_existing_canonical_values(self) -> None:
        data = self.attribution()
        data["top_calls_and_concentration"]["top1_share"]["value"] = 0.123456789012
        output = renderer.render_text(data)
        self.assertIn("top1_share=0.123456789012", output)
        self.assertIn("unknown_visible_estimated_tokens=0", output)
        self.assertIn("call_hhi=0.100553287061", output)
        self.assertIn(renderer.attribution_sha256(data), output)

    def test_json_remains_the_canonical_fact_source(self) -> None:
        data = self.attribution()
        before = copy.deepcopy(data)
        rendered = renderer.render_json(data)
        self.assertEqual(json.loads(rendered), data)
        self.assertEqual(data, before)
        self.assertEqual(rendered, renderer.canonical_bytes(data))

    def test_same_input_has_deterministic_markdown_text_and_json(self) -> None:
        data = self.attribution()
        clone = copy.deepcopy(data)
        self.assertEqual(renderer.render_markdown(data), renderer.render_markdown(clone))
        self.assertEqual(renderer.render_text(data), renderer.render_text(clone))
        self.assertEqual(renderer.render_json(data), renderer.render_json(clone))

    def test_partial_unknown_and_unsupported_are_rendered_without_coercion(self) -> None:
        partial = self.attribution("partial")
        markdown = renderer.render_markdown(partial)
        text = renderer.render_text(partial)
        self.assertIn("Unknown visible estimated tokens: 10", markdown)
        self.assertIn("transcript_only", markdown)
        self.assertIn("unattributed_tokens=10", text)

        unsupported = copy.deepcopy(partial)
        call = next(row for row in unsupported["call_attribution"] if row["status"] == "unknown")
        call["coverage_state"] = "unsupported_tool_path"
        call["status"] = "unsupported"
        call["attributed_visible_estimated_tokens"] = None
        call["unattributed_visible_estimated_tokens"] = None
        markdown = renderer.render_markdown(unsupported)
        self.assertIn("unsupported_tool_path", markdown)
        self.assertIn("unknown | unknown | unsupported", markdown)

    def test_renderer_outputs_no_diagnosis_language(self) -> None:
        data = self.attribution()
        outputs = (renderer.render_markdown(data).lower(), renderer.render_text(data).lower())
        for output in outputs:
            for forbidden in ("waste", "avoidable", "optimization", "recommendation", "potential savings"):
                self.assertNotIn(forbidden, output)

    def test_source_purity_and_no_analytical_dependencies(self) -> None:
        source = (SCRIPTS / "acp_attribution_renderer.py").read_text(encoding="utf-8")
        for forbidden in (
            "acp_collector", "acp_normalizer", "acp_reporter", "correlate_events",
            "statistics", "import math", "tool_response", "normalized_event",
        ):
            self.assertNotIn(forbidden, source)
        with self.assertRaises(renderer.RenderError):
            renderer.render_markdown({"schema_id": "fact-report-v1"})


if __name__ == "__main__":
    unittest.main()
