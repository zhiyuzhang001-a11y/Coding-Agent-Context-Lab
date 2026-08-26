#!/usr/bin/env python3
"""Run the frozen ACP-0.4 task set repeatedly and attribute path versus cost variance."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import run_acp0_4 as base
from run_co1_gate2 import git_output


SCHEMA_ID = "acp0-4a-variance-attribution-v1"
REPETITIONS = 5
TOOL_ENTRY_RATE_DELTA = 0.10
MEAN_CALL_OR_CYCLE_DELTA = 0.25
CASE_DIRECTION_COUNT = 8
MIN_CONDITIONAL_COVERAGE = 0.50


def describe(values: list[int | float]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None, "mad": None}
    median = statistics.median(values)
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 6),
        "median": median,
        "min": min(values),
        "max": max(values),
        "mad": statistics.median(abs(value - median) for value in values),
    }


def path_signature(run: dict[str, Any]) -> str:
    value = {
        "tool_entry": int(run.get("tool_call_count", 0)) > 0,
        "tool_call_count": int(run.get("tool_call_count", 0)),
        "model_cycle_count": int(run.get("model_cycles", 0)),
        "tool_family_sequence": list(run.get("tool_families", [])),
    }
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def run_schedule(cases: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any], str]]:
    schedule = []
    for repetition in range(1, REPETITIONS + 1):
        offset = (repetition - 1) % len(cases)
        ordered = cases[offset:] + cases[:offset]
        for case in ordered:
            arms = list(case["order"])
            if repetition % 2 == 0:
                arms.reverse()
            for arm in arms:
                schedule.append((repetition, case, arm))
    return schedule


def load_existing_result(path: Path, case: dict[str, Any], repetition: int, arm: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("arm") != arm or result.get("expected") != case["expected"]:
        raise RuntimeError(f"existing result identity mismatch: {path}")
    result["base_case_id"] = case["id"]
    result["repetition"] = repetition
    return result


def prepare_homes(lab: Path, artifacts: Path, codex: Path, source_home: Path) -> dict[str, Path]:
    auth = source_home / "auth.json"
    if not auth.is_file():
        raise RuntimeError(f"Codex auth missing: {auth}")
    homes = {}
    for arm in base.ARMS:
        home = artifacts / f"codex-home-{arm}"
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        auth_link = home / "auth.json"
        if not auth_link.exists():
            auth_link.symlink_to(auth)
        config = "" if arm == "off" else (
            "[marketplaces.acp0-4-lab]\n" f"source_type = \"local\"\nsource = {json.dumps(str(lab))}\n\n"
            "[plugins.\"acp-observe-only@acp0-4-lab\"]\nenabled = true\n"
        )
        (home / "config.toml").write_text(config, encoding="utf-8")
        if arm == "on":
            completed = subprocess.run(
                [str(codex), "plugin", "add", "acp-observe-only@acp0-4-lab"],
                env=dict(os.environ, CODEX_HOME=str(home)), text=True, capture_output=True, timeout=90,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        homes[arm] = home
    return homes


def fresh_host_probes(collector: Path, workspace: Path) -> dict[str, Any]:
    """Run idempotent preflight probes without retaining a prior resume's events."""
    if workspace.exists():
        shutil.rmtree(workspace)
    return base.run_host_probes(collector, workspace)


def summarize(
    manifest: dict[str, Any], runs: list[dict[str, Any]], host_probes: dict[str, Any]
) -> dict[str, Any]:
    expected_count = len(manifest["cases"]) * len(base.ARMS) * REPETITIONS
    by_case_arm: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        by_case_arm[(run["base_case_id"], run["arm"])].append(run)

    case_rows = []
    case_call_higher = 0
    case_cycle_higher = 0
    conditional_pairs: list[tuple[int, int]] = []
    conditional_strata = []
    for case in manifest["cases"]:
        arm_rows = {}
        paths: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"off": [], "on": []})
        for arm in base.ARMS:
            members = sorted(by_case_arm[(case["id"], arm)], key=lambda item: item["repetition"])
            for member in members:
                paths[path_signature(member)][arm].append(member)
            tokens = [int(item.get("usage", {}).get("total_tokens", 0)) for item in members]
            calls = [int(item.get("tool_call_count", 0)) for item in members]
            cycles = [int(item.get("model_cycles", 0)) for item in members]
            entries = [value > 0 for value in calls]
            arm_rows[arm] = {
                "run_count": len(members), "correct_count": sum(bool(item.get("correct")) for item in members),
                "token_distribution": describe(tokens), "tool_call_distribution": describe(calls),
                "model_cycle_distribution": describe(cycles),
                "tool_entry_count": sum(entries), "tool_entry_rate": round(sum(entries) / len(entries), 6) if entries else None,
                "path_signature_counts": dict(sorted(Counter(path_signature(item) for item in members).items())),
            }
        if arm_rows["on"]["tool_call_distribution"]["mean"] > arm_rows["off"]["tool_call_distribution"]["mean"]:
            case_call_higher += 1
        if arm_rows["on"]["model_cycle_distribution"]["mean"] > arm_rows["off"]["model_cycle_distribution"]["mean"]:
            case_cycle_higher += 1

        for signature, members in sorted(paths.items()):
            off = sorted(int(item["usage"]["total_tokens"]) for item in members["off"])
            on = sorted(int(item["usage"]["total_tokens"]) for item in members["on"])
            count = min(len(off), len(on))
            if count:
                selected_off, selected_on = off[:count], on[:count]
                conditional_pairs.extend(zip(selected_off, selected_on))
                conditional_strata.append({
                    "case_id": case["id"], "path_signature": json.loads(signature),
                    "off_count": len(off), "on_count": len(on), "matched_count_per_arm": count,
                    "off_token_distribution": describe(off), "on_token_distribution": describe(on),
                    "matched_pooled_ratio": sum(selected_on) / sum(selected_off) if sum(selected_off) else None,
                })
        off_median = arm_rows["off"]["token_distribution"]["median"]
        on_median = arm_rows["on"]["token_distribution"]["median"]
        case_rows.append({
            "case_id": case["id"], "category": case["category"], "off": arm_rows["off"], "on": arm_rows["on"],
            "median_token_ratio": on_median / off_median if off_median else None,
        })

    off_runs = [run for run in runs if run["arm"] == "off"]
    on_runs = [run for run in runs if run["arm"] == "on"]
    values = lambda rows, field: [int(item.get(field, 0)) for item in rows]
    off_tokens = [int(item.get("usage", {}).get("total_tokens", 0)) for item in off_runs]
    on_tokens = [int(item.get("usage", {}).get("total_tokens", 0)) for item in on_runs]
    off_calls, on_calls = values(off_runs, "tool_call_count"), values(on_runs, "tool_call_count")
    off_cycles, on_cycles = values(off_runs, "model_cycles"), values(on_runs, "model_cycles")
    off_entry = sum(value > 0 for value in off_calls) / len(off_calls) if off_calls else 0
    on_entry = sum(value > 0 for value in on_calls) / len(on_calls) if on_calls else 0
    mean_call_delta = statistics.fmean(on_calls) - statistics.fmean(off_calls) if off_calls and on_calls else 0
    mean_cycle_delta = statistics.fmean(on_cycles) - statistics.fmean(off_cycles) if off_cycles and on_cycles else 0
    path_signals = {
        "tool_entry_rate_delta_at_least_0_10": on_entry - off_entry >= TOOL_ENTRY_RATE_DELTA,
        "mean_tool_call_delta_at_least_0_25": mean_call_delta >= MEAN_CALL_OR_CYCLE_DELTA,
        "mean_model_cycle_delta_at_least_0_25": mean_cycle_delta >= MEAN_CALL_OR_CYCLE_DELTA,
        "case_tool_call_mean_higher_at_least_8": case_call_higher >= CASE_DIRECTION_COUNT,
        "case_model_cycle_mean_higher_at_least_8": case_cycle_higher >= CASE_DIRECTION_COUNT,
    }
    comparable_per_arm = len(conditional_pairs)
    conditional_coverage = (2 * comparable_per_arm / len(runs)) if runs else 0
    conditional_off = [off for off, _ in conditional_pairs]
    conditional_on = [on for _, on in conditional_pairs]
    pooled_ratio = sum(on_tokens) / sum(off_tokens) if sum(off_tokens) else None
    case_ratios = [row["median_token_ratio"] for row in case_rows if row["median_token_ratio"] is not None]
    hard_checks = {
        "all_120_runs_present": len(runs) == expected_count,
        "all_runs_completed_with_usage": len(runs) == expected_count and all(
            run.get("status") == "completed" and int(run.get("usage", {}).get("total_tokens", 0)) > 0 for run in runs
        ),
        "correctness_zero_regression": len(runs) == expected_count and all(bool(run.get("correct")) for run in runs),
        "host_hard_gates_pass": host_probes.get("status") == "passed",
        "collector_observed_every_on_tool_call": all(
            int(run.get("collector_event_count", 0)) == int(run.get("tool_call_count", 0)) for run in on_runs
        ),
        "collector_never_invokes_tools": all(not run.get("collector_invoked_tool", False) for run in on_runs),
        "equal_repetitions_per_case_arm": all(
            len(by_case_arm[(case["id"], arm)]) == REPETITIONS for case in manifest["cases"] for arm in base.ARMS
        ),
        "no_runs_excluded": len(runs) == expected_count,
    }
    any_path_signal = any(path_signals.values())
    hard_pass = all(hard_checks.values())
    cost_pass = pooled_ratio is not None and pooled_ratio <= manifest["token_ratio_ceiling"]
    if not hard_pass:
        attribution = "inconclusive"
        graduation = "fail"
    elif any_path_signal:
        attribution = "possible_systematic_effect"
        graduation = "fail"
    elif conditional_coverage < MIN_CONDITIONAL_COVERAGE:
        attribution = "inconclusive"
        graduation = "inconclusive" if cost_pass else "fail"
    else:
        attribution = "likely_stochastic"
        graduation = "pass" if cost_pass else "fail"
    return {
        "schema_version": 1, "schema_id": SCHEMA_ID,
        "attribution_conclusion": attribution, "graduation_verdict": graduation,
        "hard_checks": hard_checks, "path_signals": path_signals,
        "frozen_thresholds": {
            "repetitions_per_case_arm": REPETITIONS, "token_ratio_ceiling": manifest["token_ratio_ceiling"],
            "tool_entry_rate_delta": TOOL_ENTRY_RATE_DELTA, "mean_call_or_cycle_delta": MEAN_CALL_OR_CYCLE_DELTA,
            "case_direction_count": CASE_DIRECTION_COUNT, "min_conditional_coverage": MIN_CONDITIONAL_COVERAGE,
        },
        "overall": {
            "run_count": len(runs), "off_run_count": len(off_runs), "on_run_count": len(on_runs),
            "off_token_distribution": describe(off_tokens), "on_token_distribution": describe(on_tokens),
            "pooled_token_ratio": pooled_ratio,
            "case_balanced_median_ratio": statistics.median(case_ratios) if case_ratios else None,
            "off_tool_entry_count": sum(value > 0 for value in off_calls), "on_tool_entry_count": sum(value > 0 for value in on_calls),
            "off_tool_entry_rate": round(off_entry, 6), "on_tool_entry_rate": round(on_entry, 6),
            "tool_entry_rate_delta": round(on_entry - off_entry, 6),
            "off_tool_call_distribution": describe(off_calls), "on_tool_call_distribution": describe(on_calls),
            "mean_tool_call_delta": round(mean_call_delta, 6),
            "off_model_cycle_distribution": describe(off_cycles), "on_model_cycle_distribution": describe(on_cycles),
            "mean_model_cycle_delta": round(mean_cycle_delta, 6),
            "collector_event_count": sum(int(run.get("collector_event_count", 0)) for run in on_runs),
            "collector_duration_ms": round(sum(float(run.get("collector_total_duration_ms", 0)) for run in on_runs), 3),
        },
        "conditional_cost": {
            "matched_run_count_per_arm": comparable_per_arm, "coverage": round(conditional_coverage, 6),
            "off_token_distribution": describe(conditional_off), "on_token_distribution": describe(conditional_on),
            "pooled_ratio": sum(conditional_on) / sum(conditional_off) if sum(conditional_off) else None,
            "strata": conditional_strata,
        },
        "cases": case_rows,
        "no_cherry_picking": {
            "pilot_run7_included": False, "outliers_removed": False, "failed_runs_removed": False,
            "single_case_reruns": False, "all_scheduled_runs_included": len(runs) == expected_count,
        },
    }


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    repository = Path(git_output(plugin, "rev-parse", "--show-toplevel"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=plugin / "resources" / "acp0_4_cases.json")
    parser.add_argument("--artifacts", type=Path, default=repository / ".agent-token-manager" / "acp0-4a")
    parser.add_argument("--codex", type=Path, default=Path("/Applications/ChatGPT.app/Contents/Resources/codex"))
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    manifest = base.load_manifest(args.manifest)
    subject_commit = git_output(repository, "rev-parse", manifest["subject_commit"])
    artifacts = args.artifacts.resolve()
    if artifacts.exists() and any(artifacts.iterdir()) and not (args.resume or args.preflight_only):
        raise RuntimeError(f"refusing non-empty artifacts without --resume: {artifacts}")
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)

    contract = json.loads((plugin / "resources" / "acp0_contract.json").read_text(encoding="utf-8"))
    collector = plugin / contract["acp0_1_collector_audit"]["collector_path"]
    hooks = plugin / contract["acp0_1_collector_audit"]["hooks_manifest_path"]
    collector_hash = contract["acp0_1_collector_audit"]["collector_sha256"]
    hooks_hash = contract["acp0_1_collector_audit"]["hooks_manifest_sha256"]
    if base.sha256_bytes(collector.read_bytes()) != collector_hash or base.sha256_bytes(hooks.read_bytes()) != hooks_hash:
        raise RuntimeError("frozen online artifacts drifted")
    host_probes = fresh_host_probes(collector, artifacts / "host-probes")
    preflight = {
        "schema_version": 1, "fixture_id": manifest["fixture_id"], "subject_commit": subject_commit,
        "manifest_sha256": base.sha256_bytes(args.manifest.read_bytes()), "collector_sha256": collector_hash,
        "hooks_manifest_sha256": hooks_hash, "repetitions_per_case_arm": REPETITIONS,
        "scheduled_run_count": len(run_schedule(manifest["cases"])), "pilot_run7_included": False,
        "host_probes": host_probes,
    }
    (artifacts / "preflight.json").write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.preflight_only:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0 if host_probes["status"] == "passed" else 1

    lab_parent = Path(tempfile.mkdtemp(prefix="acp04a-marketplace-", dir="/private/tmp"))
    lab = base.prepare_marketplace(lab_parent, collector, collector_hash, hooks, hooks_hash)
    homes = prepare_homes(
        lab, artifacts, args.codex.resolve(), Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    )
    runs = []
    for repetition, case, arm in run_schedule(manifest["cases"]):
        repeated = dict(case, id=f"{case['id']}__r{repetition:02d}")
        result_path = artifacts / f"{repeated['id']}-{arm}" / "result.json"
        result = load_existing_result(result_path, case, repetition, arm) if args.resume else None
        if result is None:
            result = base.run_case(
                repository, subject_commit, repeated, arm, args.codex.resolve(), homes[arm], artifacts,
                args.model, args.reasoning_effort, args.timeout,
            )
            result["base_case_id"] = case["id"]
            result["repetition"] = repetition
        runs.append(result)
    summary = summarize(manifest, runs, host_probes)
    summary.update({
        "fixture_id": manifest["fixture_id"], "subject_commit": subject_commit,
        "harness_commit": git_output(repository, "rev-parse", "HEAD"),
        "manifest_sha256": preflight["manifest_sha256"], "collector_sha256": collector_hash,
        "hooks_manifest_sha256": hooks_hash, "model": args.model, "reasoning_effort": args.reasoning_effort,
        "usage_source": "Codex cumulative turn.completed usage; cycle count from cumulative usage events",
    })
    (artifacts / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    shutil.rmtree(lab_parent, ignore_errors=True)
    return 0 if summary["graduation_verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
