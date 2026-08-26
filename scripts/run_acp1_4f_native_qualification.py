#!/usr/bin/env python3
"""Run ACP-1.4F-1 Native-only qualification over the frozen 12-case universe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import run_acp1_3c_qualification as base


RUNNER_VERSION = "acp1-4f-native-qualification-runner-v0.1"
RESULT_SCHEMA_ID = "acp1-4f-native-qualification-result-v1"
REGISTRY_SCHEMA_ID = "acp1-4f-native-qualification-registry-v1"
FAILURE_MARKERS = ("script failed", "script error")


class QualificationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationError(f"object_required:{path.name}")
    return value


def load_contract(root: Path, path: Path, index_path: Path) -> dict[str, Any]:
    index = load(index_path)
    contract = load(path)
    if index.get("schema_id") != "acp1-4f-f0-frozen-index-v1":
        raise QualificationError("invalid_f0_index")
    if index.get("agent_run_count") != 0 or index.get("authorization_boundary", {}).get("native_qualification_ready") is not True:
        raise QualificationError("f0_not_ready")
    if contract.get("experiment_id") != "acp1-4f-combined-prospective-generalization-v2.1":
        raise QualificationError("invalid_experiment_version")
    if sha256_file(path) != index["artifacts"]["contract"]["sha256"]:
        raise QualificationError("contract_hash_mismatch")
    if len(contract.get("cases", [])) != 12 or contract["qualification"]["native_repetitions_per_case"] != 10:
        raise QualificationError("invalid_native_design")
    if contract["execution"]["builder_enabled_during_native"] or contract["policy"]["collector_or_hook_mutation"]:
        raise QualificationError("native_only_boundary_violation")
    for artifact in index["artifacts"].values():
        artifact_path = root / artifact["path"]
        if not artifact_path.is_file() or sha256_file(artifact_path) != artifact["sha256"]:
            raise QualificationError(f"frozen_artifact_mismatch:{artifact['path']}")
    return contract


def build_prompt(case: dict[str, Any]) -> str:
    return (
        "Work only from the local frozen fixture repository. Do not use web tools, plugins, skills, "
        "Task Navigator, Smart Read, context_router, navigation_map, or subagents. Do not modify files. "
        "Use the requested local tool style and gather evidence before answering. " + case["prompt"]
    )


def executable_kind(command: str) -> str:
    normalized = base.normalize_command(command).casefold()
    if re.search(r"(?:^|[;&|]\s*)(?:/[^ ]*/)?(?:rg|grep|find)\b", normalized):
        return "search"
    if re.search(r"(?:^|[;&|]\s*)(?:/[^ ]*/)?(?:sed|cat|head|tail|awk|nl)\b", normalized):
        return "read"
    if re.search(r"(?:^|[;&|]\s*)(?:/[^ ]*/)?(?:python3?|pytest|make|npm|cargo)\b", normalized):
        return "program"
    return "other"


def candidate_match(call: dict[str, Any], case: dict[str, Any], minimum_chars: int) -> bool:
    command = base.normalize_command(str(call.get("command", ""))).casefold()
    output = str(call.get("output", ""))
    identity = case["candidate_identity"]
    return (
        executable_kind(command) in set(identity["allowed_executable_kinds"])
        and all(str(term).casefold() in command for term in identity["required_command_terms"])
        and len(output) >= minimum_chars
        and not any(marker in output.casefold() for marker in FAILURE_MARKERS)
    )


def analyze_calls(calls: list[dict[str, Any]], case: dict[str, Any], minimum_chars: int) -> dict[str, Any]:
    matching = [index for index, call in enumerate(calls) if candidate_match(call, case, minimum_chars)]
    unique_index = matching[0] if len(matching) == 1 else None
    path = []
    for index, call in enumerate(calls):
        output = str(call.get("output", ""))
        relation = "ambiguous" if len(matching) > 1 and index in matching else ("candidate" if index == unique_index else "noncandidate")
        path.append({
            "tool_family": str(call.get("tool_name", "unknown")),
            "executable_kind": executable_kind(str(call.get("command", ""))),
            "candidate_relation": relation,
            "success_semantics": "failure" if any(marker in output.casefold() for marker in FAILURE_MARKERS) else "success",
        })
    candidate = calls[unique_index] if unique_index is not None else None
    output = str(candidate.get("output", "")) if candidate else ""
    return {
        "candidate_match_count": len(matching),
        "candidate_recurred": len(matching) == 1,
        "candidate_ambiguous": len(matching) > 1,
        "candidate_result_chars": len(output) if candidate else None,
        "candidate_visible_estimated_tokens": (len(output) + 3) // 4 if candidate else None,
        "candidate_request_sha256": sha256_text(base.normalize_command(str(candidate.get("command", "")))) if candidate else None,
        "candidate_result_sha256": sha256_text(output) if candidate else None,
        "path_signature_sha256": hashlib.sha256(canonical_bytes(path)).hexdigest(),
    }


def score(final: str, oracle: dict[str, Any]) -> bool:
    actual = final.strip()
    if oracle["scorer"] == "exact_text_casefold_v1":
        return actual.casefold() == str(oracle["expected"]).casefold()
    if oracle["scorer"] == "exact_text_v1":
        return actual == str(oracle["expected"])
    raise QualificationError(f"unsupported_scorer:{oracle['scorer']}")


def materialize_subject(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)


def run_one(
    contract: dict[str, Any], oracle_registry: dict[str, Any], case: dict[str, Any], repetition: int,
    codex: Path, source_home: Path, artifacts: Path, timeout: int, resume: bool, subjects: Path,
) -> dict[str, Any]:
    run_id = f"{case['case_id']}__r{repetition:02d}-native"
    run_dir = artifacts / run_id
    result_path = run_dir / "result.json"
    if resume and result_path.is_file():
        result = load(result_path)
        if result.get("run_id") != run_id or result.get("case_id") != case["case_id"]:
            raise QualificationError(f"resume_identity_mismatch:{run_id}")
        return result
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix="acp14f-native-"))
    workdir = temporary / "subject"
    started = time.perf_counter()
    try:
        materialize_subject(subjects, workdir)
        home = base.prepare_home(run_dir, source_home)
        before = set(home.rglob("*.jsonl"))
        environment = dict(os.environ)
        environment["CODEX_HOME"] = str(home)
        environment["PWD"] = str(workdir)
        command = [
            str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust",
            "--skip-git-repo-check", "--sandbox", contract["execution"]["sandbox"],
            "--model", contract["execution"]["model"], "--cd", str(workdir),
            "--config", f'model_reasoning_effort="{contract["execution"]["reasoning_effort"]}"',
            "--config", "features.multi_agent=false", build_prompt(case),
        ]
        completed = subprocess.run(command, cwd=workdir, env=environment, text=True, capture_output=True, timeout=timeout)
        (run_dir / "codex.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        exec_events = base.load_jsonl(run_dir / "codex.jsonl")
        transcript = base.new_transcript(home, before)
        transcript_events = base.load_jsonl(transcript) if transcript else []
        calls = base.transcript_calls(transcript_events)
        final = base.final_message(exec_events)
        result = {
            "schema_version": 1,
            "run_id": run_id,
            "case_id": case["case_id"],
            "repetition": repetition,
            "arm": "native",
            "experiment_id": contract["experiment_id"],
            "model": contract["execution"]["model"],
            "reasoning_effort": contract["execution"]["reasoning_effort"],
            "status": "completed" if completed.returncode == 0 else "failed",
            "process_returncode": completed.returncode,
            "correct": completed.returncode == 0 and score(final, oracle_registry["cases"][case["case_id"]]),
            "final_text": final,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "usage": base.final_usage(exec_events),
            "model_cycles": len(base.cumulative_usage_series(transcript_events)),
            "tool_call_count": len(calls),
            "tool_request_hashes": [sha256_text(base.normalize_command(str(call.get("command", "")))) for call in calls],
            "tool_result_hashes": [sha256_text(str(call.get("output", ""))) for call in calls],
            "prompt_sha256": sha256_text(build_prompt(case)),
            "transcript_available": bool(transcript_events),
            "hook_or_collector_used": False,
            "treatment_builder_used": False,
            **analyze_calls(calls, case, contract["candidate_identity"]["minimum_result_chars"]),
        }
    except Exception as error:
        result = {
            "schema_version": 1, "run_id": run_id, "case_id": case["case_id"], "repetition": repetition,
            "arm": "native", "status": "failed", "correct": False, "error": f"{type(error).__name__}: {error}",
            "hook_or_collector_used": False, "treatment_builder_used": False,
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    result_path.write_bytes(canonical_bytes(result))
    return result


def distribution(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {"count": len(values), "min": min(values), "median": statistics.median(values), "mean": round(statistics.mean(values), 6), "max": max(values)}


def summarize_case(contract: dict[str, Any], case: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    gate = contract["qualification"]
    completed = sum(run.get("status") == "completed" and int(run.get("usage", {}).get("total_tokens", 0)) > 0 for run in runs)
    correct = sum(bool(run.get("correct")) for run in runs)
    recurrence = sum(bool(run.get("candidate_recurred")) for run in runs)
    ambiguous = sum(bool(run.get("candidate_ambiguous")) for run in runs)
    paths = Counter(str(run.get("path_signature_sha256")) for run in runs if run.get("path_signature_sha256"))
    top = paths.most_common()
    dominant_frequency = top[0][1] if top else 0
    tied = bool(top and sum(count == dominant_frequency for _, count in top) > 1)
    path_status = "ambiguous" if tied else ("known" if top else "unknown")
    checks = {
        "completed_with_usage": completed == gate["completed_with_usage"],
        "correctness": correct >= gate["correct_min"],
        "candidate_recurrence": recurrence >= gate["candidate_recurrence_min"],
        "identity_unambiguous": ambiguous <= gate["ambiguous_max"],
        "dominant_path_stability": path_status == "known" and dominant_frequency >= gate["dominant_path_frequency_min"],
    }
    status = "qualified" if all(checks.values()) else ("diagnostic_only" if all(value for key, value in checks.items() if key != "dominant_path_stability") else "rejected")
    target_tokens = [int(run["candidate_visible_estimated_tokens"]) for run in runs if isinstance(run.get("candidate_visible_estimated_tokens"), int)]
    total_tokens = [int(run["usage"]["total_tokens"]) for run in runs if isinstance(run.get("usage", {}).get("total_tokens"), int)]
    return {
        "case_id": case["case_id"], "case_version": case["case_version"], "family": case["family"],
        "project_form": case["project_form"], "status": status,
        "reason_codes": [key for key, value in checks.items() if not value], "gates": checks,
        "native_calibration": {
            "run_count": len(runs), "completed_with_usage": completed, "correct": correct,
            "candidate_recurrence": recurrence, "ambiguous_candidate_matches": ambiguous,
            "dominant_path_frequency": dominant_frequency, "dominant_path_status": path_status,
            "target_visible_token_distribution": distribution(target_tokens),
            "session_total_token_distribution": distribution(total_tokens),
        },
        "candidate_identity": {
            "method": contract["candidate_identity"]["method"],
            "definition_sha256": hashlib.sha256(canonical_bytes(case["candidate_identity"])).hexdigest(),
        },
    }


def compact_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id_hash": sha256_text(str(run.get("run_id", ""))), "case_id": run.get("case_id"),
        "repetition": run.get("repetition"), "status": run.get("status"), "correct": bool(run.get("correct")),
        "total_tokens": run.get("usage", {}).get("total_tokens"), "model_cycles": run.get("model_cycles"),
        "tool_call_count": run.get("tool_call_count"), "candidate_match_count": run.get("candidate_match_count"),
        "candidate_recurred": bool(run.get("candidate_recurred")), "candidate_ambiguous": bool(run.get("candidate_ambiguous")),
        "candidate_visible_estimated_tokens": run.get("candidate_visible_estimated_tokens"),
        "path_signature_sha256": run.get("path_signature_sha256"), "hook_or_collector_used": bool(run.get("hook_or_collector_used")),
        "treatment_builder_used": bool(run.get("treatment_builder_used")),
    }


def build_outputs(contract: dict[str, Any], contract_path: Path, runner_path: Path, runs: list[dict[str, Any]], host: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_case = defaultdict(list)
    for run in runs:
        by_case[run.get("case_id")].append(run)
    summaries = [summarize_case(contract, case, by_case[case["case_id"]]) for case in contract["cases"]]
    family_qualified = Counter(row["family"] for row in summaries if row["status"] == "qualified")
    native_coverage_gate = sum(row["status"] == "qualified" for row in summaries) >= 9 and all(family_qualified[family] >= 3 for family in ("read", "search", "bash"))
    result = {
        "schema_version": 1, "schema_id": RESULT_SCHEMA_ID, "experiment_id": contract["experiment_id"],
        "runner_version": RUNNER_VERSION, "contract_sha256": sha256_file(contract_path), "run_count": len(runs),
        "case_count": len(summaries), "host": host, "runs": [compact_run(run) for run in runs], "case_summaries": summaries,
        "native_coverage_gate": native_coverage_gate,
        "policy": {"native_only": True, "builder_used": False, "intervention": False, "agent_run_budget_consumed": len(runs)},
    }
    registry = {
        "schema_version": 1, "schema_id": REGISTRY_SCHEMA_ID, "status": "f1_complete_under_frozen_native_scope",
        "experiment_id": contract["experiment_id"], "source_result_sha256": hashlib.sha256(canonical_bytes(result)).hexdigest(),
        "contract_sha256": sha256_file(contract_path), "runner_sha256": sha256_file(runner_path), "cases": summaries,
        "summary": {
            "proposed": 12, "qualified": sum(row["status"] == "qualified" for row in summaries),
            "diagnostic_only": sum(row["status"] == "diagnostic_only" for row in summaries),
            "rejected": sum(row["status"] == "rejected" for row in summaries),
            "qualified_by_family": {family: family_qualified[family] for family in ("read", "search", "bash")},
        },
        "native_coverage_gate": native_coverage_gate,
        "consumer_policy": {"f2_must_consume_all_ten_native_observations": True, "run_selection_allowed": False, "builder_was_disabled": True},
    }
    return result, registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    workspace = root.parents[1]
    parser.add_argument("--contract", type=Path, default=root / "resources/acp1_4f_frozen_contract.json")
    parser.add_argument("--index", type=Path, default=root / "resources/acp1_4f_f0_frozen_index.json")
    parser.add_argument("--oracle", type=Path, default=root / "resources/acp1_4f_oracle_registry.json")
    parser.add_argument("--subjects", type=Path, default=root / "resources/acp1_4f_subjects")
    parser.add_argument("--artifacts", type=Path, default=workspace / ".agent-token-manager/acp1-4f-native-v21-20260819")
    parser.add_argument("--public-result", type=Path, default=root / "resources/acp1_4f_qualification_results.json")
    parser.add_argument("--registry", type=Path, default=root / "resources/acp1_4f_native_registry.json")
    parser.add_argument("--codex", type=Path, default=Path(shutil.which("codex") or "codex"))
    parser.add_argument("--source-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--offline-check", action="store_true")
    args = parser.parse_args()
    contract = load_contract(root, args.contract.resolve(), args.index.resolve())
    oracle = load(args.oracle.resolve())
    if set(oracle.get("cases", {})) != {case["case_id"] for case in contract["cases"]}:
        raise QualificationError("oracle_case_set_mismatch")
    if args.offline_check:
        print(canonical_bytes({"status": "ready", "case_count": 12, "run_count": 120, "builder_enabled": False, "experiment_id": contract["experiment_id"]}).decode(), end="")
        return 0
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    host_version = subprocess.run([str(args.codex.resolve()), "--version"], text=True, capture_output=True, timeout=30)
    host = {"binary_sha256": sha256_file(args.codex.resolve()), "version": host_version.stdout.strip(), "model": contract["execution"]["model"], "reasoning_effort": contract["execution"]["reasoning_effort"]}
    runs = []
    total = 120
    for case in contract["cases"]:
        for repetition in range(1, 11):
            run = run_one(contract, oracle, case, repetition, args.codex.resolve(), args.source_home.resolve(), artifacts, args.timeout, args.resume, args.subjects.resolve())
            runs.append(run)
            print(f"[{len(runs):03d}/{total}] {case['case_id']} r{repetition:02d} status={run.get('status')} correct={run.get('correct')} recurrence={run.get('candidate_recurred')}", file=sys.stderr, flush=True)
    result, registry = build_outputs(contract, args.contract.resolve(), Path(__file__).resolve(), runs, host)
    args.public_result.resolve().write_bytes(canonical_bytes(result))
    args.registry.resolve().write_bytes(canonical_bytes(registry))
    print(canonical_bytes({"run_count": 120, "summary": registry["summary"], "native_coverage_gate": registry["native_coverage_gate"], "result_sha256": sha256_file(args.public_result.resolve()), "registry_sha256": sha256_file(args.registry.resolve())}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

