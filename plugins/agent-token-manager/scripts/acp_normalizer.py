#!/usr/bin/env python3
"""Normalize ACP collector telemetry and build an auditable coverage ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


NORMALIZED_SCHEMA_ID = "normalized-event-v1"
LEDGER_SCHEMA_ID = "coverage-ledger-v1"
TRANSCRIPT_SCHEMA_ID = "transcript-call-v1"
PIPELINE_SCHEMA_ID = "acp0-2-pipeline-v1"
NORMALIZER_VERSION = "acp-normalizer-v0.1"
HASH = re.compile(r"^[0-9a-f]{64}$")
SOURCE_FIELDS = {
    "schema_version", "session_id_hash", "event_id", "timestamp", "tool_family",
    "command_shape", "result_status", "path_hashes", "explicit_ranges", "raw_chars",
    "estimated_tokens", "estimation_method", "output_sha256", "code_bearing",
    "coverage_state", "coverage_reason", "duration_ms",
}
NORMALIZED_FIELDS = {
    "schema_version", "schema_id", "source_event_schema", "event_id", "session_id_hash",
    "call_id", "call_index", "timestamp", "tool_family", "command_shape", "result_status",
    "raw_output_chars", "estimated_raw_tokens", "estimation_method", "output_sha256",
    "code_bearing", "path_hashes", "explicit_ranges", "model_visible_chars",
    "estimated_model_visible_tokens", "model_visible_estimation_method",
    "collector_duration_ms", "source_coverage_state", "coverage_state", "coverage_reason",
    "normalization_status", "normalization_reason", "linkage_status", "linkage_reason",
    "collector_sha256", "normalizer_version",
}
SOURCE_COVERAGE_STATES = {
    "observed_and_matched", "observed_not_matched", "transcript_only",
    "unsupported_tool_path", "parse_unknown",
}
RESULT_STATUSES = {"success", "error", "unknown"}
KNOWN_TOOL_FAMILIES = {"bash", "local_read", "mcp", "hosted"}
TRANSCRIPT_FIELDS = {
    "schema_version", "schema_id", "session_id_hash", "call_id", "call_index",
    "tool_family", "output_sha256", "model_visible_chars",
    "estimated_model_visible_tokens", "estimation_method",
}


class NormalizationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def fingerprint(value: Any) -> str:
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError):
        payload = f"unserializable:{type(value).__name__}"
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def _require_hash(value: Any, field: str) -> None:
    if not isinstance(value, str) or HASH.fullmatch(value) is None:
        raise NormalizationError(f"invalid_{field}")


def validate_source_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise NormalizationError("event_not_object")
    if set(event) != SOURCE_FIELDS:
        raise NormalizationError("event_fields_do_not_match_acp_event_v1")
    if event.get("schema_version") != 1:
        raise NormalizationError("unsupported_source_schema_version")
    _require_hash(event.get("session_id_hash"), "session_id_hash")
    _require_hash(event.get("event_id"), "event_id")
    _require_hash(event.get("output_sha256"), "output_sha256")
    if not isinstance(event.get("timestamp"), str) or not event["timestamp"]:
        raise NormalizationError("invalid_timestamp")
    if event.get("result_status") not in RESULT_STATUSES:
        raise NormalizationError("invalid_result_status")
    if event.get("coverage_state") not in SOURCE_COVERAGE_STATES:
        raise NormalizationError("invalid_source_coverage_state")
    if not isinstance(event.get("coverage_reason"), str) or not event["coverage_reason"]:
        raise NormalizationError("invalid_source_coverage_reason")
    if not isinstance(event.get("tool_family"), str) or not event["tool_family"]:
        raise NormalizationError("invalid_tool_family")
    if not isinstance(event.get("command_shape"), str) or not event["command_shape"]:
        raise NormalizationError("invalid_command_shape")
    if not isinstance(event.get("code_bearing"), bool):
        raise NormalizationError("invalid_code_bearing")
    for field in ("raw_chars", "estimated_tokens"):
        value = event.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise NormalizationError(f"invalid_{field}")
    if event["estimated_tokens"] != (event["raw_chars"] + 3) // 4:
        raise NormalizationError("raw_token_estimate_drift")
    if event.get("estimation_method") != "chars_div_4_v1":
        raise NormalizationError("unsupported_estimation_method")
    if not isinstance(event.get("path_hashes"), list) or not isinstance(event.get("explicit_ranges"), list):
        raise NormalizationError("invalid_path_metadata")
    for path_hash in event["path_hashes"]:
        _require_hash(path_hash, "path_hash")
    for item in event["explicit_ranges"]:
        if not isinstance(item, dict) or set(item) != {"path_hash", "start_line", "end_line"}:
            raise NormalizationError("invalid_explicit_range")
        _require_hash(item.get("path_hash"), "range_path_hash")
        start, end = item.get("start_line"), item.get("end_line")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            raise NormalizationError("invalid_explicit_range_bounds")
    duration = event.get("duration_ms")
    if duration is not None and (not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0):
        raise NormalizationError("invalid_duration_ms")
    return event


def validate_transcript_call(call: Any) -> dict[str, Any]:
    if not isinstance(call, dict):
        raise NormalizationError("transcript_call_not_object")
    if set(call) != TRANSCRIPT_FIELDS:
        raise NormalizationError("transcript_call_fields_invalid")
    if call.get("schema_version") != 1 or call.get("schema_id") != TRANSCRIPT_SCHEMA_ID:
        raise NormalizationError("transcript_call_schema_invalid")
    for field in ("session_id_hash", "call_id", "output_sha256"):
        _require_hash(call.get(field), field)
    if not isinstance(call.get("call_index"), int) or isinstance(call["call_index"], bool) or call["call_index"] < 0:
        raise NormalizationError("transcript_call_index_invalid")
    if not isinstance(call.get("tool_family"), str) or not call["tool_family"]:
        raise NormalizationError("transcript_tool_family_invalid")
    for field in ("model_visible_chars", "estimated_model_visible_tokens"):
        value = call.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise NormalizationError(f"transcript_{field}_invalid")
    if call.get("estimation_method") != "chars_div_4_v1":
        raise NormalizationError("transcript_estimation_method_invalid")
    if call["estimated_model_visible_tokens"] != (call["model_visible_chars"] + 3) // 4:
        raise NormalizationError("model_visible_token_estimate_drift")
    return call


def correlate_events(
    events: list[dict[str, Any]], transcript_calls: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    event_id_counts = Counter(event["event_id"] for event in events)
    exact: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    fallback: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for call in transcript_calls:
        exact[(call["session_id_hash"], call["call_id"])].append(call)
        fallback[(call["session_id_hash"], call["tool_family"], call["output_sha256"])].append(call)

    claimed: set[tuple[str, str]] = set()
    correlations: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = event["event_id"]
        if event_id_counts[event_id] > 1:
            correlations[event_id] = {"status": "ambiguous", "reason": "duplicate_event_id"}
            continue
        exact_candidates = exact.get((event["session_id_hash"], event_id), [])
        consistent_exact = [
            call for call in exact_candidates
            if call["tool_family"] == event["tool_family"] and call["output_sha256"] == event["output_sha256"]
        ]
        if exact_candidates and not consistent_exact:
            correlations[event_id] = {"status": "ambiguous", "reason": "stable_id_signal_mismatch"}
            continue
        candidates = consistent_exact or fallback.get(
            (event["session_id_hash"], event["tool_family"], event["output_sha256"]), []
        )
        candidates = [call for call in candidates if (call["session_id_hash"], call["call_id"]) not in claimed]
        if len(candidates) == 1:
            call = candidates[0]
            claimed.add((call["session_id_hash"], call["call_id"]))
            correlations[event_id] = {"status": "matched", "reason": "stable_id_hash_family_match", "call": call}
        elif len(candidates) > 1:
            correlations[event_id] = {"status": "ambiguous", "reason": "multiple_hash_family_candidates"}
        else:
            correlations[event_id] = {"status": "unmatched", "reason": "no_transcript_candidate"}
    return correlations, [
        call for call in transcript_calls
        if (call["session_id_hash"], call["call_id"]) not in claimed
    ]


def normalize_event(
    event: dict[str, Any], correlation: dict[str, Any], *, collector_sha256: str
) -> dict[str, Any]:
    validate_source_event(event)
    _require_hash(collector_sha256, "collector_sha256")
    status = correlation["status"]
    call = correlation.get("call") if status == "matched" else None
    source_state = event["coverage_state"]
    if source_state == "unsupported_tool_path":
        coverage_state = "unsupported_tool_path"
        coverage_reason = event["coverage_reason"]
    elif status == "matched":
        coverage_state = "observed_and_matched"
        coverage_reason = correlation["reason"]
    elif source_state == "parse_unknown":
        coverage_state = "parse_unknown"
        coverage_reason = event["coverage_reason"]
    else:
        coverage_state = "observed_not_matched"
        coverage_reason = correlation["reason"]

    complete = (
        coverage_state == "observed_and_matched"
        and source_state not in {"parse_unknown", "unsupported_tool_path"}
        and event["tool_family"] in KNOWN_TOOL_FAMILIES
    )
    if complete:
        partial_reason = None
    elif source_state in {"parse_unknown", "unsupported_tool_path"}:
        partial_reason = event["coverage_reason"]
    elif event["tool_family"] not in KNOWN_TOOL_FAMILIES:
        partial_reason = "unknown_tool_family"
    else:
        partial_reason = coverage_reason
    result = {
        "schema_version": 1,
        "schema_id": NORMALIZED_SCHEMA_ID,
        "source_event_schema": "acp-event-v1",
        "event_id": event["event_id"],
        "session_id_hash": event["session_id_hash"],
        "call_id": call["call_id"] if call else None,
        "call_index": call["call_index"] if call else None,
        "timestamp": event["timestamp"],
        "tool_family": event["tool_family"],
        "command_shape": event["command_shape"],
        "result_status": event["result_status"],
        "raw_output_chars": event["raw_chars"],
        "estimated_raw_tokens": event["estimated_tokens"],
        "estimation_method": event["estimation_method"],
        "output_sha256": event["output_sha256"],
        "code_bearing": event["code_bearing"],
        "path_hashes": event["path_hashes"],
        "explicit_ranges": event["explicit_ranges"],
        "model_visible_chars": call["model_visible_chars"] if call else None,
        "estimated_model_visible_tokens": call["estimated_model_visible_tokens"] if call else None,
        "model_visible_estimation_method": call["estimation_method"] if call else None,
        "collector_duration_ms": event["duration_ms"],
        "source_coverage_state": source_state,
        "coverage_state": coverage_state,
        "coverage_reason": coverage_reason,
        "normalization_status": "complete" if complete else "partial",
        "normalization_reason": partial_reason,
        "linkage_status": status,
        "linkage_reason": correlation["reason"],
        "collector_sha256": collector_sha256,
        "normalizer_version": NORMALIZER_VERSION,
    }
    if set(result) != NORMALIZED_FIELDS:
        raise NormalizationError("normalized_event_closed_schema_violation")
    return result


def normalize_batch(
    source_events: list[Any], transcript_calls: list[Any], *, collector_sha256: str
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    valid_events: list[dict[str, Any]] = []
    for index, event in enumerate(source_events):
        try:
            valid_events.append(validate_source_event(event))
        except NormalizationError as error:
            diagnostics.append({
                "input_kind": "collector_event", "input_index": index,
                "status": "rejected", "reason": str(error), "source_fingerprint": fingerprint(event),
            })
    valid_calls: list[dict[str, Any]] = []
    for index, call in enumerate(transcript_calls):
        try:
            valid_calls.append(validate_transcript_call(call))
        except NormalizationError as error:
            diagnostics.append({
                "input_kind": "transcript_call", "input_index": index,
                "status": "rejected", "reason": str(error), "source_fingerprint": fingerprint(call),
            })
    correlations, transcript_only = correlate_events(valid_events, valid_calls)
    normalized = [
        normalize_event(event, correlations[event["event_id"]], collector_sha256=collector_sha256)
        for event in valid_events
    ]
    normalized.sort(key=lambda item: (item["session_id_hash"], item["call_index"] is None, item["call_index"] or 0, item["event_id"]))
    diagnostics.sort(key=lambda item: (item["input_kind"], item["input_index"], item["reason"]))
    return {
        "schema_version": 1,
        "schema_id": "normalized-batch-v1",
        "normalizer_version": NORMALIZER_VERSION,
        "collector_sha256": collector_sha256,
        "events": normalized,
        "transcript_only_calls": sorted(transcript_only, key=lambda item: (item["session_id_hash"], item["call_index"], item["call_id"])),
        "diagnostics": diagnostics,
    }


def coverage_metric(numerator: int, denominator: int | None, *, unit: str, denominator_source: str) -> dict[str, Any]:
    if denominator is None or denominator == 0:
        return {
            "status": "unknown_denominator", "numerator": numerator, "denominator": denominator,
            "ratio": None, "unit": unit, "denominator_source": denominator_source,
        }
    return {
        "status": "complete" if numerator == denominator else "partial",
        "numerator": numerator, "denominator": denominator,
        "ratio": round(numerator / denominator, 6), "unit": unit,
        "denominator_source": denominator_source,
    }


def build_coverage_ledger(batch: dict[str, Any], transcript_calls: list[dict[str, Any]], *, fixture_id: str | None = None) -> dict[str, Any]:
    events = batch["events"]
    valid_calls = []
    for call in transcript_calls:
        try:
            valid_calls.append(validate_transcript_call(call))
        except NormalizationError:
            continue
    matched = [event for event in events if event["coverage_state"] == "observed_and_matched"]
    eligible = [event for event in events if event["source_coverage_state"] != "unsupported_tool_path"]
    transcript_sessions = {call["session_id_hash"] for call in valid_calls}
    matched_sessions = {event["session_id_hash"] for event in matched}
    visible_total = sum(call["estimated_model_visible_tokens"] for call in valid_calls)
    visible_matched = sum(event["estimated_model_visible_tokens"] or 0 for event in matched)
    raw_total = sum(event["raw_output_chars"] for event in eligible)
    raw_matched = sum(event["raw_output_chars"] for event in matched)
    known_family = sum(event["tool_family"] in KNOWN_TOOL_FAMILIES for event in events)

    coverage_states = Counter(event["coverage_state"] for event in events)
    reasons = Counter()
    unknown_raw_chars = 0
    unknown_raw_tokens = 0
    unknown_model_visible_tokens = 0
    for event in events:
        if event["normalization_status"] != "complete":
            reasons[event["normalization_reason"] or event["coverage_reason"]] += 1
            unknown_raw_chars += event["raw_output_chars"]
            unknown_raw_tokens += event["estimated_raw_tokens"]
            unknown_model_visible_tokens += event["estimated_model_visible_tokens"] or 0
    if batch["transcript_only_calls"]:
        reasons["transcript_only"] += len(batch["transcript_only_calls"])
        unknown_model_visible_tokens += sum(
            call["estimated_model_visible_tokens"] for call in batch["transcript_only_calls"]
        )

    by_family: dict[str, Any] = {}
    for family in sorted({event["tool_family"] for event in events}):
        members = [event for event in events if event["tool_family"] == family]
        by_family[family] = {
            "event_count": len(members),
            "coverage_state_counts": dict(sorted(Counter(item["coverage_state"] for item in members).items())),
            "raw_output_chars": sum(item["raw_output_chars"] for item in members),
        }
    by_shape: dict[str, Any] = {}
    for shape in sorted({event["command_shape"] for event in events}):
        members = [event for event in events if event["command_shape"] == shape]
        by_shape[shape] = {
            "event_count": len(members),
            "coverage_state_counts": dict(sorted(Counter(item["coverage_state"] for item in members).items())),
        }

    return {
        "schema_version": 1,
        "schema_id": LEDGER_SCHEMA_ID,
        "normalizer_version": batch["normalizer_version"],
        "collector_sha256": batch["collector_sha256"],
        "fixture_id": fixture_id,
        "metrics": {
            "session_coverage": coverage_metric(len(matched_sessions), len(transcript_sessions), unit="sessions", denominator_source="transcript_sessions"),
            "call_coverage": coverage_metric(len(matched), len(valid_calls), unit="calls", denominator_source="transcript_completed_tool_calls"),
            "model_visible_token_coverage": coverage_metric(visible_matched, visible_total, unit="estimated_tokens", denominator_source="transcript_model_visible_tool_tokens"),
            "linkage_coverage": coverage_metric(len(matched), len(eligible), unit="events", denominator_source="collector_supported_events"),
            "raw_char_linkage_coverage": coverage_metric(raw_matched, raw_total, unit="characters", denominator_source="collector_supported_raw_output_chars"),
            "tool_family_classification_coverage": coverage_metric(known_family, len(events), unit="events", denominator_source="normalized_collector_events"),
        },
        "counts": {
            "normalized_event_count": len(events),
            "transcript_call_count": len(valid_calls),
            "matched_event_count": len(matched),
            "transcript_only_call_count": len(batch["transcript_only_calls"]),
            "rejected_input_count": len(batch["diagnostics"]),
            "coverage_state_counts": dict(sorted(coverage_states.items())),
        },
        "coverage_by_tool_family": by_family,
        "coverage_by_command_shape": by_shape,
        "unknown": {
            "count": sum(reasons.values()),
            "raw_output_chars": unknown_raw_chars,
            "estimated_raw_tokens": unknown_raw_tokens,
            "estimated_model_visible_tokens": unknown_model_visible_tokens,
            "reason_counts": dict(sorted(reasons.items())),
        },
        "no_extrapolation_beyond_inputs": True,
    }


def load_jsonl(path: Path) -> list[Any]:
    records: list[Any] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"malformed_json_sha256": hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest()})
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("--transcript-calls", type=Path)
    parser.add_argument("--collector-sha256", required=True)
    args = parser.parse_args()
    source_events = load_jsonl(args.events)
    transcript_calls = load_jsonl(args.transcript_calls) if args.transcript_calls else []
    batch = normalize_batch(source_events, transcript_calls, collector_sha256=args.collector_sha256)
    result = {
        "schema_version": 1,
        "schema_id": PIPELINE_SCHEMA_ID,
        "normalizer_version": NORMALIZER_VERSION,
        "normalized_batch": batch,
        "coverage_ledger": build_coverage_ledger(batch, transcript_calls),
    }
    sys.stdout.buffer.write(canonical_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
