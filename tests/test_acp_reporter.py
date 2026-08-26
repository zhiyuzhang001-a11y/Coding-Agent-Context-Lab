from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


normalizer = load_module("acp_normalizer_report_tests", SCRIPTS / "acp_normalizer.py")
replay = load_module("replay_acp0_2_report_tests", SCRIPTS / "replay_acp0_2.py")
reporter = load_module("acp_reporter_tests", SCRIPTS / "acp_reporter.py")


class AcpReporterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        resources = ROOT / "resources"
        cls.contract = json.loads((resources / "acp0_contract.json").read_text(encoding="utf-8"))
        cls.collector_sha256 = cls.contract["acp0_1_collector_audit"]["collector_sha256"]
        cls.paired_fixture = json.loads((resources / "acp0_co1_4_replay_fixture.json").read_text(encoding="utf-8"))
        cls.synthetic_fixture = json.loads((resources / "acp0_2_synthetic_host_events.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((resources / "acp0_3_fact_report_schema.json").read_text(encoding="utf-8"))

    def pipeline(self, synthetic: bool = False):
        if synthetic:
            source, calls, markers = replay.synthetic_host_inputs(
                self.synthetic_fixture, collector_sha256=self.collector_sha256,
            )
            fixture_id = self.synthetic_fixture["fixture_id"]
        else:
            source, calls = replay.paired_inputs(self.paired_fixture)
            markers = []
            fixture_id = self.paired_fixture["fixture_id"]
        batch = normalizer.normalize_batch(source, calls, collector_sha256=self.collector_sha256)
        ledger = normalizer.build_coverage_ledger(batch, calls, fixture_id=fixture_id)
        return {
            "schema_version": 1,
            "schema_id": normalizer.PIPELINE_SCHEMA_ID,
            "normalizer_version": normalizer.NORMALIZER_VERSION,
            "normalized_batch": batch,
            "coverage_ledger": ledger,
        }, markers

    def test_co1_4_report_reproduces_frozen_baseline(self) -> None:
        pipeline, _ = self.pipeline()
        report = reporter.build_fact_report(pipeline)
        self.assertEqual(report["report_scope"]["session_count"], 12)
        self.assertEqual(report["layers"]["session_level_cost"]["tool_calls"]["value"], 16)
        visible = report["layers"]["model_visible_tool_context"]["estimated_model_visible_tokens"]
        self.assertEqual(visible["value"], 17651)
        self.assertEqual(visible["status"], "complete")
        self.assertEqual(report["layers"]["observed_tool_result_cost"]["raw_output_chars"]["value"], 69831)
        self.assertEqual(report["layers"]["observed_tool_result_cost"]["estimated_raw_tokens"]["value"], 17465)

    def test_frozen_measurement_layers_and_unknown_cycle_boundaries(self) -> None:
        pipeline, _ = self.pipeline()
        report = reporter.build_fact_report(pipeline)
        self.assertEqual(set(report["layers"]), {
            "observed_tool_result_cost", "model_visible_tool_context", "session_level_cost", "profiler_cost",
        })
        self.assertIsNone(report["layers"]["session_level_cost"]["session_total_tokens"]["value"])
        self.assertEqual(report["layers"]["session_level_cost"]["model_cycles"]["status"], "unknown")
        self.assertEqual(report["drilldowns"]["model_cycles"]["cycles"], [])
        self.assertEqual(report["drilldowns"]["model_cycles"]["status"], "unknown")
        self.assertIsNone(report["layers"]["profiler_cost"]["local_duration_ms"]["value"])

    def test_report_is_deterministic_and_markdown_only_renders_report(self) -> None:
        pipeline, _ = self.pipeline()
        first = reporter.build_fact_report(pipeline)
        second = reporter.build_fact_report(copy.deepcopy(pipeline))
        self.assertEqual(reporter.render_json(first), reporter.render_json(second))
        self.assertEqual(reporter.render_markdown(first), reporter.render_markdown(second))
        self.assertIn("12 sessions", reporter.render_markdown(first))
        self.assertIn("17651 estimated_tokens [complete]", reporter.render_markdown(first))

    def test_traceability_and_input_hashes(self) -> None:
        pipeline, _ = self.pipeline()
        report = reporter.build_fact_report(pipeline)
        self.assertEqual(report["generated_from"]["normalized_batch_sha256"], reporter.sha256(pipeline["normalized_batch"]))
        self.assertEqual(report["generated_from"]["coverage_ledger_sha256"], reporter.sha256(pipeline["coverage_ledger"]))
        for layer in report["layers"].values():
            for item in layer.values():
                self.assertTrue(item["source_refs"])
                self.assertIn(item["status"], reporter.FACT_STATUSES)

    def test_no_recategorization_new_correlation_or_p90(self) -> None:
        pipeline, _ = self.pipeline()
        report = reporter.build_fact_report(pipeline)
        self.assertEqual([row["tool_family"] for row in report["drilldowns"]["tool_families"]], ["bash"])
        self.assertNotIn("p90", json.dumps(report))
        source = (SCRIPTS / "acp_reporter.py").read_text(encoding="utf-8")
        self.assertNotIn("correlate_events", source)
        self.assertNotIn("import acp_normalizer", source)
        self.assertTrue(report["report_policy"]["no_new_correlation"])

    def test_distributions_top_calls_and_duplicate_facts_are_factual(self) -> None:
        pipeline, _ = self.pipeline()
        report = reporter.build_fact_report(pipeline)
        distribution = report["drilldowns"]["distributions"]["matched_estimated_model_visible_tokens"]
        self.assertEqual(set(distribution), {"count", "min", "median", "max"})
        self.assertEqual(distribution["count"]["value"], 16)
        top = report["drilldowns"]["largest_calls"]["largest_matched_model_visible_calls"]
        self.assertEqual(top[0]["estimated_model_visible_tokens"], 2455)
        duplicates = report["duplicate_facts"]
        self.assertEqual(duplicates["exact_payload_duplicate"]["repeated_observation_count"], 2)
        self.assertEqual(duplicates["same_file_repeat"]["status"], "unknown")
        self.assertEqual(duplicates["range_overlap"]["status"], "unknown")
        self.assertIn("factual relationships only", duplicates["disclaimer"])

    def test_synthetic_partial_coverage_and_privacy_are_preserved(self) -> None:
        pipeline, markers = self.pipeline(synthetic=True)
        report = reporter.build_fact_report(pipeline)
        coverage = report["drilldowns"]["evidence_coverage"]
        self.assertEqual(coverage["counts"]["transcript_call_count"], 3)
        self.assertEqual(coverage["counts"]["normalized_event_count"], 3)
        self.assertEqual(coverage["counts"]["matched_event_count"], 2)
        self.assertEqual(coverage["metrics"]["model_visible_token_coverage"]["numerator"], 14)
        self.assertEqual(coverage["metrics"]["model_visible_token_coverage"]["denominator"], 24)
        rows = report["drilldowns"]["tool_calls"]
        self.assertEqual(sum(row["row_kind"] == "transcript_only_call" for row in rows), 1)
        rendered = reporter.render_json(report).decode() + reporter.render_markdown(report)
        for marker in markers:
            self.assertNotIn(marker, rendered)

    def test_fact_report_schema_validates(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        pipeline, _ = self.pipeline()
        report = reporter.build_fact_report(pipeline)
        jsonschema.Draft202012Validator.check_schema(self.schema)
        jsonschema.validate(report, self.schema)

    def test_report_has_no_interpretive_metric_keys(self) -> None:
        pipeline, _ = self.pipeline()
        report = reporter.build_fact_report(pipeline)
        keys: list[str] = []

        def walk(value):
            if isinstance(value, dict):
                keys.extend(value.keys())
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(report)
        forbidden = {
            "wasted_tokens", "avoidable_tokens", "duplicate_read_ratio", "context_amplification",
            "optimization_opportunity", "recommendation", "replacement", "slicing",
        }
        self.assertTrue(forbidden.isdisjoint(keys))


if __name__ == "__main__":
    unittest.main()
