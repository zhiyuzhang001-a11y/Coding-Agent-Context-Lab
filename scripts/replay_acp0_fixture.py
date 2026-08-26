#!/usr/bin/env python3
"""Deterministically replay the frozen ACP-0 CO-1.4 measurement fixture."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def summarize(fixture: dict[str, Any]) -> dict[str, Any]:
    columns = fixture["event_columns"]
    events = [dict(zip(columns, row, strict=True)) for row in fixture["events"]]
    fixed = fixture["fixed_event_values"]
    states = Counter(fixed["coverage_state"] for _ in events)
    shapes = Counter(event["command_shape"] for event in events)
    hashes = Counter(event["output_sha256"] for event in events)
    visible_tokens = sum(event["estimated_model_visible_tokens"] for event in events)
    matched_tokens = visible_tokens if fixed["coverage_state"] == "observed_and_matched" else 0
    matched_count = states["observed_and_matched"]
    return {
        "schema_version": 1,
        "fixture_id": fixture["fixture_id"],
        "session_count": len({event["session_id_hash"] for event in events}),
        "event_count": len(events),
        "raw_chars": sum(event["raw_chars"] for event in events),
        "estimated_raw_tokens": sum(event["estimated_raw_tokens"] for event in events),
        "model_visible_chars": sum(event["model_visible_chars"] for event in events),
        "estimated_model_visible_tokens": visible_tokens,
        "matched_event_count": matched_count,
        "matched_model_visible_tokens": matched_tokens,
        "call_coverage": matched_count / len(events) if events else 0.0,
        "model_visible_token_weighted_coverage": matched_tokens / visible_tokens if visible_tokens else 0.0,
        "exact_payload_duplicate_count": sum(count - 1 for count in hashes.values() if count > 1),
        "coverage_state_counts": dict(sorted(states.items())),
        "command_shape_counts": dict(sorted(shapes.items())),
        "unsupported_paths": sorted(fixture["expected"]["unsupported_paths"]),
        "estimation_method": fixture["source"]["estimation_method"],
    }


def render_summary(fixture: dict[str, Any]) -> bytes:
    return (json.dumps(summarize(fixture), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", nargs="?", type=Path, default=plugin / "resources" / "acp0_co1_4_replay_fixture.json")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    sys.stdout.buffer.write(render_summary(fixture))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
