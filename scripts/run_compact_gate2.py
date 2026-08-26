#!/usr/bin/env python3
"""Run Compact Navigator against the frozen M2d no-identifier quality gate."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

from ast_navigation_provider import estimate_tokens
from compact_navigator import CompactNavigator
from run_m2c_benchmark import CASES, has_code_identifier
from run_m2d_benchmark import SECONDARY_CASES
from task_navigator import TaskNavigator


FROZEN_SERENA_COMMIT = "3ad624f511511bb7a77447e413425198fc574349"
FROZEN_M2D_COMMIT = "4af5900"
FROZEN_M2D_FAILURES = {"environment-diagnostics"}
FROZEN_RESCUE_CASES = {"configured-tool-validation", "read-only-tool-set"}
COMPACT_PARAMETERS = {
    "total_budget": 8400,
    "navigation_budget": 2400,
    "expansion_budget": 6000,
    "model_visible_budget": 1600,
    "max_steps": 8,
    "max_fanout": 8,
    "max_hops": 2,
    "max_source_reads": 8,
    "max_elapsed_ms": 5000,
}


def _evidence_ref(evidence: dict[str, Any]) -> str:
    return f"{evidence['evidence_id']}={evidence['hash']}"


def evidence_hits_target(evidence: dict[str, Any], case: dict[str, Any]) -> bool:
    return evidence.get("path") == case["path"] and evidence.get("symbol") == case["target"]


def classify_evidence(
    evidence: Iterable[dict[str, Any]],
    case: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """Use the benchmark oracle only after evidence has been returned."""
    relevant = set(case["relevant"])
    accepted: list[str] = []
    rejected: list[str] = []
    uncertain: list[str] = []
    for item in evidence:
        reference = _evidence_ref(item)
        if evidence_hits_target(item, case):
            accepted.append(reference)
        elif item.get("symbol") in relevant:
            accepted.append(reference)
        else:
            rejected.append(reference)
    return accepted, rejected, uncertain


def _regression_reason(
    correct: bool,
    first: dict[str, Any],
    state: Any,
    target_marker_id: str,
) -> str | None:
    if correct:
        return None
    if first["phase"] == "completed" and first.get("stop_reason") == "evidence_sufficient":
        return "false_structural_completion"
    target_expanded = any(key.startswith(f"{target_marker_id}:") for key in state.expanded)
    if target_marker_id in state.selected or target_expanded:
        return "evidence_not_packaged"
    if state.external_call_count == 2:
        return "verification_supplement_failed"
    return "candidate_not_reached"


def run_compact_case(
    root: Path,
    data_dir: Path,
    case: dict[str, Any],
    repository_label: str,
) -> dict[str, Any]:
    compact = CompactNavigator(root, data_dir)
    markers = compact.navigator.provider.store.load_markers(compact.navigator.provider.name)
    target = next(marker for marker in markers if marker.symbol == case["target"])
    request_id = f"compact-gate2-{repository_label}-{case['id']}"
    started = time.perf_counter()
    first = compact.navigate(case["task"], request_id, **COMPACT_PARAMETERS)
    packages = [first]
    if first["phase"] == "needs_verification":
        accepted, rejected, uncertain = classify_evidence(first["evidence"], case)
        target_in_first = any(evidence_hits_target(item, case) for item in first["evidence"])
        second = compact.verify(
            first["task_id"],
            f"{request_id}-verify",
            accepted_evidence=accepted,
            rejected_evidence=rejected,
            uncertain_evidence=uncertain,
            missing_questions=[]
            if target_in_first
            else ["Which returned or adjacent implementation directly satisfies the task?"],
        )
        packages.append(second)
    state = compact.navigator.store.load(first["task_id"])
    visible_evidence = [item for package in packages for item in package.get("evidence", [])]
    unique_evidence = {
        (item["evidence_id"], item["hash"]): item
        for item in visible_evidence
    }
    correct = any(evidence_hits_target(item, case) for item in unique_evidence.values())
    target_expanded = any(key.startswith(f"{target.id}:") for key in state.expanded)
    target_discovery_hits = [
        hit
        for hit in state.discovery_hits.get(target.id, [])
        if hit.get("provider") == "bounded-text"
    ]
    model_visible_tokens = sum(
        int(package.get("budget", {}).get("model_visible_tokens", estimate_tokens(package)))
        for package in packages
        if package.get("status") == "ok"
    )
    return {
        "id": case["id"],
        "task": case["task"],
        "target": case["target"],
        "path": case["path"],
        "contains_code_identifier": has_code_identifier(case),
        "frozen_m2d_success": case["id"] not in FROZEN_M2D_FAILURES,
        "frozen_rescue_case": case["id"] in FROZEN_RESCUE_CASES,
        "correct": correct,
        "target_selected": target.id in state.selected,
        "target_expanded": target_expanded,
        "regression_reason": _regression_reason(correct, first, state, target.id),
        "phase_path": [package.get("phase") for package in packages],
        "external_calls": state.external_call_count,
        "internal_steps": len(state.selected),
        "source_reads": len(state.expanded),
        "evidence_count": len(unique_evidence),
        "evidence_tokens": sum(estimate_tokens(item.get("code", "")) for item in unique_evidence.values()),
        "model_visible_payload_tokens": model_visible_tokens,
        "navigation_tokens": state.navigation_tokens,
        "expansion_tokens": state.expansion_tokens,
        "consumed_tokens": state.consumed_tokens,
        "within_internal_budget": state.consumed_tokens <= state.total_budget,
        "within_model_visible_budget": all(
            package.get("budget", {}).get("model_visible_tokens", 0)
            <= package.get("budget", {}).get("model_visible_budget", 0)
            for package in packages
            if package.get("status") == "ok"
        ),
        "max_recorded_hop": max(state.compact_marker_hops.values(), default=0),
        "discovery_queries": len(state.discovery_queries),
        "bounded_text_target_hit": bool(target_discovery_hits),
        "stop_reason": state.stop_reason,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "visible_symbols": [item.get("symbol") for item in unique_evidence.values()],
    }


def _run_repository(
    root: Path,
    cases: tuple[dict[str, Any], ...],
    label: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"agent-token-compact-gate2-{label}-") as temporary:
        data_dir = Path(temporary) / "data"
        provider = TaskNavigator(root, data_dir, discovery_sources={}).provider
        started = time.perf_counter()
        provider.index()
        index_elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        results = [run_compact_case(root, data_dir, case, label) for case in cases]
    return {
        "label": label,
        "repository": str(root),
        "index_elapsed_ms": index_elapsed_ms,
        "results": results,
    }


def run_gate2(serena_root: Path, manager_root: Path) -> dict[str, Any]:
    repositories = [
        _run_repository(serena_root, CASES, "serena"),
        _run_repository(manager_root, SECONDARY_CASES, "agent-token-manager"),
    ]
    results = [item for repository in repositories for item in repository["results"]]
    prior_successes = [item for item in results if item["frozen_m2d_success"]]
    regressions = [item["id"] for item in prior_successes if not item["correct"]]
    rescue_regressions = [
        item["id"] for item in results if item["frozen_rescue_case"] and not item["correct"]
    ]
    protocol_violations = [
        item["id"]
        for item in results
        if item["external_calls"] > 2
        or not item["within_internal_budget"]
        or not item["within_model_visible_budget"]
        or not item["stop_reason"]
        or item["max_recorded_hop"] > COMPACT_PARAMETERS["max_hops"]
    ]
    passed = (
        len(results) == 10
        and all(not item["contains_code_identifier"] for item in results)
        and len(prior_successes) == 9
        and not regressions
        and not rescue_regressions
        and not protocol_violations
    )
    return {
        "schema_version": 1,
        "benchmark": "m2e-0.1b-compact-gate2",
        "status": "passed" if passed else "failed",
        "frozen_conditions": {
            "m2d_commit": FROZEN_M2D_COMMIT,
            "serena_commit": FROZEN_SERENA_COMMIT,
            "compact_parameters": COMPACT_PARAMETERS,
            "oracle_policy": "post-return evidence classification only",
        },
        "repositories": repositories,
        "summary": {
            "case_count": len(results),
            "compact_correct": sum(item["correct"] for item in results),
            "frozen_success_preserved": sum(item["correct"] for item in prior_successes),
            "frozen_success_total": len(prior_successes),
            "regressions": regressions,
            "rescue_regressions": rescue_regressions,
            "protocol_violations": protocol_violations,
            "one_call_tasks": sum(item["external_calls"] == 1 for item in results),
            "two_call_tasks": sum(item["external_calls"] == 2 for item in results),
            "max_external_calls": max((item["external_calls"] for item in results), default=0),
            "total_internal_steps": sum(item["internal_steps"] for item in results),
            "total_source_reads": sum(item["source_reads"] for item in results),
            "total_model_visible_payload_tokens": sum(
                item["model_visible_payload_tokens"] for item in results
            ),
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("serena_root", type=Path)
    parser.add_argument("--manager-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = run_gate2(
        args.serena_root.expanduser().resolve(),
        args.manager_root.expanduser().resolve(),
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
