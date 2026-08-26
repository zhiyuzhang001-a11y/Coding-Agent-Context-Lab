from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "resources"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import acp_repeated_evidence as engine  # noqa: E402
import acp_repeated_evidence_renderer as renderer  # noqa: E402


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def fixture_inputs() -> tuple[dict, dict, dict, dict]:
    fixture = json.loads((RESOURCES / "acp1_1_relation_fixture.json").read_text(encoding="utf-8"))
    events = []
    calls = []
    for item in fixture["events"]:
        call_id = digest(item["call"])
        path_hashes = [] if item["path"] is None else [digest(item["path"])]
        ranges = []
        if item["range"] is not None:
            ranges = [{
                "path_hash": digest(item["path"]),
                "start_line": item["range"][0],
                "end_line": item["range"][1],
            }]
        linkage = item.get("linkage_status", "matched")
        event = {
            "event_id": call_id,
            "call_id": call_id,
            "call_index": item["index"],
            "session_id_hash": digest(item["session"]),
            "linkage_status": linkage,
            "estimated_model_visible_tokens": item["tokens"],
            "output_sha256": digest(item["payload"]),
            "path_hashes": path_hashes,
            "explicit_ranges": ranges,
            "coverage_state": item.get("coverage_state", "observed_and_matched"),
            "tool_family": "read",
        }
        events.append(event)
        if linkage == "matched" and item["tokens"] is not None:
            calls.append({
                "call_id": call_id,
                "status": "complete",
                "attributed_visible_estimated_tokens": item["tokens"],
            })
    denominator = sum(item["tokens"] or 0 for item in fixture["events"] if item.get("linkage_status", "matched") == "matched")
    batch = {"schema_version": 1, "schema_id": "normalized-batch-v1", "events": events}
    ledger = {"schema_version": 1, "schema_id": "coverage-ledger-v1", "unknown": {}}
    attribution = {
        "schema_version": 1,
        "schema_id": "cost-attribution-baseline-v1",
        "scope_and_denominators": {
            "observed_matched_model_visible_estimated_tokens": {"value": denominator},
        },
        "coverage_summary": {"status": "partial"},
        "call_attribution": calls,
        "policy": {"fact_only": True, "online_effect": False},
    }
    return fixture, batch, ledger, attribution


class AcpRepeatedEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture, self.batch, self.ledger, self.attribution = fixture_inputs()

    def analysis(self) -> dict:
        return engine.build_analysis(self.batch, self.ledger, self.attribution)

    def test_contract_fixture_freezes_relation_and_unique_volume_counts(self) -> None:
        result = self.analysis()
        expected = self.fixture["expected"]
        volume = result["observation_volume"]
        self.assertEqual(result["denominator_and_coverage"]["eligible_observed_call_count"], expected["eligible_observed_call_count"])
        self.assertEqual(volume["denominator_visible_estimated_tokens"], expected["eligible_observed_visible_estimated_tokens"])
        self.assertEqual(volume["relation_count"], expected["relation_count"])
        self.assertEqual(volume["relation_type_counts"], expected["relation_type_counts"])
        self.assertEqual(volume["unique_repeated_observation_count"], expected["unique_repeated_observation_count"])
        self.assertEqual(volume["unique_repeated_observation_tokens"], expected["unique_repeated_observation_tokens"])
        self.assertEqual(volume["repeated_observation_share"], expected["repeated_observation_share"])

    def test_multiple_relation_types_count_later_tokens_once(self) -> None:
        result = self.analysis()
        call_id = digest(self.fixture["expected"]["multi_relation_later_call"])
        row = next(row for row in result["unique_repeated_observations"] if row["call_id"] == call_id)
        self.assertEqual(row["relation_count"], 3)
        self.assertEqual(row["relation_types"], ["exact_payload_repeat", "exact_range_repeat", "same_path_repeat"])
        self.assertEqual(row["visible_estimated_tokens"], 100)
        self.assertTrue(row["counted_once"])
        self.assertEqual(result["observation_volume"]["unique_repeated_observation_tokens"], 330)

    def test_same_path_same_range_changed_payload_keeps_content_unknown(self) -> None:
        result = self.analysis()
        later = digest(self.fixture["expected"]["same_range_changed_payload_later_call"])
        relations = [row for row in result["call_relations"] if row["later_call_id"] == later]
        self.assertEqual({row["relation_type"] for row in relations}, {"same_path_repeat", "exact_range_repeat"})
        self.assertTrue(all(row["observed_payload_equality"] is False for row in relations))
        self.assertTrue(all(row["content_stability"] == "unknown" for row in relations))

    def test_half_open_range_math_distinguishes_exact_contains_overlap_and_disjoint(self) -> None:
        result = self.analysis()
        types_by_later = {
            label: {row["relation_type"] for row in result["call_relations"] if row["later_call_id"] == digest(label)}
            for label in ("multi-1", "contains-1", "overlap-1", "disjoint-1")
        }
        self.assertIn("exact_range_repeat", types_by_later["multi-1"])
        self.assertIn("range_contains", types_by_later["contains-1"])
        self.assertIn("range_overlap", types_by_later["overlap-1"])
        self.assertEqual(types_by_later["disjoint-1"], {"same_path_repeat"})
        exact = next(row for row in result["call_relations"] if row["relation_type"] == "exact_range_repeat")
        self.assertEqual(exact["earlier_range"], {"start_line": 1, "end_line_exclusive": 11})

    def test_cross_session_payload_identity_never_creates_relation(self) -> None:
        result = self.analysis()
        cross_calls = {digest("cross-a-0"), digest("cross-b-0")}
        self.assertFalse(any(
            row["earlier_call_id"] in cross_calls or row["later_call_id"] in cross_calls
            for row in result["call_relations"]
        ))
        self.assertEqual(result["source_and_scope"]["relation_scope"], "within_session")
        self.assertFalse(result["source_and_scope"]["cross_session_relations_created"])

    def test_unknown_unsupported_and_cycle_states_are_preserved(self) -> None:
        result = self.analysis()
        self.assertEqual(result["unknowns"]["source_noneligible_call_count"], 1)
        self.assertEqual(result["unknowns"]["source_noneligible_reason_counts"], {"unsupported_tool_path": 1})
        self.assertEqual(result["unknowns"]["cycle_relation_state"], "unknown")
        self.assertEqual({row["cross_cycle"] for row in result["call_relations"]}, {"unknown"})

    def test_engine_is_deterministic_read_only_offline_and_schema_valid(self) -> None:
        originals = copy.deepcopy((self.batch, self.ledger, self.attribution))
        first = self.analysis()
        second = self.analysis()
        self.assertEqual(engine.canonical_bytes(first), engine.canonical_bytes(second))
        self.assertEqual((self.batch, self.ledger, self.attribution), originals)
        source = (SCRIPTS / "acp_repeated_evidence.py").read_text(encoding="utf-8")
        self.assertNotIn("acp_collector", source)
        self.assertNotIn("hooks", source.lower())
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        schema = json.loads((RESOURCES / "acp1_1_repeated_evidence_schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(first, schema)

    def test_renderer_only_presents_canonical_values_and_no_diagnosis(self) -> None:
        result = self.analysis()
        markdown = renderer.render_markdown(result)
        text = renderer.render_text(result)
        self.assertIn("Unique repeated observation tokens: 330", markdown)
        self.assertIn("unique_repeated_observation_tokens=330", text)
        self.assertIn("Relations: 11", markdown)
        serialized = json.dumps(result, sort_keys=True).lower() + markdown.lower() + text.lower()
        for forbidden in ("wasted_tokens", "avoidable_tokens", "potential_savings", "optimization_opportunity"):
            self.assertNotIn(forbidden, serialized)
        source = (SCRIPTS / "acp_repeated_evidence_renderer.py").read_text(encoding="utf-8")
        self.assertNotIn("import acp_repeated_evidence", source)

    def test_input_layer_mismatch_is_rejected(self) -> None:
        bad = copy.deepcopy(self.attribution)
        bad["scope_and_denominators"]["observed_matched_model_visible_estimated_tokens"]["value"] += 1
        with self.assertRaises(engine.RepeatedEvidenceError):
            engine.build_analysis(self.batch, self.ledger, bad)


if __name__ == "__main__":
    unittest.main()
