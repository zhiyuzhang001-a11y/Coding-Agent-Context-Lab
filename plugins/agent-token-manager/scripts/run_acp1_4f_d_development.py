#!/usr/bin/env python3
"""Run ACP-1.4F-D Native-only Screen/Extension benchmark development probes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import acp1_4f_futility as shared_futility
import audit_acp1_4f_native_paths as taxonomy
from run_acp1_3c_qualification import canonical_bytes, prepare_home
from run_co0_gate import load_jsonl
from run_co1_1_pilot import cumulative_usage_series
from run_co1_gate2 import final_message, final_usage, new_transcript


RUNNER_VERSION = "acp1-4f-d-development-runner-v0.1"
REGISTRY_SCHEMA_ID = "acp1-4f-d-development-registry-v1"
CHECKPOINT_SCHEMA_ID = "acp1-4f-d-private-checkpoint-v1"
TRUNCATION_MARKERS = ("warning: truncated output", "output truncated", "tokens truncated")


class DevelopmentError(ValueError):
    pass


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DevelopmentError(f"expected_object:{path.name}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def subject_inventory_digest(root: Path) -> tuple[int, str]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    return len(rows), hashlib.sha256(canonical_bytes({"schema_version": 1, "files": rows})).hexdigest()


def prompt_inferable(case: dict[str, Any], oracle: dict[str, Any]) -> bool:
    expected = str(oracle["expected"]).strip().casefold()
    prompt = str(case["prompt"]).casefold()
    return bool(expected) and expected in prompt


def entropy(distribution: Counter[str]) -> float | None:
    total = sum(distribution.values())
    if not total:
        return None
    value = -sum((count / total) * math.log2(count / total) for count in distribution.values())
    return round(value, 6)


def dominant(distribution: Counter[str]) -> tuple[str | None, int]:
    if not distribution:
        return (None, 0)
    rows = distribution.most_common()
    if len(rows) > 1 and rows[0][1] == rows[1][1]:
        return (None, rows[0][1])
    return rows[0]


def structural_relation(case: dict[str, Any], command: str, output: str, carrier: str) -> bool:
    identity = case["request_identity"]
    lowered_command = command.casefold()
    lowered_output = output.casefold()
    scopes = [str(value).casefold() for value in identity.get("subject_scopes", [])]
    anchors = [str(value).casefold() for value in identity.get("request_anchors", [])]
    query_terms = [str(value).casefold() for value in identity.get("query_terms", [])]
    structural_fields = [str(value).casefold() for value in identity.get("structural_fields", [])]
    read_terms = anchors or structural_fields or query_terms
    search_terms = query_terms or anchors or structural_fields
    scope_related = any(scope in lowered_command or f"{scope}/" in lowered_output for scope in scopes)
    if not scope_related and "." in lowered_command:
        scope_related = any(f"{scope}/" in lowered_output for scope in scopes)
    family = taxonomy.compatible_family(carrier)
    if family == "read_like":
        return scope_related and bool(read_terms) and any(term in lowered_command or term in lowered_output for term in read_terms)
    if family == "search_like":
        return scope_related and bool(search_terms) and any(term in lowered_command for term in search_terms)
    if family == "structured_bash_like":
        field_related = not structural_fields or any(field in lowered_output for field in structural_fields)
        return scope_related and field_related
    return False


def analyze_exec_events(events: list[dict[str, Any]], case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    opportunities: list[dict[str, Any]] = []
    host_families: list[str] = []
    path: list[str] = []
    unknown = False
    truncation = False
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item", {})
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        command = str(item.get("command", ""))
        output = str(item.get("aggregated_output", ""))
        carrier = taxonomy.carrier_kind(command, output)
        family = taxonomy.compatible_family(carrier)
        path.append(carrier)
        if family:
            host_families.append(family)
        observed_truncation = any(marker in output.casefold() for marker in TRUNCATION_MARKERS)
        truncation = truncation or observed_truncation
        if observed_truncation:
            unknown = True
            continue
        successful = item.get("exit_code") == 0 and len(output) >= int(contract["measurement"]["minimum_result_chars"])
        if successful and structural_relation(case, command, output, carrier):
            tokens = (len(output) + 3) // 4
            opportunities.append({"carrier": carrier, "family": family, "tokens": tokens})
    compatible = [row for row in opportunities if row["family"]]
    unique = compatible[0] if len(compatible) == 1 else None
    return {
        "measurement_unknown": unknown,
        "truncation_observed": truncation,
        "opportunity_count": len(opportunities),
        "ambiguous_identity": len(opportunities) > 1,
        "evidence_opportunity_identified": len(opportunities) == 1,
        "compatible_carrier_identified": len(compatible) == 1,
        "meaningful_evidence": bool(unique and unique["tokens"] >= int(contract["measurement"]["minimum_meaningful_evidence_tokens"])),
        "evidence_tokens": unique["tokens"] if unique else None,
        "carrier": unique["carrier"] if unique else None,
        "evidence_family": unique["family"] if unique else None,
        "host_family_path": host_families,
        "carrier_path_sha256": hashlib.sha256(canonical_bytes(path)).hexdigest(),
    }


def futility_reasons(runs: list[dict[str, Any]], total: int, gates: dict[str, Any], prompt_is_inferable: bool) -> list[str]:
    observed = len(runs)
    remaining = max(0, total - observed)
    correct = sum(bool(row.get("correct")) for row in runs)
    opportunity = sum(bool(row.get("evidence_opportunity_identified")) for row in runs)
    compatible = sum(bool(row.get("compatible_carrier_identified")) for row in runs)
    meaningful = sum(bool(row.get("meaningful_evidence")) for row in runs)
    ambiguous = sum(bool(row.get("ambiguous_identity")) for row in runs)
    unknown = sum(bool(row.get("measurement_unknown")) for row in runs)
    truncation = sum(bool(row.get("truncation_observed")) for row in runs)
    families = Counter(str(row.get("evidence_family")) for row in runs if row.get("evidence_family"))
    dominant_family_count = max(families.values(), default=0)
    core_possible = shared_futility.case_can_still_qualify(
        observed, total, correct, opportunity, ambiguous, dominant_family_count,
        int(gates["correct_min"]), int(gates["evidence_opportunity_recurrence_min"]),
        int(gates["ambiguous_identity_max"]), int(gates["dominant_observed_evidence_family_min"]),
    )
    reasons: list[str] = []
    if prompt_is_inferable:
        reasons.append("F_PROMPT_INFERABLE")
    if ambiguous > int(gates["ambiguous_identity_max"]):
        reasons.append("F_AMBIGUOUS_IDENTITY")
    if unknown > int(gates["measurement_unknown_max"]):
        reasons.append("F_TRUNCATION_UNRESOLVED" if truncation else "F_EVIDENCE_NOT_IDENTIFIABLE")
    if correct + remaining < int(gates["correct_min"]):
        reasons.append("F_CORRECTNESS_UNSTABLE")
    if opportunity + remaining < int(gates["evidence_opportunity_recurrence_min"]):
        reasons.append("F_EVIDENCE_NOT_IDENTIFIABLE")
    if compatible + remaining < int(gates["compatible_carrier_recurrence_min"]):
        reasons.append("F_NO_COMPATIBLE_CARRIER")
    if meaningful + remaining < int(gates["meaningful_evidence_recurrence_min"]):
        reasons.extend(["F_EVIDENCE_TOO_SMALL", "F_INTERVENTION_NOT_MEANINGFUL"])
    if dominant_family_count + remaining < int(gates["dominant_observed_evidence_family_min"]):
        reasons.append("F_TOOL_PATH_UNSTABLE")
    if not core_possible and not reasons:
        reasons.append("F_EVIDENCE_NOT_IDENTIFIABLE")
    return list(dict.fromkeys(reasons))


def distribution(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"min": None, "median": None, "max": None}
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


def summarize_case(case: dict[str, Any], runs: list[dict[str, Any]], contract: dict[str, Any], oracle: dict[str, Any]) -> dict[str, Any]:
    tool_distribution: Counter[str] = Counter()
    evidence_distribution: Counter[str] = Counter()
    carrier_distribution: Counter[str] = Counter()
    for run in runs:
        for family in run.get("host_family_path", []):
            tool_distribution[family] += 1
        if run.get("evidence_family"):
            evidence_distribution[str(run["evidence_family"])] += 1
        if run.get("carrier"):
            carrier_distribution[str(run["carrier"])] += 1
    dominant_tool, _ = dominant(tool_distribution)
    dominant_evidence, dominant_evidence_count = dominant(evidence_distribution)
    completed = sum(row.get("status") == "completed" and int(row.get("usage_total_tokens", 0)) > 0 for row in runs)
    correct = sum(bool(row.get("correct")) for row in runs)
    opportunity = sum(bool(row.get("evidence_opportunity_identified")) for row in runs)
    compatible = sum(bool(row.get("compatible_carrier_identified")) for row in runs)
    meaningful = sum(bool(row.get("meaningful_evidence")) for row in runs)
    ambiguous = sum(bool(row.get("ambiguous_identity")) for row in runs)
    unknown = sum(bool(row.get("measurement_unknown")) for row in runs)
    truncation = sum(bool(row.get("truncation_observed")) for row in runs)
    inferable = prompt_inferable(case, oracle)
    reasons = futility_reasons(runs, int(contract["execution"]["maximum_repetitions_per_case"]), contract["final_case_gates"], inferable)
    final = len(runs) == int(contract["execution"]["maximum_repetitions_per_case"])
    qualified = final and not reasons and completed == 10
    screen_complete = len(runs) >= int(contract["execution"]["screen_repetitions"])
    screen_admitted = screen_complete and not reasons
    if qualified:
        state = "qualified"
    elif final:
        state = "rejected"
    elif screen_complete and screen_admitted:
        state = "screen_admitted"
    elif screen_complete:
        state = "screen_rejected"
    else:
        state = "pending"
    if unknown:
        state = "measurement_unknown"
    evidence_tokens = [int(row["evidence_tokens"]) for row in runs if isinstance(row.get("evidence_tokens"), int)]
    return {
        "case_id": case["case_id"],
        "design": {
            "project_form": case["project_form"],
            "intended_evidence_form": case["intended_evidence_form"],
            "answer_uniqueness": case["answer_uniqueness"],
            "prompt_inferability_check": "fail" if inferable else "pass",
        },
        "screen": {"runs": min(len(runs), 3), "admitted_to_extension": screen_admitted if screen_complete else None},
        "correctness": {"pass_count": correct, "stability": round(correct / len(runs), 6) if runs else None},
        "tool_family": {"distribution": dict(sorted(tool_distribution.items())), "dominant_family": dominant_tool, "entropy": entropy(tool_distribution)},
        "evidence_family": {"distribution": dict(sorted(evidence_distribution.items())), "dominant_family": dominant_evidence, "recurrence": dominant_evidence_count},
        "carrier": {"compatible_count": compatible, "distribution": dict(sorted(carrier_distribution.items())), "recurrence": max(carrier_distribution.values(), default=0)},
        "identity": {"stable": (ambiguous == 0 and opportunity >= 8) if final else None, "ambiguity_rate": round(ambiguous / len(runs), 6) if runs else None, "equivalence_scope": sorted(carrier_distribution)},
        "measurement": {"evidence_tokens": distribution(evidence_tokens), "truncation_observed": truncation, "measurement_unknown": unknown},
        "qualification": {"opportunity_recurrence": opportunity, "oracle_free": True, "intervention_compatible": qualified if final else None},
        "status": {"state": state, "reason_codes": reasons},
        "_private_counts": {"completed_with_usage": completed, "meaningful_evidence_recurrence": meaningful},
    }


def public_case(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "_private_counts"}


def build_registry(pool: dict[str, Any], contract: dict[str, Any], oracle_registry: dict[str, Any], runs: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        by_case[str(run["case_id"])].append(run)
    rows = [summarize_case(case, by_case[case["case_id"]], contract, oracle_registry["cases"][case["case_id"]]) for case in pool["cases"]]
    qualified_by_family = Counter(
        str(row["evidence_family"]["dominant_family"])
        for row in rows
        if row["status"]["state"] == "qualified" and row["evidence_family"]["dominant_family"]
    )
    supported = sum(count >= int(contract["verdict"]["minimum_qualified_cases_per_observed_family"]) for count in qualified_by_family.values())
    verdict = None
    if stage == "complete":
        verdict = "READY_FOR_NEW_HOLDOUT" if supported >= 3 else ("SUPPORTED_FOR_SUBSET_ONLY" if supported == 2 else "BENCHMARK_SEMANTICS_NOT_SUPPORTED")
    return {
        "schema_version": 1,
        "schema_id": REGISTRY_SCHEMA_ID,
        "protocol_id": contract["protocol_id"],
        "status": stage,
        "agent_run_count": len(runs),
        "cases": [public_case(row) for row in rows],
        "verdict": verdict,
    }


def materialize_subjects(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)


def run_one(case: dict[str, Any], oracle: dict[str, Any], contract: dict[str, Any], repetition: int, codex: Path, source_home: Path, subjects: Path, artifacts: Path, resume: bool, timeout: int) -> dict[str, Any]:
    run_id = f"{case['case_id']}__r{repetition:02d}-native"
    run_dir = artifacts / run_id
    result_path = run_dir / "result.json"
    if resume and result_path.is_file():
        result = load(result_path)
        if result.get("run_id") != run_id:
            raise DevelopmentError("resume_identity_mismatch")
        return result
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = Path(tempfile.mkdtemp(prefix="acp14fd-"))
    workdir = temporary / "subject"
    try:
        materialize_subjects(subjects, workdir)
        home = prepare_home(run_dir, source_home)
        before = set(home.rglob("*.jsonl"))
        environment = dict(os.environ)
        environment["CODEX_HOME"] = str(home)
        environment["PWD"] = str(workdir)
        command = [
            str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust",
            "--skip-git-repo-check", "--sandbox", contract["execution"]["sandbox"],
            "--model", contract["execution"]["model"], "--cd", str(workdir),
            "--config", f'model_reasoning_effort="{contract["execution"]["reasoning_effort"]}"',
            "--config", "features.multi_agent=false", case["prompt"],
        ]
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=workdir, env=environment, text=True, capture_output=True, timeout=timeout)
        (run_dir / "codex.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        events = load_jsonl(run_dir / "codex.jsonl")
        transcript = new_transcript(home, before)
        transcript_events = load_jsonl(transcript) if transcript else []
        final = final_message(events)
        analysis = analyze_exec_events(events, case, contract)
        result = {
            "schema_version": 1,
            "run_id": run_id,
            "case_id": case["case_id"],
            "repetition": repetition,
            "status": "completed" if completed.returncode == 0 else "failed",
            "correct": completed.returncode == 0 and final.strip() == str(oracle["expected"]),
            "final_text": final,
            "usage": final_usage(events),
            "usage_total_tokens": int(final_usage(events).get("total_tokens", 0)),
            "model_cycles": len(cumulative_usage_series(transcript_events)),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "treatment_builder_used": False,
            "collector_or_hook_used": False,
            "intervention_used": False,
            **analysis,
        }
    except Exception as error:
        result = {"schema_version": 1, "run_id": run_id, "case_id": case["case_id"], "repetition": repetition, "status": "failed", "correct": False, "error": f"{type(error).__name__}: {error}"}
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    result_path.write_bytes(canonical_bytes(result))
    return result


def load_existing_runs(artifacts: Path) -> list[dict[str, Any]]:
    return [load(path) for path in sorted(artifacts.glob("*/result.json"))]


def write_checkpoint(path: Path, contract: dict[str, Any], pool: dict[str, Any], runs: list[dict[str, Any]], stage: str) -> None:
    payload = {
        "schema_version": 1,
        "schema_id": CHECKPOINT_SCHEMA_ID,
        "protocol_id": contract["protocol_id"],
        "pool_id": pool["pool_id"],
        "stage": stage,
        "attempted_run_count": len(runs),
        "completed_run_count": sum(row.get("status") == "completed" for row in runs),
        "run_inventory": [{"run_id": row["run_id"], "sha256": hashlib.sha256(canonical_bytes(row)).hexdigest()} for row in runs],
    }
    path.write_bytes(canonical_bytes(payload))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    plugin = Path(__file__).resolve().parents[1]
    workspace = plugin.parents[1]
    parser.add_argument("--contract", type=Path, default=plugin / "resources/acp1_4f_d_development_contract.json")
    parser.add_argument("--index", type=Path, default=plugin / "resources/acp1_4f_d_frozen_protocol_index.json")
    parser.add_argument("--pool", type=Path, default=plugin / "resources/acp1_4f_d_case_pool.json")
    parser.add_argument("--oracle", type=Path, default=plugin / "resources/acp1_4f_d_oracle_registry.json")
    parser.add_argument("--subjects", type=Path, default=plugin / "resources/acp1_4f_d_subjects")
    parser.add_argument("--artifacts", type=Path, default=workspace / ".agent-token-manager/acp1-4f-development-v1")
    parser.add_argument("--registry", type=Path, default=plugin / "resources/acp1_4f_d_development_registry.json")
    parser.add_argument("--stage", choices=("offline-check", "screen", "extension", "summarize"), default="offline-check")
    parser.add_argument("--codex", type=Path, default=Path(shutil.which("codex") or "codex"))
    parser.add_argument("--source-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    contract = load(args.contract.resolve())
    pool = load(args.pool.resolve())
    oracle = load(args.oracle.resolve())
    case_ids = {case["case_id"] for case in pool["cases"]}
    if len(pool["cases"]) != contract["pool"]["case_count"] or set(oracle.get("cases", {})) != case_ids:
        raise DevelopmentError("pool_or_oracle_case_set_mismatch")
    if any(prompt_inferable(case, oracle["cases"][case["case_id"]]) for case in pool["cases"]):
        raise DevelopmentError("prompt_inferability_check_failed")
    if args.stage != "offline-check":
        index = load(args.index.resolve())
        if index.get("protocol_id") != contract["protocol_id"] or index.get("agent_run_count_at_freeze") != 0:
            raise DevelopmentError("invalid_frozen_protocol_index")
        for artifact in index["artifacts"].values():
            path = plugin / artifact["path"]
            if not path.is_file() or sha256_file(path) != artifact["sha256"]:
                raise DevelopmentError(f"frozen_artifact_mismatch:{artifact['path']}")
        subject_count, subject_digest = subject_inventory_digest(args.subjects.resolve())
        if subject_count != index["subjects"]["file_count"] or subject_digest != index["subjects"]["inventory_sha256"]:
            raise DevelopmentError("frozen_subject_inventory_mismatch")
        if args.stage == "screen" and not contract["authorization"]["screen_runs_authorized"]:
            raise DevelopmentError("screen_not_authorized")
        if args.stage == "extension" and not contract["authorization"]["extension_runs_authorized"]:
            raise DevelopmentError("extension_not_authorized")
    if args.stage == "offline-check":
        print(canonical_bytes({"status": "ready", "protocol_id": contract["protocol_id"], "case_count": len(pool["cases"]), "screen_run_count": 72, "hard_agent_run_cap": 240}).decode(), end="")
        return 0
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    runs = load_existing_runs(artifacts) if args.resume or args.stage in {"extension", "summarize"} else []
    if args.stage in {"screen", "extension"}:
        start = 1 if args.stage == "screen" else 4
        end = 3 if args.stage == "screen" else 10
        for case in pool["cases"]:
            existing = [run for run in runs if run["case_id"] == case["case_id"]]
            summary = summarize_case(case, existing, contract, oracle["cases"][case["case_id"]])
            if args.stage == "extension" and summary["status"]["state"] != "screen_admitted":
                continue
            for repetition in range(start, end + 1):
                if any(run["case_id"] == case["case_id"] and run["repetition"] == repetition for run in runs):
                    continue
                run = run_one(case, oracle["cases"][case["case_id"]], contract, repetition, args.codex.resolve(), args.source_home.resolve(), args.subjects.resolve(), artifacts, args.resume, args.timeout)
                runs.append(run)
                if len(runs) > int(contract["execution"]["hard_agent_run_cap"]):
                    raise DevelopmentError("hard_agent_run_cap_exceeded")
                write_checkpoint(artifacts / "checkpoint.json", contract, pool, runs, args.stage)
                current = [row for row in runs if row["case_id"] == case["case_id"]]
                if futility_reasons(current, 10, contract["final_case_gates"], False):
                    break
    stage_name = "screen_complete" if args.stage == "screen" else ("complete" if args.stage in {"extension", "summarize"} else "screen_in_progress")
    registry = build_registry(pool, contract, oracle, runs, stage_name)
    args.registry.resolve().write_bytes(canonical_bytes(registry))
    print(canonical_bytes({"status": stage_name, "agent_run_count": len(runs), "verdict": registry["verdict"]}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
