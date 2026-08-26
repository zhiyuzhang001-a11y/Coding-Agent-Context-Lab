#!/usr/bin/env python3
"""Build a deterministic, offline-only ACP factual cost-attribution artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCHEMA_ID = "cost-attribution-baseline-v1"
GENERATOR_VERSION = "acp-attributor-v0.1"
MEASUREMENT_CONTRACT_ID = "acp-measurement-v1"
TOP_K = 10
ROUND_PLACES = 12


class AttributionError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def ref(pointer: str) -> dict[str, str]:
    return {"artifact": "fact_report", "json_pointer": pointer}


def metric(
    value: Any,
    unit: str,
    status: str,
    pointer: str,
    *,
    denominator_name: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    result = {
        "value": value,
        "unit": unit,
        "status": status,
        "denominator_name": denominator_name,
        "source_refs": [ref(pointer)],
    }
    if note:
        result["note"] = note
    return result


def _status(value: str) -> str:
    return {
        "complete": "complete",
        "partial": "partial",
        "unknown": "unknown",
        "unknown_denominator": "unknown",
        "unsupported": "unsupported",
    }.get(value, "unknown")


def _share(numerator: int | float, denominator: int) -> float | None:
    return round(numerator / denominator, ROUND_PLACES) if denominator else None


def _distribution(values: list[int]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "min": None, "median": None, "max": None, "p90": None}
    p90 = ordered[math.ceil(0.9 * len(ordered)) - 1] if len(ordered) >= 10 else None
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "max": ordered[-1],
        "p90": p90,
    }


def validate_fact_report(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schema_id") != "fact-report-v1":
        raise AttributionError("input_must_be_fact_report_v1")
    policy = report.get("report_policy")
    if not isinstance(policy, dict) or not policy.get("fact_only") or not policy.get("no_new_correlation"):
        raise AttributionError("fact_report_policy_not_frozen")
    for key in ("layers", "drilldowns", "duplicate_facts"):
        if not isinstance(report.get(key), dict):
            raise AttributionError(f"missing_{key}")
    drilldowns = report["drilldowns"]
    if not isinstance(drilldowns.get("tool_calls"), list) or not isinstance(drilldowns.get("sessions"), list):
        raise AttributionError("missing_frozen_drilldowns")
    return report


def _eligible(row: dict[str, Any]) -> bool:
    return (
        row.get("row_kind") == "observed_event"
        and row.get("linkage_status") == "matched"
        and isinstance(row.get("estimated_model_visible_tokens"), int)
        and not isinstance(row.get("estimated_model_visible_tokens"), bool)
        and row["estimated_model_visible_tokens"] >= 0
    )


def _sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -row["estimated_model_visible_tokens"],
        row["session_id_hash"],
        row.get("call_index") is None,
        row.get("call_index") or 0,
        row.get("event_id") or row.get("call_id") or "",
    )


def _session_attribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[row["session_id_hash"]].append((index, row))
    result = []
    for session_id in sorted(grouped):
        members = grouped[session_id]
        attributed = sum(row["estimated_model_visible_tokens"] for _, row in members if _eligible(row))
        unattributed = sum(
            row["estimated_model_visible_tokens"]
            for _, row in members
            if row.get("row_kind") == "transcript_only_call"
            and isinstance(row.get("estimated_model_visible_tokens"), int)
        )
        denominator = attributed + unattributed
        unsupported = any(row.get("coverage_state") == "unsupported_tool_path" for _, row in members)
        status = "unsupported" if unsupported and denominator == 0 else ("complete" if denominator and not unattributed else "partial")
        if denominator == 0 and not unsupported:
            status = "unknown"
        unsupported_only = unsupported and denominator == 0
        result.append({
            "session_id_hash": session_id,
            "observed_event_count": sum(row.get("row_kind") == "observed_event" for _, row in members),
            "denominator_visible_estimated_tokens": None if unsupported_only else denominator,
            "attributed_visible_estimated_tokens": None if unsupported_only else attributed,
            "unattributed_visible_estimated_tokens": None if unsupported_only else unattributed,
            "attribution_coverage": _share(attributed, denominator),
            "status": status,
            "source_refs": [ref(f"/drilldowns/tool_calls/{index}") for index, _ in members],
        })
    return result


def _call_attribution(rows: list[dict[str, Any]], denominator: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible = sorted([row for row in rows if _eligible(row)], key=_sort_key)
    ranks = {row.get("event_id"): rank for rank, row in enumerate(eligible, start=1)}
    output = []
    for index, row in enumerate(rows):
        is_eligible = _eligible(row)
        known_unattributed = (
            row.get("row_kind") == "transcript_only_call"
            and isinstance(row.get("estimated_model_visible_tokens"), int)
        )
        attributed = row["estimated_model_visible_tokens"] if is_eligible else 0
        unattributed = row["estimated_model_visible_tokens"] if known_unattributed else 0
        if is_eligible:
            status = "complete"
        elif row.get("coverage_state") == "unsupported_tool_path":
            status = "unsupported"
        elif known_unattributed:
            status = "partial"
        else:
            status = "unknown"
        unsupported = row.get("coverage_state") == "unsupported_tool_path"
        output.append({
            "row_kind": row["row_kind"],
            "call_id": row.get("call_id"),
            "session_id_hash": row["session_id_hash"],
            "call_index": row.get("call_index"),
            "tool_family": row["tool_family"],
            "coverage_state": row["coverage_state"],
            "attributed_visible_estimated_tokens": None if unsupported else attributed,
            "unattributed_visible_estimated_tokens": None if unsupported else unattributed,
            "rank": ranks.get(row.get("event_id")) if is_eligible else None,
            "visible_token_share": _share(attributed, denominator) if is_eligible else None,
            "status": status,
            "source_refs": [ref(f"/drilldowns/tool_calls/{index}")],
        })
    return output, eligible


def _family_attribution(
    report: dict[str, Any], eligible: list[dict[str, Any]], denominator: int, coverage_status: str,
) -> list[dict[str, Any]]:
    values: dict[str, list[int]] = defaultdict(list)
    for row in eligible:
        values[row["tool_family"]].append(row["estimated_model_visible_tokens"])
    source_families = [row["tool_family"] for row in report["drilldowns"]["tool_families"]]
    return [
        {
            "tool_family": family,
            "call_count": metric(len(values[family]), "calls", coverage_status, "/drilldowns/tool_calls"),
            "visible_estimated_tokens": metric(sum(values[family]), "estimated_tokens", coverage_status, "/drilldowns/tool_calls"),
            "visible_token_share": metric(
                _share(sum(values[family]), denominator), "ratio", coverage_status if denominator else "unknown",
                "/layers/model_visible_tool_context/estimated_model_visible_tokens",
                denominator_name="observed_matched_model_visible_estimated_tokens",
            ),
            "distribution": _distribution(values[family]),
            "source_refs": [ref("/drilldowns/tool_calls")],
        }
        for family in sorted(set(source_families) | set(values))
    ]


def _top_metric(eligible: list[dict[str, Any]], count: int, denominator: int, name: str) -> dict[str, Any]:
    numerator = sum(row["estimated_model_visible_tokens"] for row in eligible[:count])
    return metric(
        _share(numerator, denominator), "ratio", "complete" if denominator else "unknown",
        "/drilldowns/tool_calls", denominator_name="observed_matched_model_visible_estimated_tokens",
        note=f"{name}; selected_call_count={min(count, len(eligible))}; numerator={numerator}",
    )


def _repetition_facts(report: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    token_by_event = {
        row["event_id"]: row["estimated_model_visible_tokens"]
        for row in rows if _eligible(row) and row.get("event_id")
    }
    source = report["duplicate_facts"]

    def summarize(name: str, pointer: str) -> dict[str, Any]:
        item = source[name]
        groups = item.get("groups", item.get("pairs", []))
        event_ids: set[str] = set()
        for group in groups:
            event_ids.update(group.get("event_ids", []))
            for key in ("left_event_id", "right_event_id"):
                if group.get(key):
                    event_ids.add(group[key])
        known = event_ids & set(token_by_event)
        status = _status(item.get("status", "unknown"))
        if event_ids and len(known) < len(event_ids) and status == "complete":
            status = "partial"
        unknown_volume = status in {"unknown", "unsupported"} and not event_ids
        return {
            "status": status,
            "relationship_count": item.get("repeated_observation_count", item.get("overlap_pair_count", 0)),
            "listed_observation_count": len(event_ids),
            "known_attributed_observation_count": len(known),
            "group_observation_visible_estimated_tokens": None if unknown_volume else sum(token_by_event[event_id] for event_id in known),
            "groups": groups,
            "source_refs": [ref(pointer)],
        }

    return {
        "disclaimer": "Repeated evidence is a factual relationship; its observed volume does not establish waste, necessity, or actionability.",
        "exact_payload_duplicate": summarize("exact_payload_duplicate", "/duplicate_facts/exact_payload_duplicate"),
        "same_file_repeat": summarize("same_file_repeat", "/duplicate_facts/same_file_repeat"),
        "range_overlap": summarize("range_overlap", "/duplicate_facts/range_overlap"),
    }


def build_attribution(report: Any) -> dict[str, Any]:
    report = validate_fact_report(report)
    calls = report["drilldowns"]["tool_calls"]
    visible = report["layers"]["model_visible_tool_context"]["estimated_model_visible_tokens"]
    observed = report["layers"]["observed_tool_result_cost"]["tool_result_count"]
    token_coverage = report["drilldowns"]["evidence_coverage"]["metrics"]["model_visible_token_coverage"]
    unknown = report["drilldowns"]["evidence_coverage"]["unknown"]
    denominator = visible["value"]
    if not isinstance(denominator, int) or denominator < 0:
        raise AttributionError("invalid_frozen_visible_token_numerator")
    coverage_status = _status(token_coverage["status"])
    call_rows, eligible = _call_attribution(calls, denominator)
    attributed = sum(row["estimated_model_visible_tokens"] for row in eligible)
    if attributed != denominator:
        raise AttributionError("eligible_call_sum_drift_from_frozen_denominator")
    families = _family_attribution(report, eligible, denominator, coverage_status)
    family_hhi = sum((sum(row["estimated_model_visible_tokens"] for row in eligible if row["tool_family"] == family["tool_family"]) / denominator) ** 2 for family in families) if denominator else None
    call_hhi = sum((row["estimated_model_visible_tokens"] / denominator) ** 2 for row in eligible) if denominator else None
    ten_count = min(len(eligible), math.ceil(0.1 * len(eligible)))
    twenty_count = min(len(eligible), math.ceil(0.2 * len(eligible)))
    top_calls = [
        {
            "rank": rank,
            "session_id_hash": row["session_id_hash"],
            "call_id": row.get("call_id"),
            "call_index": row.get("call_index"),
            "tool_family": row["tool_family"],
            "visible_estimated_tokens": row["estimated_model_visible_tokens"],
            "visible_token_share": _share(row["estimated_model_visible_tokens"], denominator),
            "source_refs": [ref("/drilldowns/tool_calls")],
        }
        for rank, row in enumerate(eligible[:TOP_K], start=1)
    ]
    cycle = report["drilldowns"]["model_cycles"]
    result = {
        "schema_version": 1,
        "schema_id": SCHEMA_ID,
        "generator_version": GENERATOR_VERSION,
        "source_fact_report_sha256": sha256(report),
        "measurement_contract_id": MEASUREMENT_CONTRACT_ID,
        "scope_and_denominators": {
            "observed_calls": metric(observed["value"], "events", _status(observed["status"]), "/layers/observed_tool_result_cost/tool_result_count"),
            "observed_matched_model_visible_estimated_tokens": metric(denominator, "estimated_tokens", coverage_status, "/layers/model_visible_tool_context/estimated_model_visible_tokens"),
            "session_total_tokens": metric(None, "tokens", "unknown", "/layers/session_level_cost/session_total_tokens"),
            "model_cycles": metric(None, "cycles", "unknown", "/layers/session_level_cost/model_cycles"),
        },
        "coverage_summary": {
            "status": coverage_status,
            "metrics": report["drilldowns"]["evidence_coverage"]["metrics"],
            "unknown_count": unknown["count"],
            "unknown_estimated_model_visible_tokens": unknown["estimated_model_visible_tokens"],
            "source_refs": [ref("/drilldowns/evidence_coverage")],
        },
        "session_attribution": _session_attribution(calls),
        "tool_family_attribution": families,
        "call_attribution": call_rows,
        "top_calls_and_concentration": {
            "eligible_call_count": len(eligible),
            "top_calls": top_calls,
            "top1_share": _top_metric(eligible, 1, denominator, "top1"),
            "top3_share": _top_metric(eligible, 3, denominator, "top3"),
            "topk_share": _top_metric(eligible, TOP_K, denominator, f"top{TOP_K}"),
            "top10_percent_share": _top_metric(eligible, ten_count, denominator, "top10_percent"),
            "top20_percent_share": _top_metric(eligible, twenty_count, denominator, "top20_percent"),
            "call_hhi": metric(round(call_hhi, ROUND_PLACES) if call_hhi is not None else None, "hhi", "complete" if denominator else "unknown", "/drilldowns/tool_calls", denominator_name="observed_matched_model_visible_estimated_tokens"),
            "tool_family_hhi": metric(round(family_hhi, ROUND_PLACES) if family_hhi is not None else None, "hhi", "complete" if denominator else "unknown", "/drilldowns/tool_calls", denominator_name="observed_matched_model_visible_estimated_tokens"),
        },
        "cycle_structure_or_unknown": {
            "status": _status(cycle["status"]),
            "cycles": cycle["cycles"],
            "reason": cycle["reason"],
            "source_refs": [ref("/drilldowns/model_cycles")],
        },
        "objective_repetition_facts": _repetition_facts(report, calls),
        "unknown_volume_and_reasons": {
            "count": unknown["count"],
            "estimated_model_visible_tokens": unknown["estimated_model_visible_tokens"],
            "reason_counts": unknown["reason_counts"],
            "source_refs": [ref("/drilldowns/evidence_coverage/unknown")],
        },
        "traceability_index": [],
        "policy": {
            "fact_only": True,
            "no_new_correlation": True,
            "no_extrapolation": True,
            "tool_visible_share_is_not_session_share": True,
            "repetition_does_not_imply_waste": True,
            "canonical_fact_source": "json",
            "online_effect": False,
        },
    }
    trace_sources = {
        "/scope_and_denominators/observed_calls": "/layers/observed_tool_result_cost/tool_result_count",
        "/scope_and_denominators/observed_matched_model_visible_estimated_tokens": "/layers/model_visible_tool_context/estimated_model_visible_tokens",
        "/coverage_summary": "/drilldowns/evidence_coverage",
        "/session_attribution": "/drilldowns/sessions",
        "/tool_family_attribution": "/drilldowns/tool_families",
        "/call_attribution": "/drilldowns/tool_calls",
        "/top_calls_and_concentration": "/drilldowns/tool_calls",
        "/objective_repetition_facts": "/duplicate_facts",
        "/unknown_volume_and_reasons": "/drilldowns/evidence_coverage/unknown",
    }
    result["traceability_index"] = [
        {"metric_path": path, "source_refs": [ref(pointer)]}
        for path, pointer in trace_sources.items()
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fact_report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.fact_report.read_text(encoding="utf-8"))
    print(canonical_bytes(build_attribution(report)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
