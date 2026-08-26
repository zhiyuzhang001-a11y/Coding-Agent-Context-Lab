#!/usr/bin/env python3
"""Run ACP-1.4E offline preflight, Native qualification, pilot, and v2 formal."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import run_acp1_4_generalization as base


RUNNER_VERSION = "acp1-4e-prospective-v2-runner-v0.1"
BASE_APPLY_TREATMENT = base.apply_treatment
FROZEN_HASHES = {
    "resources/acp1_4d_frozen_activation_audit_index.json": "7a647e91e067a222020ce8b1df7192e5cf8a530f7aaf645d2afd758857aa9d6d",
    "resources/acp1_4d_frozen_experiment_manifest.json": "3710780c5270c27034a89b02303cb06e161c960d499502fcb9ec4b3bdad29870",
    "resources/acp1_4c_results.json": "b95680b3264a53fa3979d0e643405f1b762d145d877d341ec31e83b805b7f2d2",
    "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
    "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
}


class V2ValidationError(ValueError):
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
        raise V2ValidationError(f"object_required:{path.name}")
    return value


def load_spec(path: Path, plugin: Path) -> dict[str, Any]:
    spec = load(path)
    if spec.get("schema_id") != "acp1-4e-prospective-v2-spec-v1":
        raise V2ValidationError("invalid_spec")
    if len(spec.get("cases", [])) != 3 or any(row.get("case_version") != 2 for row in spec["cases"]):
        raise V2ValidationError("invalid_v2_sampling_frame")
    if {row["supersedes"] for row in spec["cases"]} != {
        "read_context_router_limit_v1", "search_budget_stop_v1", "search_token_router_v1",
    }:
        raise V2ValidationError("invalid_supersedes_set")
    if spec["qualification"]["qualified_case_min_for_formal"] != 3 or spec["formal"]["minimum_evidence_reduction_ratio"] != 0.35:
        raise V2ValidationError("gate_drift")
    if any(spec["policy"][key] for key in (
        "v1_history_changed", "activation_gate_changed", "failed_cases_replaced", "collector_or_hook_mutation",
        "production_slicing_or_replacement", "real_time_recommendation", "global_generalization_claim", "global_savings_claim",
    )):
        raise V2ValidationError("policy_boundary_violation")
    for relative, expected in FROZEN_HASHES.items():
        if sha256_file(plugin / relative) != expected:
            raise V2ValidationError(f"frozen_hash_mismatch:{relative}")
    return spec


def replace_term(value: str, term: str) -> str:
    return re.sub(re.escape(term), "__ACP14E_ABLATED_TERM__", value, flags=re.IGNORECASE)


def apply_treatment(workdir: Path, case: dict[str, Any]) -> dict[str, Any]:
    treatment = case["treatment"]
    if treatment["method"] != "line-selective-term-projection-v2":
        return BASE_APPLY_TREATMENT(workdir, case)
    term = treatment["term"]
    preserved_target = treatment["preserved_target"]
    pattern = re.compile(treatment["preserved_line_regex"])
    preserved = False
    changed_files = changed_lines = matched_lines = 0
    paths: list[Path] = []
    for relative in treatment["scope"]:
        target = workdir / relative
        paths.extend(sorted(path for path in target.rglob("*") if path.is_file()) if target.is_dir() else [target])
    for path in sorted(set(paths)):
        relative = path.relative_to(workdir).as_posix()
        try:
            before = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rows = before.splitlines(keepends=True)
        changed = False
        for index, row in enumerate(rows):
            if term.casefold() not in row.casefold():
                continue
            matched_lines += 1
            bare = row.rstrip("\r\n").strip()
            may_preserve = relative == preserved_target and pattern.search(bare) is not None
            if may_preserve and (not treatment["preserve_first_matching_line_only"] or not preserved):
                preserved = True
                continue
            rows[index] = replace_term(row, term)
            changed = True
            changed_lines += 1
        if changed:
            path.write_text("".join(rows), encoding="utf-8")
            changed_files += 1
    if not preserved:
        raise V2ValidationError(f"preserved_evidence_not_found:{case['case_id']}")
    return {
        "method": treatment["method"], "changed_file_count": changed_files, "changed_line_count": changed_lines,
        "matched_line_count": matched_lines, "preserved_line_count": 1,
    }


base.apply_treatment = apply_treatment


def run_offline_command(workdir: Path, case: dict[str, Any]) -> str:
    completed = subprocess.run(["/bin/zsh", "-lc", case["offline_command"]], cwd=workdir, text=True, capture_output=True, timeout=30)
    if completed.returncode != 0:
        raise V2ValidationError(f"offline_command_failed:{case['case_id']}:{completed.returncode}")
    return completed.stdout


def offline_preflight(spec: dict[str, Any], repository: Path) -> dict[str, Any]:
    rows = []
    for case in spec["cases"]:
        arm_outputs = {}
        metas = {}
        for arm in ("control", "treatment"):
            temporary = Path(tempfile.mkdtemp(prefix="acp14e-offline-"))
            workdir = temporary / "subject"
            try:
                base.qualification.materialize_subject(repository, spec["subject_commit"], workdir)
                metas[arm] = apply_treatment(workdir, case) if arm == "treatment" else {"method": "none_control", "changed_file_count": 0, "changed_line_count": 0}
                arm_outputs[arm] = run_offline_command(workdir, case)
            finally:
                shutil.rmtree(temporary, ignore_errors=True)
        before, after = len(arm_outputs["control"]), len(arm_outputs["treatment"])
        reduction = (before - after) / before if before else None
        uncensored = True
        if case["case_id"] == "search_token_router_v2":
            uncensored = max(before, after) < spec["offline"]["token_router_censoring_ceiling_chars"]
        checks = {
            "control_contains_expected_evidence": case["expected"].casefold() in arm_outputs["control"].casefold(),
            "treatment_contains_expected_evidence": case["expected"].casefold() in arm_outputs["treatment"].casefold(),
            "activation": reduction is not None and reduction >= spec["offline"]["minimum_evidence_reduction_ratio"],
            "nonempty_treatment": after > 0,
            "uncensored_scope": uncensored,
            "single_variable_source_treatment": metas["treatment"]["changed_file_count"] > 0,
        }
        rows.append({
            "case_id": case["case_id"], "status": "pass" if all(checks.values()) else "fail", "checks": checks,
            "control_chars": before, "treatment_chars": after, "evidence_reduction_ratio": reduction,
            "control_sha256": sha256_text(arm_outputs["control"]), "treatment_sha256": sha256_text(arm_outputs["treatment"]),
            "treatment": metas["treatment"],
        })
    return {
        "schema_version": 1, "schema_id": "acp1-4e-offline-preflight-v1", "agent_run_count": 0,
        "case_count": len(rows), "cases": rows, "status": "pass" if all(row["status"] == "pass" for row in rows) else "fail",
    }


def qualification_outputs(spec: dict[str, Any], spec_path: Path, runs: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [base.qualification_case(spec, case, [run for run in runs if run["case_id"] == case["case_id"]]) for case in spec["cases"]]
    qualified = sum(row["status"] == "qualified" for row in cases)
    formal_gate = qualified >= spec["qualification"]["qualified_case_min_for_formal"]
    result = {
        "schema_version": 1, "schema_id": "acp1-4e-v2-qualification-result-v1", "experiment_id": spec["experiment_id"],
        "runner_version": RUNNER_VERSION, "spec_sha256": sha256_file(spec_path), "run_count": len(runs), "cases": cases,
        "runs": [base.compact(run) for run in runs], "formal_eligibility_gate": formal_gate,
        "policy": {"native_only": True, "v1_preserved": True, "intervention": False},
    }
    registry = {
        "schema_version": 1, "schema_id": "acp1-4e-v2-registry-v1", "status": "qualification_complete_under_frozen_scope",
        "source_result_sha256": hashlib.sha256(canonical_bytes(result)).hexdigest(), "spec_sha256": sha256_file(spec_path),
        "cases": cases, "formal_eligibility_gate": formal_gate,
        "funnel": {"proposed": 3, "qualified": qualified, "diagnostic_only": sum(row["status"] == "diagnostic_only" for row in cases), "rejected": sum(row["status"] == "rejected" for row in cases)},
        "history_policy": {"v1_preserved": True, "all_three_v2_required_for_formal": True, "thresholds_changed": False},
    }
    return result, registry


def pilot_output(spec: dict[str, Any], cases: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = base.paired_rows(runs)
    rows = []
    for case in cases:
        pair = next((row for row in pairs if row["case_id"] == case["case_id"]), None)
        ratio = pair["evidence_reduction_ratio"] if pair else None
        checks = {
            "pair_complete": pair is not None,
            "both_correct": bool(pair and pair["control"].get("correct") and pair["treatment"].get("correct")),
            "identity_unique": bool(pair and all(arm.get("candidate_recurred") and not arm.get("candidate_ambiguous") for arm in (pair["control"], pair["treatment"]))),
            "activation": ratio is not None and ratio >= spec["formal"]["minimum_evidence_reduction_ratio"],
            "success_semantics": bool(pair and pair["control"].get("candidate_success_semantics") and pair["treatment"].get("candidate_success_semantics")),
        }
        rows.append({"case_id": case["case_id"], "checks": checks, "evidence_reduction_ratio": ratio, "status": "pass" if all(checks.values()) else "fail"})
    return {
        "schema_version": 1, "schema_id": "acp1-4e-v2-pilot-result-v1", "run_count": len(runs),
        "included_in_formal_statistics": False, "cases": rows,
        "status": "pass" if len(rows) == 3 and all(row["status"] == "pass" for row in rows) else "inconclusive_plumbing",
    }


def formal_output(spec: dict[str, Any], spec_path: Path, registry_path: Path, cases: list[dict[str, Any]], qrows: dict[str, dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [base.formal_case(spec, case, qrows[case["case_id"]], runs) for case in cases]
    resolved = sum(row["verdict"] == "PASS" for row in summaries)
    verdict = "ACTIVATION_RESOLVED" if resolved == 3 else ("PARTIALLY_RESOLVED" if resolved else "NOT_RESOLVED")
    return {
        "schema_version": 1, "schema_id": "acp1-4e-v2-formal-result-v1", "experiment_id": spec["experiment_id"],
        "runner_version": RUNNER_VERSION, "spec_sha256": sha256_file(spec_path), "registry_sha256": sha256_file(registry_path),
        "run_count": len(runs), "cases": summaries,
        "summary": {"case_count": 3, "pass": resolved, "fail": sum(row["verdict"] == "FAIL" for row in summaries), "inconclusive": sum(row["verdict"] == "INCONCLUSIVE" for row in summaries), "verdict": verdict},
        "runs": [base.compact(run) for run in runs],
        "policy": {**spec["policy"], "session_ratios_descriptive_only": True, "global_generalization_claim": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    plugin = Path(__file__).resolve().parents[1]
    workspace = plugin.parents[1]
    parser.add_argument("--phase", choices=("offline", "qualification", "pilot", "formal"), required=True)
    parser.add_argument("--repository", type=Path, default=workspace)
    parser.add_argument("--spec", type=Path, default=plugin / "resources/acp1_4e_experiment_spec.json")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--offline-result", type=Path, default=plugin / "resources/acp1_4e_offline_preflight.json")
    parser.add_argument("--qualification-result", type=Path, default=plugin / "resources/acp1_4e_qualification_results.json")
    parser.add_argument("--registry", type=Path, default=plugin / "resources/acp1_4e_candidate_registry.json")
    parser.add_argument("--pilot-result", type=Path, default=plugin / "resources/acp1_4e_pilot_results.json")
    parser.add_argument("--formal-result", type=Path, default=plugin / "resources/acp1_4e_results.json")
    parser.add_argument("--codex", type=Path, default=Path(shutil.which("codex") or "codex"))
    parser.add_argument("--source-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    spec_path = args.spec.resolve()
    spec = load_spec(spec_path, plugin)
    if args.phase == "offline":
        result = offline_preflight(spec, args.repository.resolve())
        args.offline_result.resolve().write_bytes(canonical_bytes(result))
        print(canonical_bytes({"phase": "offline", "status": result["status"], "result_sha256": sha256_file(args.offline_result.resolve())}).decode(), end="")
        return 0
    preflight = load(args.offline_result.resolve())
    if preflight.get("status") != "pass" or preflight.get("agent_run_count") != 0:
        raise V2ValidationError("offline_preflight_not_passed")
    artifacts = (args.artifacts or workspace / ".agent-token-manager" / f"acp1-4e-{args.phase}-20260819").resolve()
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    common = (args.repository.resolve(), args.codex.resolve(), args.source_home.resolve(), artifacts, args.timeout, args.resume)
    if args.phase == "qualification":
        schedule = [(case, ordinal, "native") for case in spec["cases"] for ordinal in range(1, 11)]
        runs = [base.prepare_run(spec, case, "qualification", ordinal, arm, *common) for case, ordinal, arm in schedule]
        result, registry = qualification_outputs(spec, spec_path, runs)
        args.qualification_result.resolve().write_bytes(canonical_bytes(result))
        args.registry.resolve().write_bytes(canonical_bytes(registry))
        output = {"phase": "qualification", "run_count": len(runs), "funnel": registry["funnel"], "formal_eligibility_gate": registry["formal_eligibility_gate"], "result_sha256": sha256_file(args.qualification_result.resolve()), "registry_sha256": sha256_file(args.registry.resolve())}
    else:
        registry = load(args.registry.resolve())
        if registry.get("spec_sha256") != sha256_file(spec_path) or not registry.get("formal_eligibility_gate"):
            raise V2ValidationError("v2_not_eligible")
        qrows = {row["case_id"]: row for row in registry["cases"] if row["status"] == "qualified"}
        cases = [case for case in spec["cases"] if case["case_id"] in qrows]
        if len(cases) != 3:
            raise V2ValidationError("all_three_v2_cases_required")
        if args.phase == "pilot":
            schedule = [(case, 1, arm) for case in cases for arm in ("control", "treatment")]
            runs = [base.prepare_run(spec, case, "pilot", ordinal, arm, *common) for case, ordinal, arm in schedule]
            result = pilot_output(spec, cases, runs)
            args.pilot_result.resolve().write_bytes(canonical_bytes(result))
            output = {"phase": "pilot", "run_count": len(runs), "status": result["status"], "result_sha256": sha256_file(args.pilot_result.resolve())}
        else:
            pilot = load(args.pilot_result.resolve())
            if pilot.get("status") != "pass" or pilot.get("included_in_formal_statistics") is not False:
                raise V2ValidationError("pilot_not_passed")
            schedule = base.schedule_formal(cases, spec["formal"]["blocks_per_case"])
            runs = [base.prepare_run(spec, case, "formal", ordinal, arm, *common) for case, ordinal, arm in schedule]
            result = formal_output(spec, spec_path, args.registry.resolve(), cases, qrows, runs)
            args.formal_result.resolve().write_bytes(canonical_bytes(result))
            output = {"phase": "formal", "run_count": len(runs), "summary": result["summary"], "result_sha256": sha256_file(args.formal_result.resolve())}
    print(canonical_bytes(output).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
