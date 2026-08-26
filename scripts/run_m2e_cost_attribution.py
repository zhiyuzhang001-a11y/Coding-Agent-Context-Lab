#!/usr/bin/env python3
"""Attribute M2e calibration orchestration costs without retaining source bodies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from m2e_events import _read_like_command, load_jsonl, summarize_usage


SCHEMA_VERSION = 1
METHOD = "chars_div_4_v1"
TASK_ACTION_RE = re.compile(r"task_navigator\.py[\"']?\s+(start|next|expand|feedback|discover|stop)\b")
MAP_ACTION_RE = re.compile(r"navigation_map\.py[\"']?\s+(index|query|status)\b")
EVIDENCE_RE = re.compile(r"--evidence\s+([^\s\"']+)")
MARKER_RE = re.compile(r"--marker-id\s+([^\s\"']+)")
TEST_RE = re.compile(r"(?:^|\s)(?:python\d*\s+-m\s+)?(?:pytest|unittest)\b|\btests?[/_.]", re.I)
EDIT_RE = re.compile(r"\bapply_patch\b|\bpatch\b|\b(?:perl|sed)\s+-i\b", re.I)


def estimated_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def completed_commands(events: Iterable[dict[str, Any]]) -> list[tuple[int, str, str]]:
    completed: list[tuple[int, str, str]] = []
    for sequence, event in enumerate(events):
        item: Any = None
        if event.get("type") in {"item.completed", "item_completed"}:
            item = event.get("item")
        else:
            payload = event.get("payload")
            if isinstance(payload, dict) and payload.get("type") in {
                "item.completed",
                "item_completed",
            }:
                item = payload.get("item")
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        command = str(item.get("command", ""))
        output = str(item.get("aggregated_output", item.get("output", "")))
        completed.append((sequence, command, output))
    return completed


def command_operations(command: str) -> list[str]:
    operations: list[str] = []
    if "skills/budgeted-code-reading/SKILL.md" in command:
        operations.append("skill_bootstrap")
    operations.extend(match.group(1) for match in MAP_ACTION_RE.finditer(command))
    operations.extend(match.group(1) for match in TASK_ACTION_RE.finditer(command))
    router_count = command.count("context_router.py") + command.count("smart_read.py")
    operations.extend("source_evidence" for _ in range(router_count))
    if operations:
        return operations
    if _read_like_command(command):
        return ["source_evidence"]
    if TEST_RE.search(command):
        return ["editing_and_tests"]
    if EDIT_RE.search(command):
        return ["editing_and_tests"]
    return ["other"]


def payload_bucket(operations: list[str]) -> str:
    distinct = set(operations)
    if len(distinct) > 1:
        return "compound"
    operation = operations[0]
    if operation == "expand":
        return "source_evidence"
    if operation in {"index", "query", "status", "start", "next", "feedback", "discover", "stop"}:
        return "navigation_metadata"
    return operation


def _case_oracle(manifest: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    return {
        str(case["id"]): {
            "paths": [str(value) for value in case.get("expected_paths", [])],
            "symbols": [str(value) for value in case.get("expected_symbols", [])],
        }
        for case in manifest.get("cases", [])
    }


def analyze_run(summary_path: Path, oracle: dict[str, dict[str, list[str]]]) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    raw_directory = Path(summary["raw_artifacts"]["directory"])
    events, invalid_lines = load_jsonl(raw_directory / "codex.jsonl")
    usage = summarize_usage(events)
    commands = completed_commands(events)
    case_oracle = oracle.get(str(summary.get("case_id")), {"paths": [], "symbols": []})

    final_evidence_ids: set[str] = set()
    for _, command, _ in commands:
        if "task_navigator.py" in command and " stop " in command:
            final_evidence_ids.update(EVIDENCE_RE.findall(command))

    output_counts = Counter(sha256_text(output) for _, _, output in commands)
    output_seen: Counter[str] = Counter()
    source_commands: Counter[str] = Counter()
    invocation_counts: Counter[str] = Counter()
    payload_tokens: Counter[str] = Counter()
    payload_calls: Counter[str] = Counter()
    trace: list[dict[str, Any]] = []
    duplicate_payload_count = 0
    duplicate_payload_tokens = 0
    repeated_source_count = 0
    repeated_source_tokens = 0
    effective_evidence_count = 0
    effective_evidence_tokens = 0

    for sequence, command, output in commands:
        operations = command_operations(command)
        invocation_counts.update(operations)
        bucket = payload_bucket(operations)
        tokens = estimated_tokens(output)
        payload_calls[bucket] += 1
        payload_tokens[bucket] += tokens

        output_hash = sha256_text(output)
        duplicate_payload = output_seen[output_hash] > 0
        output_seen[output_hash] += 1
        if duplicate_payload:
            duplicate_payload_count += 1
            duplicate_payload_tokens += tokens

        source_like = bucket == "source_evidence" or "source_evidence" in operations
        command_hash = sha256_text(command)
        repeated_source = source_like and source_commands[command_hash] > 0
        if source_like:
            source_commands[command_hash] += 1
        if repeated_source:
            repeated_source_count += 1
            repeated_source_tokens += tokens

        marker_ids = MARKER_RE.findall(command)
        final_marker_match = bool(set(marker_ids) & final_evidence_ids)
        oracle_match = any(value and value in output for value in case_oracle["paths"] + case_oracle["symbols"])
        effective_evidence = source_like and (final_marker_match or oracle_match)
        if effective_evidence:
            effective_evidence_count += 1
            effective_evidence_tokens += tokens

        trace.append(
            {
                "sequence": sequence,
                "command_sha256": command_hash,
                "output_sha256": output_hash,
                "output_chars": len(output),
                "estimated_output_tokens": tokens,
                "operations": operations,
                "payload_bucket": bucket,
                "duplicate_model_visible_payload": duplicate_payload,
                "repeated_source_command": repeated_source,
                "effective_evidence": effective_evidence,
                "effective_evidence_basis": (
                    "final_marker_and_oracle"
                    if final_marker_match and oracle_match
                    else "final_marker"
                    if final_marker_match
                    else "oracle_text_match"
                    if oracle_match
                    else "none"
                ),
            }
        )

    estimated_payload_total = sum(payload_tokens.values())
    total_tokens = int(usage.get("total_tokens", 0))
    return {
        "run_id": summary["run_id"],
        "case_id": summary["case_id"],
        "kind": summary["kind"],
        "arm": summary["arm"],
        "repetition": summary["repetition"],
        "success": summary["success"],
        "source_summary": str(summary_path),
        "invalid_jsonl_lines": invalid_lines,
        "model_usage": usage,
        "completed_command_results": len(commands),
        "operation_invocations": dict(sorted(invocation_counts.items())),
        "payload_calls": dict(sorted(payload_calls.items())),
        "estimated_payload_tokens": dict(sorted(payload_tokens.items())),
        "estimated_payload_total_tokens": estimated_payload_total,
        "estimated_payload_share_of_model_total": (
            round(estimated_payload_total / total_tokens, 6) if total_tokens else None
        ),
        "unallocated_model_usage_residual": max(0, total_tokens - estimated_payload_total),
        "duplicate_model_visible_payload": {
            "count": duplicate_payload_count,
            "estimated_tokens": duplicate_payload_tokens,
            "method": "exact completed-output sha256; empty started events excluded",
        },
        "duplicate_source_read": {
            "count": repeated_source_count,
            "estimated_tokens": repeated_source_tokens,
            "method": "exact source-command sha256 within one run",
        },
        "effective_evidence": {
            "count": effective_evidence_count,
            "estimated_tokens": effective_evidence_tokens,
            "method": "final evidence marker or calibration oracle text match; diagnostic only",
        },
        "trace": trace,
    }


def select_latest_successful(artifacts: Path) -> list[Path]:
    selected: dict[tuple[str, int, str], tuple[str, Path]] = {}
    for path in artifacts.glob("*/**/summary.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not value.get("success"):
            continue
        key = (str(value.get("case_id")), int(value.get("repetition", 0)), str(value.get("arm")))
        batch = path.parent.parent.name
        previous = selected.get(key)
        if previous is None or batch > previous[0]:
            selected[key] = (batch, path)
    return [selected[key][1] for key in sorted(selected)]


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    arms: dict[str, Any] = {}
    for arm in ("native", "m2d"):
        members = [run for run in runs if run["arm"] == arm]
        invocations: Counter[str] = Counter()
        payloads: Counter[str] = Counter()
        for run in members:
            invocations.update(run["operation_invocations"])
            payloads.update(run["estimated_payload_tokens"])
        totals = [run["model_usage"]["total_tokens"] for run in members]
        arms[arm] = {
            "run_count": len(members),
            "model_total_tokens": sum(totals),
            "model_median_tokens": statistics.median(totals) if totals else None,
            "completed_command_results": sum(run["completed_command_results"] for run in members),
            "operation_invocations": dict(sorted(invocations.items())),
            "estimated_payload_tokens": dict(sorted(payloads.items())),
            "estimated_payload_total_tokens": sum(run["estimated_payload_total_tokens"] for run in members),
            "duplicate_model_visible_payload_count": sum(
                run["duplicate_model_visible_payload"]["count"] for run in members
            ),
            "duplicate_model_visible_payload_tokens": sum(
                run["duplicate_model_visible_payload"]["estimated_tokens"] for run in members
            ),
            "duplicate_source_read_count": sum(run["duplicate_source_read"]["count"] for run in members),
            "effective_evidence_tokens": sum(run["effective_evidence"]["estimated_tokens"] for run in members),
        }

    pairs: list[dict[str, Any]] = []
    grouped: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for run in runs:
        grouped[(run["case_id"], run["repetition"])][run["arm"]] = run
    for (case_id, repetition), members in sorted(grouped.items()):
        if set(members) != {"native", "m2d"}:
            continue
        native = members["native"]["model_usage"]["total_tokens"]
        m2d = members["m2d"]["model_usage"]["total_tokens"]
        pairs.append(
            {
                "case_id": case_id,
                "repetition": repetition,
                "native_total_tokens": native,
                "m2d_total_tokens": m2d,
                "ratio": round(m2d / native, 6) if native else None,
            }
        )
    ratios = [pair["ratio"] for pair in pairs if pair["ratio"] is not None]
    native = arms["native"]
    m2d = arms["m2d"]
    model_regret = m2d["model_total_tokens"] - native["model_total_tokens"]
    payload_regret = m2d["estimated_payload_total_tokens"] - native["estimated_payload_total_tokens"]
    extra_results = m2d["completed_command_results"] - native["completed_command_results"]
    return {
        "arms": arms,
        "pairs": pairs,
        "paired_ratio_median": statistics.median(ratios) if ratios else None,
        "comparison": {
            "model_total_token_regret": model_regret,
            "estimated_one_time_payload_token_regret": payload_regret,
            "payload_regret_share_of_model_regret": (
                round(payload_regret / model_regret, 6) if model_regret else None
            ),
            "extra_completed_command_results": extra_results,
            "model_regret_per_extra_command_result": (
                round(model_regret / extra_results, 3) if extra_results else None
            ),
            "interpretation": (
                "descriptive only: repeated model inference over accumulated context is not "
                "separately observable and requires roundtrip ablation"
            ),
        },
    }


def build_attribution(
    summary_paths: list[Path], manifest_path: Path
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    oracle = _case_oracle(manifest)
    runs = [analyze_run(path, oracle) for path in summary_paths]
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark": "m2e-0.1a-cost-attribution",
        "measurement_contract": {
            "model_total": "final cumulative input_tokens + output_tokens",
            "payload_tokens": METHOD,
            "operation_usage": "unavailable: session exposes only final cumulative model usage",
            "causal_attribution": "requires ablation; payload shares are descriptive",
            "privacy": "trace stores hashes, sizes, labels and booleans; no command or output bodies",
        },
        "selection": "latest successful summary for each case/repetition/arm",
        "runs": runs,
        "aggregate": aggregate_runs(runs),
    }


def main() -> int:
    plugin = Path(__file__).resolve().parents[1]
    repository = plugin.parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=repository / ".agent-token-manager" / "m2e-calibration",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=plugin / "resources" / "m2e_calibration_cases.json",
    )
    parser.add_argument("--summary", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    summaries = [path.resolve() for path in args.summary]
    if not summaries:
        summaries = select_latest_successful(args.artifacts.resolve())
    if not summaries:
        parser.error("no successful M2e summaries found")
    result = build_attribution(summaries, args.manifest.resolve())
    encoded = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        try:
            args.output.chmod(0o600)
        except OSError:
            pass
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
