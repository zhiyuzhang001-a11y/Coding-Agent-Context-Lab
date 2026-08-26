#!/usr/bin/env python3
"""Run ACP-1.3D pilot and formal candidate-specific controlled ablations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

import run_acp1_3c_qualification as qualification
from run_co0_gate import load_jsonl
from run_co1_1_pilot import cumulative_usage_series
from run_co1_gate2 import final_message, final_usage, new_transcript, normalize_command, transcript_calls


RUNNER_VERSION = "acp1-3d-controlled-ablation-runner-v0.1"
RESULT_SCHEMA_ID = "acp1-3d-controlled-ablation-result-v1"
ARMS = ("control", "treatment")
FAILURE_MARKERS = ("script failed", "script error")
FROZEN_HASHES = {
    "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
    "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
    "resources/acp1_3b_frozen_feasibility_index.json": "6397007ce8fdb2229b45490249be70ad4017adf0df41388135d71be04bb10fc3",
    "resources/acp1_3c_candidate_registry.json": "b618e64409b5e3e9d75b9b2a412b6bbd58c486a363afa4f58968e8a17f58f0f8",
    "resources/acp1_3c_frozen_registry_index.json": "a4c599bd1084429a16cd6977d5128d1031d1fbaa03b907d26b329cbf1ce59090",
    "resources/acp1_3c_frozen_experiment_manifest.json": "ddf15adaa883a16e192d7c4e2a53ba3a7a7ba3d51ceb43b029d98a0ebac4a45c",
}


class AblationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AblationError(f"object_required:{path.name}")
    return value


def load_spec(path: Path, plugin: Path) -> dict[str, Any]:
    spec = load_object(path)
    if spec.get("schema_id") != "acp1-3d-controlled-ablation-spec-v1":
        raise AblationError("invalid_spec")
    registry_path = plugin / "resources/acp1_3c_candidate_registry.json"
    if sha256_file(registry_path) != spec["upstream_registry_sha256"]:
        raise AblationError("upstream_registry_hash_mismatch")
    registry = load_object(registry_path)
    qualified = {(row["case_id"], row["case_version"]) for row in registry["cases"] if row["status"] == "qualified"}
    requested = {(row["case_id"], row["case_version"]) for row in spec["cases"]}
    if requested != qualified:
        raise AblationError("eligible_case_set_mismatch")
    if len(requested) != 2 or spec["formal"]["blocks_per_case"] != 20:
        raise AblationError("invalid_formal_design")
    if spec["policy"]["production_slicing_or_replacement"] or spec["policy"]["collector_or_hook_mutation"]:
        raise AblationError("experimental_harness_policy_required")
    for relative, expected in FROZEN_HASHES.items():
        target = plugin / relative
        if not target.is_file() or sha256_file(target) != expected:
            raise AblationError(f"frozen_hash_mismatch:{relative}")
    return spec


def build_prompt(case: dict[str, Any]) -> str:
    return (
        "Work only from the local repository. Do not use web tools, plugins, skills, Task Navigator, "
        "Smart Read, context_router, navigation_map, or subagents. Do not modify repository files. "
        + case["question"]
    )


def _replace_terms(value: str, terms: list[str]) -> str:
    result = value
    for term in terms:
        result = re.sub(re.escape(term), "__ACP_ABLATED_TERM__", result, flags=re.IGNORECASE)
    return result


def apply_treatment(workdir: Path, case: dict[str, Any]) -> dict[str, Any]:
    treatment = case["treatment"]
    if treatment["method"] == "prefix-source-projection-v1":
        target = workdir / treatment["target"]
        before = target.read_text(encoding="utf-8")
        lines = before.splitlines(keepends=True)
        keep = int(treatment["keep_first_lines"])
        after = "".join(lines[:keep])
        target.write_text(after, encoding="utf-8")
        return {
            "method": treatment["method"], "changed_file_count": 1,
            "changed_line_count": max(0, len(lines) - keep),
            "source_before_sha256": sha256_text(before), "source_after_sha256": sha256_text(after),
        }
    if treatment["method"] == "hashed-nontarget-match-ablation-v1":
        preserved = treatment["preserved_target"]
        terms = list(treatment["match_terms"])
        changed_files = 0
        changed_lines = 0
        before_hash = hashlib.sha256()
        after_hash = hashlib.sha256()
        for path in sorted(item for item in workdir.rglob("*") if item.is_file()):
            relative = path.relative_to(workdir).as_posix()
            try:
                before = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            before_hash.update(relative.encode("utf-8") + b"\0" + before.encode("utf-8"))
            if relative == preserved:
                after = before
            else:
                rows = before.splitlines(keepends=True)
                changed = False
                for index, row in enumerate(rows, 1):
                    if not any(term.casefold() in row.casefold() for term in terms):
                        continue
                    digest = hashlib.sha256(f"{relative}:{index}".encode("utf-8")).digest()
                    if digest[0] % 2 == int(treatment["ablate_when_first_byte_mod_2"]):
                        rows[index - 1] = _replace_terms(row, terms)
                        changed = True
                        changed_lines += 1
                after = "".join(rows)
                if changed:
                    path.write_text(after, encoding="utf-8")
                    changed_files += 1
            after_hash.update(relative.encode("utf-8") + b"\0" + after.encode("utf-8"))
        return {
            "method": treatment["method"], "changed_file_count": changed_files,
            "changed_line_count": changed_lines,
            "source_before_sha256": before_hash.hexdigest(), "source_after_sha256": after_hash.hexdigest(),
        }
    raise AblationError(f"unknown_treatment:{treatment['method']}")


def logical_match(call: dict[str, Any], case: dict[str, Any]) -> bool:
    command = normalize_command(str(call.get("command", ""))).casefold()
    output = str(call.get("output", ""))
    return all(str(term).casefold() in command for term in case["candidate_command_terms"]) and not any(
        marker in output.casefold() for marker in FAILURE_MARKERS
    )


def analyze_calls(calls: list[dict[str, Any]], case: dict[str, Any]) -> dict[str, Any]:
    matching = [index for index, call in enumerate(calls) if logical_match(call, case)]
    unique_index = matching[0] if len(matching) == 1 else None
    path: list[dict[str, str]] = []
    for index, call in enumerate(calls):
        relation = "ambiguous" if len(matching) > 1 and index in matching else ("candidate" if index == unique_index else "noncandidate")
        path.append({
            "tool_family": str(call.get("tool_name", "unknown")),
            "first_executable_kind": qualification.first_executable_kind(str(call.get("command", ""))),
            "candidate_relation": relation,
        })
    candidate = calls[unique_index] if unique_index is not None else None
    output = str(candidate.get("output", "")) if candidate else ""
    return {
        "candidate_match_count": len(matching),
        "candidate_recurred": len(matching) == 1,
        "candidate_ambiguous": len(matching) > 1,
        "candidate_result_chars": len(output) if candidate else None,
        "candidate_visible_estimated_tokens": (len(output) + 3) // 4 if candidate else None,
        "candidate_request_sha256": sha256_text(normalize_command(str(candidate.get("command", "")))) if candidate else None,
        "candidate_result_sha256": sha256_text(output) if candidate else None,
        "candidate_success_semantics": candidate is not None and not any(marker in output.casefold() for marker in FAILURE_MARKERS),
        "path_signature_sha256": sha256_bytes(canonical_bytes(path)),
    }


def run_one(
    spec: dict[str, Any], case: dict[str, Any], phase: str, block: int, arm: str,
    repository: Path, codex: Path, source_home: Path, artifacts: Path, timeout: int, resume: bool,
) -> dict[str, Any]:
    run_id = f"{phase}__{case['case_id']}__b{block:02d}-{arm}"
    run_dir = artifacts / run_id
    result_path = run_dir / "result.json"
    if resume and result_path.is_file():
        result = load_object(result_path)
        if result.get("run_id") != run_id or result.get("arm") != arm:
            raise AblationError(f"resume_identity_mismatch:{run_id}")
        return result
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix="acp13d-"))
    workdir = temporary / "subject"
    started = time.perf_counter()
    try:
        qualification.materialize_subject(repository, spec["subject_commit"], workdir)
        treatment_meta = apply_treatment(workdir, case) if arm == "treatment" else {
            "method": "none_control", "changed_file_count": 0, "changed_line_count": 0,
            "source_before_sha256": None, "source_after_sha256": None,
        }
        home = qualification.prepare_home(run_dir, source_home)
        before = set(home.rglob("*.jsonl"))
        environment = dict(os.environ, CODEX_HOME=str(home), PWD=str(workdir))
        command = [
            str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust", "--skip-git-repo-check",
            "--sandbox", "read-only", "--model", spec["model"], "--cd", str(workdir),
            "--config", f'model_reasoning_effort="{spec["reasoning_effort"]}"',
            "--config", "features.multi_agent=false", build_prompt(case),
        ]
        completed = subprocess.run(command, cwd=workdir, env=environment, text=True, capture_output=True, timeout=timeout)
        elapsed = round(time.perf_counter() - started, 3)
        (run_dir / "codex.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        exec_events = load_jsonl(run_dir / "codex.jsonl")
        transcript = new_transcript(home, before)
        transcript_events = load_jsonl(transcript) if transcript else []
        calls = transcript_calls(transcript_events)
        final = final_message(exec_events)
        result = {
            "schema_version": 1, "run_id": run_id, "phase": phase, "case_id": case["case_id"],
            "case_version": case["case_version"], "block": block, "arm": arm,
            "status": "completed" if completed.returncode == 0 else "failed", "process_returncode": completed.returncode,
            "correct": completed.returncode == 0 and final.strip() == case["expected"],
            "final_text": final, "expected": case["expected"], "elapsed_seconds": elapsed,
            "usage": final_usage(exec_events), "model_cycles": len(cumulative_usage_series(transcript_events)),
            "tool_call_count": len(calls), "prompt_sha256": sha256_text(build_prompt(case)),
            "tool_request_hashes": [sha256_text(normalize_command(str(call.get("command", "")))) for call in calls],
            "tool_result_hashes": [sha256_text(str(call.get("output", ""))) for call in calls],
            "transcript_available": bool(transcript_events), "hook_or_collector_used": False,
            "treatment": treatment_meta, **analyze_calls(calls, case),
        }
    except Exception as error:
        result = {
            "schema_version": 1, "run_id": run_id, "phase": phase, "case_id": case["case_id"],
            "case_version": case["case_version"], "block": block, "arm": arm,
            "status": "failed", "correct": False, "error": f"{type(error).__name__}: {error}",
            "hook_or_collector_used": False,
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    result_path.write_bytes(canonical_bytes(result))
    return result


def reduction(control: dict[str, Any], treatment: dict[str, Any]) -> float | None:
    before = control.get("candidate_visible_estimated_tokens")
    after = treatment.get("candidate_visible_estimated_tokens")
    if not isinstance(before, int) or before <= 0 or not isinstance(after, int):
        return None
    return (before - after) / before


def paired_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    for run in runs:
        pairs.setdefault((run["case_id"], int(run["block"])), {})[run["arm"]] = run
    rows = []
    for (case_id, block), arms in sorted(pairs.items()):
        if set(arms) != set(ARMS):
            continue
        control, treatment = arms["control"], arms["treatment"]
        rows.append({
            "case_id": case_id, "block": block, "control": control, "treatment": treatment,
            "evidence_reduction_ratio": reduction(control, treatment),
            "tool_call_delta": int(treatment.get("tool_call_count", 0)) - int(control.get("tool_call_count", 0)),
            "cycle_delta": int(treatment.get("model_cycles", 0)) - int(control.get("model_cycles", 0)),
            "session_token_delta": int(treatment.get("usage", {}).get("total_tokens", 0)) - int(control.get("usage", {}).get("total_tokens", 0)),
        })
    return rows


def nearest_rank(values: list[int | float], probability: float) -> int | float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def distribution(values: list[int | float]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "min": None, "p25": None, "median": None, "mean": None, "p75": None, "max": None}
    return {
        "count": len(values), "min": min(values), "p25": nearest_rank(values, 0.25),
        "median": statistics.median(values), "mean": round(statistics.mean(values), 9),
        "p75": nearest_rank(values, 0.75), "max": max(values),
    }


def pilot_summary(spec: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    cases = []
    for case in spec["cases"]:
        selected = [run for run in runs if run["case_id"] == case["case_id"]]
        pair = paired_rows(selected)
        control = next((run for run in selected if run["arm"] == "control"), {})
        treatment = next((run for run in selected if run["arm"] == "treatment"), {})
        ratio = pair[0]["evidence_reduction_ratio"] if pair else None
        checks = {
            "both_completed_with_usage": all(run.get("status") == "completed" and int(run.get("usage", {}).get("total_tokens", 0)) > 0 for run in selected) and len(selected) == 2,
            "both_correct": all(run.get("correct") for run in selected) and len(selected) == 2,
            "unique_logical_candidate": all(run.get("candidate_recurred") and not run.get("candidate_ambiguous") for run in selected) and len(selected) == 2,
            "success_semantics": all(run.get("candidate_success_semantics") for run in selected) and len(selected) == 2,
            "result_hash_changed": control.get("candidate_result_sha256") != treatment.get("candidate_result_sha256") and bool(control.get("candidate_result_sha256")),
            "activation": ratio is not None and ratio >= spec["thresholds"]["minimum_evidence_reduction_ratio"],
        }
        cases.append({"case_id": case["case_id"], "checks": checks, "evidence_reduction_ratio": ratio, "status": "pass" if all(checks.values()) else "fail"})
    return {
        "schema_version": 1, "schema_id": "acp1-3d-pilot-result-v1", "run_count": len(runs),
        "included_in_formal_statistics": False, "cases": cases,
        "status": "pass" if len(cases) == 2 and all(row["status"] == "pass" for row in cases) else "inconclusive_plumbing",
    }


def compact_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id_hash": sha256_text(str(run.get("run_id", ""))), "case_id": run.get("case_id"),
        "block": run.get("block"), "arm": run.get("arm"), "status": run.get("status"),
        "correct": bool(run.get("correct")), "total_tokens": run.get("usage", {}).get("total_tokens"),
        "model_cycles": run.get("model_cycles"), "tool_call_count": run.get("tool_call_count"),
        "candidate_recurred": bool(run.get("candidate_recurred")), "candidate_ambiguous": bool(run.get("candidate_ambiguous")),
        "candidate_visible_estimated_tokens": run.get("candidate_visible_estimated_tokens"),
        "candidate_success_semantics": bool(run.get("candidate_success_semantics")),
        "candidate_result_sha256": run.get("candidate_result_sha256"),
        "path_signature_sha256": run.get("path_signature_sha256"),
        "treatment_method": run.get("treatment", {}).get("method"),
        "hook_or_collector_used": bool(run.get("hook_or_collector_used")),
    }


def formal_case_summary(spec: dict[str, Any], case: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds = spec["thresholds"]
    selected = [run for run in runs if run["case_id"] == case["case_id"]]
    control = [run for run in selected if run["arm"] == "control"]
    treatment = [run for run in selected if run["arm"] == "treatment"]
    pairs = paired_rows(selected)
    comparable_reductions = [row["evidence_reduction_ratio"] for row in pairs if row["evidence_reduction_ratio"] is not None]
    control_correct = sum(bool(run.get("correct")) for run in control)
    treatment_correct = sum(bool(run.get("correct")) for run in treatment)
    accuracy_delta = treatment_correct / 20 - control_correct / 20
    treatment_only_failures = sum(row["control"].get("correct") and not row["treatment"].get("correct") for row in pairs)
    dominant = case["upstream_dominant_path_sha256"]
    control_retention = sum(run.get("path_signature_sha256") == dominant for run in control) / 20
    treatment_retention = sum(run.get("path_signature_sha256") == dominant for run in treatment) / 20
    control_paths = Counter(str(run.get("path_signature_sha256")) for run in control)
    treatment_paths = Counter(str(run.get("path_signature_sha256")) for run in treatment)
    novel_compensation = sorted(path for path, count in treatment_paths.items() if count >= thresholds["novel_treatment_path_repeated_min"] and control_paths.get(path, 0) == 0)
    completed = sum(run.get("status") == "completed" and int(run.get("usage", {}).get("total_tokens", 0)) > 0 for run in selected)
    g2 = (
        sum(run.get("candidate_recurred") and not run.get("candidate_ambiguous") for run in treatment) == 20
        and len(comparable_reductions) >= thresholds["target_recurrence_min"]
        and statistics.median(comparable_reductions) >= thresholds["minimum_evidence_reduction_ratio"]
        and all(row["control"].get("candidate_result_sha256") != row["treatment"].get("candidate_result_sha256") for row in pairs if row["evidence_reduction_ratio"] is not None)
    )
    g3 = (
        control_correct >= thresholds["control_correct_min"] and treatment_correct >= thresholds["treatment_correct_min"]
        and accuracy_delta >= thresholds["accuracy_delta_min"] and treatment_only_failures <= thresholds["treatment_only_failures_max"]
    )
    tool_deltas = [row["tool_call_delta"] for row in pairs]
    cycle_deltas = [row["cycle_delta"] for row in pairs]
    g4 = (
        sum(run.get("candidate_recurred") for run in control) >= thresholds["target_recurrence_min"]
        and sum(run.get("candidate_recurred") for run in treatment) >= thresholds["target_recurrence_min"]
        and treatment_retention - control_retention >= thresholds["dominant_path_retention_delta_min"]
        and len(tool_deltas) == 20 and statistics.median(tool_deltas) <= thresholds["paired_median_tool_call_delta_max"]
        and not novel_compensation
    )
    g5 = len(cycle_deltas) == 20 and statistics.median(cycle_deltas) <= thresholds["paired_median_cycle_delta_max"]
    g6 = all(run.get("candidate_success_semantics") for run in selected if run.get("candidate_recurred")) and all(not run.get("candidate_ambiguous") for run in selected)
    g7 = completed == thresholds["formal_completed_with_usage_required"] and len(pairs) == 20
    gates = {
        "g1_eligibility": True, "g2_activation": g2, "g3_correctness": g3, "g4_tool_path": g4,
        "g5_cycle": g5, "g6_success_semantics": g6, "g7_outcome_completeness": g7, "g8_no_overclaim_frozen_integrity": True,
    }
    if not g2 or not g7:
        verdict = "INCONCLUSIVE"
    elif all(gates.values()):
        verdict = "PASS"
    else:
        verdict = "FAIL"
    control_total = [int(run["usage"]["total_tokens"]) for run in control if isinstance(run.get("usage", {}).get("total_tokens"), int)]
    treatment_total = [int(run["usage"]["total_tokens"]) for run in treatment if isinstance(run.get("usage", {}).get("total_tokens"), int)]
    pooled_ratio = sum(treatment_total) / sum(control_total) if control_total and sum(control_total) else None
    session_deltas = [row["session_token_delta"] for row in pairs]
    if not all(gates[f"g{number}_{name}"] for number, name in ((2, "activation"), (3, "correctness"), (4, "tool_path"), (5, "cycle"), (6, "success_semantics"), (7, "outcome_completeness"))):
        cost_effect = "not_interpretable"
    elif pooled_ratio is not None and pooled_ratio < spec["session_cost_effect"]["reduction_pooled_ratio_below"] and statistics.median(session_deltas) < 0:
        cost_effect = "observed_reduction"
    elif pooled_ratio is not None and spec["session_cost_effect"]["neutral_pooled_ratio_min"] <= pooled_ratio <= spec["session_cost_effect"]["neutral_pooled_ratio_max"]:
        cost_effect = "neutral"
    elif pooled_ratio is not None and pooled_ratio > spec["session_cost_effect"]["increase_pooled_ratio_above"] and statistics.median(session_deltas) > 0:
        cost_effect = "observed_increase"
    else:
        cost_effect = "inconclusive"
    control_target = [int(run["candidate_visible_estimated_tokens"]) for run in control if isinstance(run.get("candidate_visible_estimated_tokens"), int)]
    treatment_target = [int(run["candidate_visible_estimated_tokens"]) for run in treatment if isinstance(run.get("candidate_visible_estimated_tokens"), int)]
    return {
        "case_id": case["case_id"], "case_version": case["case_version"], "verdict": verdict, "gates": gates,
        "counts": {
            "control_runs": len(control), "treatment_runs": len(treatment), "completed_with_usage": completed,
            "control_correct": control_correct, "treatment_correct": treatment_correct,
            "treatment_only_failures": treatment_only_failures,
            "control_target_recurrence": sum(run.get("candidate_recurred") for run in control),
            "treatment_target_recurrence": sum(run.get("candidate_recurred") for run in treatment),
        },
        "activation": {
            "comparable_pair_count": len(comparable_reductions),
            "evidence_reduction_ratio": distribution(comparable_reductions),
            "control_target_tokens": distribution(control_target), "treatment_target_tokens": distribution(treatment_target),
        },
        "behavior": {
            "accuracy_delta": accuracy_delta, "control_dominant_path_retention": control_retention,
            "treatment_dominant_path_retention": treatment_retention,
            "dominant_path_retention_delta": treatment_retention - control_retention,
            "tool_call_delta": distribution(tool_deltas), "cycle_delta": distribution(cycle_deltas),
            "novel_treatment_compensation_path_count": len(novel_compensation),
        },
        "session_cost": {
            "effect": cost_effect, "pooled_treatment_control_ratio": pooled_ratio,
            "control_total_tokens": distribution(control_total), "treatment_total_tokens": distribution(treatment_total),
            "paired_total_token_delta": distribution(session_deltas),
        },
        "claim_scope": {
            "potentially_avoidable_observed_evidence_supported": verdict == "PASS",
            "end_to_end_savings_claim": False, "global_generalization": False,
        },
    }


def formal_summary(spec: dict[str, Any], spec_path: Path, runs: list[dict[str, Any]]) -> dict[str, Any]:
    cases = [formal_case_summary(spec, case, runs) for case in spec["cases"]]
    return {
        "schema_version": 1, "schema_id": RESULT_SCHEMA_ID, "experiment_id": spec["experiment_id"],
        "runner_version": RUNNER_VERSION, "spec_sha256": sha256_file(spec_path), "run_count": len(runs),
        "cases": cases, "runs": [compact_run(run) for run in runs],
        "summary": {
            "case_count": len(cases), "pass_count": sum(row["verdict"] == "PASS" for row in cases),
            "fail_count": sum(row["verdict"] == "FAIL" for row in cases),
            "inconclusive_count": sum(row["verdict"] == "INCONCLUSIVE" for row in cases),
        },
        "policy": spec["policy"],
    }


def scheduled_runs(spec: dict[str, Any], phase: str) -> list[tuple[dict[str, Any], int, str]]:
    schedule = []
    blocks = 1 if phase == "pilot" else spec["formal"]["blocks_per_case"]
    for case in spec["cases"]:
        for block in range(1, blocks + 1):
            order = ["control", "treatment"] if phase == "pilot" or block % 2 else ["treatment", "control"]
            for arm in order:
                schedule.append((case, block, arm))
    return schedule


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    plugin = Path(__file__).resolve().parents[1]
    workspace = plugin.parents[1]
    parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    parser.add_argument("--repository", type=Path, default=workspace)
    parser.add_argument("--spec", type=Path, default=plugin / "resources/acp1_3d_experiment_spec.json")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--pilot-result", type=Path, default=plugin / "resources/acp1_3d_pilot_results.json")
    parser.add_argument("--formal-result", type=Path, default=plugin / "resources/acp1_3d_results.json")
    parser.add_argument("--codex", type=Path, default=Path(shutil.which("codex") or "codex"))
    parser.add_argument("--source-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--offline-check", action="store_true")
    args = parser.parse_args()
    spec_path = args.spec.resolve()
    spec = load_spec(spec_path, plugin)
    if args.offline_check:
        print(canonical_bytes({"case_count": len(spec["cases"]), "pilot_runs": 4, "formal_runs": 80, "spec_sha256": sha256_file(spec_path)}).decode("utf-8"), end="")
        return 0
    if args.phase == "formal":
        pilot = load_object(args.pilot_result.resolve())
        if pilot.get("status") != "pass" or pilot.get("included_in_formal_statistics") is not False:
            raise AblationError("pilot_not_passed")
    default_name = f"acp1-3d-{args.phase}-20260818"
    artifacts = (args.artifacts or (workspace / ".agent-token-manager" / default_name)).resolve()
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    runs = [run_one(
        spec, case, args.phase, block, arm, args.repository.resolve(), args.codex.resolve(),
        args.source_home.resolve(), artifacts, args.timeout, args.resume,
    ) for case, block, arm in scheduled_runs(spec, args.phase)]
    if args.phase == "pilot":
        result = pilot_summary(spec, runs)
        args.pilot_result.resolve().write_bytes(canonical_bytes(result))
        output_path = args.pilot_result.resolve()
    else:
        result = formal_summary(spec, spec_path, runs)
        args.formal_result.resolve().write_bytes(canonical_bytes(result))
        output_path = args.formal_result.resolve()
    print(canonical_bytes({"phase": args.phase, "run_count": len(runs), "status": result.get("status", result.get("summary")), "result_sha256": sha256_file(output_path)}).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
