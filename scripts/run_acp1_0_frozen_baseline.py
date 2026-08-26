#!/usr/bin/env python3
"""Generate and verify the first governed, manifest-bound ACP-1.0 frozen baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import acp_attribution_renderer
import acp_attributor
import acp_normalizer
import acp_reporter
import build_experiment_manifest
import decide_recalibration
import replay_acp0_2
import validate_benchmark_registry


RUNNER_VERSION = "acp1-frozen-baseline-runner-v0.1"
INDEX_SCHEMA_ID = "acp1-0-frozen-baseline-index-v1"
OUTPUT_NAMES = {
    "normalized_result": "acp1_0_frozen_normalized_batch.json",
    "coverage_ledger": "acp1_0_frozen_coverage_ledger.json",
    "fact_report": "acp1_0_frozen_fact_report.json",
    "attribution": "acp1_0_frozen_attribution.json",
    "markdown": "acp1_0_frozen_attribution.md",
    "cli_text": "acp1_0_frozen_attribution.txt",
    "calibration_state": "acp1_0_frozen_calibration_state.json",
    "baseline_index": "acp1_0_frozen_baseline_index.json",
    "experiment_manifest": "acp1_0_frozen_experiment_manifest.json",
}


class BaselineError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_spec(spec: Any, root: Path, runner_path: Path) -> dict[str, Any]:
    if not isinstance(spec, dict) or spec.get("schema_id") != "acp1-0-frozen-baseline-spec-v1":
        raise BaselineError("invalid_frozen_baseline_spec")
    required = {
        "schema_version", "schema_id", "baseline_id", "logical_started_at", "logical_completed_at",
        "time_block", "repository_commit", "environment", "source_observation", "governance",
        "component_hashes", "expected", "privacy",
    }
    if set(spec) != required:
        raise BaselineError("frozen_baseline_spec_fields_drift")
    for name, item in spec["component_hashes"].items():
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise BaselineError(f"component_hash_mismatch:{name}")
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, timeout=10,
    )
    if completed.returncode != 0 or completed.stdout.strip() != spec["repository_commit"]:
        raise BaselineError("repository_commit_mismatch")
    codex_path = shutil.which("codex")
    if not codex_path or sha256_file(Path(codex_path)) != spec["environment"]["host_binary_sha256"]:
        raise BaselineError("host_binary_hash_mismatch")
    version = subprocess.run([codex_path, "--version"], text=True, capture_output=True, timeout=10)
    if version.returncode != 0 or version.stdout.strip() != spec["environment"]["codex_version"]:
        raise BaselineError("codex_version_mismatch")
    if platform.system() != spec["environment"]["os"] or platform.machine() != spec["environment"]["architecture"]:
        raise BaselineError("os_or_architecture_mismatch")
    if not runner_path.is_file():
        raise BaselineError("runner_path_missing")
    return spec


def _pipeline_bytes(spec: dict[str, Any], root: Path) -> dict[str, Any]:
    fixture = _load_json(root / spec["component_hashes"]["fixture"]["path"])
    collector_hash = spec["component_hashes"]["collector"]["sha256"]
    events, calls = replay_acp0_2.paired_inputs(fixture)
    batch = acp_normalizer.normalize_batch(events, calls, collector_sha256=collector_hash)
    ledger = acp_normalizer.build_coverage_ledger(batch, calls, fixture_id=fixture["fixture_id"])
    pipeline = {
        "schema_version": 1,
        "schema_id": acp_normalizer.PIPELINE_SCHEMA_ID,
        "normalizer_version": acp_normalizer.NORMALIZER_VERSION,
        "normalized_batch": batch,
        "coverage_ledger": ledger,
    }
    report = acp_reporter.build_fact_report(pipeline, top_limit=100)
    attribution = acp_attributor.build_attribution(report)
    outputs = {
        "normalized_result": acp_normalizer.canonical_bytes(batch),
        "coverage_ledger": acp_normalizer.canonical_bytes(ledger),
        "fact_report": acp_reporter.render_json(report),
        "attribution": acp_attributor.canonical_bytes(attribution),
        "markdown": acp_attribution_renderer.render_markdown(attribution).encode("utf-8"),
        "cli_text": acp_attribution_renderer.render_text(attribution).encode("utf-8"),
    }
    return {"fixture": fixture, "batch": batch, "ledger": ledger, "report": report, "attribution": attribution, "outputs": outputs}


def _measurement_gate(spec: dict[str, Any], pipeline: dict[str, Any]) -> bool:
    expected = spec["expected"]
    report = pipeline["report"]
    attribution = pipeline["attribution"]
    scope = attribution["scope_and_denominators"]
    concentration = attribution["top_calls_and_concentration"]
    repetition = attribution["objective_repetition_facts"]["exact_payload_duplicate"]
    return all((
        report["report_scope"]["session_count"] == expected["session_count"],
        scope["observed_calls"]["value"] == expected["observed_calls"],
        scope["observed_matched_model_visible_estimated_tokens"]["value"] == expected["observed_matched_visible_estimated_tokens"],
        attribution["coverage_summary"]["status"] == expected["coverage_status"],
        attribution["unknown_volume_and_reasons"]["count"] == expected["unknown_count"],
        attribution["unknown_volume_and_reasons"]["estimated_model_visible_tokens"] == expected["unknown_visible_estimated_tokens"],
        concentration["top1_share"]["value"] == expected["top1_share"],
        concentration["top3_share"]["value"] == expected["top3_share"],
        concentration["topk_share"]["value"] == expected["top10_share"],
        concentration["call_hhi"]["value"] == expected["call_hhi"],
        concentration["tool_family_hhi"]["value"] == expected["tool_family_hhi"],
        repetition["group_observation_visible_estimated_tokens"] == expected["exact_repeat_group_observation_visible_tokens"],
        attribution["cycle_structure_or_unknown"]["status"] == expected["model_cycle_status"],
        scope["session_total_tokens"]["status"] == expected["session_total_status"],
        report["report_policy"]["fact_only"],
        report["report_policy"]["no_new_correlation"],
        attribution["policy"]["fact_only"],
        attribution["policy"]["no_new_correlation"],
        attribution["policy"]["tool_visible_share_is_not_session_share"],
        not attribution["policy"]["online_effect"],
    ))


def _privacy_gate(spec: dict[str, Any], outputs: dict[str, bytes]) -> bool:
    if any(spec["privacy"].values()):
        return False
    combined = b"\n".join(outputs.values()).decode("utf-8", errors="replace")
    forbidden = ("/Users/", "tool_response", "SYNTHETIC_PRIVATE_BODY", "raw_session_id\"")
    return not any(marker in combined for marker in forbidden)


def run_baseline(spec_path: Path, root: Path, output_dir: Path, runner_path: Path) -> dict[str, Any]:
    spec = _verify_spec(_load_json(spec_path), root, runner_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    first = _pipeline_bytes(spec, root)
    second = _pipeline_bytes(spec, root)
    deterministic = all(first["outputs"][name] == second["outputs"][name] for name in first["outputs"])
    if not deterministic:
        raise BaselineError("end_to_end_determinism_failed")
    if not _measurement_gate(spec, first):
        raise BaselineError("measurement_integrity_failed")
    if not _privacy_gate(spec, first["outputs"]):
        raise BaselineError("privacy_integrity_failed")

    registry_path = root / spec["component_hashes"]["registry"]["path"]
    registry = _load_json(registry_path)
    governance_validation = validate_benchmark_registry.validate_registry(registry, root)
    governed_input = next((
        item for item in registry["formal_baseline_inputs"]
        if item["input_id"] == spec["governance"]["formal_input_id"]
        and item["version"] == spec["governance"]["formal_input_version"]
    ), None)
    governance_valid = bool(
        governance_validation["valid"] and governed_input
        and governed_input["admission_status"] == "active"
        and governed_input["fixture_sha256"] == spec["component_hashes"]["fixture"]["sha256"]
        and registry["registry_version"] == spec["governance"]["registry_version"]
    )
    if not governance_valid:
        raise BaselineError("benchmark_governance_failed")

    output_paths = {name: output_dir / OUTPUT_NAMES[name] for name in first["outputs"]}
    for name, payload in first["outputs"].items():
        output_paths[name].write_bytes(payload)

    config_digest = sha256_bytes(canonical_bytes(spec["environment"]["safe_config"]))
    sandbox_digest = sha256_bytes(canonical_bytes(spec["environment"]["sandbox_profile"]))
    allowlist_digest = sha256_bytes(canonical_bytes(sorted(build_experiment_manifest.ENVIRONMENT_NAMES)))
    online_path_digest = sha256_bytes(canonical_bytes({
        "collector_sha256": spec["component_hashes"]["collector"]["sha256"],
        "hooks_manifest_sha256": spec["component_hashes"]["hooks_manifest"]["sha256"],
    }))
    measurement_semantics_digest = sha256_bytes(canonical_bytes({
        "measurement_contract_id": "acp-measurement-v1",
        "normalized_schema_sha256": spec["component_hashes"]["normalized_schema"]["sha256"],
        "ledger_schema_sha256": spec["component_hashes"]["ledger_schema"]["sha256"],
        "fact_report_schema_sha256": spec["component_hashes"]["fact_report_schema"]["sha256"],
        "attribution_schema_sha256": spec["component_hashes"]["attribution_schema"]["sha256"],
        "attribution_semantics_sha256": spec["component_hashes"]["attribution_semantics"]["sha256"],
    }))
    environment = {
        "codex_version": spec["environment"]["codex_version"],
        "host_binary_sha256": spec["environment"]["host_binary_sha256"],
        "model_identifier": spec["environment"]["model_identifier"],
        "reasoning_effort": spec["environment"]["reasoning_effort"],
        "os": spec["environment"]["os"],
        "architecture": spec["environment"]["architecture"],
        "hook_api_version": spec["environment"]["hook_api_version"],
        "config_digest": config_digest,
        "sandbox_digest": sandbox_digest,
        "environment_allowlist_digest": allowlist_digest,
        "collector_sha256": spec["component_hashes"]["collector"]["sha256"],
        "normalizer_sha256": spec["component_hashes"]["normalizer"]["sha256"],
        "reporter_sha256": spec["component_hashes"]["reporter"]["sha256"],
    }
    artifact_descriptor = {
        "fixture": {"status": "produced", "path": str(root / spec["component_hashes"]["fixture"]["path"]), "visibility": "public"},
        "runner": {"status": "produced", "path": str(runner_path), "visibility": "public"},
        "spec": {"status": "produced", "path": str(spec_path), "visibility": "public"},
        "raw_private_artifact": {"status": "not_produced", "visibility": "private"},
        "normalized_result": {"status": "produced", "path": str(output_paths["normalized_result"]), "visibility": "public"},
        "coverage_ledger": {"status": "produced", "path": str(output_paths["coverage_ledger"]), "visibility": "public"},
        "fact_report": {"status": "produced", "path": str(output_paths["fact_report"]), "visibility": "public"},
        "public_compact_result": {"status": "not_produced", "visibility": "public"},
    }
    descriptor = {
        "phase": "acp-1.0-3-frozen-baseline",
        "started_at": spec["logical_started_at"],
        "completed_at": spec["logical_completed_at"],
        "time_block": spec["time_block"],
        "environment": environment,
        "artifacts": artifact_descriptor,
    }
    preliminary_manifest = build_experiment_manifest.build_manifest(descriptor)
    policy_path = root / "resources/acp0h_recalibration_policy.json"
    policy = decide_recalibration.load_policy(policy_path)
    supplemental = {
        "collector_online_path_digest": online_path_digest,
        "measurement_semantics_digest": measurement_semantics_digest,
        "attributor_sha256": spec["component_hashes"]["attributor"]["sha256"],
        "renderer_sha256": spec["component_hashes"]["renderer"]["sha256"],
        "event_schema_sha256": sha256_bytes(canonical_bytes({"schema_id": "acp-event-v1"})),
        "normalized_schema_sha256": spec["component_hashes"]["normalized_schema"]["sha256"],
        "ledger_schema_sha256": spec["component_hashes"]["ledger_schema"]["sha256"],
        "fact_report_schema_sha256": spec["component_hashes"]["fact_report_schema"]["sha256"],
        "attribution_schema_sha256": spec["component_hashes"]["attribution_schema"]["sha256"],
        "expected_attribution_sha256": sha256_bytes(first["outputs"]["attribution"]),
    }
    calibration_state = decide_recalibration.state_from_manifest(preliminary_manifest, supplemental, policy)
    calibration_path = output_dir / OUTPUT_NAMES["calibration_state"]
    calibration_path.write_bytes(decide_recalibration.canonical_bytes(calibration_state))

    artifacts = {
        "fixture": {"path": spec["component_hashes"]["fixture"]["path"], "sha256": spec["component_hashes"]["fixture"]["sha256"]},
        "benchmark_registry": {"path": spec["component_hashes"]["registry"]["path"], "sha256": spec["component_hashes"]["registry"]["sha256"]},
        "spec": {"path": str(spec_path.relative_to(root)), "sha256": sha256_file(spec_path)},
        "runner": {"path": str(runner_path.relative_to(root)), "sha256": sha256_file(runner_path)},
    }
    for name, path in output_paths.items():
        artifacts[name] = {"path": str(path.relative_to(root)), "sha256": sha256_file(path)}
    artifacts["calibration_state"] = {"path": str(calibration_path.relative_to(root)), "sha256": sha256_file(calibration_path)}
    for name in ("collector", "hooks_manifest", "normalizer", "reporter", "attributor", "renderer", "manifest_generator", "recalibration_engine", "registry_validator"):
        artifacts[name] = spec["component_hashes"][name]

    declared_unknowns = [
        "environment.hook_api_version",
        "source_observation.model_identifier",
        "source_observation.reasoning_effort",
        "attribution.session_total_tokens",
        "attribution.model_cycles",
    ]
    index = {
        "schema_version": 1,
        "schema_id": INDEX_SCHEMA_ID,
        "baseline_id": spec["baseline_id"],
        "status": "complete_under_frozen_experiment_scope",
        "runner_version": RUNNER_VERSION,
        "experiment_scope": {
            "kind": "offline_replay",
            "source_fixture_id": spec["source_observation"]["fixture_id"],
            "source_observation_model_identifier": spec["source_observation"]["model_identifier"],
            "derivation_model_invocation_used": False,
            "declared_unknowns": declared_unknowns,
        },
        "governance": {
            "registry_version": registry["registry_version"],
            "registry_sha256": sha256_file(registry_path),
            "formal_input_id": governed_input["input_id"],
            "formal_input_version": governed_input["version"],
            "formal_input_admission_status": governed_input["admission_status"],
            "validation_sha256": sha256_bytes(validate_benchmark_registry.canonical_bytes(governance_validation)),
        },
        "artifacts": dict(sorted(artifacts.items())),
        "measurement_snapshot": {
            "sessions": spec["expected"]["session_count"],
            "observed_calls": spec["expected"]["observed_calls"],
            "observed_matched_visible_estimated_tokens": spec["expected"]["observed_matched_visible_estimated_tokens"],
            "coverage_status": spec["expected"]["coverage_status"],
            "unknown_count": spec["expected"]["unknown_count"],
            "top1_share": spec["expected"]["top1_share"],
            "top3_share": spec["expected"]["top3_share"],
            "top10_share": spec["expected"]["top10_share"],
            "call_hhi": spec["expected"]["call_hhi"],
            "tool_family_hhi": spec["expected"]["tool_family_hhi"],
            "exact_repeat_group_observation_visible_tokens": spec["expected"]["exact_repeat_group_observation_visible_tokens"],
        },
        "gates": {
            "g1_provenance_complete_with_declared_unknowns": True,
            "g2_governance_valid": governance_valid,
            "g3_end_to_end_determinism": deterministic,
            "g4_measurement_integrity": True,
            "g5_freeze_integrity": True,
        },
        "policy": {
            "fact_only": True,
            "no_diagnosis": True,
            "no_online_effect": True,
            "raw_private_artifact_produced": False,
            "manifest_binds_index_transitively": True,
        },
    }
    index_path = output_dir / OUTPUT_NAMES["baseline_index"]
    index_path.write_bytes(canonical_bytes(index))
    descriptor["artifacts"]["public_compact_result"] = {
        "status": "produced", "path": str(index_path), "visibility": "public",
    }
    manifest = build_experiment_manifest.build_manifest(descriptor)
    if manifest["artifacts"]["public_compact_result"]["sha256"] != sha256_file(index_path):
        raise BaselineError("manifest_index_binding_failed")
    for artifact_name in ("fixture", "runner", "spec", "normalized_result", "coverage_ledger", "fact_report", "public_compact_result"):
        if manifest["artifacts"][artifact_name]["status"] != "produced":
            raise BaselineError(f"manifest_artifact_not_produced:{artifact_name}")
    if manifest["artifacts"]["raw_private_artifact"]["status"] != "not_produced":
        raise BaselineError("raw_private_artifact_must_not_be_produced")
    manifest_path = output_dir / OUTPUT_NAMES["experiment_manifest"]
    manifest_path.write_bytes(canonical_bytes(manifest))
    return {"index": index, "manifest": manifest, "paths": {**output_paths, "calibration_state": calibration_path, "baseline_index": index_path, "experiment_manifest": manifest_path}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_0_frozen_baseline_spec.json")
    parser.add_argument("--output-dir", type=Path, default=root / "resources")
    args = parser.parse_args()
    result = run_baseline(args.spec.resolve(), args.root.resolve(), args.output_dir.resolve(), Path(__file__).resolve())
    print(canonical_bytes({
        "baseline_id": result["index"]["baseline_id"],
        "status": result["index"]["status"],
        "manifest_sha256": sha256_file(result["paths"]["experiment_manifest"]),
        "index_sha256": sha256_file(result["paths"]["baseline_index"]),
        "gates": result["index"]["gates"],
    }).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
