from __future__ import annotations

import hashlib
import importlib.util
import json
import math
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


normalizer = load_module("acp_normalizer_acp1_contract", SCRIPTS / "acp_normalizer.py")
replay = load_module("replay_acp0_2_acp1_contract", SCRIPTS / "replay_acp0_2.py")
reporter = load_module("acp_reporter_acp1_contract", SCRIPTS / "acp_reporter.py")


class Acp10ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((RESOURCES / "acp0_contract.json").read_text(encoding="utf-8"))
        cls.dictionary = json.loads((RESOURCES / "acp1_0_semantic_dictionary.json").read_text(encoding="utf-8"))
        cls.schema = json.loads((RESOURCES / "acp1_0_attribution_schema.json").read_text(encoding="utf-8"))
        cls.fixture = json.loads((RESOURCES / "acp1_0_attribution_fixture.json").read_text(encoding="utf-8"))
        cls.collector_hash = cls.contract["acp0_1_collector_audit"]["collector_sha256"]

    def fact_report(self, case_id: str) -> dict:
        case = next(case for case in self.fixture["cases"] if case["case_id"] == case_id)
        source_fixture = json.loads((ROOT / case["input_path"]).read_text(encoding="utf-8"))
        if case_id == "co1_4_complete":
            events, calls = replay.paired_inputs(source_fixture)
            fixture_id = source_fixture["fixture_id"]
        else:
            events, calls, _ = replay.synthetic_host_inputs(source_fixture, collector_sha256=self.collector_hash)
            fixture_id = source_fixture["fixture_id"]
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

    def test_contract_identifiers_and_fact_only_boundaries_are_frozen(self) -> None:
        self.assertEqual(self.dictionary["schema_id"], "acp1-0-semantic-dictionary-v1")
        self.assertEqual(self.dictionary["output_schema_id"], "cost-attribution-baseline-v1")
        self.assertEqual(self.schema["$id"], "cost-attribution-baseline-v1")
        self.assertTrue(self.dictionary["cycle_policy"]["consume_existing_cycle_identity_only"])
        self.assertFalse(self.dictionary["cycle_policy"]["timestamp_inference"])
        self.assertFalse(self.dictionary["repetition_policy"]["necessity_or_actionability_inference"])
        self.assertTrue(self.dictionary["coverage_policy"]["unknown_is_valid"])
        policy = self.schema["properties"]["policy"]["properties"]
        self.assertEqual(policy["fact_only"]["const"], True)
        self.assertEqual(policy["online_effect"]["const"], False)
        self.assertEqual(policy["tool_visible_share_is_not_session_share"]["const"], True)

    def test_fixture_inputs_are_hash_anchored_and_privacy_safe(self) -> None:
        for case in self.fixture["cases"]:
            if "input_path" in case:
                digest = hashlib.sha256((ROOT / case["input_path"]).read_bytes()).hexdigest()
                self.assertEqual(digest, case["input_sha256"])
        self.assertTrue(all(value is False for value in self.fixture["privacy"].values()))
        serialized = json.dumps(self.fixture, ensure_ascii=False)
        self.assertNotIn("/Users/", serialized)
        for case in self.fixture["cases"]:
            self.assertNotIn("raw_session_id", case.get("input", {}))

    def test_complete_fixture_freezes_baseline_concentration_and_repetition(self) -> None:
        expected = self.fixture["cases"][0]["expected"]
        report = self.fact_report("co1_4_complete")
        visible = report["layers"]["model_visible_tool_context"]["estimated_model_visible_tokens"]
        calls = [
            row for row in report["drilldowns"]["tool_calls"]
            if row["estimated_model_visible_tokens"] is not None
        ]
        values = sorted((row["estimated_model_visible_tokens"] for row in calls), reverse=True)
        denominator = visible["value"]
        family_values = [row["matched_estimated_model_visible_tokens"] for row in report["drilldowns"]["tool_families"]]
        hhi = sum((value / denominator) ** 2 for value in family_values)

        self.assertEqual(report["report_scope"]["session_count"], expected["session_count"])
        self.assertEqual(len(calls), expected["observed_calls"])
        self.assertEqual(denominator, expected["observed_matched_model_visible_estimated_tokens"])
        self.assertEqual(visible["status"], expected["model_visible_token_coverage_status"])
        self.assertEqual(sum(values[:1]), expected["top1_tokens"])
        self.assertEqual(round(sum(values[:1]) / denominator, 12), expected["top1_share"])
        self.assertEqual(sum(values[:3]), expected["top3_tokens"])
        self.assertEqual(round(sum(values[:3]) / denominator, 12), expected["top3_share"])
        self.assertEqual(len(family_values), expected["tool_family_count"])
        self.assertEqual(round(hhi, 12), expected["tool_family_hhi"])
        self.assertEqual(
            report["duplicate_facts"]["exact_payload_duplicate"]["repeated_observation_count"],
            expected["exact_payload_repeated_observation_count"],
        )
        self.assertEqual(report["duplicate_facts"]["same_file_repeat"]["status"], "unknown")
        self.assertEqual(report["drilldowns"]["model_cycles"]["status"], "unknown")

    def test_partial_fixture_preserves_denominator_unknown_and_family_shares(self) -> None:
        case = next(case for case in self.fixture["cases"] if case["case_id"] == "synthetic_partial")
        expected = case["expected"]
        report = self.fact_report("synthetic_partial")
        coverage = report["drilldowns"]["evidence_coverage"]
        metric = coverage["metrics"]["model_visible_token_coverage"]
        families = {
            row["tool_family"]: row["matched_estimated_model_visible_tokens"]
            for row in report["drilldowns"]["tool_families"]
        }
        shares = {
            name: round(value / metric["numerator"], 12) if metric["numerator"] else 0.0
            for name, value in families.items()
        }
        self.assertEqual(metric["numerator"], expected["observed_matched_model_visible_estimated_tokens"])
        self.assertEqual(metric["denominator"], expected["model_visible_token_coverage_denominator"])
        self.assertEqual(metric["status"], expected["model_visible_token_coverage_status"])
        self.assertEqual(families, expected["tool_family_visible_tokens"])
        self.assertEqual(shares, expected["tool_family_visible_shares"])
        self.assertEqual(report["duplicate_facts"]["same_file_repeat"]["status"], "partial")
        self.assertEqual(report["duplicate_facts"]["range_overlap"]["status"], "partial")

    def test_ambiguous_and_unsupported_cases_forbid_inference(self) -> None:
        ambiguous = next(case for case in self.fixture["cases"] if case["case_id"] == "synthetic_ambiguous_linkage")
        unsupported = next(case for case in self.fixture["cases"] if case["case_id"] == "synthetic_unsupported_path")
        self.assertIsNone(ambiguous["input"]["estimated_model_visible_tokens"])
        self.assertEqual(ambiguous["expected"]["attributed_visible_tokens"], 0)
        self.assertTrue(ambiguous["expected"]["no_candidate_selection"])
        self.assertIsNone(unsupported["input"]["estimated_model_visible_tokens"])
        self.assertTrue(unsupported["expected"]["no_extrapolation"])

    def test_p90_nearest_rank_is_preregistered_before_engine_output(self) -> None:
        values = list(range(1, 11))
        rank = math.ceil(0.9 * len(values))
        self.assertEqual(values[rank - 1], 9)
        distribution = self.dictionary["metric_scope"]["distribution"]
        self.assertEqual(distribution["p90_formula"], "nearest_rank")
        self.assertEqual(distribution["p90_minimum_sample_count"], 10)

    def test_output_schema_is_valid_when_jsonschema_is_available(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        jsonschema.Draft202012Validator.check_schema(self.schema)


if __name__ == "__main__":
    unittest.main()
