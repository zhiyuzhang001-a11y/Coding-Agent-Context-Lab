#!/usr/bin/env python3
"""Generate deterministic offline experiment candidates from frozen ACP facts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_ID = "cost-necessity-hypothesis-catalog-v1"
GENERATOR_VERSION = "acp-hypothesis-catalog-v0.1"
HIGH_COST_MIN_SHARE = 0.10
HIGH_COST_MIN_TOKENS = 1000
HIGH_COST_MAX_CANDIDATES = 5
CONCENTRATION_MIN_CALL_HHI = 0.18
CONCENTRATION_MIN_TOP3_SHARE = 0.60
REQUIRED_VALIDATION = [
    "construct_isolated_paired_task_replay",
    "apply_controlled_evidence_intervention_in_experimental_harness",
    "compare_correctness",
    "compare_tool_path_and_model_cycles",
    "estimate_delta_only_if_correctness_is_preserved",
]
BLOCKING_REASONS = ["missing_controlled_intervention_interface", "missing_replayable_task_context"]


class HypothesisError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _stable_id(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _ref(artifact: str, pointer: str) -> dict[str, str]:
    return {"artifact": artifact, "json_pointer": pointer}


def _validate_inputs(attribution: Any, repetition: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(attribution, dict) or attribution.get("schema_id") != "cost-attribution-baseline-v1":
        raise HypothesisError("input_must_be_cost_attribution_baseline_v1")
    if not isinstance(repetition, dict) or repetition.get("schema_id") != "repeated-evidence-analysis-v1":
        raise HypothesisError("input_must_be_repeated_evidence_analysis_v1")
    if not attribution.get("policy", {}).get("fact_only") or attribution.get("policy", {}).get("online_effect"):
        raise HypothesisError("attribution_policy_not_frozen")
    if not repetition.get("policy", {}).get("fact_only") or not repetition.get("policy", {}).get("no_diagnosis"):
        raise HypothesisError("repetition_policy_not_frozen")
    if repetition.get("source_and_scope", {}).get("relation_scope") != "within_session":
        raise HypothesisError("repetition_scope_not_frozen")
    if repetition["source_and_scope"].get("attribution_sha256") != sha256(attribution):
        raise HypothesisError("repetition_attribution_hash_mismatch")
    denominator = attribution.get("scope_and_denominators", {}).get(
        "observed_matched_model_visible_estimated_tokens", {}
    ).get("value")
    if not isinstance(denominator, int) or isinstance(denominator, bool) or denominator < 0:
        raise HypothesisError("invalid_attribution_denominator")
    if repetition.get("observation_volume", {}).get("denominator_visible_estimated_tokens") != denominator:
        raise HypothesisError("repetition_denominator_mismatch")
    return attribution, repetition


def _feasibility() -> dict[str, Any]:
    return {"status": "blocked", "reason_codes": list(BLOCKING_REASONS)}


def _candidate(
    hypothesis_type: str,
    target_scope: str,
    target_call_ids: list[str],
    observed_tokens: int,
    observed_share: float | None,
    factual_basis: dict[str, Any],
    source_refs: list[dict[str, str]],
) -> dict[str, Any]:
    identity = {
        "hypothesis_type": hypothesis_type,
        "target_scope": target_scope,
        "target_call_ids": sorted(target_call_ids),
        "factual_basis": factual_basis,
    }
    return {
        "hypothesis_id": _stable_id(identity),
        "hypothesis_type": hypothesis_type,
        "target_scope": target_scope,
        "target_call_ids": sorted(target_call_ids),
        "observed_exposure_tokens": observed_tokens,
        "observed_share": observed_share,
        "factual_basis": factual_basis,
        "necessity_status": "unknown",
        "causal_status": "untested",
        "candidate_status": "eligible_for_future_controlled_validation",
        "required_validation": list(REQUIRED_VALIDATION),
        "validation_feasibility": _feasibility(),
        "source_refs": source_refs,
    }


def build_catalog(attribution: Any, repetition: Any) -> dict[str, Any]:
    originals = copy.deepcopy((attribution, repetition))
    attribution, repetition = _validate_inputs(attribution, repetition)
    denominator = attribution["scope_and_denominators"]["observed_matched_model_visible_estimated_tokens"]["value"]
    complete_calls = {
        row["call_id"]: row for row in attribution.get("call_attribution", [])
        if row.get("status") == "complete"
        and isinstance(row.get("attributed_visible_estimated_tokens"), int)
        and isinstance(row.get("visible_token_share"), (int, float))
    }
    candidates: list[dict[str, Any]] = []

    high_cost = sorted(
        (
            row for row in complete_calls.values()
            if row["attributed_visible_estimated_tokens"] >= HIGH_COST_MIN_TOKENS
            and row["visible_token_share"] >= HIGH_COST_MIN_SHARE
        ),
        key=lambda row: (row.get("rank") is None, row.get("rank") or 0, row["call_id"]),
    )[:HIGH_COST_MAX_CANDIDATES]
    for row in high_cost:
        candidates.append(_candidate(
            "high_cost_call_candidate", "call", [row["call_id"]],
            row["attributed_visible_estimated_tokens"], row["visible_token_share"],
            {
                "basis_kind": "frozen_call_exposure_threshold",
                "call_rank": row.get("rank"),
                "min_observed_exposure_tokens": HIGH_COST_MIN_TOKENS,
                "min_visible_token_share": HIGH_COST_MIN_SHARE,
            },
            [_ref("attribution", "/call_attribution")],
        ))

    concentration = attribution["top_calls_and_concentration"]
    call_hhi = concentration["call_hhi"]["value"]
    top3_share = concentration["top3_share"]["value"]
    concentration_triggers = []
    if isinstance(call_hhi, (int, float)) and call_hhi >= CONCENTRATION_MIN_CALL_HHI:
        concentration_triggers.append("call_hhi_threshold")
    if isinstance(top3_share, (int, float)) and top3_share >= CONCENTRATION_MIN_TOP3_SHARE:
        concentration_triggers.append("top3_share_threshold")
    if concentration_triggers:
        top_calls = concentration.get("top_calls", [])[:3]
        target_ids = [row["call_id"] for row in top_calls]
        observed_tokens = sum(row["visible_estimated_tokens"] for row in top_calls)
        candidates.append(_candidate(
            "cost_concentration_candidate", "catalog", target_ids,
            observed_tokens, top3_share,
            {
                "basis_kind": "frozen_concentration_threshold",
                "call_hhi": call_hhi,
                "top3_share": top3_share,
                "triggered_conditions": concentration_triggers,
                "min_call_hhi": CONCENTRATION_MIN_CALL_HHI,
                "min_top3_share": CONCENTRATION_MIN_TOP3_SHARE,
            },
            [_ref("attribution", "/top_calls_and_concentration")],
        ))

    for row in repetition.get("unique_repeated_observations", []):
        call = complete_calls.get(row.get("call_id"))
        if not call:
            raise HypothesisError("repeated_candidate_call_not_in_attribution")
        candidates.append(_candidate(
            "repeated_or_overlapping_evidence_candidate", "call", [row["call_id"]],
            row["visible_estimated_tokens"], call["visible_token_share"],
            {
                "basis_kind": "acp1_1_unique_within_session_relation",
                "relation_count": row["relation_count"],
                "relation_types": row["relation_types"],
                "relation_ids": row["relation_ids"],
                "counted_once": row["counted_once"],
            },
            [_ref("repeated_evidence", "/unique_repeated_observations"), _ref("attribution", "/call_attribution")],
        ))

    candidates.sort(key=lambda row: (-row["observed_exposure_tokens"], row["hypothesis_type"], row["hypothesis_id"]))
    type_counts = Counter(row["hypothesis_type"] for row in candidates)
    unique_target_ids = sorted({call_id for row in candidates for call_id in row["target_call_ids"]})
    unique_target_tokens = sum(complete_calls[call_id]["attributed_visible_estimated_tokens"] for call_id in unique_target_ids)
    unique_target_share = round(unique_target_tokens / denominator, 12) if denominator else None
    catalog_status = "candidates_present" if candidates else "empty_no_preregistered_trigger"
    result = {
        "schema_version": 1,
        "schema_id": SCHEMA_ID,
        "generator_version": GENERATOR_VERSION,
        "source_and_scope": {
            "attribution_sha256": sha256(attribution),
            "repeated_evidence_analysis_sha256": sha256(repetition),
            "catalog_scope": "offline_experiment_candidate_generation",
            "intervention_executed": False,
        },
        "candidate_generation_policy": {
            "policy_id": "acp1-2-candidate-policy-v1",
            "high_cost_min_visible_token_share": HIGH_COST_MIN_SHARE,
            "high_cost_min_observed_exposure_tokens": HIGH_COST_MIN_TOKENS,
            "high_cost_max_candidates": HIGH_COST_MAX_CANDIDATES,
            "concentration_min_call_hhi": CONCENTRATION_MIN_CALL_HHI,
            "concentration_min_top3_share": CONCENTRATION_MIN_TOP3_SHARE,
            "repeated_candidate_requires_unique_within_session_observation": True,
            "candidate_is_not_anomaly_or_verdict": True,
            "empty_catalog_is_valid": True,
        },
        "catalog_status": catalog_status,
        "hypothesis_candidates": candidates,
        "candidate_summary": {
            "candidate_count": len(candidates),
            "candidate_type_counts": {
                name: type_counts[name] for name in (
                    "high_cost_call_candidate", "cost_concentration_candidate",
                    "repeated_or_overlapping_evidence_candidate",
                )
            },
            "unique_target_call_count": len(unique_target_ids),
            "unique_target_call_ids": unique_target_ids,
            "unique_target_observed_exposure_tokens": unique_target_tokens,
            "unique_target_observed_share": unique_target_share,
            "target_exposure_counting_rule": "each target call counted once across overlapping candidates",
        },
        "unknowns": {
            "necessity_status": "unknown",
            "causal_status": "untested",
            "candidate_validation_feasibility": "blocked" if candidates else "not_applicable_no_candidates",
            "blocking_reason_codes": list(BLOCKING_REASONS) if candidates else [],
            "replayable_task_context_available": False,
            "controlled_intervention_interface_available": False,
        },
        "traceability": [
            {"output_path": "/hypothesis_candidates", "source_refs": [_ref("attribution", "/call_attribution"), _ref("attribution", "/top_calls_and_concentration"), _ref("repeated_evidence", "/unique_repeated_observations")]},
            {"output_path": "/candidate_summary", "source_refs": [_ref("attribution", "/scope_and_denominators/observed_matched_model_visible_estimated_tokens"), _ref("attribution", "/call_attribution")]},
            {"output_path": "/unknowns", "source_refs": [_ref("attribution", "/coverage_summary"), _ref("repeated_evidence", "/unknowns")]},
        ],
        "policy": {
            "fact_grounded_candidates_only": True,
            "necessity_verdict_produced": False,
            "causal_claim_produced": False,
            "avoidable_or_savings_estimate_produced": False,
            "agent_recommendation_produced": False,
            "intervention_executed": False,
            "online_effect": False,
            "canonical_fact_source": "json",
        },
    }
    if originals != (attribution, repetition):
        raise HypothesisError("input_mutation_detected")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attribution", type=Path)
    parser.add_argument("repeated_evidence", type=Path)
    args = parser.parse_args()
    attribution = json.loads(args.attribution.read_text(encoding="utf-8"))
    repetition = json.loads(args.repeated_evidence.read_text(encoding="utf-8"))
    print(canonical_bytes(build_catalog(attribution, repetition)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
