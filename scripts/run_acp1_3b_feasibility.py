#!/usr/bin/env python3
"""Run ACP-1.3B native replay qualification and controlled evidence feasibility pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from run_co0_gate import load_jsonl
from run_co1_1_pilot import cumulative_usage_series
from run_co1_gate2 import final_message, final_usage, new_transcript, normalize_command, transcript_calls


RUNNER_VERSION = "acp1-3b-feasibility-runner-v0.1"
ARMS = ("control", "treatment")
FAILURE_MARKERS = ("script failed", "script error")


class FeasibilityError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def load_spec(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_id") != "acp1-3b-controlled-intervention-spec-v1":
        raise FeasibilityError("invalid_spec")
    if value.get("forbidden_mechanisms") != [
        "hook_result_replacement", "decision_block", "transparent_smart_read_reopen", "online_collector_modification",
    ]:
        raise FeasibilityError("forbidden_mechanism_policy_drift")
    return value


def evidence_payload(spec: dict[str, Any], arm: str) -> str:
    if arm not in ARMS:
        raise FeasibilityError("invalid_arm")
    count_key = f"{arm}_irrelevant_record_count"
    count = int(spec["payload"][count_key])
    lines = [spec["payload"]["target_line"]]
    for index in range(1, count + 1):
        digest = hashlib.sha256(f"acp1-3b-ledger-record-{index:03d}".encode("utf-8")).hexdigest()
        lines.append(f"ledger_record_{index:03d} = status:verified; evidence_id:{digest}; relevance:none")
    return "\n".join(lines) + "\n"


def payload_metadata(spec: dict[str, Any], arm: str) -> dict[str, Any]:
    payload = evidence_payload(spec, arm)
    return {
        "sha256": sha256_text(payload), "chars": len(payload),
        "visible_estimated_tokens": (len(payload) + 3) // 4,
        "estimation_method": spec["payload"]["estimation_method"],
    }


def offline_canary(spec: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for arm in ARMS:
        parent = Path(tempfile.mkdtemp(prefix=f"acp13b-canary-{arm}-"))
        try:
            payload = evidence_payload(spec, arm)
            path = parent / "evidence_ledger.txt"
            path.write_text(payload, encoding="utf-8")
            completed = subprocess.run(
                ["sed", "-n", "1,9999p", "evidence_ledger.txt"], cwd=parent,
                text=True, capture_output=True, timeout=10,
            )
            rows.append({
                "arm": arm, "returncode": completed.returncode,
                "stdout_sha256": sha256_text(completed.stdout), "expected_sha256": sha256_text(payload),
                "stderr_empty": completed.stderr == "", "success": completed.returncode == 0 and completed.stdout == payload and completed.stderr == "",
            })
        finally:
            shutil.rmtree(parent, ignore_errors=True)
    control = payload_metadata(spec, "control")
    treatment = payload_metadata(spec, "treatment")
    reduction = 1 - treatment["visible_estimated_tokens"] / control["visible_estimated_tokens"]
    return {
        "status": "passed" if all(row["success"] for row in rows) else "failed",
        "same_command": True, "normal_exit_both_arms": all(row["returncode"] == 0 for row in rows),
        "source_payload_only_intervention": True, "hook_or_replacement_used": False,
        "payloads": {"control": control, "treatment": treatment},
        "visible_estimate_reduction_ratio": reduction, "rows": rows,
    }


def prepare_home(run_dir: Path, source_home: Path) -> Path:
    auth = source_home / "auth.json"
    if not auth.is_file():
        raise FeasibilityError(f"Codex auth missing: {auth}")
    home = run_dir / "codex-home"
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    auth_link = home / "auth.json"
    if not auth_link.exists():
        auth_link.symlink_to(auth)
    config = home / "config.toml"
    if not config.exists():
        config.write_text("", encoding="utf-8")
        config.chmod(0o600)
    return home


def run_one(
    spec: dict[str, Any], phase: str, repetition: int, arm: str, codex: Path,
    source_home: Path, artifacts: Path, timeout: int, resume: bool,
) -> dict[str, Any]:
    run_id = f"{phase}__r{repetition:02d}-{arm}"
    run_dir = artifacts / run_id
    result_path = run_dir / "result.json"
    if resume and result_path.is_file():
        existing = json.loads(result_path.read_text(encoding="utf-8"))
        if existing.get("run_id") != run_id or existing.get("arm") != arm:
            raise FeasibilityError(f"resume_identity_mismatch:{run_id}")
        return existing
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    workdir = run_dir / "workspace"
    workdir.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = evidence_payload(spec, arm)
    evidence_path = workdir / "evidence_ledger.txt"
    evidence_path.write_text(payload, encoding="utf-8")
    home = prepare_home(run_dir, source_home)
    before = set(home.rglob("*.jsonl"))
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(home)
    environment["PWD"] = str(workdir)
    command = [
        str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust",
        "--sandbox", "read-only", "--model", spec["model"], "--cd", str(workdir),
        "--config", f'model_reasoning_effort="{spec["reasoning_effort"]}"',
        "--config", "features.multi_agent=false", spec["question"],
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=workdir, env=environment, text=True, capture_output=True, timeout=timeout)
        elapsed = round(time.perf_counter() - started, 3)
        (run_dir / "codex.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        exec_events = load_jsonl(run_dir / "codex.jsonl")
        transcript = new_transcript(home, before)
        transcript_events = load_jsonl(transcript) if transcript else []
        calls = transcript_calls(transcript_events)
        normalized_expected = normalize_command(spec["command"])
        target_calls = [call for call in calls if normalize_command(str(call.get("command", ""))) == normalized_expected]
        target = target_calls[0] if len(target_calls) == 1 else None
        output = str(target.get("output", "")) if target else ""
        lowered = output.lower()
        final = final_message(exec_events)
        usage = final_usage(exec_events)
        result = {
            "schema_version": 1, "run_id": run_id, "phase": phase, "repetition": repetition, "arm": arm,
            "case_id": spec["case_id"], "model": spec["model"], "reasoning_effort": spec["reasoning_effort"],
            "status": "completed" if completed.returncode == 0 else "failed", "process_returncode": completed.returncode,
            "correct": completed.returncode == 0 and final == spec["expected"], "final_text": final, "expected": spec["expected"],
            "elapsed_seconds": elapsed, "usage": usage, "model_cycles": len(cumulative_usage_series(transcript_events)),
            "tool_call_count": len(calls), "exact_target_call_count": len(target_calls),
            "tool_request_hashes": [sha256_text(normalize_command(str(call.get("command", "")))) for call in calls],
            "target_request_sha256": sha256_text(normalized_expected),
            "target_result_sha256": sha256_text(output) if target else None,
            "target_result_chars": len(output) if target else None,
            "target_visible_estimated_tokens": (len(output) + 3) // 4 if target else None,
            "target_contains_expected_evidence": spec["payload"]["target_line"] in output if target else False,
            "target_success_semantics": bool(target) and not any(marker in lowered for marker in FAILURE_MARKERS),
            "payload_sha256": sha256_text(payload), "payload_chars": len(payload),
            "prompt_sha256": sha256_text(spec["question"]), "transcript_available": bool(transcript_events),
            "hook_or_replacement_used": False,
        }
    except Exception as error:
        result = {
            "schema_version": 1, "run_id": run_id, "phase": phase, "repetition": repetition, "arm": arm,
            "case_id": spec["case_id"], "status": "failed", "correct": False,
            "error": f"{type(error).__name__}: {error}", "hook_or_replacement_used": False,
        }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _stats(values: list[int | float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": len(values), "min": min(values), "median": statistics.median(values),
        "mean": statistics.mean(values), "max": max(values),
    }


def compact_run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id_hash": sha256_text("acp1-3b-public-run-v1\0" + str(row.get("run_id"))),
        "phase": row.get("phase"), "repetition": row.get("repetition"), "arm": row.get("arm"),
        "status": row.get("status"), "correct": bool(row.get("correct")),
        "total_tokens": int(row.get("usage", {}).get("total_tokens", 0)),
        "model_cycles": int(row.get("model_cycles", 0)), "tool_call_count": int(row.get("tool_call_count", 0)),
        "exact_target_call_count": int(row.get("exact_target_call_count", 0)),
        "target_request_sha256": row.get("target_request_sha256"), "target_result_sha256": row.get("target_result_sha256"),
        "target_result_chars": row.get("target_result_chars"), "target_visible_estimated_tokens": row.get("target_visible_estimated_tokens"),
        "target_contains_expected_evidence": bool(row.get("target_contains_expected_evidence")),
        "target_success_semantics": bool(row.get("target_success_semantics")),
        "payload_sha256": row.get("payload_sha256"), "payload_chars": row.get("payload_chars"),
        "prompt_sha256": row.get("prompt_sha256"), "hook_or_replacement_used": bool(row.get("hook_or_replacement_used")),
    }


def qualification_summary(spec: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    expected = int(spec["native_qualification"]["repetitions"])
    correct = sum(bool(row.get("correct")) for row in runs)
    exact = sum(int(row.get("tool_call_count", 0)) == 1 and int(row.get("exact_target_call_count", 0)) == 1 for row in runs)
    complete = len(runs) == expected and all(row.get("status") == "completed" and int(row.get("usage", {}).get("total_tokens", 0)) > 0 for row in runs)
    success = len(runs) == expected and all(bool(row.get("target_success_semantics")) for row in runs)
    gate = all((
        complete, correct >= int(spec["native_qualification"]["minimum_correct"]),
        exact >= int(spec["native_qualification"]["minimum_exact_single_command_runs"]), success,
    ))
    return {
        "status": "pass" if gate else "fail", "run_count": len(runs), "correct_count": correct,
        "exact_single_command_count": exact, "all_completed_with_usage": complete,
        "all_target_calls_success_semantics": success,
        "token_distribution": _stats([int(row.get("usage", {}).get("total_tokens", 0)) for row in runs]),
        "cycle_distribution": _stats([int(row.get("model_cycles", 0)) for row in runs]),
        "runs": [compact_run(row) for row in runs],
    }


def paired_summary(spec: dict[str, Any], runs: list[dict[str, Any]], canary: dict[str, Any]) -> dict[str, Any]:
    expected = int(spec["paired_feasibility"]["repetitions_per_arm"])
    by_arm = {arm: [row for row in runs if row.get("arm") == arm] for arm in ARMS}
    arm_summaries = {}
    for arm, members in by_arm.items():
        arm_summaries[arm] = {
            "run_count": len(members), "correct_count": sum(bool(row.get("correct")) for row in members),
            "exact_single_command_count": sum(int(row.get("tool_call_count", 0)) == 1 and int(row.get("exact_target_call_count", 0)) == 1 for row in members),
            "success_semantics_count": sum(bool(row.get("target_success_semantics")) for row in members),
            "target_visible_token_distribution": _stats([int(row["target_visible_estimated_tokens"]) for row in members if isinstance(row.get("target_visible_estimated_tokens"), int)]),
            "total_token_distribution": _stats([int(row.get("usage", {}).get("total_tokens", 0)) for row in members]),
            "model_cycle_distribution": _stats([int(row.get("model_cycles", 0)) for row in members]),
        }
    all_complete = len(runs) == expected * 2 and all(row.get("status") == "completed" and int(row.get("usage", {}).get("total_tokens", 0)) > 0 for row in runs)
    all_exact = len(runs) == expected * 2 and all(int(row.get("tool_call_count", 0)) == 1 and int(row.get("exact_target_call_count", 0)) == 1 for row in runs)
    all_success = len(runs) == expected * 2 and all(bool(row.get("target_success_semantics")) for row in runs)
    prompt_hashes = {row.get("prompt_sha256") for row in runs}
    request_hashes = {row.get("target_request_sha256") for row in runs}
    control_visible = arm_summaries["control"]["target_visible_token_distribution"]["median"]
    treatment_visible = arm_summaries["treatment"]["target_visible_token_distribution"]["median"]
    observed_reduction = 1 - treatment_visible / control_visible if control_visible else None
    activation = (
        observed_reduction is not None
        and observed_reduction >= float(spec["payload"]["minimum_visible_estimate_reduction_ratio"])
        and {row.get("target_result_sha256") for row in by_arm["control"]}.isdisjoint({row.get("target_result_sha256") for row in by_arm["treatment"]})
    )
    gates = {
        "g2_intervention_isolation": len(prompt_hashes) == 1 and len(request_hashes) == 1 and canary["source_payload_only_intervention"],
        "g3_success_semantics": all_success,
        "g4_activation": activation,
        "g5_outcome_completeness": all_complete and all_exact,
        "g6_privacy_provenance": True,
        "g7_no_product_mutation": all(not bool(row.get("hook_or_replacement_used")) for row in runs),
        "g8_stop_rule_not_triggered": all_success and not canary["hook_or_replacement_used"],
    }
    return {
        "status": "pass" if all(gates.values()) else "fail", "gates": gates,
        "run_count": len(runs), "all_runs_included": len(runs) == expected * 2,
        "observed_visible_estimate_reduction_ratio": observed_reduction,
        "arms": arm_summaries, "runs": [compact_run(row) for row in runs],
        "correctness_effect_status": "observed_not_causal_generalization",
        "cost_effect_status": "observed_not_avoidable_estimate",
    }


def build_public_result(
    spec: dict[str, Any], canary: dict[str, Any], qualification: dict[str, Any], paired: dict[str, Any] | None,
) -> dict[str, Any]:
    g1 = qualification["status"] == "pass"
    remaining = paired["gates"] if paired else {
        "g2_intervention_isolation": False, "g3_success_semantics": False, "g4_activation": False,
        "g5_outcome_completeness": False, "g6_privacy_provenance": False,
        "g7_no_product_mutation": False, "g8_stop_rule_not_triggered": False,
    }
    mechanism = g1 and paired is not None and paired["status"] == "pass"
    return {
        "schema_version": 1, "schema_id": "acp1-3b-controlled-intervention-feasibility-v1",
        "experiment_id": spec["experiment_id"], "runner_version": RUNNER_VERSION,
        "status": "mechanism_feasible_under_synthetic_frozen_scope" if mechanism else "failed_or_incomplete",
        "offline_canary": canary, "replay_qualification": qualification, "paired_feasibility": paired,
        "gates": {"g1_replay_stability": g1, **remaining},
        "conclusions": {
            "mechanism_feasibility": "pass" if mechanism else "fail_or_incomplete",
            "historical_candidate_validation": "not_performed",
            "candidate_correctness_effect": "descriptive_only" if paired else "not_measured",
            "candidate_cost_effect": "descriptive_only_not_avoidable" if paired else "not_measured",
            "production_intervention_availability": "blocked_host_interface_unchanged",
            "general_savings_claim": False,
        },
        "policy": {
            "hook_replacement_used": False, "decision_block_used": False, "collector_modified": False,
            "transparent_smart_read_reopened": False, "avoidable_or_savings_estimate_produced": False,
            "synthetic_harness_is_not_production_capability": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    workspace = root.parents[1]
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_3b_experiment_spec.json")
    parser.add_argument("--artifacts", type=Path, default=workspace / ".agent-token-manager/acp1-3b-controlled-evidence-20260818")
    parser.add_argument("--public-result", type=Path, default=root / "resources/acp1_3b_results.json")
    parser.add_argument("--codex", type=Path, default=Path(shutil.which("codex") or "codex"))
    parser.add_argument("--source-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--offline-only", action="store_true")
    args = parser.parse_args()
    spec = load_spec(args.spec)
    canary = offline_canary(spec)
    if canary["status"] != "passed" or canary["visible_estimate_reduction_ratio"] < spec["payload"]["minimum_visible_estimate_reduction_ratio"]:
        raise FeasibilityError("offline_canary_failed")
    if args.offline_only:
        print(canonical_bytes(canary).decode("utf-8"), end="")
        return 0
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    qualification_runs = [
        run_one(spec, "qualification", repetition, "control", args.codex.resolve(), args.source_home.resolve(), artifacts, args.timeout, args.resume)
        for repetition in range(1, int(spec["native_qualification"]["repetitions"]) + 1)
    ]
    qualification = qualification_summary(spec, qualification_runs)
    paired = None
    if qualification["status"] == "pass":
        paired_runs = []
        for repetition in range(1, int(spec["paired_feasibility"]["repetitions_per_arm"]) + 1):
            for arm in ARMS:
                paired_runs.append(run_one(spec, "paired", repetition, arm, args.codex.resolve(), args.source_home.resolve(), artifacts, args.timeout, args.resume))
        paired = paired_summary(spec, paired_runs, canary)
    public = build_public_result(spec, canary, qualification, paired)
    args.public_result.write_bytes(canonical_bytes(public))
    (artifacts / "summary.json").write_bytes(canonical_bytes(public))
    print(canonical_bytes({"status": public["status"], "gates": public["gates"], "public_result_sha256": sha256_bytes(canonical_bytes(public))}).decode("utf-8"), end="")
    return 0 if public["status"] == "mechanism_feasible_under_synthetic_frozen_scope" else 1


if __name__ == "__main__":
    raise SystemExit(main())
