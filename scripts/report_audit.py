#!/usr/bin/env python3
"""Summarize Agent Token Manager JSONL audit data."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_LARGE_READ_TOKENS = 1000


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    tools: Counter[str] = Counter()
    hashes: Counter[str] = Counter()
    total_tokens = 0
    read_tokens = 0
    large_read_candidates = 0
    large_read_candidate_tokens = 0
    largest_read_result_tokens = 0
    cache_statuses: Counter[str] = Counter()
    route_reasons: Counter[str] = Counter()
    manager_reads = 0
    for record in records:
        tokens = int(record.get("estimated_response_tokens", 0) or 0)
        total_tokens += tokens
        if record.get("read_like"):
            read_tokens += tokens
            largest_read_result_tokens = max(largest_read_result_tokens, tokens)
            threshold = int(record.get("large_read_threshold_tokens", DEFAULT_LARGE_READ_TOKENS) or DEFAULT_LARGE_READ_TOKENS)
            if bool(record.get("large_read_candidate", tokens >= threshold)):
                large_read_candidates += 1
                large_read_candidate_tokens += tokens
        tools[str(record.get("tool_name", "unknown"))] += tokens
        digest = record.get("response_sha256")
        if isinstance(digest, str) and digest:
            hashes[digest] += 1
        manager_read = record.get("manager_read")
        if isinstance(manager_read, dict) and manager_read:
            manager_reads += 1
            cache_status = manager_read.get("cache_status")
            route_reason = manager_read.get("route_reason")
            if isinstance(cache_status, str):
                cache_statuses[cache_status] += 1
            if isinstance(route_reason, str):
                route_reasons[route_reason] += 1

    repeated_results = sum(count - 1 for count in hashes.values() if count > 1)
    return {
        "tool_calls": len(records),
        "estimated_response_tokens": total_tokens,
        "estimated_read_response_tokens": read_tokens,
        "read_share_percent": round((read_tokens / total_tokens * 100), 1) if total_tokens else 0.0,
        "repeated_identical_results": repeated_results,
        "large_read_candidates": large_read_candidates,
        "large_read_candidate_tokens": large_read_candidate_tokens,
        "largest_read_result_tokens": largest_read_result_tokens,
        "manager_reads": manager_reads,
        "cache_statuses": dict(cache_statuses.most_common()),
        "route_reasons": dict(route_reasons.most_common()),
        "tokens_by_tool": dict(tools.most_common()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_file", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = summarize(load_records(args.audit_file))
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print(f"Tool calls: {summary['tool_calls']}")
    print(f"Estimated result tokens: {summary['estimated_response_tokens']}")
    print(f"Estimated read-result tokens: {summary['estimated_read_response_tokens']}")
    print(f"Read share: {summary['read_share_percent']}%")
    print(f"Repeated identical results: {summary['repeated_identical_results']}")
    print(f"Large-read candidates: {summary['large_read_candidates']}")
    print(f"Large-read candidate tokens: {summary['large_read_candidate_tokens']}")
    print(f"Largest read result: {summary['largest_read_result_tokens']} tokens")
    print(f"Manager reads: {summary['manager_reads']}")
    print(f"Cache statuses: {summary['cache_statuses']}")
    print(f"Route reasons: {summary['route_reasons']}")
    for tool, tokens in summary["tokens_by_tool"].items():
        print(f"  {tool}: {tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
