#!/usr/bin/env python3
"""Audit ACP-1.4F v2.1 Native path semantics without running an Agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


RESULT_SCHEMA_ID = "acp1-4f-r-native-path-audit-result-v1"
FAILURE_MARKERS = ("script failed", "script error")


class AuditError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError(f"expected_object:{path.name}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def completed_inventory_digest(paths: list[Path], logical_id: str) -> str:
    rows = [load(path) for path in paths]
    inventory = {
        "schema_version": 1,
        "logical_id": logical_id,
        "completed_run_count": len(paths),
        "runs": [{"run_id": row["run_id"], "sha256": sha256_file(path)} for path, row in zip(paths, rows)],
    }
    return hashlib.sha256(canonical_bytes(inventory)).hexdigest()


def load_exec_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise AuditError(f"malformed_exec_jsonl:{path.name}:{number}") from error
        if event.get("type") != "item.completed":
            continue
        item = event.get("item", {})
        if isinstance(item, dict) and item.get("type") == "command_execution":
            events.append(item)
    return events


def carrier_kind(command: str, output: str) -> str:
    lowered = command.casefold()
    if re.search(r"\brg\b", lowered):
        return "bash_rg"
    if re.search(r"\bgrep\b", lowered):
        return "bash_grep"
    if re.search(r"\bsed\b", lowered):
        return "bash_sed"
    if re.search(r"\bcat\b", lowered):
        return "bash_cat"
    if re.search(r"\bhead\b", lowered):
        return "bash_head_tail"
    if re.search(r"\btail\b", lowered):
        return "bash_head_tail"
    if re.search(r"\b(?:pytest|make|npm|cargo)\b", lowered):
        return "bash_test_summary"
    stripped = output.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "bash_json"
    if re.search(r"\b(?:count|total|length|wc\s+-l)\b", lowered):
        return "bash_structured_count"
    return "unsupported"


def compatible_family(carrier: str) -> str | None:
    if carrier in {"bash_sed", "bash_cat", "bash_head_tail"}:
        return "read_like"
    if carrier in {"bash_rg", "bash_grep"}:
        return "search_like"
    if carrier in {"bash_json", "bash_test_summary", "bash_structured_count", "bash_exit_status"}:
        return "structured_bash_like"
    return None


def request_related(case: dict[str, Any], command: str, output: str, carrier: str) -> bool:
    lowered_command = command.casefold()
    lowered_output = output.casefold()
    subject = str(case["subject_path"]).casefold()
    project = str(case["project_form"]).casefold()
    project_offset = subject.find(project)
    request_relative_subject = subject[project_offset:] if project_offset >= 0 else subject
    if case["family"] == "read":
        return compatible_family(carrier) == "read_like" and request_relative_subject in lowered_command
    if case["family"] == "search":
        query = str(case["query_shape"]["term"]).casefold()
        query_related = query in lowered_command
        scope_related = project in lowered_command or f"{project}/" in lowered_output
        return compatible_family(carrier) == "search_like" and query_related and scope_related
    if case["family"] == "bash":
        return compatible_family(carrier) == "structured_bash_like" and request_relative_subject in lowered_command
    return False


def path_entropy(signatures: list[str]) -> tuple[float, float]:
    if not signatures:
        return (0.0, 0.0)
    counts = Counter(signatures)
    total = len(signatures)
    entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
    normalized = entropy / math.log2(total) if total > 1 else 0.0
    return (round(entropy, 6), round(normalized, 6))


def analyze_run(result_path: Path, case: dict[str, Any], minimum_chars: int) -> dict[str, Any]:
    result = load(result_path)
    events_path = result_path.with_name("codex.jsonl")
    if result.get("status") != "completed" or not events_path.is_file():
        return {"measurement_unknown": True, "reason": "missing_or_incomplete_artifact"}
    executions = load_exec_events(events_path)
    carriers: list[str] = []
    related: list[str] = []
    for event in executions:
        command = str(event.get("command", ""))
        output = str(event.get("aggregated_output", ""))
        exit_code = event.get("exit_code")
        carrier = carrier_kind(command, output)
        carriers.append(carrier)
        successful = exit_code == 0 and len(output) >= minimum_chars and not any(marker in output.casefold() for marker in FAILURE_MARKERS)
        if successful and request_related(case, command, output, carrier):
            related.append(carrier)
    compatible = [carrier for carrier in related if compatible_family(carrier) is not None]
    return {
        "measurement_unknown": False,
        "correct": bool(result.get("correct")),
        "v2_1_candidate_recurred": bool(result.get("candidate_recurred")),
        "v2_1_candidate_ambiguous": bool(result.get("candidate_ambiguous")),
        "v2_1_path_signature": str(result.get("path_signature_sha256", "")),
        "historical_tool_call_count": int(result.get("tool_call_count", 0)),
        "actual_command_execution_count": len(executions),
        "meta_or_nonexecution_call_count": max(0, int(result.get("tool_call_count", 0)) - len(executions)),
        "related_carriers": related,
        "compatible_carriers": compatible,
        "exactly_one_evidence_opportunity": len(related) == 1,
        "exactly_one_compatible_carrier": len(compatible) == 1,
        "identity_false_negative": not bool(result.get("candidate_recurred")) and len(compatible) == 1,
    }


def summarize_case(case: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    observed = len(runs)
    unknown = sum(bool(run.get("measurement_unknown")) for run in runs)
    known = [run for run in runs if not run.get("measurement_unknown")]
    paths = [run["v2_1_path_signature"] for run in known if run.get("v2_1_path_signature")]
    path_counts = Counter(paths)
    carrier_counts = Counter(
        run["compatible_carriers"][0]
        for run in known
        if len(run.get("compatible_carriers", [])) == 1
    )
    entropy, normalized_entropy = path_entropy(paths)
    correct = sum(bool(run.get("correct")) for run in known)
    v2_recurrence = sum(bool(run.get("v2_1_candidate_recurred")) for run in known)
    evidence_recurrence = sum(bool(run.get("exactly_one_evidence_opportunity")) for run in known)
    carrier_recurrence = sum(bool(run.get("exactly_one_compatible_carrier")) for run in known)
    false_negatives = sum(bool(run.get("identity_false_negative")) for run in known)
    extra_meta_runs = sum(int(run.get("meta_or_nonexecution_call_count", 0)) > 0 for run in known)
    dominant_path = max(path_counts.values(), default=0)
    dominant_carrier = max(carrier_counts.values(), default=0)
    labels: list[str] = []
    if unknown:
        labels.append("MEASUREMENT_UNKNOWN")
    if false_negatives:
        labels.append("IDENTITY_MISMATCH")
    if observed == 10 and carrier_recurrence >= 8:
        labels.append("STABLE_AT_EVIDENCE_LEVEL")
        if dominant_path < 8:
            labels.append("PATH_GATE_MISMATCH")
    elif observed == 10 and carrier_recurrence < 8:
        labels.append("GENUINE_EVIDENCE_INSTABILITY")
    elif observed < 10:
        labels.append("INSUFFICIENT_DIAGNOSTIC_EVIDENCE")
    expected_family = {"read": "read_like", "search": "search_like", "bash": "structured_bash_like"}[case["family"]]
    observed_families = {compatible_family(carrier) for carrier in carrier_counts}
    if observed_families and observed_families != {expected_family}:
        labels.append("TOOL_FAMILY_UNSUITABLE")
    return {
        "case_id": case["case_id"],
        "family": case["family"],
        "project_form": case["project_form"],
        "observed_completed_runs": observed,
        "correct_runs": correct,
        "measurement_unknown_runs": unknown,
        "v2_1_candidate_recurrence": v2_recurrence,
        "evidence_opportunity_recurrence": evidence_recurrence,
        "intervention_compatible_carrier_recurrence": carrier_recurrence,
        "identity_false_negative_runs": false_negatives,
        "runs_with_meta_or_nonexecution_calls": extra_meta_runs,
        "carrier_distribution": dict(sorted(carrier_counts.items())),
        "dominant_carrier_frequency": dominant_carrier,
        "distinct_v2_1_path_signatures": len(path_counts),
        "dominant_v2_1_path_frequency": dominant_path,
        "path_entropy_bits": entropy,
        "normalized_path_entropy": normalized_entropy,
        "diagnostic_labels": labels,
    }


def build_audit(plugin: Path, private: Path, contract_path: Path) -> dict[str, Any]:
    contract = load(contract_path)
    source = contract["source_experiment"]
    frozen_contract_path = plugin / "resources/acp1_4f_frozen_contract.json"
    early_stop_path = plugin / "resources/acp1_4f_f1_early_stop.json"
    early_index_path = plugin / "resources/acp1_4f_f1_frozen_early_stop_index.json"
    if sha256_file(early_stop_path) != source["public_early_stop_sha256"]:
        raise AuditError("early_stop_hash_mismatch")
    if sha256_file(early_index_path) != source["public_frozen_index_sha256"]:
        raise AuditError("early_stop_index_hash_mismatch")
    frozen_contract = load(frozen_contract_path)
    paths = sorted(private.glob("*/result.json"))
    logical_id = load(early_index_path)["private_source"]["logical_id"]
    if completed_inventory_digest(paths, logical_id) != source["private_completed_inventory_sha256"]:
        raise AuditError("private_inventory_hash_mismatch")
    case_by_id = {case["case_id"]: case for case in frozen_contract["cases"]}
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        result = load(path)
        case_id = str(result.get("case_id", ""))
        if case_id not in case_by_id:
            raise AuditError("unknown_case_id")
        by_case[case_id].append(analyze_run(path, case_by_id[case_id], frozen_contract["candidate_identity"]["minimum_result_chars"]))
    case_summaries = [summarize_case(case, by_case[case["case_id"]]) for case in frozen_contract["cases"] if by_case[case["case_id"]]]
    totals = {
        "observed_completed_runs": sum(row["observed_completed_runs"] for row in case_summaries),
        "correct_runs": sum(row["correct_runs"] for row in case_summaries),
        "measurement_unknown_runs": sum(row["measurement_unknown_runs"] for row in case_summaries),
        "v2_1_candidate_recurrence": sum(row["v2_1_candidate_recurrence"] for row in case_summaries),
        "evidence_opportunity_recurrence": sum(row["evidence_opportunity_recurrence"] for row in case_summaries),
        "intervention_compatible_carrier_recurrence": sum(row["intervention_compatible_carrier_recurrence"] for row in case_summaries),
        "identity_false_negative_runs": sum(row["identity_false_negative_runs"] for row in case_summaries),
        "runs_with_meta_or_nonexecution_calls": sum(row["runs_with_meta_or_nonexecution_calls"] for row in case_summaries),
    }
    has_identity_mismatch = any("IDENTITY_MISMATCH" in row["diagnostic_labels"] for row in case_summaries)
    has_path_mismatch = any("PATH_GATE_MISMATCH" in row["diagnostic_labels"] for row in case_summaries)
    sufficient_existing_signal = (
        totals["measurement_unknown_runs"] == 0
        and totals["evidence_opportunity_recurrence"] == totals["observed_completed_runs"]
        and has_identity_mismatch
        and has_path_mismatch
    )
    audit_exit = "PROCEED_TO_BENCHMARK_DEVELOPMENT_POOL" if sufficient_existing_signal else "INCONCLUSIVE"
    return {
        "schema_version": 1,
        "schema_id": RESULT_SCHEMA_ID,
        "audit_id": contract["audit_id"],
        "status": "complete_under_read_only_audit_scope",
        "audit_exit": audit_exit,
        "interpretation": "v2.1 measured identity and full-trajectory stability more strictly than request-related intervention-compatible evidence recurrence",
        "not_an_intervention_generalization_result": True,
        "agent_run_count": 0,
        "source_integrity": {
            "audit_contract_sha256": sha256_file(contract_path),
            "v2_1_contract_sha256": sha256_file(frozen_contract_path),
            "f1_early_stop_sha256": sha256_file(early_stop_path),
            "f1_frozen_index_sha256": sha256_file(early_index_path),
            "private_completed_inventory_sha256": source["private_completed_inventory_sha256"],
        },
        "totals": totals,
        "case_summaries": case_summaries,
        "causal_claims": {
            "r1_s1_b1_tested": False,
            "treatment_builder_used": False,
            "collector_or_hook_used": False,
            "intervention_used": False,
            "v2_1_reclassified": False,
            "future_formal_reuse_allowed": False,
        },
        "next_boundary": {
            "development_pool_authorized_by_this_result": False,
            "new_agent_runs": 0,
            "future_holdout_must_be_new": True,
            "qualification_unit_to_calibrate": "intervention_compatible_evidence_opportunity",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    plugin = Path(__file__).resolve().parents[1]
    workspace = plugin.parents[1]
    parser.add_argument("--plugin", type=Path, default=plugin)
    parser.add_argument("--private", type=Path, default=workspace / ".agent-token-manager/acp1-4f-native-v21-20260819")
    parser.add_argument("--contract", type=Path, default=plugin / "resources/acp1_4f_r_audit_contract.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_audit(args.plugin.resolve(), args.private.resolve(), args.contract.resolve())
    payload = canonical_bytes(result)
    if args.output:
        args.output.resolve().write_bytes(payload)
    else:
        print(payload.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
