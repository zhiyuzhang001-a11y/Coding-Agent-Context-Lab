#!/usr/bin/env python3
"""Validate ACP benchmark governance, source identity, qualification, and admission rules."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_ID = "acp-benchmark-registry-v1"
VALIDATION_SCHEMA_ID = "acp-benchmark-registry-validation-v1"
ROLES = {"stable_gate", "stochastic_diagnostic", "coverage_probe", "failure_injection"}
ADMISSIONS = {"active", "diagnostic_only", "retired_but_preserved", "pending"}
GATES = {
    "absolute_correctness", "distribution_parity", "cost_neutrality", "path_neutrality",
    "host_transparency", "collector_coverage",
}


class RegistryError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_registry(registry: Any, root: Path) -> dict[str, Any]:
    if not isinstance(registry, dict) or registry.get("schema_id") != SCHEMA_ID:
        raise RegistryError("input_must_be_acp_benchmark_registry_v1")
    cases = registry.get("cases")
    formal_inputs = registry.get("formal_baseline_inputs")
    policy = registry.get("governance_policy")
    source = registry.get("source_fixture")
    if not isinstance(cases, list) or not isinstance(formal_inputs, list) or not isinstance(policy, dict) or not isinstance(source, dict):
        raise RegistryError("registry_missing_cases_policy_or_source")

    source_path = root / source.get("path", "")
    if not source_path.is_file() or sha256_bytes(source_path.read_bytes()) != source.get("sha256"):
        raise RegistryError("source_fixture_hash_mismatch")
    fixture = _read_json(source_path)
    fixture_cases = fixture.get("cases")
    if fixture.get("fixture_id") != source.get("fixture_id") or not isinstance(fixture_cases, list):
        raise RegistryError("source_fixture_identity_mismatch")
    if len(cases) != len(fixture_cases):
        raise RegistryError("migration_must_preserve_every_source_case")

    identities: set[tuple[str, int]] = set()
    registry_by_identity: dict[str, dict[str, Any]] = {}
    historical_cases = []
    for case in cases:
        if not isinstance(case, dict):
            raise RegistryError("case_not_object")
        case_id = case.get("case_id")
        version = case.get("version")
        identity = (case_id, version)
        if not isinstance(case_id, str) or not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise RegistryError("invalid_case_identity")
        if identity in identities:
            raise RegistryError("duplicate_case_identity")
        identities.add(identity)
        registry_by_identity[f"{case_id}@{version}"] = case

        role = case.get("benchmark_role")
        admission = case.get("admission_status")
        gates = case.get("allowed_gate_usage")
        calibration = case.get("native_calibration")
        truth = case.get("ground_truth")
        if role not in ROLES or admission not in ADMISSIONS or not isinstance(gates, list) or not set(gates) <= GATES:
            raise RegistryError(f"invalid_role_admission_or_gates:{case_id}")
        if len(gates) != len(set(gates)) or not isinstance(calibration, dict) or not isinstance(truth, dict):
            raise RegistryError(f"invalid_case_contract:{case_id}")
        repetitions = calibration.get("repetitions")
        correct = calibration.get("correct")
        if not isinstance(repetitions, int) or not isinstance(correct, int) or not 0 <= correct <= repetitions:
            raise RegistryError(f"invalid_native_counts:{case_id}")

        pointer = truth.get("source_pointer", "")
        prefix = "resources/acp0_4_cases.json#/cases/"
        if not isinstance(pointer, str) or not pointer.startswith(prefix):
            raise RegistryError(f"invalid_source_pointer:{case_id}")
        try:
            source_index = int(pointer[len(prefix):])
            source_case = fixture_cases[source_index]
        except (ValueError, IndexError):
            raise RegistryError(f"invalid_source_pointer:{case_id}") from None
        if source_case.get("id") != case_id:
            raise RegistryError(f"source_case_identity_mismatch:{case_id}")
        if truth.get("question_sha256") != sha256_text(source_case["question"]):
            raise RegistryError(f"question_hash_mismatch:{case_id}")
        if truth.get("expected_answer_sha256") != sha256_text(source_case["expected"]):
            raise RegistryError(f"expected_answer_hash_mismatch:{case_id}")

        evidence_path = calibration.get("evidence_path")
        evidence_hash = calibration.get("evidence_sha256")
        if evidence_path is not None:
            evidence = root / evidence_path
            if not evidence.is_file() or sha256_bytes(evidence.read_bytes()) != evidence_hash:
                raise RegistryError(f"native_evidence_hash_mismatch:{case_id}")
        elif evidence_hash is not None:
            raise RegistryError(f"native_evidence_path_missing:{case_id}")

        basis = calibration.get("basis")
        status = calibration.get("status")
        if basis == "historical_migration":
            migration = policy["migration_exception"]
            if registry.get("registry_version") != migration["applies_only_to_registry_version"]:
                raise RegistryError(f"historical_exception_wrong_registry:{case_id}")
            if repetitions < migration["minimum_repetitions"] or correct != repetitions:
                raise RegistryError(f"historical_migration_not_perfect:{case_id}")
            if status != "qualified_stable" or role == "stochastic_diagnostic":
                raise RegistryError(f"historical_migration_classification_invalid:{case_id}")
            historical_cases.append(case_id)
        elif basis == "prospective_native_calibration":
            if repetitions < policy["new_stable_minimum_repetitions"]:
                raise RegistryError(f"prospective_calibration_too_small:{case_id}")
            if role == "stochastic_diagnostic":
                if status != "qualified_stochastic":
                    raise RegistryError(f"stochastic_qualification_invalid:{case_id}")
            elif status != "qualified_stable" or correct < policy["new_stable_minimum_correct"]:
                raise RegistryError(f"stable_qualification_invalid:{case_id}")
        elif basis == "none":
            if status != "not_qualified" or repetitions or correct:
                raise RegistryError(f"unqualified_case_has_calibration_claim:{case_id}")
        else:
            raise RegistryError(f"invalid_calibration_basis:{case_id}")

        if truth.get("audit_status") == "pending" and admission != "pending":
            raise RegistryError(f"pending_ground_truth_admitted:{case_id}")
        if status == "not_qualified" and admission not in {"pending", "retired_but_preserved"}:
            raise RegistryError(f"unqualified_case_admitted:{case_id}")
        if role == "stochastic_diagnostic":
            forbidden = {"absolute_correctness", "cost_neutrality", "path_neutrality"}
            if admission != "diagnostic_only" or set(gates) & forbidden or "distribution_parity" not in gates:
                raise RegistryError(f"stochastic_case_gate_violation:{case_id}")
        elif admission == "diagnostic_only":
            raise RegistryError(f"nonstochastic_case_marked_diagnostic:{case_id}")
        if role == "stable_gate" and (admission != "active" or status != "qualified_stable" or "absolute_correctness" not in gates):
            raise RegistryError(f"stable_gate_not_qualified_active:{case_id}")
        if admission == "retired_but_preserved" and not case.get("retired_reason"):
            raise RegistryError(f"retired_case_missing_reason:{case_id}")
        if admission != "retired_but_preserved" and case.get("retired_reason") is not None:
            raise RegistryError(f"active_case_has_retired_reason:{case_id}")

    fixture_ids = {case["id"] for case in fixture_cases}
    if {case["case_id"] for case in cases} != fixture_ids:
        raise RegistryError("registry_case_set_drift")
    for identity, case in registry_by_identity.items():
        supersedes = case.get("supersedes")
        if supersedes is not None:
            if supersedes not in registry_by_identity or supersedes == identity:
                raise RegistryError(f"invalid_supersedes:{identity}")
            prior = registry_by_identity[supersedes]
            if prior["case_id"] != case["case_id"] or prior["version"] >= case["version"]:
                raise RegistryError(f"supersedes_must_reference_older_same_case:{identity}")

    formal_identities: set[tuple[str, int]] = set()
    active_formal_inputs = 0
    for item in formal_inputs:
        if not isinstance(item, dict):
            raise RegistryError("formal_baseline_input_not_object")
        identity = (item.get("input_id"), item.get("version"))
        if identity in formal_identities:
            raise RegistryError("duplicate_formal_baseline_input_identity")
        formal_identities.add(identity)
        fixture_path = root / item.get("fixture_path", "")
        if not fixture_path.is_file() or sha256_bytes(fixture_path.read_bytes()) != item.get("fixture_sha256"):
            raise RegistryError(f"formal_baseline_fixture_hash_mismatch:{identity[0]}")
        admission = item.get("admission_status")
        qualification = item.get("qualification_status")
        if admission == "active":
            active_formal_inputs += 1
            if qualification != "qualified_measurement_fixture" or item.get("benchmark_role") != "coverage_probe":
                raise RegistryError(f"formal_baseline_input_not_qualified:{identity[0]}")
        elif admission == "pending" and qualification != "pending":
            raise RegistryError(f"pending_formal_input_has_qualification:{identity[0]}")
        elif admission == "retired_but_preserved" and not item.get("retired_reason"):
            raise RegistryError(f"retired_formal_input_missing_reason:{identity[0]}")
        if admission != "retired_but_preserved" and item.get("retired_reason") is not None:
            raise RegistryError(f"formal_input_has_unexpected_retired_reason:{identity[0]}")

    variance_path = root / "resources/acp0_4a_results.json"
    variance = _read_json(variance_path)
    failed = variance["correctness_evidence"]
    off_failed = sum(run["run_id"].endswith("-off") for run in failed["failed_runs"])
    migrated_correct = sum(case["native_calibration"]["correct"] for case in cases if case["native_calibration"]["basis"] == "historical_migration")
    if failed["failed_case"] != "single_file_range_count" or off_failed != 2 or migrated_correct != 55:
        raise RegistryError("historical_migration_evidence_drift")
    if variance["correctness_evidence"]["off_correct"] != migrated_correct + 3:
        raise RegistryError("historical_native_aggregate_drift")

    roles = Counter(case["benchmark_role"] for case in cases)
    admissions = Counter(case["admission_status"] for case in cases)
    return {
        "schema_version": 1,
        "schema_id": VALIDATION_SCHEMA_ID,
        "registry_version": registry["registry_version"],
        "registry_sha256": sha256_bytes(canonical_bytes(registry)),
        "valid": True,
        "case_count": len(cases),
        "role_counts": dict(sorted(roles.items())),
        "admission_counts": dict(sorted(admissions.items())),
        "historical_migration_case_count": len(historical_cases),
        "prospective_native_case_count": sum(case["native_calibration"]["basis"] == "prospective_native_calibration" for case in cases),
        "formal_baseline_input_count": len(formal_inputs),
        "active_formal_baseline_input_count": active_formal_inputs,
        "source_fixture_sha256": source["sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    registry = _read_json(args.registry)
    print(canonical_bytes(validate_registry(registry, args.root.resolve())).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
