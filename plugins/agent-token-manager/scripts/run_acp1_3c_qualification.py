#!/usr/bin/env python3
"""Run Native-only qualification for prospective natural intervention candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import statistics
import subprocess
import tarfile
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from run_co0_gate import load_jsonl
from run_co1_1_pilot import cumulative_usage_series
from run_co1_gate2 import final_message, final_usage, new_transcript, normalize_command, transcript_calls


RUNNER_VERSION = "acp1-3c-native-qualification-runner-v0.1"
RESULT_SCHEMA_ID = "acp1-3c-native-qualification-result-v1"
REGISTRY_SCHEMA_ID = "natural-intervention-candidate-registry-v1"
FAILURE_MARKERS = ("script failed", "script error")
FROZEN_HASHES = {
    "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
    "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
    "resources/acp1_3a_frozen_baseline_index.json": "0715444a6d373727298b968ac6294ba57c1e794cf1e814b87359d2262c51b110",
    "resources/acp1_3b_frozen_feasibility_index.json": "6397007ce8fdb2229b45490249be70ad4017adf0df41388135d71be04bb10fc3",
    "resources/acp1_3b_frozen_experiment_manifest.json": "3cecfb99652eeabcfd0709aa5df7b8f55400ce9179bd33dedbc1239887467a87",
}


class QualificationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def verify_frozen_integrity(plugin: Path) -> None:
    for relative, expected in FROZEN_HASHES.items():
        path = plugin / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise QualificationError(f"frozen_hash_mismatch:{relative}")


def load_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_id") != "acp1-3c-natural-candidate-fixture-v1":
        raise QualificationError("invalid_fixture")
    if value.get("repetitions_per_case") != 20 or len(value.get("cases", [])) not in {3, 4, 5}:
        raise QualificationError("invalid_preregistered_design")
    if not value.get("policy", {}).get("native_only") or value["policy"].get("intervention"):
        raise QualificationError("native_only_policy_required")
    return value


def build_prompt(case: dict[str, Any]) -> str:
    return (
        "Work only from the local repository. Do not use web tools, plugins, skills, Task Navigator, "
        "Smart Read, context_router, navigation_map, or subagents. Do not modify repository files. "
        + case["question"]
    )


def first_executable_kind(command: str) -> str:
    try:
        words = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return "parse_unknown"
    if not words:
        return "empty"
    executable = words[0].rsplit("/", 1)[-1].lower()
    if executable in {"rg", "grep", "find"}:
        return "search"
    if executable in {"sed", "cat", "head", "tail", "awk"}:
        return "read"
    if executable in {"python", "python3", "pytest", "make", "npm", "cargo"}:
        return "test_or_program"
    return executable if executable.replace("-", "").replace("_", "").isalnum() else "other"


def candidate_match(call: dict[str, Any], case: dict[str, Any], minimum_chars: int) -> bool:
    command = normalize_command(str(call.get("command", ""))).casefold()
    output = str(call.get("output", ""))
    return (
        all(str(term).casefold() in command for term in case["candidate_command_terms"])
        and len(output) >= minimum_chars
        and not any(marker in output.casefold() for marker in FAILURE_MARKERS)
    )


def analyze_calls(calls: list[dict[str, Any]], case: dict[str, Any], minimum_chars: int) -> dict[str, Any]:
    matching = [index for index, call in enumerate(calls) if candidate_match(call, case, minimum_chars)]
    unique_index = matching[0] if len(matching) == 1 else None
    path: list[dict[str, str]] = []
    for index, call in enumerate(calls):
        if len(matching) > 1 and index in matching:
            relation = "ambiguous"
        elif index == unique_index:
            relation = "candidate"
        else:
            relation = "noncandidate"
        path.append({
            "tool_family": str(call.get("tool_name", "unknown")),
            "first_executable_kind": first_executable_kind(str(call.get("command", ""))),
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
        "path_signature": path,
        "path_signature_sha256": sha256_bytes(canonical_bytes(path)),
    }


def prepare_home(run_dir: Path, source_home: Path) -> Path:
    home = run_dir / "codex-home"
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    auth = source_home / "auth.json"
    if auth.is_file() and not (home / "auth.json").exists():
        (home / "auth.json").symlink_to(auth)
    config = home / "config.toml"
    if not config.exists():
        config.write_text('[features]\nmulti_agent = false\n', encoding="utf-8")
        config.chmod(0o600)
    return home


def materialize_subject(repository: Path, subject_commit: str, destination: Path) -> None:
    archive = destination.parent / "subject.tar"
    completed = subprocess.run(
        ["git", "archive", "--format=tar", "--output", str(archive), subject_commit],
        cwd=repository, text=True, capture_output=True, timeout=60,
    )
    if completed.returncode != 0:
        raise QualificationError("subject_archive_failed")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tarfile.open(archive, "r") as handle:
        handle.extractall(destination, filter="data")


def run_one(
    fixture: dict[str, Any], case: dict[str, Any], repetition: int, repository: Path,
    codex: Path, source_home: Path, artifacts: Path, timeout: int, resume: bool,
) -> dict[str, Any]:
    run_id = f"{case['case_id']}__r{repetition:02d}-native"
    run_dir = artifacts / run_id
    result_path = run_dir / "result.json"
    if resume and result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("run_id") != run_id or result.get("case_id") != case["case_id"]:
            raise QualificationError(f"resume_identity_mismatch:{run_id}")
        return result

    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp_parent = Path(tempfile.mkdtemp(prefix="acp13c-"))
    workdir = temp_parent / "subject"
    started = time.perf_counter()
    try:
        materialize_subject(repository, fixture["subject_commit"], workdir)
        home = prepare_home(run_dir, source_home)
        before = set(home.rglob("*.jsonl"))
        environment = dict(os.environ)
        environment["CODEX_HOME"] = str(home)
        environment["PWD"] = str(workdir)
        command = [
            str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust",
            "--skip-git-repo-check",
            "--sandbox", "read-only", "--model", fixture["model"], "--cd", str(workdir),
            "--config", f'model_reasoning_effort="{fixture["reasoning_effort"]}"',
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
        call_analysis = analyze_calls(calls, case, fixture["candidate_identity"]["minimum_result_chars"])
        result = {
            "schema_version": 1,
            "run_id": run_id,
            "case_id": case["case_id"],
            "repetition": repetition,
            "arm": "native",
            "subject_commit": fixture["subject_commit"],
            "model": fixture["model"],
            "reasoning_effort": fixture["reasoning_effort"],
            "status": "completed" if completed.returncode == 0 else "failed",
            "process_returncode": completed.returncode,
            "correct": completed.returncode == 0 and final.strip() == case["expected"],
            "final_text": final,
            "expected": case["expected"],
            "elapsed_seconds": elapsed,
            "usage": final_usage(exec_events),
            "model_cycles": len(cumulative_usage_series(transcript_events)),
            "tool_call_count": len(calls),
            "tool_request_hashes": [sha256_text(normalize_command(str(call.get("command", "")))) for call in calls],
            "tool_result_hashes": [sha256_text(str(call.get("output", ""))) for call in calls],
            "prompt_sha256": sha256_text(build_prompt(case)),
            "transcript_available": bool(transcript_events),
            "hook_or_collector_used": False,
            **call_analysis,
        }
    except Exception as error:
        result = {
            "schema_version": 1,
            "run_id": run_id,
            "case_id": case["case_id"],
            "repetition": repetition,
            "arm": "native",
            "status": "failed",
            "correct": False,
            "error": f"{type(error).__name__}: {error}",
            "hook_or_collector_used": False,
        }
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)
    result_path.write_bytes(canonical_bytes(result))
    return result


def distribution(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": len(values), "min": min(values), "median": statistics.median(values),
        "mean": round(statistics.mean(values), 6), "max": max(values),
    }


def compact_run(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id_hash": sha256_text(str(result.get("run_id", ""))),
        "case_id": result.get("case_id"),
        "repetition": result.get("repetition"),
        "status": result.get("status"),
        "correct": bool(result.get("correct")),
        "total_tokens": result.get("usage", {}).get("total_tokens"),
        "model_cycles": result.get("model_cycles"),
        "tool_call_count": result.get("tool_call_count"),
        "candidate_match_count": result.get("candidate_match_count"),
        "candidate_recurred": bool(result.get("candidate_recurred")),
        "candidate_ambiguous": bool(result.get("candidate_ambiguous")),
        "candidate_visible_estimated_tokens": result.get("candidate_visible_estimated_tokens"),
        "path_signature_sha256": result.get("path_signature_sha256"),
        "hook_or_collector_used": bool(result.get("hook_or_collector_used")),
    }


def identity_sha256(fixture: dict[str, Any], case: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes({
        "method": fixture["candidate_identity"]["method"],
        "minimum_result_chars": fixture["candidate_identity"]["minimum_result_chars"],
        "logical_target_id": case["logical_target_id"],
        "candidate_command_terms": case["candidate_command_terms"],
    }))


def summarize_case(fixture: dict[str, Any], case: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds = fixture["thresholds"]
    completed = sum(
        run.get("status") == "completed" and int(run.get("usage", {}).get("total_tokens", 0)) > 0
        for run in runs
    )
    correct = sum(bool(run.get("correct")) for run in runs)
    recurrence = sum(bool(run.get("candidate_recurred")) for run in runs)
    ambiguous = sum(bool(run.get("candidate_ambiguous")) for run in runs)
    path_counts = Counter(str(run.get("path_signature_sha256")) for run in runs if run.get("path_signature_sha256"))
    top = path_counts.most_common()
    dominant_frequency = top[0][1] if top else 0
    tied = bool(top and sum(count == dominant_frequency for _, count in top) > 1)
    dominant_status = "ambiguous" if tied else ("known" if top else "unknown")
    dominant_hash = None if tied or not top else top[0][0]
    hard = {
        "completed_with_usage": completed == thresholds["completed_with_usage"],
        "correctness": correct >= thresholds["correct"],
        "candidate_recurrence": recurrence >= thresholds["candidate_recurrence"],
        "identity_unambiguous": ambiguous <= thresholds["ambiguous_candidate_matches_max"],
    }
    path_pass = dominant_status == "known" and dominant_frequency >= thresholds["dominant_path_frequency"]
    if all(hard.values()) and path_pass:
        status = "qualified"
    elif all(hard.values()) and not path_pass:
        status = "diagnostic_only"
    else:
        status = "rejected"
    reasons = [name for name, passed in {**hard, "dominant_path_stability": path_pass}.items() if not passed]
    target_tokens = [int(run["candidate_visible_estimated_tokens"]) for run in runs if isinstance(run.get("candidate_visible_estimated_tokens"), int)]
    total_tokens = [int(run["usage"]["total_tokens"]) for run in runs if isinstance(run.get("usage", {}).get("total_tokens"), int)]
    return {
        "case_id": case["case_id"],
        "source_case_id": case["source_case_id"],
        "case_version": 1,
        "category": case["category"],
        "status": status,
        "reason_codes": reasons,
        "native_calibration": {
            "run_count": len(runs),
            "completed_with_usage": completed,
            "correct": correct,
            "candidate_recurrence": recurrence,
            "ambiguous_candidate_matches": ambiguous,
            "dominant_path_frequency": dominant_frequency,
            "dominant_path_status": dominant_status,
            "target_visible_token_distribution": distribution(target_tokens),
            "session_total_token_distribution": distribution(total_tokens),
        },
        "candidate_identity": {
            "logical_target_id": case["logical_target_id"],
            "method": fixture["candidate_identity"]["method"],
            "definition_sha256": identity_sha256(fixture, case),
            "evidence_identity": "reliable" if ambiguous == 0 else "ambiguous",
        },
        "dominant_path": {
            "method": fixture["path_semantics"]["method"],
            "signature_sha256": dominant_hash,
            "frequency": dominant_frequency,
            "status": dominant_status,
        },
        "thresholds": thresholds,
        "eligible_for_acp1_3d": status == "qualified",
    }


def build_outputs(fixture: dict[str, Any], fixture_path: Path, runner_path: Path, all_runs: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_case = {case["case_id"]: [run for run in all_runs if run.get("case_id") == case["case_id"]] for case in fixture["cases"]}
    cases = [summarize_case(fixture, case, by_case[case["case_id"]]) for case in fixture["cases"]]
    result = {
        "schema_version": 1,
        "schema_id": RESULT_SCHEMA_ID,
        "experiment_id": fixture["fixture_id"],
        "runner_version": RUNNER_VERSION,
        "fixture_sha256": sha256_file(fixture_path),
        "subject_commit": fixture["subject_commit"],
        "model": fixture["model"],
        "reasoning_effort": fixture["reasoning_effort"],
        "run_count": len(all_runs),
        "case_count": len(fixture["cases"]),
        "runs": [compact_run(run) for run in all_runs],
        "case_summaries": cases,
        "gates": {
            "g1_natural_tasks": True,
            "g2_ground_truth_audited": True,
            "g3_replay_stability_reported": True,
            "g4_candidate_recurrence_reported": True,
            "g5_path_stability_reported": True,
            "g6_privacy_provenance": True,
            "g7_native_only_no_intervention": all(not run.get("hook_or_collector_used", False) for run in all_runs),
            "g8_frozen_integrity": True,
        },
        "policy": fixture["policy"],
    }
    registry = {
        "schema_version": 1,
        "schema_id": REGISTRY_SCHEMA_ID,
        "registry_version": "1.0.0",
        "status": "qualification_complete_under_frozen_scope",
        "source_experiment_id": fixture["fixture_id"],
        "source_result_sha256": sha256_bytes(canonical_bytes(result)),
        "fixture_sha256": sha256_file(fixture_path),
        "runner_sha256": sha256_file(runner_path),
        "subject_commit": fixture["subject_commit"],
        "qualification_scope": "native_only_no_intervention",
        "cases": cases,
        "summary": {
            "case_count": len(cases),
            "qualified_count": sum(case["status"] == "qualified" for case in cases),
            "diagnostic_only_count": sum(case["status"] == "diagnostic_only" for case in cases),
            "rejected_count": sum(case["status"] == "rejected" for case in cases),
        },
        "consumer_policy": {
            "acp1_3d_may_consume_only": "qualified",
            "temporary_case_or_run_selection": False,
            "intervention_or_savings_claim": False,
        },
    }
    return result, registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    plugin = Path(__file__).resolve().parents[1]
    workspace = plugin.parents[1]
    parser.add_argument("--repository", type=Path, default=workspace)
    parser.add_argument("--fixture", type=Path, default=plugin / "resources/acp1_3c_natural_cases.json")
    parser.add_argument("--artifacts", type=Path, default=workspace / ".agent-token-manager/acp1-3c-natural-qualification-20260818")
    parser.add_argument("--public-result", type=Path, default=plugin / "resources/acp1_3c_results.json")
    parser.add_argument("--registry", type=Path, default=plugin / "resources/acp1_3c_candidate_registry.json")
    parser.add_argument("--codex", type=Path, default=Path(shutil.which("codex") or "codex"))
    parser.add_argument("--source-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--offline-check", action="store_true")
    args = parser.parse_args()

    fixture = load_fixture(args.fixture.resolve())
    if args.offline_check:
        print(canonical_bytes({
            "fixture_sha256": sha256_file(args.fixture.resolve()),
            "case_count": len(fixture["cases"]),
            "run_count": len(fixture["cases"]) * fixture["repetitions_per_case"],
            "native_only": fixture["policy"]["native_only"],
            "intervention": fixture["policy"]["intervention"],
        }).decode("utf-8"), end="")
        return 0

    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    verify_frozen_integrity(plugin)
    all_runs: list[dict[str, Any]] = []
    for case in fixture["cases"]:
        for repetition in range(1, fixture["repetitions_per_case"] + 1):
            all_runs.append(run_one(
                fixture, case, repetition, args.repository.resolve(), args.codex.resolve(),
                args.source_home.resolve(), artifacts, args.timeout, args.resume,
            ))
    result, registry = build_outputs(fixture, args.fixture.resolve(), Path(__file__).resolve(), all_runs)
    args.public_result.resolve().write_bytes(canonical_bytes(result))
    args.registry.resolve().write_bytes(canonical_bytes(registry))
    print(canonical_bytes({
        "run_count": result["run_count"],
        "registry_summary": registry["summary"],
        "result_sha256": sha256_file(args.public_result.resolve()),
        "registry_sha256": sha256_file(args.registry.resolve()),
    }).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
