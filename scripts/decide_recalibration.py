#!/usr/bin/env python3
"""Deterministically decide whether ACP needs no, smoke, or full paired recalibration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


STATE_SCHEMA_ID = "acp-calibration-state-v1"
DECISION_SCHEMA_ID = "recalibration-decision-v1"
POLICY_ID = "acp-recalibration-policy-v1"
MODES = {"none": 0, "smoke": 1, "full_paired": 2}
HASH = re.compile(r"^[0-9a-f]{64}$")
TEXT_FIELDS = {"codex_version", "model_identifier", "hook_api_version", "os", "architecture"}
SUPPLEMENTAL_FIELDS = {
    "collector_online_path_digest", "measurement_semantics_digest", "attributor_sha256",
    "renderer_sha256", "event_schema_sha256", "normalized_schema_sha256",
    "ledger_schema_sha256", "fact_report_schema_sha256", "attribution_schema_sha256",
    "expected_attribution_sha256",
}


class RecalibrationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_policy(path: Path) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("policy_id") != POLICY_ID:
        raise RecalibrationError("unsupported_recalibration_policy")
    smoke = policy.get("smoke_fields")
    full = policy.get("full_paired_fields")
    if not isinstance(smoke, list) or not isinstance(full, list):
        raise RecalibrationError("invalid_policy_field_lists")
    if set(smoke) & set(full):
        raise RecalibrationError("policy_fields_overlap")
    if len(smoke) != len(set(smoke)) or len(full) != len(set(full)):
        raise RecalibrationError("policy_fields_not_unique")
    return policy


def validate_state(state: Any, policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict) or state.get("schema_version") != 1 or state.get("schema_id") != STATE_SCHEMA_ID:
        raise RecalibrationError("input_must_be_acp_calibration_state_v1")
    tracked = set(policy["smoke_fields"]) | set(policy["full_paired_fields"])
    expected = tracked | {"schema_version", "schema_id"}
    if set(state) != expected:
        raise RecalibrationError("calibration_state_fields_do_not_match_policy")
    for field in tracked:
        value = state[field]
        if field in TEXT_FIELDS:
            if not isinstance(value, str) or not value:
                raise RecalibrationError(f"invalid_{field}")
        elif value != "unknown" and (not isinstance(value, str) or HASH.fullmatch(value) is None):
            raise RecalibrationError(f"invalid_{field}")
    return state


def state_from_manifest(manifest: Any, supplemental: Any, policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("schema_id") != "experiment-manifest-v1":
        raise RecalibrationError("input_must_be_experiment_manifest_v1")
    if not isinstance(supplemental, dict) or set(supplemental) != SUPPLEMENTAL_FIELDS:
        raise RecalibrationError("supplemental_component_fields_do_not_match")
    environment = manifest.get("environment")
    artifacts = manifest.get("artifacts")
    if not isinstance(environment, dict) or not isinstance(artifacts, dict):
        raise RecalibrationError("manifest_missing_environment_or_artifacts")
    fixture = artifacts.get("fixture")
    if not isinstance(fixture, dict):
        raise RecalibrationError("manifest_missing_fixture_artifact")
    fixture_hash = fixture.get("sha256") if fixture.get("status") == "produced" else "unknown"
    state = {
        "schema_version": 1,
        "schema_id": STATE_SCHEMA_ID,
        "codex_version": environment.get("codex_version", "unknown"),
        "host_binary_sha256": environment.get("host_binary_sha256", "unknown"),
        "model_identifier": environment.get("model_identifier", "unknown"),
        "hook_api_version": environment.get("hook_api_version", "unknown"),
        "os": environment.get("os", "unknown"),
        "architecture": environment.get("architecture", "unknown"),
        "config_digest": environment.get("config_digest", "unknown"),
        "sandbox_digest": environment.get("sandbox_digest", "unknown"),
        "environment_allowlist_digest": environment.get("environment_allowlist_digest", "unknown"),
        "collector_sha256": environment.get("collector_sha256", "unknown"),
        "normalizer_sha256": environment.get("normalizer_sha256", "unknown"),
        "reporter_sha256": environment.get("reporter_sha256", "unknown"),
        "fixture_sha256": fixture_hash or "unknown",
        **supplemental,
    }
    return validate_state(state, policy)


def decide(previous: Any, current: Any, policy: dict[str, Any]) -> dict[str, Any]:
    previous = validate_state(previous, policy)
    current = validate_state(current, policy)
    field_modes = {
        **{field: "smoke" for field in policy["smoke_fields"]},
        **{field: "full_paired" for field in policy["full_paired_fields"]},
    }
    reasons = []
    unchanged = []
    for field in sorted(field_modes):
        if previous[field] == current[field]:
            unchanged.append(field)
        else:
            reasons.append({
                "field": field,
                "reason_code": f"{field}_changed",
                "required_mode": field_modes[field],
            })
    required_mode = "none"
    for reason in reasons:
        if MODES[reason["required_mode"]] > MODES[required_mode]:
            required_mode = reason["required_mode"]
    if required_mode == "full_paired":
        suites = [policy["smoke_suite"]["suite_id"], policy["full_paired_suite"]["suite_id"]]
    elif required_mode == "smoke":
        suites = [policy["smoke_suite"]["suite_id"]]
    else:
        suites = []
    return {
        "schema_version": 1,
        "schema_id": DECISION_SCHEMA_ID,
        "policy_id": policy["policy_id"],
        "previous_state_sha256": fingerprint(previous),
        "current_state_sha256": fingerprint(current),
        "recalibration_required": bool(reasons),
        "required_mode": required_mode,
        "reasons": reasons,
        "required_suites": suites,
        "unchanged_fields": unchanged,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "resources" / "acp0h_recalibration_policy.json",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    compare_parser = subparsers.add_parser("compare", help="compare two calibration states")
    compare_parser.add_argument("previous_state", type=Path)
    compare_parser.add_argument("current_state", type=Path)
    state_parser = subparsers.add_parser("state", help="derive a calibration state from a manifest")
    state_parser.add_argument("manifest", type=Path)
    state_parser.add_argument("supplemental_components", type=Path)
    args = parser.parse_args()
    policy = load_policy(args.policy)
    if args.command == "state":
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        supplemental = json.loads(args.supplemental_components.read_text(encoding="utf-8"))
        result = state_from_manifest(manifest, supplemental, policy)
    else:
        previous = json.loads(args.previous_state.read_text(encoding="utf-8"))
        current = json.loads(args.current_state.read_text(encoding="utf-8"))
        result = decide(previous, current, policy)
    print(canonical_bytes(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
