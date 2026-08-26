#!/usr/bin/env python3
"""Audit one ACP correctness case with Native calibration and prospective closure."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import run_acp0_4 as base
import run_acp0_4a as variance
from run_co1_gate2 import git_output


BASELINE_SCHEMA_ID = "acp0-4b-native-calibration-v1"
PAIRED_SCHEMA_ID = "acp0-4b-prospective-correctness-v1"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def answer_shape(run: dict[str, Any], expected: str) -> str:
    if run.get("status") != "completed":
        return "execution_failure"
    answer = str(run.get("final_text", "")).strip()
    if answer == expected:
        return "correct"
    if answer in {"6", "8"}:
        return "off_by_one_like"
    if answer == "5":
        return "first_cluster_only_like"
    if answer == "10":
        return "endpoint_like"
    if re.fullmatch(r"[+-]?\d+", answer):
        return "other_integer"
    return "malformed_or_missing"


def compact_run(run: dict[str, Any], repetition: int, expected: str) -> dict[str, Any]:
    return {
        "repetition": repetition,
        "arm": run.get("arm"),
        "status": run.get("status"),
        "answer": run.get("final_text", ""),
        "correct": bool(run.get("correct")),
        "answer_shape": answer_shape(run, expected),
        "tool_calls": int(run.get("tool_call_count", 0)),
        "model_cycles": int(run.get("model_cycles", 0)),
        "total_tokens": int(run.get("usage", {}).get("total_tokens", 0)),
        "collector_events": int(run.get("collector_event_count", 0)),
        "collector_invoked_tool": bool(run.get("collector_invoked_tool", False)),
    }


def prepare_native_home(artifacts: Path, source_home: Path) -> Path:
    auth = source_home / "auth.json"
    if not auth.is_file():
        raise RuntimeError(f"Codex auth missing: {auth}")
    home = artifacts / "codex-home-off"
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    auth_link = home / "auth.json"
    if not auth_link.exists():
        auth_link.symlink_to(auth)
    (home / "config.toml").write_text("", encoding="utf-8")
    return home


def existing_result(path: Path, *, arm: str, expected: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    result = load_json(path)
    if result.get("arm") != arm or result.get("expected") != expected:
        raise RuntimeError(f"existing result identity mismatch: {path}")
    return result


def select_case(fixture: dict[str, Any], case_id: str, expected: str) -> dict[str, Any]:
    matches = [case for case in fixture.get("cases", []) if case.get("id") == case_id]
    if len(matches) != 1 or matches[0].get("expected") != expected:
        raise RuntimeError("frozen correctness case or oracle drifted")
    return matches[0]


def baseline_summary(spec: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected_count = int(spec["native_calibration"]["repetitions"])
    correct = sum(row["correct"] for row in rows)
    stable_minimum = int(spec["native_calibration"]["empirically_stable_minimum_correct"])
    complete = len(rows) == expected_count and all(
        row["status"] == "completed" and row["total_tokens"] > 0 for row in rows
    )
    classification = "empirically_stable_gate" if correct >= stable_minimum else "stochastic_diagnostic"
    return {
        "schema_version": 1,
        "schema_id": BASELINE_SCHEMA_ID,
        "status": "complete" if complete else "incomplete",
        "case_id": spec["case_id"],
        "expected": spec["expected"],
        "run_count": len(rows),
        "correct_count": correct,
        "wrong_count": len(rows) - correct,
        "accuracy": correct / len(rows) if rows else None,
        "classification": classification,
        "classification_threshold": {"empirically_stable_minimum_correct": stable_minimum, "denominator": expected_count},
        "answer_shape_counts": dict(sorted(Counter(row["answer_shape"] for row in rows).items())),
        "tool_call_distribution": variance.describe([row["tool_calls"] for row in rows]),
        "model_cycle_distribution": variance.describe([row["model_cycles"] for row in rows]),
        "token_distribution": variance.describe([row["total_tokens"] for row in rows]),
        "all_runs_included": len(rows) == expected_count,
        "runs": rows,
    }


def validate_frozen_baseline(spec: dict[str, Any], baseline: dict[str, Any]) -> None:
    repetitions = int(spec["native_calibration"]["repetitions"])
    stable_minimum = int(spec["native_calibration"]["empirically_stable_minimum_correct"])
    correct = int(baseline.get("correct_count", -1))
    expected_classification = "empirically_stable_gate" if correct >= stable_minimum else "stochastic_diagnostic"
    if (
        baseline.get("schema_id") != BASELINE_SCHEMA_ID
        or baseline.get("case_id") != spec["case_id"]
        or baseline.get("expected") != spec["expected"]
        or int(baseline.get("run_count", -1)) != repetitions
        or baseline.get("classification") != expected_classification
        or baseline.get("all_runs_included") is not True
    ):
        raise RuntimeError("frozen Native calibration result does not match the preregistered specification")


def paired_summary(
    spec: dict[str, Any], baseline: dict[str, Any], rows: list[dict[str, Any]],
    host_probes: dict[str, Any], inherited: dict[str, Any],
) -> dict[str, Any]:
    repetitions = int(spec["prospective_correctness"]["repetitions_per_arm"])
    by_arm = {arm: [row for row in rows if row["arm"] == arm] for arm in base.ARMS}
    correct = {arm: sum(row["correct"] for row in by_arm[arm]) for arm in base.ARMS}
    accuracy = {arm: correct[arm] / repetitions for arm in base.ARMS}
    delta = accuracy["on"] - accuracy["off"]
    classification = baseline["classification"]
    if classification == "empirically_stable_gate":
        criterion = {
            "name": "empirically_stable_parity",
            "on_minimum_correct": int(spec["prospective_correctness"]["empirically_stable_on_minimum_correct"]),
            "on_not_below_off": True,
        }
        correctness_pass = correct["on"] >= criterion["on_minimum_correct"] and correct["on"] >= correct["off"]
    elif classification == "stochastic_diagnostic":
        criterion = {
            "name": "stochastic_accuracy_non_degradation",
            "minimum_accuracy_delta": float(spec["prospective_correctness"]["stochastic_minimum_accuracy_delta"]),
        }
        correctness_pass = delta >= criterion["minimum_accuracy_delta"]
    else:
        raise RuntimeError(f"unknown frozen classification: {classification}")

    on_rows = by_arm["on"]
    hard_checks = {
        "all_40_runs_present": len(rows) == repetitions * 2,
        "all_runs_completed_with_usage": len(rows) == repetitions * 2 and all(
            row["status"] == "completed" and row["total_tokens"] > 0 for row in rows
        ),
        "host_hard_gates_pass": host_probes.get("status") == "passed",
        "collector_observed_every_on_tool_call": all(row["collector_events"] == row["tool_calls"] for row in on_rows),
        "collector_never_invokes_tools": all(not row["collector_invoked_tool"] for row in on_rows),
        "prospective_correctness_criterion_pass": correctness_pass,
    }
    inherited_checks = {
        "acp0_4a_cost_gate_pass": bool(inherited["cost_neutrality"]["pooled_gate_pass"]),
        "acp0_4a_path_gate_pass": not bool(inherited["path_neutrality"]["any_preregistered_systematic_signal"]),
        "acp0_4a_host_gate_pass": bool(inherited["hard_checks"]["host_hard_gates_pass"]),
        "acp0_4a_result_remains_inconclusive": inherited.get("status") == "inconclusive",
    }
    graduation = all(hard_checks.values()) and all(inherited_checks.values())
    arm_summaries = {}
    for arm in base.ARMS:
        members = by_arm[arm]
        arm_summaries[arm] = {
            "run_count": len(members),
            "correct_count": correct[arm],
            "accuracy": accuracy[arm],
            "answer_shape_counts": dict(sorted(Counter(row["answer_shape"] for row in members).items())),
            "tool_call_distribution": variance.describe([row["tool_calls"] for row in members]),
            "model_cycle_distribution": variance.describe([row["model_cycles"] for row in members]),
            "token_distribution": variance.describe([row["total_tokens"] for row in members]),
        }
    return {
        "schema_version": 1,
        "schema_id": PAIRED_SCHEMA_ID,
        "status": "pass" if graduation else "fail",
        "acp0_graduation": "pass" if graduation else "fail",
        "case_id": spec["case_id"],
        "classification": classification,
        "criterion": criterion,
        "accuracy_delta_on_minus_off": delta,
        "hard_checks": hard_checks,
        "inherited_checks": inherited_checks,
        "arms": arm_summaries,
        "runs_enter_cost_or_path_gate": False,
        "all_runs_included": len(rows) == repetitions * 2,
        "runs": rows,
        "host_probes": host_probes,
    }


def run_one(
    *, repository: Path, subject_commit: str, case: dict[str, Any], repetition: int, phase: str,
    arm: str, codex: Path, home: Path, artifacts: Path, model: str, reasoning: str, timeout: int, resume: bool,
) -> dict[str, Any]:
    repeated = dict(case, id=f"{case['id']}__{phase}_r{repetition:02d}")
    path = artifacts / f"{repeated['id']}-{arm}" / "result.json"
    result = existing_result(path, arm=arm, expected=case["expected"]) if resume else None
    if result is None:
        result = base.run_case(
            repository, subject_commit, repeated, arm, codex, home, artifacts, model, reasoning, timeout,
        )
    return result


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    repository = Path(git_output(plugin, "rev-parse", "--show-toplevel"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("native-calibration", "paired-validation"))
    parser.add_argument("--spec", type=Path, default=plugin / "resources" / "acp0_4b_correctness_spec.json")
    parser.add_argument("--fixture", type=Path, default=plugin / "resources" / "acp0_4_cases.json")
    parser.add_argument("--baseline-results", type=Path, default=plugin / "resources" / "acp0_4b_native_calibration_results.json")
    parser.add_argument("--inherited-results", type=Path, default=plugin / "resources" / "acp0_4a_results.json")
    parser.add_argument("--artifacts", type=Path, default=repository / ".agent-token-manager" / "acp0-4b")
    parser.add_argument("--codex", type=Path, default=Path("/Applications/ChatGPT.app/Contents/Resources/codex"))
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    spec = load_json(args.spec)
    fixture = base.load_manifest(args.fixture)
    case = select_case(fixture, spec["case_id"], spec["expected"])
    subject_commit = git_output(repository, "rev-parse", spec["subject_commit"])
    phase_dir = args.artifacts.resolve() / args.phase
    if phase_dir.exists() and any(phase_dir.iterdir()) and not args.resume:
        raise RuntimeError(f"refusing non-empty phase artifacts without --resume: {phase_dir}")
    phase_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    codex = args.codex.resolve()
    source_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()

    if args.phase == "native-calibration":
        home = prepare_native_home(phase_dir, source_home)
        rows = []
        for repetition in range(1, int(spec["native_calibration"]["repetitions"]) + 1):
            result = run_one(
                repository=repository, subject_commit=subject_commit, case=case, repetition=repetition,
                phase="baseline", arm="off", codex=codex, home=home, artifacts=phase_dir,
                model=args.model, reasoning=args.reasoning_effort, timeout=args.timeout, resume=args.resume,
            )
            rows.append(compact_run(result, repetition, spec["expected"]))
        summary = baseline_summary(spec, rows)
        summary.update({"subject_commit": subject_commit, "model": args.model, "reasoning_effort": args.reasoning_effort})
        (phase_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["status"] == "complete" else 1

    baseline = load_json(args.baseline_results)
    inherited = load_json(args.inherited_results)
    validate_frozen_baseline(spec, baseline)
    contract = load_json(plugin / "resources" / "acp0_contract.json")
    collector = plugin / contract["acp0_1_collector_audit"]["collector_path"]
    hooks = plugin / contract["acp0_1_collector_audit"]["hooks_manifest_path"]
    collector_hash = contract["acp0_1_collector_audit"]["collector_sha256"]
    hooks_hash = contract["acp0_1_collector_audit"]["hooks_manifest_sha256"]
    if base.sha256_bytes(collector.read_bytes()) != collector_hash or base.sha256_bytes(hooks.read_bytes()) != hooks_hash:
        raise RuntimeError("frozen collector or Hook manifest drifted")
    host_probes = variance.fresh_host_probes(collector, phase_dir / "host-probes")
    lab_parent = Path(tempfile.mkdtemp(prefix="acp04b-marketplace-", dir="/private/tmp"))
    try:
        lab = base.prepare_marketplace(lab_parent, collector, collector_hash, hooks, hooks_hash)
        homes = variance.prepare_homes(lab, phase_dir, codex, source_home)
        rows = []
        repetitions = int(spec["prospective_correctness"]["repetitions_per_arm"])
        for repetition in range(1, repetitions + 1):
            arms = list(case["order"])
            if repetition % 2 == 0:
                arms.reverse()
            for arm in arms:
                result = run_one(
                    repository=repository, subject_commit=subject_commit, case=case, repetition=repetition,
                    phase="paired", arm=arm, codex=codex, home=homes[arm], artifacts=phase_dir,
                    model=args.model, reasoning=args.reasoning_effort, timeout=args.timeout, resume=args.resume,
                )
                rows.append(compact_run(result, repetition, spec["expected"]))
        summary = paired_summary(spec, baseline, rows, host_probes, inherited)
        summary.update({
            "subject_commit": subject_commit, "model": args.model, "reasoning_effort": args.reasoning_effort,
            "collector_sha256": collector_hash, "hooks_manifest_sha256": hooks_hash,
        })
        (phase_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["acp0_graduation"] == "pass" else 1
    finally:
        shutil.rmtree(lab_parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
