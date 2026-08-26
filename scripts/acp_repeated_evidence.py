#!/usr/bin/env python3
"""Build deterministic within-session repeated-evidence facts from frozen ACP layers."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCHEMA_ID = "repeated-evidence-analysis-v1"
ENGINE_VERSION = "acp-repeated-evidence-v0.1"
RELATION_TYPES = {
    "exact_payload_repeat", "same_path_repeat", "exact_range_repeat",
    "range_contains", "range_overlap",
}
EVIDENCE_BASIS = {"output_hash", "path_identity", "explicit_range"}
ROUND_PLACES = 12


class RepeatedEvidenceError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _stable_id(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _ref(artifact: str, pointer: str, event_ids: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"artifact": artifact, "json_pointer": pointer}
    if event_ids:
        result["event_ids"] = sorted(event_ids)
    return result


def _validate_inputs(batch: Any, ledger: Any, attribution: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(batch, dict) or batch.get("schema_id") != "normalized-batch-v1":
        raise RepeatedEvidenceError("input_must_be_normalized_batch_v1")
    if not isinstance(ledger, dict) or ledger.get("schema_id") != "coverage-ledger-v1":
        raise RepeatedEvidenceError("input_must_be_coverage_ledger_v1")
    if not isinstance(attribution, dict) or attribution.get("schema_id") != "cost-attribution-baseline-v1":
        raise RepeatedEvidenceError("input_must_be_cost_attribution_baseline_v1")
    if not attribution.get("policy", {}).get("fact_only") or attribution.get("policy", {}).get("online_effect"):
        raise RepeatedEvidenceError("attribution_policy_not_frozen")
    events = batch.get("events")
    if not isinstance(events, list):
        raise RepeatedEvidenceError("normalized_events_missing")
    required = {
        "event_id", "call_id", "call_index", "session_id_hash", "linkage_status",
        "estimated_model_visible_tokens", "output_sha256", "path_hashes", "explicit_ranges",
        "coverage_state", "tool_family",
    }
    for event in events:
        if not isinstance(event, dict) or not required.issubset(event):
            raise RepeatedEvidenceError("invalid_normalized_event")
        if not isinstance(event["path_hashes"], list) or not isinstance(event["explicit_ranges"], list):
            raise RepeatedEvidenceError("invalid_path_or_range_evidence")
    denominator = attribution.get("scope_and_denominators", {}).get(
        "observed_matched_model_visible_estimated_tokens", {}
    ).get("value")
    if not isinstance(denominator, int) or isinstance(denominator, bool) or denominator < 0:
        raise RepeatedEvidenceError("invalid_frozen_denominator")
    matched_tokens = sum(
        event["estimated_model_visible_tokens"]
        for event in events
        if event["linkage_status"] == "matched"
        and isinstance(event["estimated_model_visible_tokens"], int)
        and not isinstance(event["estimated_model_visible_tokens"], bool)
    )
    if matched_tokens != denominator:
        raise RepeatedEvidenceError("normalized_attribution_denominator_mismatch")
    attribution_calls = {
        row["call_id"]: row for row in attribution.get("call_attribution", [])
        if row.get("status") == "complete" and isinstance(row.get("attributed_visible_estimated_tokens"), int)
    }
    for event in events:
        if event["linkage_status"] == "matched" and isinstance(event["estimated_model_visible_tokens"], int):
            row = attribution_calls.get(event["call_id"])
            if not row or row["attributed_visible_estimated_tokens"] != event["estimated_model_visible_tokens"]:
                raise RepeatedEvidenceError("normalized_attribution_call_mismatch")
    return batch, ledger, attribution


def _paths(event: dict[str, Any]) -> set[str]:
    return set(event["path_hashes"]) | {item["path_hash"] for item in event["explicit_ranges"]}


def _ranges(event: dict[str, Any]) -> dict[str, list[tuple[int, int]]]:
    result: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for item in event["explicit_ranges"]:
        start = item.get("start_line")
        end = item.get("end_line")
        path = item.get("path_hash")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            raise RepeatedEvidenceError("invalid_explicit_range_bounds")
        if start < 1 or end < start or not isinstance(path, str):
            raise RepeatedEvidenceError("invalid_explicit_range_bounds")
        result[path].append((start, end + 1))
    return {path: sorted(set(items)) for path, items in sorted(result.items())}


def _relation(
    relation_type: str,
    earlier: dict[str, Any],
    later: dict[str, Any],
    *,
    evidence_basis: list[str],
    evidence_identity: str,
    path_hash: str | None = None,
    earlier_range: tuple[int, int] | None = None,
    later_range: tuple[int, int] | None = None,
    overlap_line_count: int | None = None,
    containment_direction: str | None = None,
) -> dict[str, Any]:
    if relation_type not in RELATION_TYPES or not set(evidence_basis).issubset(EVIDENCE_BASIS):
        raise RepeatedEvidenceError("invalid_relation_definition")
    identity = {
        "relation_type": relation_type,
        "session_id_hash": later["session_id_hash"],
        "earlier_call_id": earlier["call_id"],
        "later_call_id": later["call_id"],
        "evidence_identity": evidence_identity,
        "path_hash": path_hash,
        "earlier_range": earlier_range,
        "later_range": later_range,
    }
    return {
        "relation_id": _stable_id(identity),
        "relation_type": relation_type,
        "session_id_hash": later["session_id_hash"],
        "earlier_call_id": earlier["call_id"],
        "later_call_id": later["call_id"],
        "earlier_call_index": earlier["call_index"],
        "later_call_index": later["call_index"],
        "evidence_basis": sorted(evidence_basis),
        "evidence_identity": evidence_identity,
        "path_hash": path_hash,
        "earlier_range": None if earlier_range is None else {
            "start_line": earlier_range[0], "end_line_exclusive": earlier_range[1],
        },
        "later_range": None if later_range is None else {
            "start_line": later_range[0], "end_line_exclusive": later_range[1],
        },
        "overlap_line_count": overlap_line_count,
        "containment_direction": containment_direction,
        "observed_payload_equality": earlier["output_sha256"] == later["output_sha256"],
        "content_stability": "unknown",
        "cross_cycle": "unknown",
        "earlier_visible_estimated_tokens": earlier["estimated_model_visible_tokens"],
        "later_visible_estimated_tokens": later["estimated_model_visible_tokens"],
        "source_refs": [
            _ref("normalized_batch", "/events", [earlier["event_id"], later["event_id"]]),
            _ref("attribution", "/call_attribution"),
        ],
    }


def _pair_relations(earlier: dict[str, Any], later: dict[str, Any]) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    if earlier["output_sha256"] == later["output_sha256"]:
        relations.append(_relation(
            "exact_payload_repeat", earlier, later,
            evidence_basis=["output_hash"], evidence_identity=earlier["output_sha256"],
        ))
    shared_paths = sorted(_paths(earlier) & _paths(later))
    for path in shared_paths:
        relations.append(_relation(
            "same_path_repeat", earlier, later,
            evidence_basis=["path_identity"], evidence_identity=path, path_hash=path,
        ))
    earlier_ranges = _ranges(earlier)
    later_ranges = _ranges(later)
    for path in sorted(set(earlier_ranges) & set(later_ranges)):
        for left in earlier_ranges[path]:
            for right in later_ranges[path]:
                overlap = min(left[1], right[1]) - max(left[0], right[0])
                if overlap <= 0:
                    continue
                if left == right:
                    relation_type = "exact_range_repeat"
                    direction = None
                elif left[0] <= right[0] and left[1] >= right[1]:
                    relation_type = "range_contains"
                    direction = "earlier_contains_later"
                elif right[0] <= left[0] and right[1] >= left[1]:
                    relation_type = "range_contains"
                    direction = "later_contains_earlier"
                else:
                    relation_type = "range_overlap"
                    direction = None
                evidence_identity = _stable_id({"path_hash": path, "earlier": left, "later": right})
                relations.append(_relation(
                    relation_type, earlier, later,
                    evidence_basis=["path_identity", "explicit_range"],
                    evidence_identity=evidence_identity, path_hash=path,
                    earlier_range=left, later_range=right, overlap_line_count=overlap,
                    containment_direction=direction,
                ))
    return relations


def _coverage_status(known: int, denominator: int) -> str:
    if denominator == 0 or known == 0:
        return "unknown"
    return "complete" if known == denominator else "partial"


def build_analysis(batch: Any, ledger: Any, attribution: Any) -> dict[str, Any]:
    original_inputs = copy.deepcopy((batch, ledger, attribution))
    batch, ledger, attribution = _validate_inputs(batch, ledger, attribution)
    events = batch["events"]
    frozen_denominator = attribution["scope_and_denominators"]["observed_matched_model_visible_estimated_tokens"]["value"]
    matched = [
        event for event in events
        if event["linkage_status"] == "matched"
        and isinstance(event["estimated_model_visible_tokens"], int)
        and not isinstance(event["estimated_model_visible_tokens"], bool)
    ]
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in matched:
        by_session[event["session_id_hash"]].append(event)

    order_eligible: list[dict[str, Any]] = []
    excluded_reasons: Counter[str] = Counter()
    excluded_tokens = 0
    for session_events in by_session.values():
        counts = Counter(event["call_index"] for event in session_events if isinstance(event["call_index"], int))
        for event in session_events:
            index = event["call_index"]
            if not isinstance(index, int) or isinstance(index, bool):
                excluded_reasons["missing_call_order"] += 1
                excluded_tokens += event["estimated_model_visible_tokens"]
            elif counts[index] != 1:
                excluded_reasons["non_unique_call_order"] += 1
                excluded_tokens += event["estimated_model_visible_tokens"]
            else:
                order_eligible.append(event)

    relation_rows: list[dict[str, Any]] = []
    eligible_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in order_eligible:
        eligible_by_session[event["session_id_hash"]].append(event)
    for session in sorted(eligible_by_session):
        ordered = sorted(eligible_by_session[session], key=lambda item: (item["call_index"], item["call_id"]))
        for later_index, later in enumerate(ordered):
            for earlier in ordered[:later_index]:
                relation_rows.extend(_pair_relations(earlier, later))
    relation_rows.sort(key=lambda row: (
        row["session_id_hash"], row["later_call_index"], row["earlier_call_index"],
        row["relation_type"], row["evidence_identity"], row["relation_id"],
    ))

    by_later: dict[str, list[dict[str, Any]]] = defaultdict(list)
    event_by_call = {event["call_id"]: event for event in order_eligible}
    for relation in relation_rows:
        by_later[relation["later_call_id"]].append(relation)
    unique_rows = []
    for call_id, relations in sorted(by_later.items(), key=lambda item: (
        event_by_call[item[0]]["session_id_hash"], event_by_call[item[0]]["call_index"], item[0],
    )):
        event = event_by_call[call_id]
        unique_rows.append({
            "session_id_hash": event["session_id_hash"],
            "call_id": call_id,
            "call_index": event["call_index"],
            "visible_estimated_tokens": event["estimated_model_visible_tokens"],
            "relation_count": len(relations),
            "relation_types": sorted({relation["relation_type"] for relation in relations}),
            "relation_ids": sorted(relation["relation_id"] for relation in relations),
            "counted_once": True,
            "source_refs": [_ref("normalized_batch", "/events", [event["event_id"]])],
        })
    unique_tokens = sum(row["visible_estimated_tokens"] for row in unique_rows)
    share = round(unique_tokens / frozen_denominator, ROUND_PLACES) if frozen_denominator else None

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for relation in relation_rows:
        grouped[(relation["relation_type"], relation["evidence_identity"])].append(relation)
    repeat_groups = []
    for (relation_type, evidence_identity), members in sorted(grouped.items()):
        call_ids = sorted({member["earlier_call_id"] for member in members} | {member["later_call_id"] for member in members})
        repeat_groups.append({
            "group_id": _stable_id({"relation_type": relation_type, "evidence_identity": evidence_identity, "call_ids": call_ids}),
            "relation_type": relation_type,
            "evidence_identity": evidence_identity,
            "relation_count": len(members),
            "observation_call_ids": call_ids,
            "relation_ids": sorted(member["relation_id"] for member in members),
        })

    path_known = sum(bool(_paths(event)) for event in order_eligible)
    range_known = sum(bool(event["explicit_ranges"]) for event in order_eligible)
    type_counts = Counter(relation["relation_type"] for relation in relation_rows)
    source_coverage = attribution["coverage_summary"]["status"]
    noneligible_reasons = Counter(
        event["coverage_state"] if event["linkage_status"] != "matched" else "null_visible_tokens"
        for event in events if event not in matched
    )
    result = {
        "schema_version": 1,
        "schema_id": SCHEMA_ID,
        "engine_version": ENGINE_VERSION,
        "source_and_scope": {
            "normalized_batch_sha256": sha256(batch),
            "coverage_ledger_sha256": sha256(ledger),
            "attribution_sha256": sha256(attribution),
            "relation_scope": "within_session",
            "cross_session_relations_created": False,
            "source_range_convention": "one_based_closed",
            "canonical_range_convention": "one_based_half_open",
        },
        "denominator_and_coverage": {
            "eligible_observed_visible_estimated_tokens": frozen_denominator,
            "eligible_observed_call_count": len(matched),
            "relation_order_eligible_call_count": len(order_eligible),
            "relation_order_coverage_status": _coverage_status(len(order_eligible), len(matched)),
            "path_identity_known_call_count": path_known,
            "path_identity_coverage_status": _coverage_status(path_known, len(order_eligible)),
            "explicit_range_known_call_count": range_known,
            "explicit_range_coverage_status": _coverage_status(range_known, len(order_eligible)),
            "cycle_coverage_status": "unknown",
            "source_attribution_coverage_status": source_coverage,
            "denominator_name": "observed_matched_model_visible_estimated_tokens",
            "source_refs": [
                _ref("attribution", "/scope_and_denominators/observed_matched_model_visible_estimated_tokens"),
                _ref("coverage_ledger", "/metrics"),
            ],
        },
        "repeat_groups": repeat_groups,
        "call_relations": relation_rows,
        "unique_repeated_observations": unique_rows,
        "path_repeat_facts": {
            "status": _coverage_status(path_known, len(order_eligible)),
            "same_path_relation_count": type_counts["same_path_repeat"],
            "distinct_path_identity_count": len({
                relation["path_hash"] for relation in relation_rows if relation["relation_type"] == "same_path_repeat"
            }),
            "content_stability": "unknown",
        },
        "range_relation_facts": {
            "status": _coverage_status(range_known, len(order_eligible)),
            "canonical_interval_convention": "one_based_half_open",
            "exact_range_relation_count": type_counts["exact_range_repeat"],
            "range_contains_relation_count": type_counts["range_contains"],
            "range_overlap_relation_count": type_counts["range_overlap"],
            "overlap_line_count_across_relations": sum(
                relation["overlap_line_count"] or 0 for relation in relation_rows
                if relation["relation_type"] in {"exact_range_repeat", "range_contains", "range_overlap"}
            ),
            "content_stability": "unknown",
        },
        "observation_volume": {
            "relation_count": len(relation_rows),
            "relation_type_counts": {name: type_counts[name] for name in sorted(RELATION_TYPES)},
            "unique_repeated_observation_count": len(unique_rows),
            "unique_repeated_observation_tokens": unique_tokens,
            "repeated_observation_share": share,
            "denominator_visible_estimated_tokens": frozen_denominator,
            "denominator_name": "observed_matched_model_visible_estimated_tokens",
            "token_counting_rule": "each eligible later call counted once regardless of relation multiplicity",
        },
        "unknowns": {
            "source_noneligible_call_count": sum(noneligible_reasons.values()),
            "source_noneligible_reason_counts": dict(sorted(noneligible_reasons.items())),
            "relation_order_excluded_call_count": sum(excluded_reasons.values()),
            "relation_order_excluded_visible_estimated_tokens": excluded_tokens,
            "reason_counts": dict(sorted(excluded_reasons.items())),
            "path_identity_unknown_call_count": len(order_eligible) - path_known,
            "explicit_range_unknown_call_count": len(order_eligible) - range_known,
            "cycle_relation_state": "unknown",
            "content_stability_state": "unknown",
        },
        "traceability": [
            {"output_path": "/call_relations", "source_refs": [_ref("normalized_batch", "/events")]},
            {"output_path": "/unique_repeated_observations", "source_refs": [_ref("normalized_batch", "/events"), _ref("attribution", "/call_attribution")]},
            {"output_path": "/observation_volume", "source_refs": [_ref("attribution", "/scope_and_denominators/observed_matched_model_visible_estimated_tokens")]},
            {"output_path": "/unknowns", "source_refs": [_ref("coverage_ledger", "/unknown"), _ref("normalized_batch", "/events")]},
        ],
        "policy": {
            "fact_only": True,
            "no_new_correlation": True,
            "no_cross_session_relation": True,
            "multiple_relations_do_not_multiply_tokens": True,
            "path_or_range_does_not_prove_content_stability": True,
            "repetition_does_not_imply_unnecessary": True,
            "no_diagnosis": True,
            "online_effect": False,
        },
    }
    if original_inputs != (batch, ledger, attribution):
        raise RepeatedEvidenceError("input_mutation_detected")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normalized_batch", type=Path)
    parser.add_argument("coverage_ledger", type=Path)
    parser.add_argument("attribution", type=Path)
    args = parser.parse_args()
    batch = json.loads(args.normalized_batch.read_text(encoding="utf-8"))
    ledger = json.loads(args.coverage_ledger.read_text(encoding="utf-8"))
    attribution = json.loads(args.attribution.read_text(encoding="utf-8"))
    print(canonical_bytes(build_analysis(batch, ledger, attribution)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
