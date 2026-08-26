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

import acp_hypothesis_catalog as engine  # noqa: E402
import acp_hypothesis_renderer as renderer  # noqa: E402


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def inputs(
    calls: list[tuple[str, int, float]],
    *,
    denominator: int = 10000,
    call_hhi: float = 0.1,
    top3_share: float = 0.3,
    repeated: list[tuple[str, int, list[str]]] | None = None,
) -> tuple[dict, dict]:
    rows = [
        {
            "call_id": digest(label), "status": "complete", "rank": index,
            "attributed_visible_estimated_tokens": tokens, "visible_token_share": share,
        }
        for index, (label, tokens, share) in enumerate(calls, start=1)
    ]
    top_calls = [
        {"call_id": row["call_id"], "visible_estimated_tokens": row["attributed_visible_estimated_tokens"]}
        for row in rows[:3]
    ]
    attribution = {
        "schema_version": 1,
        "schema_id": "cost-attribution-baseline-v1",
        "scope_and_denominators": {"observed_matched_model_visible_estimated_tokens": {"value": denominator}},
        "coverage_summary": {"status": "complete"},
        "call_attribution": rows,
        "top_calls_and_concentration": {
            "call_hhi": {"value": call_hhi}, "top3_share": {"value": top3_share}, "top_calls": top_calls,
        },
        "policy": {"fact_only": True, "online_effect": False},
    }
    repeated_rows = []
    for label, relation_count, relation_types in repeated or []:
        call = next(row for row in rows if row["call_id"] == digest(label))
        repeated_rows.append({
            "call_id": call["call_id"],
            "visible_estimated_tokens": call["attributed_visible_estimated_tokens"],
            "relation_count": relation_count,
            "relation_types": relation_types,
            "relation_ids": [digest(f"{label}-relation-{index}") for index in range(relation_count)],
            "counted_once": True,
        })
    repetition = {
        "schema_version": 1,
        "schema_id": "repeated-evidence-analysis-v1",
        "source_and_scope": {"relation_scope": "within_session", "attribution_sha256": engine.sha256(attribution)},
        "observation_volume": {"denominator_visible_estimated_tokens": denominator},
        "unique_repeated_observations": repeated_rows,
        "unknowns": {},
        "policy": {"fact_only": True, "no_diagnosis": True},
    }
    return attribution, repetition


class AcpHypothesisCatalogTests(unittest.TestCase):
    def test_frozen_baseline_generates_five_high_cost_candidates_only(self) -> None:
        attribution = json.loads((RESOURCES / "acp1_0_frozen_attribution.json").read_text(encoding="utf-8"))
        repetition = json.loads((RESOURCES / "acp1_1_frozen_analysis.json").read_text(encoding="utf-8"))
        result = engine.build_catalog(attribution, repetition)
        summary = result["candidate_summary"]
        self.assertEqual(summary["candidate_count"], 5)
        self.assertEqual(summary["candidate_type_counts"], {
            "high_cost_call_candidate": 5,
            "cost_concentration_candidate": 0,
            "repeated_or_overlapping_evidence_candidate": 0,
        })
        self.assertEqual(summary["unique_target_observed_exposure_tokens"], 10735)
        self.assertEqual(summary["unique_target_observed_share"], 0.608180839612)
        self.assertTrue(all(row["necessity_status"] == "unknown" for row in result["hypothesis_candidates"]))
        self.assertTrue(all(row["causal_status"] == "untested" for row in result["hypothesis_candidates"]))

    def test_high_cost_thresholds_are_inclusive_and_below_values_do_not_trigger(self) -> None:
        attribution, repetition = inputs([
            ("boundary", 1000, 0.1),
            ("below-share", 2000, 0.099999999999),
            ("below-tokens", 999, 0.2),
        ])
        result = engine.build_catalog(attribution, repetition)
        high = [row for row in result["hypothesis_candidates"] if row["hypothesis_type"] == "high_cost_call_candidate"]
        self.assertEqual([row["target_call_ids"] for row in high], [[digest("boundary")]])

    def test_high_cost_cap_is_five_and_order_uses_frozen_rank(self) -> None:
        calls = [(f"call-{index}", 2000 - index, 0.11) for index in range(7)]
        attribution, repetition = inputs(calls, denominator=20000)
        result = engine.build_catalog(attribution, repetition)
        high = [row for row in result["hypothesis_candidates"] if row["hypothesis_type"] == "high_cost_call_candidate"]
        self.assertEqual(len(high), 5)
        self.assertEqual({row["target_call_ids"][0] for row in high}, {digest(f"call-{index}") for index in range(5)})

    def test_concentration_thresholds_are_inclusive_and_not_verdicts(self) -> None:
        for call_hhi, top3_share in ((0.18, 0.2), (0.1, 0.6)):
            attribution, repetition = inputs([("a", 400, 0.4), ("b", 300, 0.3), ("c", 300, 0.3)], denominator=1000, call_hhi=call_hhi, top3_share=top3_share)
            result = engine.build_catalog(attribution, repetition)
            concentration = [row for row in result["hypothesis_candidates"] if row["hypothesis_type"] == "cost_concentration_candidate"]
            self.assertEqual(len(concentration), 1)
            self.assertEqual(concentration[0]["necessity_status"], "unknown")
        attribution, repetition = inputs([("a", 400, 0.4)], call_hhi=0.179999999999, top3_share=0.599999999999)
        result = engine.build_catalog(attribution, repetition)
        self.assertFalse(any(row["hypothesis_type"] == "cost_concentration_candidate" for row in result["hypothesis_candidates"]))

    def test_one_repeated_later_call_with_three_relations_creates_one_candidate(self) -> None:
        attribution, repetition = inputs(
            [("repeat", 500, 0.05)],
            repeated=[("repeat", 3, ["exact_payload_repeat", "exact_range_repeat", "same_path_repeat"])],
        )
        result = engine.build_catalog(attribution, repetition)
        repeated = [row for row in result["hypothesis_candidates"] if row["hypothesis_type"] == "repeated_or_overlapping_evidence_candidate"]
        self.assertEqual(len(repeated), 1)
        self.assertEqual(repeated[0]["observed_exposure_tokens"], 500)
        self.assertEqual(result["candidate_summary"]["unique_target_observed_exposure_tokens"], 500)

    def test_empty_catalog_is_valid_and_does_not_lower_thresholds(self) -> None:
        attribution, repetition = inputs([("small", 500, 0.05)], call_hhi=0.01, top3_share=0.05)
        result = engine.build_catalog(attribution, repetition)
        self.assertEqual(result["catalog_status"], "empty_no_preregistered_trigger")
        self.assertEqual(result["hypothesis_candidates"], [])
        self.assertEqual(result["unknowns"]["candidate_validation_feasibility"], "not_applicable_no_candidates")

    def test_candidates_are_blocked_not_silently_treated_as_false(self) -> None:
        attribution, repetition = inputs([("boundary", 1000, 0.1)])
        result = engine.build_catalog(attribution, repetition)
        row = result["hypothesis_candidates"][0]
        self.assertEqual(row["validation_feasibility"], {
            "status": "blocked",
            "reason_codes": ["missing_controlled_intervention_interface", "missing_replayable_task_context"],
        })
        self.assertEqual(row["necessity_status"], "unknown")
        self.assertEqual(row["causal_status"], "untested")

    def test_generator_is_deterministic_read_only_offline_and_schema_valid(self) -> None:
        attribution, repetition = inputs([("boundary", 1000, 0.1)])
        originals = copy.deepcopy((attribution, repetition))
        first = engine.build_catalog(attribution, repetition)
        second = engine.build_catalog(attribution, repetition)
        self.assertEqual(engine.canonical_bytes(first), engine.canonical_bytes(second))
        self.assertEqual((attribution, repetition), originals)
        source = (SCRIPTS / "acp_hypothesis_catalog.py").read_text(encoding="utf-8")
        self.assertNotIn("acp_collector", source)
        self.assertNotIn("subprocess", source)
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        schema = json.loads((RESOURCES / "acp1_2_hypothesis_catalog_schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(first, schema)

    def test_renderer_only_presents_catalog_and_no_intervention_or_estimate(self) -> None:
        attribution, repetition = inputs([("boundary", 1000, 0.1)])
        result = engine.build_catalog(attribution, repetition)
        markdown = renderer.render_markdown(result)
        text = renderer.render_text(result)
        self.assertIn("Candidate count: 1", markdown)
        self.assertIn("necessity_status=unknown", text)
        serialized = json.dumps(result, sort_keys=True).lower() + markdown.lower() + text.lower()
        for forbidden in ("wasted_tokens", "avoidable_tokens", "potential_savings", "savings_ratio"):
            self.assertNotIn(forbidden, serialized)
        source = (SCRIPTS / "acp_hypothesis_renderer.py").read_text(encoding="utf-8")
        self.assertNotIn("import acp_hypothesis_catalog", source)

    def test_source_hash_or_denominator_mismatch_is_rejected(self) -> None:
        attribution, repetition = inputs([("boundary", 1000, 0.1)])
        repetition["source_and_scope"]["attribution_sha256"] = "0" * 64
        with self.assertRaises(engine.HypothesisError):
            engine.build_catalog(attribution, repetition)


if __name__ == "__main__":
    unittest.main()
