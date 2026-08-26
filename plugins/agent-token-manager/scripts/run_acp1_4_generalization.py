#!/usr/bin/env python3
"""Run ACP-1.4A qualification and ACP-1.4B natural ablation generalization."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import run_acp1_3c_qualification as qualification
import run_acp1_3d_ablation as prior
from run_co0_gate import load_jsonl
from run_co1_1_pilot import cumulative_usage_series
from run_co1_gate2 import final_message, final_usage, new_transcript, normalize_command, transcript_calls


RUNNER_VERSION = "acp1-4-natural-generalization-runner-v0.1"
FAILURE_MARKERS = ("script failed", "script error")
FROZEN_HASHES = {
    "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
    "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
    "resources/acp1_3c_candidate_registry.json": "b618e64409b5e3e9d75b9b2a412b6bbd58c486a363afa4f58968e8a17f58f0f8",
    "resources/acp1_3d_results.json": "5f2b7d41b0f59b3b7310e90aa2b5d4ff404345ce5687ed111da85a68c0ab388a",
    "resources/acp1_3d_frozen_ablation_index.json": "740dc39d0786702a4073e034fe48d64fe4b44aefb79d339e5c4f71cc6eaee837",
    "resources/acp1_3d_frozen_experiment_manifest.json": "52c25023070f6b4b253ff7b3be6507be3d8501d2d383819918ac911f9b7675f2",
}


class GeneralizationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GeneralizationError(f"object_required:{path.name}")
    return value


def load_spec(path: Path, plugin: Path) -> dict[str, Any]:
    spec = load(path)
    if spec.get("schema_id") != "acp1-4-natural-generalization-spec-v1":
        raise GeneralizationError("invalid_spec")
    cases = spec.get("cases", [])
    family_counts = Counter(row.get("family") for row in cases)
    if len(cases) != 8 or family_counts != Counter({"read": 3, "search": 3, "bash": 2}):
        raise GeneralizationError("invalid_sampling_frame")
    if spec["qualification"]["repetitions_per_case"] != 10 or spec["formal"]["blocks_per_case"] != 10:
        raise GeneralizationError("invalid_repeated_design")
    if len({row["case_id"] for row in cases}) != len(cases):
        raise GeneralizationError("duplicate_case_id")
    allowed = {"prefix-source-projection-v1", "hashed-nontarget-match-ablation-v1", "python-unittest-method-subset-v1"}
    if any(row["treatment"]["method"] not in allowed for row in cases):
        raise GeneralizationError("unsupported_treatment")
    if any(spec["policy"][key] for key in ("collector_or_hook_mutation", "production_slicing_or_replacement", "real_time_recommendation", "global_savings_claim")):
        raise GeneralizationError("policy_boundary_violation")
    for relative, expected in FROZEN_HASHES.items():
        target = plugin / relative
        if not target.is_file() or sha256_file(target) != expected:
            raise GeneralizationError(f"frozen_hash_mismatch:{relative}")
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
        result = re.sub(re.escape(term), "__ACP14_ABLATED_TERM__", result, flags=re.IGNORECASE)
    return result


def apply_treatment(workdir: Path, case: dict[str, Any]) -> dict[str, Any]:
    treatment = case["treatment"]
    method = treatment["method"]
    if method == "prefix-source-projection-v1":
        target = workdir / treatment["target"]
        before = target.read_text(encoding="utf-8")
        rows = before.splitlines(keepends=True)
        after = "".join(rows[: int(treatment["keep_first_lines"])])
        target.write_text(after, encoding="utf-8")
        return {"method": method, "changed_file_count": 1, "changed_line_count": len(rows) - len(after.splitlines())}
    if method == "hashed-nontarget-match-ablation-v1":
        preserved = treatment["preserved_target"]
        terms = list(treatment["match_terms"])
        changed_files = changed_lines = 0
        for path in sorted(item for item in workdir.rglob("*") if item.is_file()):
            relative = path.relative_to(workdir).as_posix()
            try:
                before = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if relative == preserved:
                continue
            rows = before.splitlines(keepends=True)
            changed = False
            for index, row in enumerate(rows, 1):
                if any(term.casefold() in row.casefold() for term in terms):
                    digest = hashlib.sha256(f"{relative}:{index}".encode("utf-8")).digest()
                    if digest[0] % 2 == int(treatment["ablate_when_first_byte_mod_2"]):
                        rows[index - 1] = _replace_terms(row, terms)
                        changed = True
                        changed_lines += 1
            if changed:
                path.write_text("".join(rows), encoding="utf-8")
                changed_files += 1
        return {"method": method, "changed_file_count": changed_files, "changed_line_count": changed_lines}
    if method == "python-unittest-method-subset-v1":
        target = workdir / treatment["target"]
        relative = target.relative_to(workdir).as_posix()
        before = target.read_text(encoding="utf-8")
        tree = ast.parse(before)
        intervals: list[tuple[int, int]] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
                continue
            digest = hashlib.sha256(f"{relative}:{node.name}".encode("utf-8")).digest()
            if digest[0] % 2 != int(treatment["preserve_digest_mod_2"]):
                start = min([node.lineno, *[item.lineno for item in node.decorator_list]])
                intervals.append((start, int(node.end_lineno or node.lineno)))
        rows = before.splitlines(keepends=True)
        removed = {line for start, end in intervals for line in range(start, end + 1)}
        after = "".join(row for index, row in enumerate(rows, 1) if index not in removed)
        ast.parse(after)
        target.write_text(after, encoding="utf-8")
        return {"method": method, "changed_file_count": 1, "changed_line_count": len(removed), "removed_test_method_count": len(intervals)}
    raise GeneralizationError(f"unknown_treatment:{method}")


def analyze_calls(calls: list[dict[str, Any]], case: dict[str, Any], require_minimum: bool) -> dict[str, Any]:
    matching: list[int] = []
    for index, call in enumerate(calls):
        command = normalize_command(str(call.get("command", ""))).casefold()
        output = str(call.get("output", ""))
        terms_match = all(str(term).casefold() in command for term in case["candidate_command_terms"])
        size_match = not require_minimum or len(output) >= int(case["minimum_result_chars"])
        if terms_match and size_match and not any(marker in output.casefold() for marker in FAILURE_MARKERS):
            matching.append(index)
    unique_index = matching[0] if len(matching) == 1 else None
    path = []
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
        "candidate_visible_estimated_tokens": (len(output) + 3) // 4 if candidate else None,
        "candidate_result_sha256": sha256_text(output) if candidate else None,
        "candidate_success_semantics": candidate is not None and not any(marker in output.casefold() for marker in FAILURE_MARKERS),
        "path_signature_sha256": hashlib.sha256(canonical_bytes(path)).hexdigest(),
    }


def prepare_run(
    spec: dict[str, Any], case: dict[str, Any], phase: str, ordinal: int, arm: str,
    repository: Path, codex: Path, source_home: Path, artifacts: Path, timeout: int, resume: bool,
) -> dict[str, Any]:
    run_id = f"{phase}__{case['case_id']}__r{ordinal:02d}-{arm}"
    run_dir = artifacts / run_id
    result_path = run_dir / "result.json"
    if resume and result_path.is_file():
        value = load(result_path)
        if value.get("run_id") != run_id:
            raise GeneralizationError(f"resume_identity_mismatch:{run_id}")
        return value
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix="acp14-"))
    workdir = temporary / "subject"
    started = time.perf_counter()
    try:
        qualification.materialize_subject(repository, spec["subject_commit"], workdir)
        treatment = apply_treatment(workdir, case) if arm == "treatment" else {"method": "none_control", "changed_file_count": 0, "changed_line_count": 0}
        home = qualification.prepare_home(run_dir, source_home)
        before = set(home.rglob("*.jsonl"))
        environment = dict(os.environ, CODEX_HOME=str(home), PWD=str(workdir))
        command = [
            str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust", "--skip-git-repo-check",
            "--sandbox", "read-only", "--model", spec["model"], "--cd", str(workdir),
            "--config", f'model_reasoning_effort="{spec["reasoning_effort"]}"', "--config", "features.multi_agent=false", build_prompt(case),
        ]
        completed = subprocess.run(command, cwd=workdir, env=environment, text=True, capture_output=True, timeout=timeout)
        (run_dir / "codex.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        exec_events = load_jsonl(run_dir / "codex.jsonl")
        transcript = new_transcript(home, before)
        transcript_events = load_jsonl(transcript) if transcript else []
        calls = transcript_calls(transcript_events)
        final = final_message(exec_events)
        result = {
            "schema_version": 1, "run_id": run_id, "phase": phase, "case_id": case["case_id"], "case_version": case["case_version"],
            "family": case["family"], "ordinal": ordinal, "arm": arm,
            "status": "completed" if completed.returncode == 0 else "failed", "process_returncode": completed.returncode,
            "correct": completed.returncode == 0 and final.strip() == case["expected"], "final_text": final, "expected": case["expected"],
            "elapsed_seconds": round(time.perf_counter() - started, 3), "usage": final_usage(exec_events),
            "model_cycles": len(cumulative_usage_series(transcript_events)), "tool_call_count": len(calls),
            "prompt_sha256": sha256_text(build_prompt(case)), "hook_or_collector_used": False, "treatment": treatment,
            **analyze_calls(calls, case, require_minimum=phase == "qualification"),
        }
    except Exception as error:
        result = {
            "schema_version": 1, "run_id": run_id, "phase": phase, "case_id": case["case_id"], "case_version": case["case_version"],
            "family": case["family"], "ordinal": ordinal, "arm": arm, "status": "failed", "correct": False,
            "error": f"{type(error).__name__}: {error}", "hook_or_collector_used": False,
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    result_path.write_bytes(canonical_bytes(result))
    return result


def compact(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id_sha256": sha256_text(str(run.get("run_id", ""))), "case_id": run.get("case_id"), "family": run.get("family"),
        "ordinal": run.get("ordinal"), "arm": run.get("arm"), "status": run.get("status"), "correct": bool(run.get("correct")),
        "total_tokens": run.get("usage", {}).get("total_tokens"), "model_cycles": run.get("model_cycles"),
        "tool_call_count": run.get("tool_call_count"), "candidate_recurred": bool(run.get("candidate_recurred")),
        "candidate_ambiguous": bool(run.get("candidate_ambiguous")), "candidate_visible_estimated_tokens": run.get("candidate_visible_estimated_tokens"),
        "candidate_result_sha256": run.get("candidate_result_sha256"), "candidate_success_semantics": bool(run.get("candidate_success_semantics")),
        "path_signature_sha256": run.get("path_signature_sha256"), "treatment_method": run.get("treatment", {}).get("method"),
        "hook_or_collector_used": bool(run.get("hook_or_collector_used")),
    }


def qualification_case(spec: dict[str, Any], case: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds = spec["qualification"]
    completed = sum(run.get("status") == "completed" and int(run.get("usage", {}).get("total_tokens", 0)) > 0 for run in runs)
    correct = sum(bool(run.get("correct")) for run in runs)
    recurrence = sum(bool(run.get("candidate_recurred")) for run in runs)
    ambiguous = sum(bool(run.get("candidate_ambiguous")) for run in runs)
    paths = Counter(str(run.get("path_signature_sha256")) for run in runs if run.get("path_signature_sha256"))
    top = paths.most_common()
    dominant_frequency = top[0][1] if top else 0
    tied = bool(top and sum(count == dominant_frequency for _, count in top) > 1)
    dominant_hash = None if tied or not top else top[0][0]
    checks = {
        "completed_with_usage": completed == thresholds["completed_with_usage"],
        "correctness": correct >= thresholds["correct_min"],
        "candidate_recurrence": recurrence >= thresholds["candidate_recurrence_min"],
        "identity_unambiguous": ambiguous <= thresholds["ambiguous_max"],
        "dominant_path_stability": not tied and dominant_frequency >= thresholds["dominant_path_frequency_min"],
    }
    status = "qualified" if all(checks.values()) else ("diagnostic_only" if all(value for name, value in checks.items() if name != "dominant_path_stability") else "rejected")
    return {
        "case_id": case["case_id"], "case_version": case["case_version"], "family": case["family"], "category": case["category"],
        "status": status, "reason_codes": [name for name, value in checks.items() if not value], "eligible_for_acp1_4b": status == "qualified",
        "native_calibration": {
            "run_count": len(runs), "completed_with_usage": completed, "correct": correct, "candidate_recurrence": recurrence,
            "ambiguous_candidate_matches": ambiguous, "dominant_path_frequency": dominant_frequency,
            "target_visible_token_distribution": prior.distribution([int(run["candidate_visible_estimated_tokens"]) for run in runs if isinstance(run.get("candidate_visible_estimated_tokens"), int)]),
            "session_total_token_distribution": prior.distribution([int(run["usage"]["total_tokens"]) for run in runs if isinstance(run.get("usage", {}).get("total_tokens"), int)]),
        },
        "dominant_path": {"signature_sha256": dominant_hash, "frequency": dominant_frequency, "status": "ambiguous" if tied else ("known" if top else "unknown")},
        "candidate_identity": {"logical_target_id": case["logical_target_id"], "command_terms": case["candidate_command_terms"], "minimum_result_chars": case["minimum_result_chars"]},
        "treatment": case["treatment"], "checks": checks,
    }


def qualification_outputs(spec: dict[str, Any], spec_path: Path, runs: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [qualification_case(spec, case, [run for run in runs if run["case_id"] == case["case_id"]]) for case in spec["cases"]]
    family = {name: {"proposed": sum(row["family"] == name for row in cases), "qualified": sum(row["family"] == name and row["status"] == "qualified" for row in cases)} for name in spec["generalization"]["required_families"]}
    coverage = sum(row["status"] == "qualified" for row in cases) >= spec["generalization"]["qualified_case_min"] and all(row["qualified"] >= spec["generalization"]["qualified_per_family_min"] for row in family.values())
    result = {
        "schema_version": 1, "schema_id": "acp1-4a-qualification-result-v1", "experiment_id": spec["experiment_id"],
        "runner_version": RUNNER_VERSION, "spec_sha256": sha256_file(spec_path), "run_count": len(runs), "cases": cases,
        "runs": [compact(run) for run in runs], "family_coverage": family, "formal_coverage_gate": coverage,
        "policy": {"native_only": True, "intervention": False, "all_attrition_preserved": True},
    }
    registry = {
        "schema_version": 1, "schema_id": "acp1-4-natural-candidate-registry-v1", "status": "qualification_complete_under_frozen_scope",
        "source_result_sha256": hashlib.sha256(canonical_bytes(result)).hexdigest(), "spec_sha256": sha256_file(spec_path),
        "cases": cases, "family_coverage": family, "formal_coverage_gate": coverage,
        "funnel": {"proposed": len(cases), "qualified": sum(row["status"] == "qualified" for row in cases), "diagnostic_only": sum(row["status"] == "diagnostic_only" for row in cases), "rejected": sum(row["status"] == "rejected" for row in cases)},
        "consumer_policy": {"all_and_only_qualified_enter_formal": True, "failed_or_unsupported_preserved": True},
    }
    return result, registry


def paired_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for run in runs:
        pairs[(run["case_id"], int(run["ordinal"]))][run["arm"]] = run
    rows = []
    for (case_id, ordinal), arms in sorted(pairs.items()):
        if set(arms) != {"control", "treatment"}:
            continue
        control, treatment = arms["control"], arms["treatment"]
        before, after = control.get("candidate_visible_estimated_tokens"), treatment.get("candidate_visible_estimated_tokens")
        reduction = (before - after) / before if isinstance(before, int) and before > 0 and isinstance(after, int) else None
        rows.append({
            "case_id": case_id, "ordinal": ordinal, "control": control, "treatment": treatment, "evidence_reduction_ratio": reduction,
            "tool_call_delta": int(treatment.get("tool_call_count", 0)) - int(control.get("tool_call_count", 0)),
            "cycle_delta": int(treatment.get("model_cycles", 0)) - int(control.get("model_cycles", 0)),
            "session_token_delta": int(treatment.get("usage", {}).get("total_tokens", 0)) - int(control.get("usage", {}).get("total_tokens", 0)),
        })
    return rows


def formal_case(spec: dict[str, Any], case: dict[str, Any], qualification_row: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    threshold = spec["formal"]
    selected = [run for run in runs if run["case_id"] == case["case_id"]]
    control = [run for run in selected if run["arm"] == "control"]
    treatment = [run for run in selected if run["arm"] == "treatment"]
    pairs = paired_rows(selected)
    reductions = [row["evidence_reduction_ratio"] for row in pairs if row["evidence_reduction_ratio"] is not None]
    control_correct = sum(bool(run.get("correct")) for run in control)
    treatment_correct = sum(bool(run.get("correct")) for run in treatment)
    accuracy_delta = treatment_correct / 10 - control_correct / 10
    treatment_only_failures = sum(row["control"].get("correct") and not row["treatment"].get("correct") for row in pairs)
    dominant = qualification_row["dominant_path"]["signature_sha256"]
    control_retention = sum(run.get("path_signature_sha256") == dominant for run in control) / 10
    treatment_retention = sum(run.get("path_signature_sha256") == dominant for run in treatment) / 10
    control_paths = Counter(str(run.get("path_signature_sha256")) for run in control)
    treatment_paths = Counter(str(run.get("path_signature_sha256")) for run in treatment)
    novel = [path for path, count in treatment_paths.items() if count >= threshold["novel_treatment_path_repeated_min"] and control_paths.get(path, 0) == 0]
    completed = sum(run.get("status") == "completed" and int(run.get("usage", {}).get("total_tokens", 0)) > 0 for run in selected)
    tool_deltas, cycle_deltas = [row["tool_call_delta"] for row in pairs], [row["cycle_delta"] for row in pairs]
    gates = {
        "g1_eligibility": qualification_row["status"] == "qualified",
        "g2_activation": len(reductions) >= threshold["candidate_recurrence_min"] and statistics.median(reductions) >= threshold["minimum_evidence_reduction_ratio"] and sum(run.get("candidate_recurred") for run in treatment) >= threshold["candidate_recurrence_min"],
        "g3_correctness": control_correct >= threshold["control_correct_min"] and treatment_correct >= threshold["treatment_correct_min"] and accuracy_delta >= threshold["accuracy_delta_min"] and treatment_only_failures <= threshold["treatment_only_failures_max"],
        "g4_tool_path": sum(run.get("candidate_recurred") for run in control) >= threshold["candidate_recurrence_min"] and treatment_retention - control_retention >= threshold["dominant_path_retention_delta_min"] and len(tool_deltas) == 10 and statistics.median(tool_deltas) <= threshold["paired_median_tool_call_delta_max"] and not novel,
        "g5_cycle": len(cycle_deltas) == 10 and statistics.median(cycle_deltas) <= threshold["paired_median_cycle_delta_max"],
        "g6_success_semantics": all(run.get("candidate_success_semantics") for run in selected if run.get("candidate_recurred")) and all(not run.get("candidate_ambiguous") for run in selected),
        "g7_outcome_completeness": completed == threshold["completed_with_usage_required"] and len(pairs) == 10,
        "g8_no_overclaim_frozen_integrity": True,
    }
    verdict = "PASS" if all(gates.values()) else ("INCONCLUSIVE" if not gates["g2_activation"] or not gates["g7_outcome_completeness"] else "FAIL")
    control_total = [int(run["usage"]["total_tokens"]) for run in control if isinstance(run.get("usage", {}).get("total_tokens"), int)]
    treatment_total = [int(run["usage"]["total_tokens"]) for run in treatment if isinstance(run.get("usage", {}).get("total_tokens"), int)]
    return {
        "case_id": case["case_id"], "family": case["family"], "verdict": verdict, "gates": gates,
        "counts": {"control_runs": len(control), "treatment_runs": len(treatment), "completed_with_usage": completed, "control_correct": control_correct, "treatment_correct": treatment_correct, "treatment_only_failures": treatment_only_failures, "control_recurrence": sum(run.get("candidate_recurred") for run in control), "treatment_recurrence": sum(run.get("candidate_recurred") for run in treatment)},
        "activation": {"comparable_pair_count": len(reductions), "evidence_reduction_ratio": prior.distribution(reductions)},
        "behavior": {"accuracy_delta": accuracy_delta, "dominant_path_retention_delta": treatment_retention - control_retention, "tool_call_delta": prior.distribution(tool_deltas), "cycle_delta": prior.distribution(cycle_deltas), "novel_treatment_compensation_path_count": len(novel)},
        "session_cost": {"interpretability": "descriptive_only_if_behavior_pass" if verdict == "PASS" else "not_interpretable", "pooled_treatment_control_ratio": sum(treatment_total) / sum(control_total) if control_total and sum(control_total) else None, "control_total_tokens": prior.distribution(control_total), "treatment_total_tokens": prior.distribution(treatment_total), "paired_total_token_delta": prior.distribution([row["session_token_delta"] for row in pairs])},
        "claim_scope": {"case_specific_causal_evidence": verdict == "PASS", "global_savings_claim": False},
    }


def generalization_summary(spec: dict[str, Any], rows: list[dict[str, Any]], registry: dict[str, Any], all_qualified_ran: bool) -> dict[str, Any]:
    by_family = {}
    for family in spec["generalization"]["required_families"]:
        selected = [row for row in rows if row["family"] == family]
        by_family[family] = {"qualified": len(selected), "pass": sum(row["verdict"] == "PASS" for row in selected), "fail": sum(row["verdict"] == "FAIL" for row in selected), "inconclusive": sum(row["verdict"] == "INCONCLUSIVE" for row in selected)}
    qualified = len(rows)
    passed = sum(row["verdict"] == "PASS" for row in rows)
    failed = sum(row["verdict"] == "FAIL" for row in rows)
    coverage = registry["formal_coverage_gate"] and all_qualified_ran
    supported = coverage and qualified > 0 and passed / qualified >= spec["generalization"]["pass_rate_min"] and all(row["pass"] >= spec["generalization"]["pass_per_family_min"] for row in by_family.values())
    if not coverage or any(row["verdict"] == "INCONCLUSIVE" for row in rows):
        verdict = "INSUFFICIENT_COVERAGE"
    elif supported:
        verdict = "SUPPORTED_WITH_BOUNDARIES"
    elif passed == 0 or failed > qualified / 2:
        verdict = "NOT_SUPPORTED"
    else:
        verdict = "MIXED"
    return {"verdict": verdict, "qualified_case_count": qualified, "pass_count": passed, "fail_count": failed, "inconclusive_count": sum(row["verdict"] == "INCONCLUSIVE" for row in rows), "pass_rate": passed / qualified if qualified else None, "families": by_family, "all_qualified_ran": all_qualified_ran}


def pilot_output(spec: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = paired_rows(runs)
    families = []
    for family in spec["generalization"]["required_families"]:
        pair = next((row for row in pairs if row["control"]["family"] == family), None)
        ratio = pair["evidence_reduction_ratio"] if pair else None
        checks = {
            "pair_complete": pair is not None,
            "both_correct": bool(pair and pair["control"].get("correct") and pair["treatment"].get("correct")),
            "identity_unique": bool(pair and all(arm.get("candidate_recurred") and not arm.get("candidate_ambiguous") for arm in (pair["control"], pair["treatment"]))),
            "activation": ratio is not None and ratio >= spec["formal"]["minimum_evidence_reduction_ratio"],
            "success_semantics": bool(pair and pair["control"].get("candidate_success_semantics") and pair["treatment"].get("candidate_success_semantics")),
        }
        families.append({"family": family, "case_id": pair["case_id"] if pair else None, "checks": checks, "evidence_reduction_ratio": ratio, "status": "pass" if all(checks.values()) else "fail"})
    return {"schema_version": 1, "schema_id": "acp1-4b-family-pilot-result-v1", "run_count": len(runs), "included_in_formal_statistics": False, "families": families, "status": "pass" if len(families) == 3 and all(row["status"] == "pass" for row in families) else "inconclusive_plumbing"}


def schedule_formal(cases: list[dict[str, Any]], blocks: int) -> list[tuple[dict[str, Any], int, str]]:
    result = []
    for case in cases:
        for block in range(1, blocks + 1):
            arms = ("control", "treatment") if block % 2 else ("treatment", "control")
            result.extend((case, block, arm) for arm in arms)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    plugin = Path(__file__).resolve().parents[1]
    workspace = plugin.parents[1]
    parser.add_argument("--phase", choices=("qualification", "pilot", "formal"), required=True)
    parser.add_argument("--repository", type=Path, default=workspace)
    parser.add_argument("--spec", type=Path, default=plugin / "resources/acp1_4_experiment_spec.json")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--qualification-result", type=Path, default=plugin / "resources/acp1_4a_results.json")
    parser.add_argument("--registry", type=Path, default=plugin / "resources/acp1_4a_candidate_registry.json")
    parser.add_argument("--pilot-result", type=Path, default=plugin / "resources/acp1_4b_pilot_results.json")
    parser.add_argument("--formal-result", type=Path, default=plugin / "resources/acp1_4b_results.json")
    parser.add_argument("--codex", type=Path, default=Path(shutil.which("codex") or "codex"))
    parser.add_argument("--source-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--offline-check", action="store_true")
    args = parser.parse_args()
    spec_path = args.spec.resolve()
    spec = load_spec(spec_path, plugin)
    if args.offline_check:
        print(canonical_bytes({"spec_sha256": sha256_file(spec_path), "proposed_cases": len(spec["cases"]), "qualification_runs": 80, "formal_runs_per_qualified_case": 20}).decode(), end="")
        return 0
    artifacts = (args.artifacts or workspace / ".agent-token-manager" / f"acp1-4-{args.phase}-20260818").resolve()
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.phase == "qualification":
        schedule = [(case, repetition, "native") for case in spec["cases"] for repetition in range(1, 11)]
        runs = [prepare_run(spec, case, "qualification", ordinal, arm, args.repository.resolve(), args.codex.resolve(), args.source_home.resolve(), artifacts, args.timeout, args.resume) for case, ordinal, arm in schedule]
        result, registry = qualification_outputs(spec, spec_path, runs)
        args.qualification_result.resolve().write_bytes(canonical_bytes(result))
        args.registry.resolve().write_bytes(canonical_bytes(registry))
        output = {"phase": "qualification", "run_count": len(runs), "funnel": registry["funnel"], "formal_coverage_gate": registry["formal_coverage_gate"], "result_sha256": sha256_file(args.qualification_result.resolve()), "registry_sha256": sha256_file(args.registry.resolve())}
    else:
        registry = load(args.registry.resolve())
        if registry.get("spec_sha256") != sha256_file(spec_path):
            raise GeneralizationError("registry_spec_mismatch")
        qualified_ids = [row["case_id"] for row in registry["cases"] if row["status"] == "qualified"]
        cases = [case for case in spec["cases"] if case["case_id"] in qualified_ids]
        if {case["case_id"] for case in cases} != set(qualified_ids):
            raise GeneralizationError("qualified_case_set_mismatch")
        if args.phase == "pilot":
            representatives = []
            for family in spec["generalization"]["required_families"]:
                selected = next((case for case in cases if case["family"] == family), None)
                if selected:
                    representatives.append(selected)
            schedule = [(case, 1, arm) for case in representatives for arm in ("control", "treatment")]
            runs = [prepare_run(spec, case, "pilot", ordinal, arm, args.repository.resolve(), args.codex.resolve(), args.source_home.resolve(), artifacts, args.timeout, args.resume) for case, ordinal, arm in schedule]
            result = pilot_output(spec, runs)
            args.pilot_result.resolve().write_bytes(canonical_bytes(result))
            output = {"phase": "pilot", "run_count": len(runs), "status": result["status"], "result_sha256": sha256_file(args.pilot_result.resolve())}
        else:
            pilot = load(args.pilot_result.resolve())
            if pilot.get("status") != "pass" or pilot.get("included_in_formal_statistics") is not False:
                raise GeneralizationError("pilot_not_passed")
            schedule = schedule_formal(cases, spec["formal"]["blocks_per_case"])
            runs = [prepare_run(spec, case, "formal", ordinal, arm, args.repository.resolve(), args.codex.resolve(), args.source_home.resolve(), artifacts, args.timeout, args.resume) for case, ordinal, arm in schedule]
            qrows = {row["case_id"]: row for row in registry["cases"]}
            summaries = [formal_case(spec, case, qrows[case["case_id"]], runs) for case in cases]
            all_qualified_ran = {row["case_id"] for row in summaries} == set(qualified_ids)
            result = {
                "schema_version": 1, "schema_id": "acp1-4b-generalization-result-v1", "experiment_id": spec["experiment_id"],
                "runner_version": RUNNER_VERSION, "spec_sha256": sha256_file(spec_path), "registry_sha256": sha256_file(args.registry.resolve()),
                "run_count": len(runs), "funnel": {**registry["funnel"], "formal_cases": len(summaries), "treatment_activated": sum(row["gates"]["g2_activation"] for row in summaries), "pass": sum(row["verdict"] == "PASS" for row in summaries), "fail": sum(row["verdict"] == "FAIL" for row in summaries), "inconclusive": sum(row["verdict"] == "INCONCLUSIVE" for row in summaries)},
                "cases": summaries, "generalization": generalization_summary(spec, summaries, registry, all_qualified_ran),
                "runs": [compact(run) for run in runs], "policy": spec["policy"],
            }
            args.formal_result.resolve().write_bytes(canonical_bytes(result))
            output = {"phase": "formal", "run_count": len(runs), "generalization": result["generalization"], "result_sha256": sha256_file(args.formal_result.resolve())}
    print(canonical_bytes(output).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
