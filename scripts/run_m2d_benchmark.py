#!/usr/bin/env python3
"""Compare M2c with bounded multi-source rescue on fixed real tasks."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from run_m2c_benchmark import CASES, has_code_identifier, run_case
from task_navigator import Feedback, TaskNavigator


SECONDARY_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "task-state-persistence",
        "task": "persist navigation tasks so another process can resume their state",
        "target": "TaskStateStore.save",
        "path": "scripts/task_navigator.py",
        "relevant": ("TaskStateStore", "TaskStateStore.load"),
    },
    {
        "id": "budgeted-file-routing",
        "task": "select a compact code region when a large file cannot be returned in full",
        "target": "route_read",
        "path": "scripts/context_router.py",
        "relevant": ("smart_read", "route_read"),
    },
    {
        "id": "private-audit-record",
        "task": "create privacy preserving audit metadata for a tool response without storing its content",
        "target": "build_record",
        "path": "scripts/audit_tool_output.py",
        "relevant": ("collect_manager_metadata", "collect_explicit_paths", "is_read_like"),
    },
    {
        "id": "environment-diagnostics",
        "task": "inspect environment requirements optional backends and private data storage before navigation",
        "target": "run_doctor",
        "path": "scripts/doctor.py",
        "relevant": ("check", "is_ignored"),
    },
    {
        "id": "audit-summary",
        "task": "produce a report of repeated tool outputs and oversized read candidates from audit records",
        "target": "summarize",
        "path": "scripts/report_audit.py",
        "relevant": ("load_records",),
    },
)


def run_static_case(root: Path, data_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    navigator = TaskNavigator(root, data_dir, discovery_sources={})
    state = navigator.start(
        case["task"],
        total_budget=8400,
        navigation_budget=2400,
        expansion_budget=6000,
        task_id=f"static-benchmark-{case['id']}",
    )
    target = next(
        marker
        for marker in navigator.provider.store.load_markers(navigator.provider.name)
        if marker.symbol == case["target"]
    )
    selected: list[str] = []
    found = False
    for _ in range(8):
        choice = navigator.next(state.task_id)
        candidate = choice.get("candidate")
        if not candidate:
            break
        selected.append(candidate["symbol"])
        navigator.expand(state.task_id, candidate["id"], 650)
        if candidate["id"] == target.id:
            navigator.stop(state.task_id, "target_found", [target.id])
            found = True
            break
    final = navigator.store.load(state.task_id)
    if not final.stop_reason:
        navigator.stop(
            state.task_id,
            "low_expected_gain",
            [final.selected[-1]] if final.selected else [],
        )
        final = navigator.store.load(state.task_id)
    return {
        "correct": found,
        "stop_reason": final.stop_reason,
        "selected_symbols": selected,
        "consumed_tokens": final.consumed_tokens,
        "within_budget": final.consumed_tokens <= final.total_budget,
    }


def run_m2d_case(root: Path, data_dir: Path, case: dict[str, Any]) -> dict[str, Any]:
    navigator = TaskNavigator(root, data_dir)
    state = navigator.start(
        case["task"],
        total_budget=8400,
        navigation_budget=2400,
        expansion_budget=6000,
        task_id=f"m2d-benchmark-{case['id']}",
    )
    markers = navigator.provider.store.load_markers(navigator.provider.name)
    target = next(marker for marker in markers if marker.symbol == case["target"])
    relevant = set(case["relevant"])
    selected: list[str] = []
    found = False
    started = time.perf_counter()
    for _ in range(8):
        choice = navigator.next(state.task_id)
        candidate = choice.get("candidate")
        if not candidate:
            break
        selected.append(candidate["symbol"])
        navigator.expand(state.task_id, candidate["id"], 650)
        if candidate["id"] == target.id:
            navigator.stop(state.task_id, "target_found", [target.id])
            found = True
            break
        if navigator.store.load(state.task_id).stop_reason:
            break
        navigator.feedback(
            state.task_id,
            Feedback(
                candidate["id"],
                relevance="relevant" if candidate["symbol"] in relevant else "irrelevant",
                information_gain="high" if candidate["symbol"] in relevant else "low",
            ),
        )
    final = navigator.store.load(state.task_id)
    if not final.stop_reason:
        navigator.stop(
            state.task_id,
            "low_expected_gain",
            [final.selected[-1]] if final.selected else [],
        )
        final = navigator.store.load(state.task_id)
    target_hits = [
        hit
        for hit in final.discovery_hits.get(target.id, [])
        if hit.get("provider") == "bounded-text"
    ]
    return {
        "correct": found,
        "error_stop": not found,
        "stop_reason": final.stop_reason,
        "selected_symbols": selected,
        "selected_count": len(selected),
        "discovery_queries": len(final.discovery_queries),
        "discovery_tokens": final.discovery_tokens,
        "external_candidate_contribution": bool(target_hits),
        "external_rescue": found and bool(target_hits),
        "navigation_tokens": final.navigation_tokens,
        "expansion_tokens": final.expansion_tokens,
        "consumed_tokens": final.consumed_tokens,
        "within_budget": final.consumed_tokens <= final.total_budget,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def _run_repository(root: Path, cases: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agent-token-m2d-") as temporary:
        data_dir = Path(temporary) / "data"
        provider = TaskNavigator(root, data_dir, discovery_sources={}).provider
        started = time.perf_counter()
        provider.index()
        index_ms = round((time.perf_counter() - started) * 1000, 3)
        results = []
        for case in cases:
            m2c = run_case(root, data_dir, case, "m2c")
            m2d = run_m2d_case(root, data_dir, case)
            m2d["external_rescue"] = bool(
                not m2c["correct"]
                and m2d["correct"]
                and m2d["external_candidate_contribution"]
            )
            results.append(
                {
                    "id": case["id"],
                    "task": case["task"],
                    "target": case["target"],
                    "contains_code_identifier": has_code_identifier(case),
                    "static_top_k": run_static_case(root, data_dir, case),
                    "m2c": m2c,
                    "m2d_bounded_text": m2d,
                }
            )
    return {
        "repository": str(root),
        "case_count": len(results),
        "index_elapsed_ms": index_ms,
        "results": results,
    }


def run_benchmark(root: Path, secondary_root: Path | None = None) -> dict[str, Any]:
    repositories = [_run_repository(root, CASES)]
    if secondary_root is not None:
        repositories.append(_run_repository(secondary_root, SECONDARY_CASES))
    results = [item for repository in repositories for item in repository["results"]]
    m2c_correct = sum(item["m2c"]["correct"] for item in results)
    static_correct = sum(item["static_top_k"]["correct"] for item in results)
    m2d_correct = sum(item["m2d_bounded_text"]["correct"] for item in results)
    rescued = sum(item["m2d_bounded_text"]["external_rescue"] for item in results)
    regressions = sum(
        item["m2c"]["correct"] and not item["m2d_bounded_text"]["correct"]
        for item in results
    )
    added_tokens_on_prior_successes = [
        item["m2d_bounded_text"]["consumed_tokens"] - item["m2c"]["consumed_tokens"]
        for item in results
        if item["m2c"]["correct"]
    ]
    passed = (
        len(results) >= 5
        and all(not item["contains_code_identifier"] for item in results)
        and all(item["m2d_bounded_text"]["within_budget"] for item in results)
        and m2d_correct > m2c_correct
        and rescued >= 1
        and regressions == 0
    )
    return {
        "schema_version": 1,
        "benchmark": "m2c-vs-m2d-bounded-text-rescue",
        "status": "passed" if passed else "failed",
        "repository": str(root),
        "repositories": repositories,
        "case_count": len(results),
        "summary": {
            "m2c_correct": m2c_correct,
            "static_top_k_correct": static_correct,
            "m2d_correct": m2d_correct,
            "rescued": rescued,
            "regressions": regressions,
            "routing_regret_tokens": sum(max(0, value) for value in added_tokens_on_prior_successes),
            "routing_regret_queries": sum(
                item["m2d_bounded_text"]["discovery_queries"]
                for item in results
                if item["m2c"]["correct"]
            ),
            "marginal_tokens_per_rescue": round(
                sum(item["m2d_bounded_text"]["discovery_tokens"] for item in results) / rescued,
                3,
            )
            if rescued
            else None,
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--secondary-root", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = run_benchmark(
        args.root.expanduser().resolve(),
        args.secondary_root.expanduser().resolve() if args.secondary_root else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
