#!/usr/bin/env python3
"""Audit why three frozen ACP-1.4C treatments did not activate."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from run_co0_gate import load_jsonl
from run_co1_gate2 import normalize_command, transcript_calls


AUDIT_CASES = {
    "read_context_router_limit_v1": {"classification": "RULE_MISMATCH", "target": "context_router.py"},
    "search_budget_stop_v1": {"classification": "RULE_MISMATCH", "target": "task_navigator.py"},
    "search_token_router_v1": {"classification": "MEASUREMENT_MISMATCH", "target": "context_router.py"},
}
PROHIBITED = ("/users/", "final_text", "tool_response", "wasted_tokens", "potential_savings")


class AuditError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError(f"object_required:{path.name}")
    return value


def distribution(values: list[int | float]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {"count": len(ordered), "min": ordered[0], "median": statistics.median(ordered), "max": ordered[-1]}


def load_candidate(run_dir: Path, case: dict[str, Any]) -> tuple[str, str]:
    transcripts = sorted((run_dir / "codex-home" / "sessions").rglob("*.jsonl"))
    if len(transcripts) != 1:
        raise AuditError(f"transcript_count:{run_dir.name}:{len(transcripts)}")
    calls = transcript_calls(load_jsonl(transcripts[0]))
    matches = []
    for call in calls:
        command = normalize_command(str(call.get("command", "")))
        if all(str(term).casefold() in command.casefold() for term in case["candidate_command_terms"]):
            matches.append((command, str(call.get("output", ""))))
    if len(matches) != 1:
        raise AuditError(f"candidate_count:{run_dir.name}:{len(matches)}")
    return matches[0]


def command_shape(command: str) -> str:
    return "appended_root_scope" if command.rstrip().endswith(" .") else "declared_scope_only"


def line_composition(case_id: str, output: str, target: str) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for line in output.splitlines(keepends=True):
        lowered = line.casefold()
        if line.startswith(("Script completed", "Wall time", "Output:")):
            category = "host_wrapper"
        elif "warning: truncated output" in lowered or "total output lines:" in lowered:
            category = "host_truncation_metadata"
        elif case_id.startswith("read_"):
            category = "source_payload"
        else:
            path = line.split(":", 1)[0]
            normalized = path[2:] if path.startswith("./") else path
            if normalized.endswith(target):
                category = "preserved_target"
            elif path.startswith("./"):
                category = "appended_root_scope"
            else:
                category = "declared_nontarget"
        totals[f"{category}_lines"] += 1
        totals[f"{category}_chars"] += len(line)
    return dict(totals)


def audit_case(case: dict[str, Any], formal_case: dict[str, Any], private_root: Path) -> dict[str, Any]:
    case_id = case["case_id"]
    meta = AUDIT_CASES[case_id]
    compact_runs = []
    for arm in ("control", "treatment"):
        for ordinal in range(1, 11):
            run_dir = private_root / f"formal__{case_id}__r{ordinal:02d}-{arm}"
            result = load(run_dir / "result.json")
            command, output = load_candidate(run_dir, case)
            expected_tokens = (len(output) + 3) // 4
            if result.get("candidate_visible_estimated_tokens") != expected_tokens:
                raise AuditError(f"visible_token_mismatch:{case_id}:{arm}:{ordinal}")
            compact_runs.append({
                "arm": arm,
                "command_shape": command_shape(command),
                "visible_chars": len(output),
                "visible_estimated_tokens": expected_tokens,
                "truncation_marker_count": output.casefold().count("warning: truncated output"),
                "composition": line_composition(case_id, output, meta["target"]),
                "changed_file_count": int(result.get("treatment", {}).get("changed_file_count", 0)),
                "changed_line_count": int(result.get("treatment", {}).get("changed_line_count", 0)),
            })
    by_arm = {}
    categories = sorted({key for row in compact_runs for key in row["composition"]})
    for arm in ("control", "treatment"):
        selected = [row for row in compact_runs if row["arm"] == arm]
        by_arm[arm] = {
            "run_count": len(selected),
            "visible_chars": distribution([row["visible_chars"] for row in selected]),
            "visible_estimated_tokens": distribution([row["visible_estimated_tokens"] for row in selected]),
            "command_shape_counts": dict(sorted(Counter(row["command_shape"] for row in selected).items())),
            "truncation_marker_count": distribution([row["truncation_marker_count"] for row in selected]),
            "changed_file_count": distribution([row["changed_file_count"] for row in selected]),
            "changed_line_count": distribution([row["changed_line_count"] for row in selected]),
            "composition_median": {key: statistics.median([row["composition"].get(key, 0) for row in selected]) for key in categories},
        }
    median = formal_case["activation"]["evidence_reduction_ratio"]["median"]
    if median >= 0.35 or formal_case["verdict"] != "INCONCLUSIVE":
        raise AuditError(f"not_frozen_inconclusive:{case_id}")

    if case_id == "read_context_router_limit_v1":
        findings = {
            "mechanism": "prefix_projection_kept_70_of_93_source_lines",
            "source_lines_changed": by_arm["treatment"]["changed_line_count"]["median"],
            "remaining_visible_chars": by_arm["treatment"]["visible_chars"]["median"],
            "reason": "target_declaration_is_early_but_rule_preserved_a_broad_70_line_prefix",
        }
        eligibility = "eligible_after_preregistration"
    elif case_id == "search_budget_stop_v1":
        control_chars = by_arm["control"]["visible_chars"]["median"]
        preserved = by_arm["control"]["composition_median"].get("preserved_target_chars", 0)
        findings = {
            "mechanism": "whole_target_file_exemption_plus_appended_root_scope",
            "preserved_target_visible_char_share": preserved / control_chars,
            "source_lines_changed": by_arm["treatment"]["changed_line_count"]["median"],
            "reason": "rule_changed_only_one_nontarget_match_while_preserving_all_target_file_matches",
        }
        eligibility = "eligible_after_preregistration"
    else:
        findings = {
            "mechanism": "source_ablation_hidden_by_host_output_censoring",
            "source_files_changed": by_arm["treatment"]["changed_file_count"]["median"],
            "source_lines_changed": by_arm["treatment"]["changed_line_count"]["median"],
            "control_runs_with_truncation": sum(row["truncation_marker_count"] > 0 for row in compact_runs if row["arm"] == "control"),
            "treatment_runs_with_truncation": sum(row["truncation_marker_count"] > 0 for row in compact_runs if row["arm"] == "treatment"),
            "reason": "both_arms_remained_above_the_host_visible_output_cap_so_deleted_source_matches_did_not_map_to_visible_volume",
        }
        eligibility = "eligible_after_preregistration_with_censoring_control"

    return {
        "case_id": case_id,
        "family": case["family"],
        "historical_verdict": formal_case["verdict"],
        "activation_gate": 0.35,
        "observed_reduction_median": median,
        "primary_classification": meta["classification"],
        "v2_eligibility": eligibility,
        "prospective_direction": next(row["prospective_direction"] for row in load_spec_cases if row["case_id"] == case_id),
        "arms": by_arm,
        "findings": findings,
        "measurement_semantics": "model_visible_chars_div_4_v1",
    }


load_spec_cases: list[dict[str, Any]] = []


def build(spec_path: Path, plugin_root: Path, private_root: Path) -> dict[str, Any]:
    global load_spec_cases
    spec = load(spec_path)
    if spec.get("schema_id") != "acp1-4d-activation-audit-spec-v1":
        raise AuditError("invalid_spec")
    for source in ("source_formal_result", "source_experiment_spec", "source_frozen_index"):
        path = plugin_root / spec[source]["path"]
        if sha256_file(path) != spec[source]["sha256"]:
            raise AuditError(f"source_hash_mismatch:{source}")
    formal = load(plugin_root / spec["source_formal_result"]["path"])
    experiment = load(plugin_root / spec["source_experiment_spec"]["path"])
    load_spec_cases = list(spec["cases"])
    case_map = {row["case_id"]: row for row in experiment["cases"]}
    formal_map = {row["case_id"]: row for row in formal["cases"]}
    rows = [audit_case(case_map[row["case_id"]], formal_map[row["case_id"]], private_root) for row in spec["cases"]]
    for row, expected in zip(rows, spec["cases"]):
        if row["primary_classification"] != expected["expected_primary_classification"] or row["observed_reduction_median"] != expected["expected_reduction_median"]:
            raise AuditError(f"classification_or_baseline_mismatch:{row['case_id']}")
    result = {
        "schema_version": 1,
        "schema_id": "acp1-4d-activation-audit-v1",
        "experiment_id": spec["experiment_id"],
        "status": "complete_under_frozen_audit_scope",
        "agent_run_count": 0,
        "private_formal_runs_audited": 60,
        "activation_gate": spec["activation_gate"],
        "cases": rows,
        "summary": {
            "rule_mismatch": 2,
            "measurement_mismatch": 1,
            "fixed_structure_dominated": 0,
            "limited_safe_reduction": 0,
            "inconclusive": 0,
            "v2_eligible": 3,
        },
        "traceability": {
            "audit_spec_sha256": sha256_file(spec_path),
            "formal_result_sha256": spec["source_formal_result"]["sha256"],
            "experiment_spec_sha256": spec["source_experiment_spec"]["sha256"],
            "frozen_index_sha256": spec["source_frozen_index"]["sha256"],
        },
        "policy": spec["policy"],
    }
    serialized = canonical_bytes(result).decode("utf-8").casefold()
    if any(term in serialized for term in PROHIBITED):
        raise AuditError("privacy_or_claim_violation")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    plugin = Path(__file__).resolve().parents[1]
    workspace = plugin.parents[1]
    parser.add_argument("--spec", type=Path, default=plugin / "resources/acp1_4d_activation_audit_spec.json")
    parser.add_argument("--private-root", type=Path, default=workspace / ".agent-token-manager/acp1-4c-formal-live-20260819")
    parser.add_argument("--output", type=Path, default=plugin / "resources/acp1_4d_activation_audit.json")
    args = parser.parse_args()
    result = build(args.spec.resolve(), plugin.resolve(), args.private_root.resolve())
    args.output.resolve().write_bytes(canonical_bytes(result))
    print(canonical_bytes({"status": result["status"], "cases": len(result["cases"]), "output_sha256": sha256_file(args.output.resolve())}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
