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


normalizer = load_module("acp_normalizer_tests", SCRIPTS / "acp_normalizer.py")
replay = load_module("replay_acp0_2_tests", SCRIPTS / "replay_acp0_2.py")


class AcpNormalizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        resources = ROOT / "resources"
        cls.contract = json.loads((resources / "acp0_contract.json").read_text(encoding="utf-8"))
        cls.collector_sha256 = cls.contract["acp0_1_collector_audit"]["collector_sha256"]
        cls.paired_fixture = json.loads((resources / "acp0_co1_4_replay_fixture.json").read_text(encoding="utf-8"))
        cls.synthetic_fixture = json.loads((resources / "acp0_2_synthetic_host_events.json").read_text(encoding="utf-8"))
        cls.normalized_schema = json.loads((resources / "acp0_2_normalized_event_schema.json").read_text(encoding="utf-8"))
        cls.ledger_schema = json.loads((resources / "acp0_2_coverage_ledger_schema.json").read_text(encoding="utf-8"))
        cls.transcript_schema = json.loads((resources / "acp0_2_transcript_call_schema.json").read_text(encoding="utf-8"))
        cls.dictionary = json.loads((resources / "acp0_2_semantic_dictionary.json").read_text(encoding="utf-8"))

    def paired_pipeline(self):
        source, calls = replay.paired_inputs(self.paired_fixture)
        batch = normalizer.normalize_batch(source, calls, collector_sha256=self.collector_sha256)
        ledger = normalizer.build_coverage_ledger(batch, calls, fixture_id=self.paired_fixture["fixture_id"])
        return source, calls, batch, ledger

    def test_paired_replay_is_byte_stable_and_reproduces_frozen_baseline(self) -> None:
        source, calls = replay.paired_inputs(self.paired_fixture)
        first = replay.render_pipeline(
            source, calls, collector_sha256=self.collector_sha256,
            fixture_id=self.paired_fixture["fixture_id"],
        )
        second = replay.render_pipeline(
            source, calls, collector_sha256=self.collector_sha256,
            fixture_id=self.paired_fixture["fixture_id"],
        )
        self.assertEqual(first, second)
        result = json.loads(first)
        self.assertEqual(result["schema_id"], "acp0-2-pipeline-v1")
        self.assertEqual(result["normalizer_version"], "acp-normalizer-v0.1")
        ledger = result["coverage_ledger"]
        self.assertEqual(ledger["counts"]["normalized_event_count"], 16)
        self.assertEqual(ledger["counts"]["matched_event_count"], 16)
        self.assertEqual(ledger["metrics"]["session_coverage"]["numerator"], 12)
        self.assertEqual(ledger["metrics"]["session_coverage"]["denominator"], 12)
        self.assertEqual(ledger["metrics"]["call_coverage"]["numerator"], 16)
        self.assertEqual(ledger["metrics"]["call_coverage"]["denominator"], 16)
        self.assertEqual(ledger["metrics"]["model_visible_token_coverage"]["numerator"], 17651)
        self.assertEqual(ledger["metrics"]["model_visible_token_coverage"]["denominator"], 17651)
        self.assertTrue(all(metric["status"] == "complete" for metric in ledger["metrics"].values()))

    def test_normalized_events_match_closed_schema_and_semantic_dictionary(self) -> None:
        _, _, batch, ledger = self.paired_pipeline()
        required = set(self.normalized_schema["required"])
        dictionary_fields = set(self.dictionary["normalized_event_fields"])
        self.assertEqual(required, dictionary_fields)
        for event in batch["events"]:
            self.assertEqual(set(event), required)
            self.assertEqual(event["schema_id"], "normalized-event-v1")
            self.assertEqual(event["source_event_schema"], "acp-event-v1")
            self.assertEqual(event["normalizer_version"], "acp-normalizer-v0.1")
            self.assertEqual(event["collector_sha256"], self.collector_sha256)
            self.assertEqual(event["source_coverage_state"], "observed_not_matched")
        self.assertEqual(set(ledger), set(self.ledger_schema["required"]))

    def test_json_schemas_validate_paired_outputs(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        _, calls, batch, ledger = self.paired_pipeline()
        jsonschema.Draft202012Validator.check_schema(self.normalized_schema)
        jsonschema.Draft202012Validator.check_schema(self.ledger_schema)
        jsonschema.Draft202012Validator.check_schema(self.transcript_schema)
        for event in batch["events"]:
            jsonschema.validate(event, self.normalized_schema)
        for call in calls:
            jsonschema.validate(call, self.transcript_schema)
        jsonschema.validate(ledger, self.ledger_schema)

    def test_model_visible_fields_require_unique_transcript_linkage(self) -> None:
        source, calls = replay.paired_inputs(self.paired_fixture)
        event = source[0]
        first_call = copy.deepcopy(calls[0])
        second_call = copy.deepcopy(calls[0])
        first_call["call_id"] = "1" * 64
        second_call["call_id"] = "2" * 64
        batch = normalizer.normalize_batch([event], [first_call, second_call], collector_sha256=self.collector_sha256)
        normalized = batch["events"][0]
        self.assertEqual(normalized["linkage_status"], "ambiguous")
        self.assertEqual(normalized["linkage_reason"], "multiple_hash_family_candidates")
        self.assertIsNone(normalized["call_id"])
        self.assertIsNone(normalized["call_index"])
        self.assertIsNone(normalized["estimated_model_visible_tokens"])

    def test_stable_id_signal_mismatch_is_not_forced_into_a_match(self) -> None:
        source, calls = replay.paired_inputs(self.paired_fixture)
        call = copy.deepcopy(calls[0])
        call["output_sha256"] = "f" * 64
        batch = normalizer.normalize_batch([source[0]], [call], collector_sha256=self.collector_sha256)
        event = batch["events"][0]
        self.assertEqual(event["linkage_status"], "ambiguous")
        self.assertEqual(event["linkage_reason"], "stable_id_signal_mismatch")
        self.assertEqual(event["coverage_state"], "observed_not_matched")

    def test_bad_records_are_fingerprinted_and_do_not_break_the_batch(self) -> None:
        source, calls = replay.paired_inputs(self.paired_fixture)
        bad = copy.deepcopy(source[0])
        bad["raw_command"] = "PRIVATE COMMAND"
        original = copy.deepcopy(source[1])
        batch = normalizer.normalize_batch([bad, original], [calls[1]], collector_sha256=self.collector_sha256)
        self.assertEqual(len(batch["events"]), 1)
        self.assertEqual(len(batch["diagnostics"]), 1)
        diagnostic = batch["diagnostics"][0]
        self.assertEqual(set(diagnostic), {"input_kind", "input_index", "status", "reason", "source_fingerprint"})
        self.assertNotIn("PRIVATE COMMAND", json.dumps(diagnostic))
        self.assertEqual(source[1], original)

    def test_unknown_denominators_are_explicit(self) -> None:
        source, _ = replay.paired_inputs(self.paired_fixture)
        batch = normalizer.normalize_batch([source[0]], [], collector_sha256=self.collector_sha256)
        ledger = normalizer.build_coverage_ledger(batch, [])
        self.assertEqual(ledger["metrics"]["session_coverage"]["status"], "unknown_denominator")
        self.assertIsNone(ledger["metrics"]["session_coverage"]["ratio"])
        self.assertEqual(ledger["metrics"]["call_coverage"]["status"], "unknown_denominator")
        self.assertEqual(ledger["metrics"]["model_visible_token_coverage"]["status"], "unknown_denominator")
        self.assertEqual(ledger["metrics"]["linkage_coverage"]["status"], "partial")

    def test_synthetic_host_pipeline_is_private_deterministic_and_partial(self) -> None:
        source, calls, private_markers = replay.synthetic_host_inputs(
            self.synthetic_fixture, collector_sha256=self.collector_sha256,
        )
        first = replay.render_pipeline(
            source, calls, collector_sha256=self.collector_sha256,
            fixture_id=self.synthetic_fixture["fixture_id"],
        )
        second = replay.render_pipeline(
            source, calls, collector_sha256=self.collector_sha256,
            fixture_id=self.synthetic_fixture["fixture_id"],
        )
        self.assertEqual(first, second)
        rendered = first.decode("utf-8")
        for marker in private_markers:
            self.assertNotIn(marker, rendered)
        result = json.loads(first)
        ledger = result["coverage_ledger"]
        expected = self.synthetic_fixture["expected"]
        self.assertEqual(ledger["counts"]["normalized_event_count"], expected["collector_event_count"])
        self.assertEqual(ledger["counts"]["matched_event_count"], expected["matched_event_count"])
        self.assertEqual(ledger["counts"]["transcript_only_call_count"], expected["transcript_only_call_count"])
        self.assertEqual(ledger["metrics"]["call_coverage"]["status"], expected["call_coverage_status"])
        self.assertEqual(ledger["metrics"]["linkage_coverage"]["status"], expected["linkage_coverage_status"])
        self.assertEqual(ledger["unknown"]["estimated_model_visible_tokens"], 10)

    def test_outputs_contain_no_interpretation_or_optimization_metrics(self) -> None:
        _, _, batch, ledger = self.paired_pipeline()
        rendered = json.dumps({"batch": batch, "ledger": ledger}, ensure_ascii=False).lower()
        forbidden = (
            "duplicate_read_ratio", "wasted_tokens", "avoidable_tokens", "optimization_score",
            "optimization_opportunity", "recommendation", "replacement", "slicing",
        )
        for term in forbidden:
            self.assertNotIn(term, rendered)

    def test_coverage_metrics_always_name_denominator_provenance(self) -> None:
        _, _, _, ledger = self.paired_pipeline()
        for metric in ledger["metrics"].values():
            self.assertIn(metric["status"], {"complete", "partial", "unknown_denominator", "unsupported"})
            self.assertTrue(metric["denominator_source"])
            if metric["status"] == "unknown_denominator":
                self.assertIsNone(metric["ratio"])


if __name__ == "__main__":
    unittest.main()
