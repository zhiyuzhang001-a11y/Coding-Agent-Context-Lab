#!/usr/bin/env python3
"""Replay ACP-0.2 paired and synthetic-host fixtures deterministically."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from unittest import mock

import acp_collector
import acp_normalizer


def paired_inputs(fixture: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    semantics = fixture.get("paired_replay_contract", {})
    if semantics.get("event_order") != "source_transcript_order_within_session":
        raise ValueError("paired fixture does not declare transcript call ordering")
    if semantics.get("call_id") != "event_id_from_frozen_one_to_one_correlation":
        raise ValueError("paired fixture does not declare stable call identity")
    columns = fixture["event_columns"]
    rows = [dict(zip(columns, row, strict=True)) for row in fixture["events"]]
    call_indices: Counter[str] = Counter()
    source_events: list[dict[str, Any]] = []
    transcript_calls: list[dict[str, Any]] = []
    for global_index, row in enumerate(rows):
        session = row["session_id_hash"]
        call_index = call_indices[session]
        call_indices[session] += 1
        source_events.append({
            "schema_version": 1,
            "session_id_hash": session,
            "event_id": row["event_id"],
            "timestamp": f"2000-01-01T00:00:{global_index:02d}+00:00",
            "tool_family": "bash",
            "command_shape": row["command_shape"],
            "result_status": "unknown",
            "path_hashes": [],
            "explicit_ranges": [],
            "raw_chars": row["raw_chars"],
            "estimated_tokens": row["estimated_raw_tokens"],
            "estimation_method": "chars_div_4_v1",
            "output_sha256": row["output_sha256"],
            "code_bearing": True,
            "coverage_state": "observed_not_matched",
            "coverage_reason": "collector_only_awaiting_transcript_correlation",
            "duration_ms": None,
        })
        transcript_calls.append({
            "schema_version": 1,
            "schema_id": acp_normalizer.TRANSCRIPT_SCHEMA_ID,
            "session_id_hash": session,
            "call_id": row["event_id"],
            "call_index": call_index,
            "tool_family": "bash",
            "output_sha256": row["output_sha256"],
            "model_visible_chars": row["model_visible_chars"],
            "estimated_model_visible_tokens": row["estimated_model_visible_tokens"],
            "estimation_method": "chars_div_4_v1",
        })
    return source_events, transcript_calls


def synthetic_host_inputs(
    fixture: dict[str, Any], *, collector_sha256: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    secret = bytes.fromhex(fixture["collector_secret_hex"])
    collected: list[dict[str, Any]] = []
    private_markers: list[str] = []
    with mock.patch.object(acp_collector.time, "monotonic_ns", return_value=0):
        for item in fixture["host_events"]:
            private_markers.extend(item["private_markers"])
            collected.append(acp_collector.build_record(
                item["event"], secret, timestamp=item["timestamp"], nonce=item["nonce"], started_ns=0,
            ))
    transcript_calls: list[dict[str, Any]] = []
    per_session: Counter[str] = Counter()
    for index in fixture["matched_event_indices"]:
        event = collected[index]
        call_index = per_session[event["session_id_hash"]]
        per_session[event["session_id_hash"]] += 1
        transcript_calls.append({
            "schema_version": 1,
            "schema_id": acp_normalizer.TRANSCRIPT_SCHEMA_ID,
            "session_id_hash": event["session_id_hash"],
            "call_id": event["event_id"],
            "call_index": call_index,
            "tool_family": event["tool_family"],
            "output_sha256": event["output_sha256"],
            "model_visible_chars": event["raw_chars"],
            "estimated_model_visible_tokens": event["estimated_tokens"],
            "estimation_method": event["estimation_method"],
        })
    transcript_calls.append(fixture["transcript_only_call"])
    return collected, transcript_calls, private_markers


def render_pipeline(
    source_events: list[Any], transcript_calls: list[Any], *, collector_sha256: str, fixture_id: str
) -> bytes:
    batch = acp_normalizer.normalize_batch(source_events, transcript_calls, collector_sha256=collector_sha256)
    ledger = acp_normalizer.build_coverage_ledger(batch, transcript_calls, fixture_id=fixture_id)
    return acp_normalizer.canonical_bytes({
        "schema_version": 1,
        "schema_id": acp_normalizer.PIPELINE_SCHEMA_ID,
        "normalizer_version": acp_normalizer.NORMALIZER_VERSION,
        "normalized_batch": batch,
        "coverage_ledger": ledger,
    })


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=("paired", "synthetic"), default="paired")
    args = parser.parse_args()
    contract = json.loads((plugin / "resources" / "acp0_contract.json").read_text(encoding="utf-8"))
    collector_sha256 = contract["acp0_1_collector_audit"]["collector_sha256"]
    if args.fixture == "paired":
        fixture = json.loads((plugin / "resources" / "acp0_co1_4_replay_fixture.json").read_text(encoding="utf-8"))
        source, calls = paired_inputs(fixture)
        fixture_id = fixture["fixture_id"]
    else:
        fixture = json.loads((plugin / "resources" / "acp0_2_synthetic_host_events.json").read_text(encoding="utf-8"))
        source, calls, _ = synthetic_host_inputs(fixture, collector_sha256=collector_sha256)
        fixture_id = fixture["fixture_id"]
    sys.stdout.buffer.write(render_pipeline(source, calls, collector_sha256=collector_sha256, fixture_id=fixture_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
