#!/usr/bin/env python3
"""Extract privacy-safe host cycle observations and build a fact-only cost analysis."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


OBSERVATION_SCHEMA_ID = "cycle-cost-observations-v1"
ANALYSIS_SCHEMA_ID = "model-cycle-cost-analysis-v1"
EXTRACTOR_VERSION = "acp-cycle-cost-v0.1"
USAGE_KEYS = (
    "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
    "output_tokens", "reasoning_output_tokens", "total_tokens",
)
ARMS = ("off", "on")
MINIMUM_DESCRIPTIVE_SAMPLE = 5
REPETITION_SUFFIX = re.compile(r"__r\d+$")


class CycleCostError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _load_lines(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(USAGE_KEYS):
        raise CycleCostError("usage_keys_not_frozen")
    result: dict[str, int] = {}
    for key in USAGE_KEYS:
        item = value[key]
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise CycleCostError("invalid_usage_counter")
        result[key] = item
    if result["total_tokens"] != result["input_tokens"] + result["output_tokens"]:
        raise CycleCostError("total_token_identity_failed")
    if result["cached_input_tokens"] > result["input_tokens"]:
        raise CycleCostError("cached_input_not_subset")
    return result


def _transcript_identity(events: list[dict[str, Any]]) -> tuple[str, str, list[dict[str, int]]]:
    metas = [row.get("payload") for row in events if row.get("type") == "session_meta"]
    if len(metas) != 1 or not isinstance(metas[0], dict):
        raise CycleCostError("transcript_session_meta_not_unique")
    identity = metas[0].get("id") or metas[0].get("session_id")
    version = metas[0].get("cli_version")
    if not isinstance(identity, str) or not identity or not isinstance(version, str) or not version:
        raise CycleCostError("transcript_identity_or_version_missing")
    series: list[dict[str, int]] = []
    for row in events:
        payload = row.get("payload")
        if row.get("type") != "event_msg" or not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        usage = info.get("total_token_usage") if isinstance(info, dict) else None
        if isinstance(usage, dict):
            series.append(_usage(usage))
    if not series:
        raise CycleCostError("transcript_has_no_usage_snapshot")
    return identity, version, series


def _thread_identity(events: list[dict[str, Any]]) -> str:
    identities = [row.get("thread_id") for row in events if row.get("type") == "thread.started"]
    if len(identities) != 1 or not isinstance(identities[0], str) or not identities[0]:
        raise CycleCostError("exec_thread_identity_not_unique")
    return identities[0]


def _subtract(current: dict[str, int], previous: dict[str, int] | None) -> dict[str, int]:
    result = {key: current[key] - (previous[key] if previous else 0) for key in USAGE_KEYS}
    if any(value < 0 for value in result.values()):
        raise CycleCostError("cumulative_usage_not_monotonic")
    if result["total_tokens"] != result["input_tokens"] + result["output_tokens"]:
        raise CycleCostError("incremental_total_token_identity_failed")
    return result


def extract_private_runs(private_root: Path) -> dict[str, Any]:
    private_root = private_root.resolve()
    summary_path = private_root / "summary.json"
    if not summary_path.is_file():
        raise CycleCostError("private_summary_missing")
    transcript_by_id: dict[str, tuple[Path, str, list[dict[str, int]]]] = {}
    inventory: list[dict[str, str]] = []
    for path in sorted(private_root.glob("codex-home-*/sessions/**/*.jsonl")):
        identity, version, series = _transcript_identity(_load_lines(path))
        if identity in transcript_by_id:
            raise CycleCostError("duplicate_transcript_identity")
        transcript_by_id[identity] = (path, version, series)
        inventory.append({"kind": "transcript", "sha256": sha256_file(path)})

    public_runs: list[dict[str, Any]] = []
    used_transcripts: set[str] = set()
    models: set[str] = set()
    efforts: set[str] = set()
    commits: set[str] = set()
    versions: set[str] = set()
    for run_dir in sorted(path for path in private_root.iterdir() if path.is_dir() and (path / "result.json").is_file()):
        result_path = run_dir / "result.json"
        exec_path = run_dir / "codex.jsonl"
        if not exec_path.is_file():
            raise CycleCostError("run_exec_jsonl_missing")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "completed" or result.get("arm") not in ARMS:
            raise CycleCostError("run_not_completed_or_arm_invalid")
        thread_id = _thread_identity(_load_lines(exec_path))
        if thread_id not in transcript_by_id or thread_id in used_transcripts:
            raise CycleCostError("thread_transcript_linkage_not_exact_unique")
        transcript_path, version, series = transcript_by_id[thread_id]
        used_transcripts.add(thread_id)
        versions.add(version)
        models.add(str(result.get("model")))
        efforts.add(str(result.get("reasoning_effort")))
        commits.add(str(result.get("subject_commit")))
        if result.get("model_cycles") != len(series):
            raise CycleCostError("frozen_cycle_count_mismatch")
        frozen_usage = _usage(result.get("usage"))
        if series[-1] != frozen_usage:
            raise CycleCostError("final_usage_mismatch")
        cycles = []
        previous = None
        for ordinal, cumulative in enumerate(series, start=1):
            incremental = _subtract(cumulative, previous)
            cycles.append({"ordinal": ordinal, "cumulative_usage": cumulative, "incremental_usage": incremental})
            previous = cumulative
        source_pair_sha256 = sha256_bytes(canonical_bytes({
            "result_sha256": sha256_file(result_path),
            "exec_sha256": sha256_file(exec_path),
            "transcript_sha256": sha256_file(transcript_path),
        }))
        case_id = result.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise CycleCostError("case_id_missing")
        base_case_id = REPETITION_SUFFIX.sub("", case_id)
        public_runs.append({
            "run_id_hash": sha256_bytes(("acp1-3a-run-v1\0" + thread_id).encode("utf-8")),
            "case_id": base_case_id,
            "arm": result["arm"],
            "cycle_count": len(cycles),
            "cycles": cycles,
            "source_pair_sha256": source_pair_sha256,
        })
        inventory.extend((
            {"kind": "result", "sha256": sha256_file(result_path)},
            {"kind": "exec", "sha256": sha256_file(exec_path)},
        ))
    if len(used_transcripts) != len(public_runs):
        raise CycleCostError("run_transcript_coverage_incomplete")
    if len(models) != 1 or len(efforts) != 1 or len(commits) != 1 or len(versions) != 1:
        raise CycleCostError("source_provenance_not_uniform")
    public_runs.sort(key=lambda row: (row["arm"], row["case_id"], row["run_id_hash"]))
    arm_counts = Counter(row["arm"] for row in public_runs)
    return {
        "schema_version": 1,
        "schema_id": OBSERVATION_SCHEMA_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "source_summary": {
            "run_count": len(public_runs),
            "exact_linked_run_count": len(public_runs),
            "arm_counts": {arm: arm_counts[arm] for arm in ARMS},
            "case_count": len({row["case_id"] for row in public_runs}),
            "case_ids": sorted({row["case_id"] for row in public_runs}),
            "model_identifier": next(iter(models)),
            "reasoning_effort": next(iter(efforts)),
            "subject_commit": next(iter(commits)),
            "codex_version": next(iter(versions)),
            "private_summary_sha256": sha256_file(summary_path),
            "private_source_inventory_sha256": sha256_bytes(canonical_bytes(sorted(inventory, key=lambda row: (row["kind"], row["sha256"])))),
        },
        "runs": public_runs,
        "policy": {
            "exact_id_linkage_only": True,
            "timestamp_linkage": False,
            "private_bodies_emitted": False,
            "absolute_paths_emitted": False,
            "raw_session_identifiers_emitted": False,
            "online_effect": False,
        },
    }


def _number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(value, 12)


def _stats(values: list[float | int]) -> dict[str, Any]:
    if not values:
        raise CycleCostError("empty_distribution")
    return {
        "count": len(values), "min": min(values), "median": _number(statistics.median(values)),
        "mean": _number(statistics.mean(values)), "max": max(values),
    }


def _sample_status(count: int) -> str:
    return "sufficient_descriptive_sample" if count >= MINIMUM_DESCRIPTIVE_SAMPLE else "insufficient_descriptive_sample"


def _arm_analysis(runs: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    selected = [row for row in runs if row["arm"] == arm]
    if not selected:
        raise CycleCostError("arm_has_no_runs")
    count_groups = []
    for count in sorted({row["cycle_count"] for row in selected}):
        members = [row for row in selected if row["cycle_count"] == count]
        totals = [row["cycles"][-1]["cumulative_usage"]["total_tokens"] for row in members]
        count_groups.append({
            "cycle_count": count, "run_count": len(members), "sample_status": _sample_status(len(members)),
            "session_total_tokens": _stats(totals),
        })
    ordinal_costs = []
    maximum = max(row["cycle_count"] for row in selected)
    for ordinal in range(1, maximum + 1):
        cycles = [row["cycles"][ordinal - 1] for row in selected if row["cycle_count"] >= ordinal]
        ordinal_costs.append({
            "ordinal": ordinal,
            "run_count": len(cycles),
            "coverage_ratio": round(len(cycles) / len(selected), 12),
            "sample_status": _sample_status(len(cycles)),
            "incremental_usage": {key: _stats([row["incremental_usage"][key] for row in cycles]) for key in USAGE_KEYS},
            "cumulative_usage": {key: _stats([row["cumulative_usage"][key] for row in cycles]) for key in USAGE_KEYS},
        })
    transitions = []
    for later in range(2, maximum + 1):
        pairs = [(row["cycles"][later - 2], row["cycles"][later - 1]) for row in selected if row["cycle_count"] >= later]
        deltas = [b["incremental_usage"]["total_tokens"] - a["incremental_usage"]["total_tokens"] for a, b in pairs]
        ratios = [b["incremental_usage"]["total_tokens"] / a["incremental_usage"]["total_tokens"] for a, b in pairs]
        transitions.append({
            "from_ordinal": later - 1, "to_ordinal": later, "run_count": len(pairs),
            "sample_status": _sample_status(len(pairs)),
            "incremental_total_token_delta": _stats(deltas),
            "incremental_total_token_ratio": _stats(ratios),
        })
    cases = []
    for case_id in sorted({row["case_id"] for row in selected}):
        members = [row for row in selected if row["case_id"] == case_id]
        cases.append({
            "case_id": case_id, "run_count": len(members),
            "cycle_count_distribution": {str(key): value for key, value in sorted(Counter(row["cycle_count"] for row in members).items())},
            "session_total_tokens": _stats([row["cycles"][-1]["cumulative_usage"]["total_tokens"] for row in members]),
        })
    return {
        "arm": arm, "role": "primary_native_analysis" if arm == "off" else "independent_replication",
        "run_count": len(selected), "cycle_count_groups": count_groups,
        "cycle_ordinal_costs": ordinal_costs, "within_run_transitions": transitions,
        "case_strata": cases,
    }


def analyze_observations(observations: Any) -> dict[str, Any]:
    original = copy.deepcopy(observations)
    if not isinstance(observations, dict) or observations.get("schema_id") != OBSERVATION_SCHEMA_ID:
        raise CycleCostError("input_must_be_cycle_cost_observations_v1")
    if not observations.get("policy", {}).get("exact_id_linkage_only") or observations.get("policy", {}).get("online_effect"):
        raise CycleCostError("observation_policy_not_frozen")
    runs = observations.get("runs")
    if not isinstance(runs, list) or not runs:
        raise CycleCostError("observation_runs_missing")
    for row in runs:
        if row.get("cycle_count") != len(row.get("cycles", [])):
            raise CycleCostError("observation_cycle_count_mismatch")
        previous = None
        for expected_ordinal, cycle in enumerate(row["cycles"], start=1):
            if cycle.get("ordinal") != expected_ordinal:
                raise CycleCostError("observation_cycle_ordinal_mismatch")
            cumulative = _usage(cycle.get("cumulative_usage"))
            incremental = _usage(cycle.get("incremental_usage"))
            if incremental != _subtract(cumulative, previous):
                raise CycleCostError("observation_increment_mismatch")
            previous = cumulative
    arms = [_arm_analysis(runs, arm) for arm in ARMS]
    result = {
        "schema_version": 1,
        "schema_id": ANALYSIS_SCHEMA_ID,
        "analyzer_version": EXTRACTOR_VERSION,
        "source_and_scope": {
            "observations_sha256": sha256_bytes(canonical_bytes(observations)),
            "source_experiment": "acp0-4a-repeat5-20260817",
            "primary_arm": "off", "replication_arm": "on",
            "arms_pooled": False, "minimum_descriptive_sample": MINIMUM_DESCRIPTIVE_SAMPLE,
        },
        "cycle_semantics": {
            "identity": "ordered_host_cumulative_usage_snapshot",
            "linkage_basis": "exact_thread_id_equals_session_meta_id",
            "increment_rule": "first_equals_cumulative_then_current_minus_previous",
            "total_token_identity": "input_tokens_plus_output_tokens",
            "cached_input_is_subset_not_history_attribution": True,
        },
        "coverage": {
            "source_run_count": observations["source_summary"]["run_count"],
            "exact_linked_run_count": observations["source_summary"]["exact_linked_run_count"],
            "exact_linkage_ratio": round(observations["source_summary"]["exact_linked_run_count"] / observations["source_summary"]["run_count"], 12),
            "arm_counts": observations["source_summary"]["arm_counts"],
            "case_count": observations["source_summary"]["case_count"],
            "usage_snapshot_count": sum(row["cycle_count"] for row in runs),
            "status": "complete",
        },
        "arm_analyses": arms,
        "unknowns": {
            "new_content_tokens": "unknown", "historical_context_tokens": "unknown",
            "semantic_history_reprocessing": "unknown", "counterfactual_added_cycle_cost": "unknown",
            "necessity": "unknown", "avoidability": "unknown",
        },
        "traceability": [
            {"output_path": "/coverage", "source_path": "/source_summary"},
            {"output_path": "/arm_analyses", "source_path": "/runs"},
            {"output_path": "/unknowns", "source_path": "/policy"},
        ],
        "policy": {
            "fact_only": True, "descriptive_not_causal": True, "no_waste_or_savings_estimate": True,
            "no_intervention": True, "no_online_effect": True, "insufficient_samples_retained": True,
            "canonical_fact_source": "json",
        },
    }
    if observations != original:
        raise CycleCostError("input_mutation_detected")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_root", type=Path)
    parser.add_argument("--analysis", action="store_true")
    args = parser.parse_args()
    observations = extract_private_runs(args.private_root)
    value = analyze_observations(observations) if args.analysis else observations
    print(canonical_bytes(value).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
