from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


normalizer = load_module("acp_normalizer_attributor_tests", SCRIPTS / "acp_normalizer.py")
replay = load_module("replay_acp0_2_attributor_tests", SCRIPTS / "replay_acp0_2.py")
reporter = load_module("acp_reporter_attributor_tests", SCRIPTS / "acp_reporter.py")
attributor = load_module("acp_attributor_tests", SCRIPTS / "acp_attributor.py")


class AcpAttributorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        contract = json.loads((RESOURCES / "acp0_contract.json").read_text(encoding="utf-8"))
        cls.collector_hash = contract["acp0_1_collector_audit"]["collector_sha256"]
        cls.paired = json.loads((RESOURCES / "acp0_co1_4_replay_fixture.json").read_text(encoding="utf-8"))
        cls.synthetic = json.loads((RESOURCES / "acp0_2_synthetic_host_events.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((RESOURCES / "acp1_0_attribution_schema.json").read_text(encoding="utf-8"))

    def report(self, kind: str = "complete") -> dict:
        if kind == "complete":
            events, calls = replay.paired_inputs(self.paired)
            fixture_id = self.paired["fixture_id"]
        else:
            events, calls, _ = replay.synthetic_host_inputs(self.synthetic, collector_sha256=self.collector_hash)
            fixture_id = self.synthetic["fixture_id"]
            if kind == "ambiguous":
                target = calls[0]
                first = copy.deepcopy(target)
                second = copy.deepcopy(target)
                first["call_id"] = "d" * 64
                second["call_id"] = "e" * 64
                calls = [first, second, *calls[1:]]
        batch = normalizer.normalize_batch(events, calls, collector_sha256=self.collector_hash)
        ledger = normalizer.build_coverage_ledger(batch, calls, fixture_id=fixture_id)
        pipeline = {
            "schema_version": 1,
            "schema_id": normalizer.PIPELINE_SCHEMA_ID,
            "normalizer_version": normalizer.NORMALIZER_VERSION,
            "normalized_batch": batch,
            "coverage_ledger": ledger,
        }
        return reporter.build_fact_report(pipeline, top_limit=100)

    def test_complete_cost_map_matches_frozen_baseline(self) -> None:
        output = attributor.build_attribution(self.report())
        scope = output["scope_and_denominators"]
        concentration = output["top_calls_and_concentration"]
        self.assertEqual(scope["observed_calls"]["value"], 16)
        self.assertEqual(scope["observed_matched_model_visible_estimated_tokens"]["value"], 17651)
        self.assertEqual(concentration["eligible_call_count"], 16)
        self.assertEqual(concentration["top1_share"]["value"], 0.139085604215)
        self.assertEqual(concentration["top3_share"]["value"], 0.374596340151)
        self.assertEqual(concentration["top10_percent_share"]["value"], 0.257265877287)
        self.assertEqual(concentration["top20_percent_share"]["value"], 0.491926803014)
        self.assertEqual(concentration["tool_family_hhi"]["value"], 1.0)
        self.assertEqual(len(output["session_attribution"]), 12)
        self.assertTrue(all(row["status"] == "complete" for row in output["call_attribution"]))
        self.assertEqual(sum(row["attributed_visible_estimated_tokens"] for row in output["call_attribution"]), 17651)

    def test_partial_preserves_unattributed_and_unsupported_without_other_bucket(self) -> None:
        output = attributor.build_attribution(self.report("partial"))
        self.assertEqual(output["coverage_summary"]["status"], "partial")
        self.assertEqual(output["coverage_summary"]["unknown_estimated_model_visible_tokens"], 10)
        self.assertEqual(output["unknown_volume_and_reasons"]["estimated_model_visible_tokens"], 10)
        transcript_only = [row for row in output["call_attribution"] if row["row_kind"] == "transcript_only_call"]
        self.assertEqual(len(transcript_only), 1)
        self.assertEqual(transcript_only[0]["unattributed_visible_estimated_tokens"], 10)
        self.assertIsNone(transcript_only[0]["rank"])
        unknown_observed = [
            row for row in output["call_attribution"]
            if row["row_kind"] == "observed_event" and row["status"] == "unknown"
        ]
        self.assertEqual(len(unknown_observed), 1)
        self.assertIsNone(unknown_observed[0]["visible_token_share"])
        family = {row["tool_family"]: row for row in output["tool_family_attribution"]}
        self.assertNotIn("Other", family)
        self.assertEqual(family["other"]["visible_estimated_tokens"]["value"], 0)

    def test_unsupported_path_stays_unsupported_not_zero_cost_evidence(self) -> None:
        report = self.report("partial")
        row = next(
            row for row in report["drilldowns"]["tool_calls"]
            if row["row_kind"] == "observed_event" and row["linkage_status"] != "matched"
        )
        row["coverage_state"] = "unsupported_tool_path"
        output = attributor.build_attribution(report)
        unsupported = [row for row in output["call_attribution"] if row["status"] == "unsupported"]
        self.assertEqual(len(unsupported), 1)
        self.assertIsNone(unsupported[0]["attributed_visible_estimated_tokens"])
        self.assertIsNone(unsupported[0]["unattributed_visible_estimated_tokens"])
        self.assertIsNone(unsupported[0]["visible_token_share"])

    def test_ambiguous_linkage_is_not_selected_or_ranked(self) -> None:
        output = attributor.build_attribution(self.report("ambiguous"))
        ambiguous = [
            row for row in output["call_attribution"]
            if row["row_kind"] == "observed_event" and row["status"] == "unknown"
        ]
        self.assertTrue(ambiguous)
        self.assertTrue(all(row["rank"] is None for row in ambiguous))
        self.assertTrue(all(row["attributed_visible_estimated_tokens"] == 0 for row in ambiguous))
        self.assertGreater(output["unknown_volume_and_reasons"]["estimated_model_visible_tokens"], 10)

    def test_deterministic_read_only_and_canonical_hash(self) -> None:
        report = self.report()
        before = copy.deepcopy(report)
        first = attributor.build_attribution(report)
        second = attributor.build_attribution(copy.deepcopy(report))
        self.assertEqual(report, before)
        self.assertEqual(attributor.canonical_bytes(first), attributor.canonical_bytes(second))
        self.assertEqual(first["source_fact_report_sha256"], attributor.sha256(report))

    def test_repetition_volume_is_factual_and_does_not_claim_waste(self) -> None:
        output = attributor.build_attribution(self.report())
        exact = output["objective_repetition_facts"]["exact_payload_duplicate"]
        self.assertEqual(exact["relationship_count"], 2)
        self.assertGreater(exact["group_observation_visible_estimated_tokens"], 0)
        self.assertTrue(output["policy"]["repetition_does_not_imply_waste"])
        keys: list[str] = []

        def walk(value):
            if isinstance(value, dict):
                keys.extend(value)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(output)
        forbidden = {
            "wasted_tokens", "avoidable_tokens", "duplicate_read_ratio", "context_amplification",
            "optimization_opportunity", "recommendation", "replacement", "slicing",
        }
        self.assertTrue(forbidden.isdisjoint(keys))

    def test_engine_is_offline_and_does_not_import_online_or_correlation_code(self) -> None:
        source = (SCRIPTS / "acp_attributor.py").read_text(encoding="utf-8")
        self.assertNotIn("acp_collector", source)
        self.assertNotIn("correlate_events", source)
        self.assertNotIn("hooks.json", source)
        self.assertNotIn("tool_response", source)

    def test_output_schema_validates(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        jsonschema.Draft202012Validator.check_schema(self.schema)
        for kind in ("complete", "partial", "ambiguous"):
            jsonschema.validate(attributor.build_attribution(self.report(kind)), self.schema)


if __name__ == "__main__":
    unittest.main()
