#!/usr/bin/env python3
"""Run ACP-1.4C Bash v2 qualification and restored combined generalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import run_acp1_4_generalization as base


RUNNER_VERSION = "acp1-4c-bash-requalification-runner-v0.1"
BASE_APPLY_TREATMENT = base.apply_treatment
FROZEN_HASHES = {
    "resources/acp1_4a_candidate_registry.json": "ee5c61d14f089694fa1e9d60a70129784da999453f0fd3ce7986bd497997bc8f",
    "resources/acp1_4_frozen_generalization_index.json": "67eccea11c5488c6f2d225353506e9c5be3f8dcc269905d291d307fbebd70876",
    "resources/acp1_4_frozen_experiment_manifest.json": "5716bd57de9d575088b32ae0608dc6be73f8d7705b7ad44e9d3954cb43a76419",
    "scripts/acp_collector.py": "81efee8b5ae05fe2f9c76f73e5edacec1e8269ae5923a6ebc0019f1479f96de2",
    "hooks/hooks.json": "797b72b678ddba104acd93285f3c34542e75a58f69016fb01c99bf4ebac394dd",
}


class BashRequalificationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BashRequalificationError(f"object_required:{path.name}")
    return value


def load_spec(path: Path, plugin: Path) -> dict[str, Any]:
    spec = load(path)
    if spec.get("schema_id") != "acp1-4c-bash-requalification-spec-v1":
        raise BashRequalificationError("invalid_spec")
    if len(spec.get("cases", [])) != 3 or any(row.get("family") != "bash" or row.get("case_version") != 2 for row in spec["cases"]):
        raise BashRequalificationError("invalid_bash_v2_sampling_frame")
    if spec["qualification"]["repetitions_per_case"] != 10 or spec["formal"]["blocks_per_case"] != 10:
        raise BashRequalificationError("invalid_repeated_design")
    if any(spec["policy"][key] for key in ("collector_or_hook_mutation", "production_slicing_or_replacement", "real_time_recommendation", "global_savings_claim")):
        raise BashRequalificationError("policy_boundary_violation")
    for relative, expected in FROZEN_HASHES.items():
        target = plugin / relative
        if not target.is_file() or sha256_file(target) != expected:
            raise BashRequalificationError(f"frozen_hash_mismatch:{relative}")
    return spec


def apply_treatment(workdir: Path, case: dict[str, Any]) -> dict[str, Any]:
    treatment = case["treatment"]
    method = treatment["method"]
    if method == "json-list-prefix-projection-v1":
        target = workdir / treatment["target"]
        value = load(target)
        key = treatment["list_key"]
        rows = value.get(key)
        if not isinstance(rows, list):
            raise BashRequalificationError("json_list_required")
        before_count = len(rows)
        value[key] = rows[: int(treatment["keep_first_items"])]
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"method": method, "changed_file_count": 1, "changed_line_count": before_count - len(value[key]), "removed_item_count": before_count - len(value[key])}
    if method == "json-object-key-projection-v1":
        target = workdir / treatment["target"]
        value = load(target)
        key = treatment["object_key"]
        mapping = value.get(key)
        if not isinstance(mapping, dict):
            raise BashRequalificationError("json_object_required")
        keep = list(treatment["keep_keys"])
        if any(item not in mapping for item in keep):
            raise BashRequalificationError("missing_preserved_key")
        before_count = len(mapping)
        value[key] = {item: mapping[item] for item in keep}
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"method": method, "changed_file_count": 1, "changed_line_count": before_count - len(value[key]), "removed_key_count": before_count - len(value[key])}
    return BASE_APPLY_TREATMENT(workdir, case)


base.apply_treatment = apply_treatment


def qualification_outputs(spec: dict[str, Any], spec_path: Path, runs: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    cases = [base.qualification_case(spec, case, [run for run in runs if run["case_id"] == case["case_id"]]) for case in spec["cases"]]
    qualified = sum(row["status"] == "qualified" for row in cases)
    formal_gate = qualified >= spec["qualification"]["qualified_case_min_for_formal"]
    result = {
        "schema_version": 1, "schema_id": "acp1-4c-bash-v2-qualification-result-v1", "experiment_id": spec["experiment_id"],
        "runner_version": RUNNER_VERSION, "spec_sha256": sha256_file(spec_path), "run_count": len(runs), "cases": cases,
        "runs": [base.compact(run) for run in runs], "formal_eligibility_gate": formal_gate,
        "policy": {"bash_v2_native_only": True, "old_cases_preserved": True, "intervention": False},
    }
    registry = {
        "schema_version": 1, "schema_id": "acp1-4c-bash-v2-registry-v1", "status": "qualification_complete_under_frozen_scope",
        "source_result_sha256": hashlib.sha256(canonical_bytes(result)).hexdigest(), "spec_sha256": sha256_file(spec_path),
        "cases": cases, "formal_eligibility_gate": formal_gate,
        "funnel": {"proposed": len(cases), "qualified": qualified, "diagnostic_only": sum(row["status"] == "diagnostic_only" for row in cases), "rejected": sum(row["status"] == "rejected" for row in cases)},
        "history_policy": {"bash_v1_preserved": True, "acp1_4_verdict_changed": False, "all_and_only_v2_qualified_enter_restored_formal": True},
    }
    return result, registry


def pilot_output(spec: dict[str, Any], cases: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = base.paired_rows(runs)
    treatment_families = []
    for family in sorted({case["treatment"]["family"] for case in cases}):
        pair = next((row for row in pairs if next(case for case in cases if case["case_id"] == row["case_id"])["treatment"]["family"] == family), None)
        ratio = pair["evidence_reduction_ratio"] if pair else None
        checks = {
            "pair_complete": pair is not None,
            "both_correct": bool(pair and pair["control"].get("correct") and pair["treatment"].get("correct")),
            "identity_unique": bool(pair and all(arm.get("candidate_recurred") and not arm.get("candidate_ambiguous") for arm in (pair["control"], pair["treatment"]))),
            "activation": ratio is not None and ratio >= spec["formal"]["minimum_evidence_reduction_ratio"],
            "success_semantics": bool(pair and pair["control"].get("candidate_success_semantics") and pair["treatment"].get("candidate_success_semantics")),
        }
        treatment_families.append({"treatment_family": family, "case_id": pair["case_id"] if pair else None, "checks": checks, "evidence_reduction_ratio": ratio, "status": "pass" if all(checks.values()) else "fail"})
    return {
        "schema_version": 1, "schema_id": "acp1-4c-bash-v2-pilot-result-v1", "run_count": len(runs),
        "included_in_formal_statistics": False, "treatment_families": treatment_families,
        "status": "pass" if treatment_families and all(row["status"] == "pass" for row in treatment_families) else "inconclusive_plumbing",
    }


def combined_cases(plugin: Path, spec: dict[str, Any], bash_registry: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    old_spec = load(plugin / "resources/acp1_4_experiment_spec.json")
    old_registry = load(plugin / "resources/acp1_4a_candidate_registry.json")
    old_qualified = {row["case_id"]: row for row in old_registry["cases"] if row["status"] == "qualified"}
    bash_qualified = {row["case_id"]: row for row in bash_registry["cases"] if row["status"] == "qualified"}
    cases = [row for row in old_spec["cases"] if row["case_id"] in old_qualified] + [row for row in spec["cases"] if row["case_id"] in bash_qualified]
    return cases, {**old_qualified, **bash_qualified}


def formal_output(spec: dict[str, Any], spec_path: Path, registry_path: Path, cases: list[dict[str, Any]], qualification_rows: dict[str, dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    summaries = [base.formal_case(spec, case, qualification_rows[case["case_id"]], runs) for case in cases]
    families = Counter(case["family"] for case in cases)
    coverage_gate = all(families[family] >= spec["generalization"]["qualified_per_family_min"] for family in spec["generalization"]["required_families"])
    pseudo_registry = {"formal_coverage_gate": coverage_gate}
    generalization = base.generalization_summary(spec, summaries, pseudo_registry, len(summaries) == len(cases))
    return {
        "schema_version": 1, "schema_id": "acp1-4c-restored-generalization-result-v1", "experiment_id": spec["experiment_id"],
        "runner_version": RUNNER_VERSION, "spec_sha256": sha256_file(spec_path), "bash_registry_sha256": sha256_file(registry_path),
        "run_count": len(runs), "cases": summaries, "generalization": generalization,
        "funnel": {"combined_formal_cases": len(cases), "read_cases": families["read"], "search_cases": families["search"], "bash_cases": families["bash"], "pass": sum(row["verdict"] == "PASS" for row in summaries), "fail": sum(row["verdict"] == "FAIL" for row in summaries), "inconclusive": sum(row["verdict"] == "INCONCLUSIVE" for row in summaries)},
        "runs": [base.compact(run) for run in runs],
        "policy": {**spec["policy"], "combined_read_search_bash_baseline": True, "session_ratios_descriptive_only": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    plugin = Path(__file__).resolve().parents[1]
    workspace = plugin.parents[1]
    parser.add_argument("--phase", choices=("qualification", "pilot", "formal"), required=True)
    parser.add_argument("--repository", type=Path, default=workspace)
    parser.add_argument("--spec", type=Path, default=plugin / "resources/acp1_4c_experiment_spec.json")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--qualification-result", type=Path, default=plugin / "resources/acp1_4c_qualification_results.json")
    parser.add_argument("--registry", type=Path, default=plugin / "resources/acp1_4c_bash_v2_registry.json")
    parser.add_argument("--pilot-result", type=Path, default=plugin / "resources/acp1_4c_pilot_results.json")
    parser.add_argument("--formal-result", type=Path, default=plugin / "resources/acp1_4c_results.json")
    parser.add_argument("--codex", type=Path, default=Path(shutil.which("codex") or "codex"))
    parser.add_argument("--source-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--offline-check", action="store_true")
    args = parser.parse_args()
    spec_path = args.spec.resolve()
    spec = load_spec(spec_path, plugin)
    if args.offline_check:
        print(canonical_bytes({"spec_sha256": sha256_file(spec_path), "bash_v2_cases": 3, "qualification_runs": 30, "formal_runs_per_combined_case": 20}).decode(), end="")
        return 0
    artifacts = (args.artifacts or workspace / ".agent-token-manager" / f"acp1-4c-{args.phase}-20260819").resolve()
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    common = (args.repository.resolve(), args.codex.resolve(), args.source_home.resolve(), artifacts, args.timeout, args.resume)
    if args.phase == "qualification":
        schedule = [(case, repetition, "native") for case in spec["cases"] for repetition in range(1, 11)]
        runs = [base.prepare_run(spec, case, "qualification", ordinal, arm, *common) for case, ordinal, arm in schedule]
        result, registry = qualification_outputs(spec, spec_path, runs)
        args.qualification_result.resolve().write_bytes(canonical_bytes(result))
        args.registry.resolve().write_bytes(canonical_bytes(registry))
        output = {"phase": "qualification", "run_count": len(runs), "funnel": registry["funnel"], "formal_eligibility_gate": registry["formal_eligibility_gate"], "result_sha256": sha256_file(args.qualification_result.resolve()), "registry_sha256": sha256_file(args.registry.resolve())}
    else:
        registry = load(args.registry.resolve())
        if registry.get("spec_sha256") != sha256_file(spec_path) or not registry.get("formal_eligibility_gate"):
            raise BashRequalificationError("bash_v2_not_eligible")
        qualified_ids = {row["case_id"] for row in registry["cases"] if row["status"] == "qualified"}
        qualified = [case for case in spec["cases"] if case["case_id"] in qualified_ids]
        if args.phase == "pilot":
            representatives = []
            for family in sorted({case["treatment"]["family"] for case in qualified}):
                representatives.append(next(case for case in qualified if case["treatment"]["family"] == family))
            schedule = [(case, 1, arm) for case in representatives for arm in ("control", "treatment")]
            runs = [base.prepare_run(spec, case, "pilot", ordinal, arm, *common) for case, ordinal, arm in schedule]
            result = pilot_output(spec, qualified, runs)
            args.pilot_result.resolve().write_bytes(canonical_bytes(result))
            output = {"phase": "pilot", "run_count": len(runs), "status": result["status"], "result_sha256": sha256_file(args.pilot_result.resolve())}
        else:
            pilot = load(args.pilot_result.resolve())
            if pilot.get("status") != "pass" or pilot.get("included_in_formal_statistics") is not False:
                raise BashRequalificationError("pilot_not_passed")
            cases, qrows = combined_cases(plugin, spec, registry)
            schedule = base.schedule_formal(cases, spec["formal"]["blocks_per_case"])
            runs = [base.prepare_run(spec, case, "formal", ordinal, arm, *common) for case, ordinal, arm in schedule]
            result = formal_output(spec, spec_path, args.registry.resolve(), cases, qrows, runs)
            args.formal_result.resolve().write_bytes(canonical_bytes(result))
            output = {"phase": "formal", "run_count": len(runs), "generalization": result["generalization"], "result_sha256": sha256_file(args.formal_result.resolve())}
    print(canonical_bytes(output).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
