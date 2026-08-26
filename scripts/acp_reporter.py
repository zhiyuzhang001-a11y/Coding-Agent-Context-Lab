#!/usr/bin/env python3
"""Build deterministic, coverage-aware ACP fact reports from ACP-0.2 output."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


REPORT_SCHEMA_ID = "fact-report-v1"
REPORTER_VERSION = "acp-reporter-v0.1"
PIPELINE_SCHEMA_ID = "acp0-2-pipeline-v1"
NORMALIZED_BATCH_SCHEMA_ID = "normalized-batch-v1"
LEDGER_SCHEMA_ID = "coverage-ledger-v1"
NORMALIZER_VERSION = "acp-normalizer-v0.1"
FACT_STATUSES = {"complete", "partial", "unknown", "unsupported"}


class ReportError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def source_ref(artifact: str, pointer: str, event_ids: Iterable[str] = ()) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "json_pointer": pointer,
        "event_ids": sorted(set(event_ids)),
    }


def fact(value: Any, unit: str, status: str, refs: list[dict[str, Any]], note: str | None = None) -> dict[str, Any]:
    if status not in FACT_STATUSES:
        raise ReportError(f"invalid_fact_status:{status}")
    result = {"value": value, "unit": unit, "status": status, "source_refs": refs}
    if note is not None:
        result["note"] = note
    return result


def ledger_status(metric: dict[str, Any]) -> str:
    return "unknown" if metric["status"] == "unknown_denominator" else metric["status"]


def validate_pipeline(pipeline: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(pipeline, dict) or pipeline.get("schema_id") != PIPELINE_SCHEMA_ID:
        raise ReportError("unsupported_pipeline_schema")
    batch = pipeline.get("normalized_batch")
    ledger = pipeline.get("coverage_ledger")
    if not isinstance(batch, dict) or batch.get("schema_id") != NORMALIZED_BATCH_SCHEMA_ID:
        raise ReportError("unsupported_normalized_batch_schema")
    if not isinstance(ledger, dict) or ledger.get("schema_id") != LEDGER_SCHEMA_ID:
        raise ReportError("unsupported_coverage_ledger_schema")
    versions = {pipeline.get("normalizer_version"), batch.get("normalizer_version"), ledger.get("normalizer_version")}
    if versions != {NORMALIZER_VERSION}:
        raise ReportError("normalizer_version_mismatch")
    if batch.get("collector_sha256") != ledger.get("collector_sha256"):
        raise ReportError("collector_hash_mismatch")
    counts = ledger.get("counts", {})
    if counts.get("normalized_event_count") != len(batch.get("events", [])):
        raise ReportError("normalized_event_count_mismatch")
    if counts.get("transcript_only_call_count") != len(batch.get("transcript_only_calls", [])):
        raise ReportError("transcript_only_call_count_mismatch")
    return batch, ledger


def distribution(values: list[int], unit: str, refs: list[dict[str, Any]]) -> dict[str, Any]:
    if not values:
        return {
            "count": fact(0, "items", "complete", refs),
            "min": fact(None, unit, "unknown", refs, "No eligible observations."),
            "median": fact(None, unit, "unknown", refs, "No eligible observations."),
            "max": fact(None, unit, "unknown", refs, "No eligible observations."),
        }
    return {
        "count": fact(len(values), "items", "complete", refs),
        "min": fact(min(values), unit, "complete", refs),
        "median": fact(statistics.median(values), unit, "complete", refs),
        "max": fact(max(values), unit, "complete", refs),
    }


def _session_rows(events: list[dict[str, Any]], transcript_only: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    call_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        event_groups[event["session_id_hash"]].append(event)
    for call in transcript_only:
        call_groups[call["session_id_hash"]].append(call)
    rows = []
    for session in sorted(set(event_groups) | set(call_groups)):
        members = event_groups[session]
        extra = call_groups[session]
        matched = [item for item in members if item["linkage_status"] == "matched"]
        transcript_count = len(matched) + len(extra)
        status = "complete" if transcript_count and len(matched) == transcript_count else "partial"
        if not transcript_count:
            status = "unknown"
        rows.append({
            "session_id_hash": session,
            "observed_event_count": len(members),
            "transcript_call_count": transcript_count,
            "matched_call_count": len(matched),
            "raw_output_chars": sum(item["raw_output_chars"] for item in members),
            "estimated_raw_tokens": sum(item["estimated_raw_tokens"] for item in members),
            "matched_model_visible_chars": sum(item["model_visible_chars"] or 0 for item in matched),
            "matched_estimated_model_visible_tokens": sum(item["estimated_model_visible_tokens"] or 0 for item in matched),
            "coverage_status": status,
            "session_total_tokens": None,
            "session_total_tokens_status": "unknown",
            "model_cycle_count": None,
            "model_cycle_status": "unknown",
            "source_refs": [
                source_ref("normalized_batch", "/events", [item["event_id"] for item in members]),
                source_ref("normalized_batch", "/transcript_only_calls"),
            ],
        })
    return rows


def _call_rows(events: list[dict[str, Any]], transcript_only: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for event in events:
        rows.append({
            "row_kind": "observed_event",
            "event_id": event["event_id"],
            "call_id": event["call_id"],
            "session_id_hash": event["session_id_hash"],
            "call_index": event["call_index"],
            "tool_family": event["tool_family"],
            "command_shape": event["command_shape"],
            "result_status": event["result_status"],
            "raw_output_chars": event["raw_output_chars"],
            "estimated_raw_tokens": event["estimated_raw_tokens"],
            "model_visible_chars": event["model_visible_chars"],
            "estimated_model_visible_tokens": event["estimated_model_visible_tokens"],
            "coverage_state": event["coverage_state"],
            "linkage_status": event["linkage_status"],
            "normalization_status": event["normalization_status"],
            "source_refs": [source_ref("normalized_batch", "/events", [event["event_id"]])],
        })
    for call in transcript_only:
        rows.append({
            "row_kind": "transcript_only_call",
            "event_id": None,
            "call_id": call["call_id"],
            "session_id_hash": call["session_id_hash"],
            "call_index": call["call_index"],
            "tool_family": call["tool_family"],
            "command_shape": None,
            "result_status": "unknown",
            "raw_output_chars": None,
            "estimated_raw_tokens": None,
            "model_visible_chars": call["model_visible_chars"],
            "estimated_model_visible_tokens": call["estimated_model_visible_tokens"],
            "coverage_state": "transcript_only",
            "linkage_status": "unmatched",
            "normalization_status": "partial",
            "source_refs": [source_ref("normalized_batch", "/transcript_only_calls")],
        })
    return sorted(rows, key=lambda row: (
        row["session_id_hash"], row["call_index"] is None, row["call_index"] or 0,
        row["event_id"] or row["call_id"], row["row_kind"],
    ))


def _dimension_rows(events: list[dict[str, Any]], transcript_only: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    values = sorted({item[key] for item in events} | ({item[key] for item in transcript_only} if key == "tool_family" else set()))
    rows = []
    for value in values:
        observed = [item for item in events if item[key] == value]
        matched = [item for item in observed if item["linkage_status"] == "matched"]
        extra = [item for item in transcript_only if key == "tool_family" and item[key] == value]
        rows.append({
            key: value,
            "observed_event_count": len(observed),
            "transcript_call_count": len(matched) + len(extra),
            "matched_call_count": len(matched),
            "raw_output_chars": sum(item["raw_output_chars"] for item in observed),
            "matched_estimated_model_visible_tokens": sum(item["estimated_model_visible_tokens"] or 0 for item in matched),
            "source_refs": [source_ref("normalized_batch", "/events", [item["event_id"] for item in observed])],
        })
    return rows


def _duplicate_facts(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_payload: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_payload[event["output_sha256"]].append(event)
    payload_groups = []
    for digest, members in sorted(by_payload.items()):
        if len(members) > 1:
            payload_groups.append({
                "output_sha256": digest,
                "observation_count": len(members),
                "repeated_observation_count": len(members) - 1,
                "event_ids": sorted(item["event_id"] for item in members),
            })

    path_members: dict[str, set[str]] = defaultdict(set)
    path_known_events: set[str] = set()
    for event in events:
        paths = set(event["path_hashes"]) | {item["path_hash"] for item in event["explicit_ranges"]}
        if paths:
            path_known_events.add(event["event_id"])
        for path in paths:
            path_members[path].add(event["event_id"])
    path_groups = [
        {"path_hash": path, "observation_count": len(ids), "repeated_observation_count": len(ids) - 1, "event_ids": sorted(ids)}
        for path, ids in sorted(path_members.items()) if len(ids) > 1
    ]
    path_status = "unknown" if not path_known_events else ("complete" if len(path_known_events) == len(events) else "partial")

    ranges: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    range_event_ids: set[str] = set()
    for event in events:
        for item in event["explicit_ranges"]:
            ranges[item["path_hash"]].append((event["event_id"], item["start_line"], item["end_line"]))
            range_event_ids.add(event["event_id"])
    overlaps = []
    for path, items in sorted(ranges.items()):
        for left_index, left in enumerate(sorted(items)):
            for right in sorted(items)[left_index + 1:]:
                if left[0] == right[0]:
                    continue
                start, end = max(left[1], right[1]), min(left[2], right[2])
                if start <= end:
                    overlaps.append({
                        "path_hash": path, "left_event_id": left[0], "right_event_id": right[0],
                        "overlap_start_line": start, "overlap_end_line": end, "overlap_line_count": end - start + 1,
                    })
    overlaps.sort(key=lambda item: (item["path_hash"], item["left_event_id"], item["right_event_id"], item["overlap_start_line"]))
    range_status = "unknown" if not range_event_ids else ("complete" if len(range_event_ids) == len(events) else "partial")
    refs = [source_ref("normalized_batch", "/events", [event["event_id"] for event in events])]
    return {
        "disclaimer": "Repeated observations are factual relationships only and do not establish necessity or actionability.",
        "exact_payload_duplicate": {
            "status": "complete", "repeated_observation_count": sum(group["repeated_observation_count"] for group in payload_groups),
            "groups": payload_groups, "source_refs": refs,
        },
        "same_file_repeat": {
            "status": path_status, "repeated_observation_count": sum(group["repeated_observation_count"] for group in path_groups),
            "groups": path_groups, "source_refs": refs,
        },
        "range_overlap": {
            "status": range_status, "overlap_pair_count": len(overlaps),
            "overlap_line_count": sum(item["overlap_line_count"] for item in overlaps),
            "pairs": overlaps, "source_refs": refs,
        },
    }


def build_fact_report(pipeline: Any, *, top_limit: int = 10) -> dict[str, Any]:
    if not isinstance(top_limit, int) or isinstance(top_limit, bool) or top_limit < 1:
        raise ReportError("invalid_top_limit")
    batch, ledger = validate_pipeline(pipeline)
    events = batch["events"]
    transcript_only = batch["transcript_only_calls"]
    matched = [event for event in events if event["linkage_status"] == "matched"]
    event_ids = [event["event_id"] for event in events]
    event_ref = [source_ref("normalized_batch", "/events", event_ids)]
    ledger_count_ref = [source_ref("coverage_ledger", "/counts")]
    session_metric = ledger["metrics"]["session_coverage"]
    call_metric = ledger["metrics"]["call_coverage"]
    token_metric = ledger["metrics"]["model_visible_token_coverage"]
    linkage_metric = ledger["metrics"]["linkage_coverage"]
    all_duration_known = bool(events) and all(event["collector_duration_ms"] is not None for event in events)
    duration_status = "complete" if all_duration_known else "unknown"
    duration_value = sum(event["collector_duration_ms"] for event in events) if all_duration_known else None

    session_rows = _session_rows(events, transcript_only)
    call_rows = _call_rows(events, transcript_only)
    matched_largest = sorted(
        [row for row in call_rows if row["row_kind"] == "observed_event" and row["estimated_model_visible_tokens"] is not None],
        key=lambda row: (-row["estimated_model_visible_tokens"], row["session_id_hash"], row["call_index"], row["event_id"]),
    )[:top_limit]
    raw_largest = sorted(
        [row for row in call_rows if row["row_kind"] == "observed_event"],
        key=lambda row: (-row["raw_output_chars"], row["session_id_hash"], row["event_id"]),
    )[:top_limit]

    report = {
        "schema_version": 1,
        "schema_id": REPORT_SCHEMA_ID,
        "reporter_version": REPORTER_VERSION,
        "generated_from": {
            "pipeline_schema_id": pipeline["schema_id"],
            "normalizer_version": batch["normalizer_version"],
            "collector_sha256": batch["collector_sha256"],
            "normalized_batch_sha256": sha256(batch),
            "coverage_ledger_sha256": sha256(ledger),
            "fixture_id": ledger.get("fixture_id"),
        },
        "report_scope": {
            "kind": "fixture_run_set" if ledger.get("fixture_id") else "input_run_set",
            "session_count": len(session_rows),
            "top_call_limit": top_limit,
        },
        "layers": {
            "observed_tool_result_cost": {
                "raw_output_chars": fact(sum(event["raw_output_chars"] for event in events), "characters", "partial" if batch["diagnostics"] else "complete", event_ref),
                "estimated_raw_tokens": fact(sum(event["estimated_raw_tokens"] for event in events), "estimated_tokens", "partial" if batch["diagnostics"] else "complete", event_ref),
                "estimation_method": fact("chars_div_4_v1", "method", "complete", event_ref),
                "tool_result_count": fact(len(events), "events", "partial" if batch["diagnostics"] else "complete", ledger_count_ref),
                "code_bearing_result_count": fact(sum(event["code_bearing"] for event in events), "events", "partial" if batch["diagnostics"] else "complete", event_ref),
            },
            "model_visible_tool_context": {
                "model_visible_chars": fact(sum(event["model_visible_chars"] or 0 for event in matched), "characters", ledger_status(call_metric), [source_ref("coverage_ledger", "/metrics/call_coverage")]),
                "estimated_model_visible_tokens": fact(token_metric["numerator"], "estimated_tokens", ledger_status(token_metric), [source_ref("coverage_ledger", "/metrics/model_visible_token_coverage")]),
                "matched_tool_result_count": fact(len(matched), "calls", ledger_status(call_metric), [source_ref("coverage_ledger", "/counts/matched_event_count")]),
                "unmatched_tool_result_count": fact(len(events) - len(matched), "events", ledger_status(linkage_metric), [source_ref("coverage_ledger", "/metrics/linkage_coverage")]),
            },
            "session_level_cost": {
                "session_total_tokens": fact(None, "tokens", "unknown", [source_ref("coverage_ledger", "/metrics/session_coverage")], "No cumulative session usage is present in normalized-event-v1 or coverage-ledger-v1."),
                "model_cycles": fact(None, "cycles", "unknown", [source_ref("normalized_batch", "/events")], "No model-cycle identity is present in the input contracts."),
                "tool_calls": fact(ledger["counts"]["transcript_call_count"], "calls", ledger_status(call_metric), [source_ref("coverage_ledger", "/counts/transcript_call_count")]),
                "usage_source": fact("transcript-call-v1", "source", "partial", [source_ref("coverage_ledger", "/metrics/call_coverage")], "Source applies to tool calls and model-visible tool context only; cumulative session usage is unavailable."),
            },
            "profiler_cost": {
                "hook_invocations": fact(len(events), "events", "partial", event_ref, "Recorded events are a lower bound and do not prove total host hook invocations."),
                "local_duration_ms": fact(duration_value, "milliseconds", duration_status, event_ref),
                "log_bytes": fact(None, "bytes", "unknown", [source_ref("normalized_batch", "")], "Input artifact byte size is not part of the frozen pipeline contract."),
                "report_bytes": fact(None, "bytes", "unknown", [source_ref("normalized_batch", "")], "Serialization size is renderer-specific and not a fact-report input measurement."),
                "additional_model_cycles": fact(None, "cycles", "unknown", [source_ref("normalized_batch", "")], "Requires paired no-interference evidence."),
                "additional_tool_calls": fact(None, "calls", "unknown", [source_ref("normalized_batch", "")], "Requires paired no-interference evidence."),
                "profiler_errors": fact(None, "errors", "unknown", [source_ref("normalized_batch", "/diagnostics")], "Normalizer diagnostics are not equivalent to collector or profiler runtime errors."),
            },
        },
        "drilldowns": {
            "sessions": session_rows,
            "model_cycles": {
                "status": "unknown", "cycles": [],
                "reason": "No cycle identifiers or boundaries are present; the reporter does not infer them.",
                "source_refs": [source_ref("normalized_batch", "/events")],
            },
            "tool_calls": call_rows,
            "tool_families": _dimension_rows(events, transcript_only, "tool_family"),
            "command_shapes": _dimension_rows(events, transcript_only, "command_shape"),
            "distributions": {
                "matched_estimated_model_visible_tokens": distribution(
                    [event["estimated_model_visible_tokens"] for event in matched], "estimated_tokens", event_ref
                ),
                "observed_raw_output_chars": distribution([event["raw_output_chars"] for event in events], "characters", event_ref),
            },
            "largest_calls": {
                "largest_matched_model_visible_calls": matched_largest,
                "largest_observed_raw_results": raw_largest,
            },
            "evidence_coverage": {
                "metrics": ledger["metrics"],
                "counts": ledger["counts"],
                "unknown": ledger["unknown"],
                "coverage_by_tool_family": ledger["coverage_by_tool_family"],
                "coverage_by_command_shape": ledger["coverage_by_command_shape"],
                "source_refs": [source_ref("coverage_ledger", "")],
            },
        },
        "duplicate_facts": _duplicate_facts(events),
        "report_policy": {
            "fact_only": True,
            "no_new_correlation": True,
            "no_extrapolation_beyond_inputs": True,
            "canonical_fact_source": "json",
        },
    }
    return report


def render_json(report: dict[str, Any]) -> bytes:
    return canonical_bytes(report)


def _display_fact(item: dict[str, Any]) -> str:
    value = "unknown" if item["value"] is None else str(item["value"])
    return f"{value} {item['unit']} [{item['status']}]"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ACP Four-Layer Fact Report",
        "",
        f"- Schema: `{report['schema_id']}`",
        f"- Reporter: `{report['reporter_version']}`",
        f"- Scope: {report['report_scope']['session_count']} sessions",
        f"- Fixture: `{report['generated_from']['fixture_id'] or 'none'}`",
        "",
        "## Frozen measurement layers",
        "",
    ]
    labels = {
        "observed_tool_result_cost": "A. Observed tool-result cost",
        "model_visible_tool_context": "B. Model-visible tool context",
        "session_level_cost": "C. Session-level cost",
        "profiler_cost": "D. Profiler cost",
    }
    for layer, values in report["layers"].items():
        lines.extend([f"### {labels[layer]}", ""])
        for key, item in values.items():
            lines.append(f"- `{key}`: {_display_fact(item)}")
        lines.append("")
    coverage = report["drilldowns"]["evidence_coverage"]
    lines.extend(["## Evidence and coverage", ""])
    for name, metric in coverage["metrics"].items():
        denominator = "unknown" if metric["denominator"] is None else metric["denominator"]
        lines.append(f"- `{name}`: {metric['numerator']}/{denominator} {metric['unit']} [{metric['status']}]")
    lines.extend(["", "## Tool families", ""])
    for row in report["drilldowns"]["tool_families"]:
        lines.append(
            f"- `{row['tool_family']}`: {row['transcript_call_count']} transcript calls, "
            f"{row['matched_call_count']} matched, {row['matched_estimated_model_visible_tokens']} estimated visible tokens"
        )
    lines.extend(["", "## Largest matched model-visible calls", ""])
    for row in report["drilldowns"]["largest_calls"]["largest_matched_model_visible_calls"]:
        lines.append(
            f"- call `{row['call_index']}` / `{row['tool_family']}` / session `{row['session_id_hash'][:12]}…`: "
            f"{row['estimated_model_visible_tokens']} estimated tokens"
        )
    cycle = report["drilldowns"]["model_cycles"]
    lines.extend(["", "## Model cycles", "", f"Status: `{cycle['status']}`. {cycle['reason']}", ""])
    lines.extend(["## Repeated-observation facts", "", report["duplicate_facts"]["disclaimer"], ""])
    for name, item in report["duplicate_facts"].items():
        if name == "disclaimer":
            continue
        count_key = "overlap_pair_count" if name == "range_overlap" else "repeated_observation_count"
        lines.append(f"- `{name}`: {item[count_key]} [{item['status']}]")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--top-limit", type=int, default=10)
    args = parser.parse_args()
    pipeline = json.loads(args.pipeline.read_text(encoding="utf-8"))
    report = build_fact_report(pipeline, top_limit=args.top_limit)
    if args.format == "json":
        sys.stdout.buffer.write(render_json(report))
    else:
        sys.stdout.write(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
