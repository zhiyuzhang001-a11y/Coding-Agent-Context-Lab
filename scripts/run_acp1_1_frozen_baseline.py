#!/usr/bin/env python3
"""Generate the governed, manifest-bound ACP-1.1 repeated-evidence baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import acp_repeated_evidence
import acp_repeated_evidence_renderer
import build_experiment_manifest
import validate_benchmark_registry


RUNNER_VERSION = "acp1-1-frozen-baseline-runner-v0.1"
INDEX_SCHEMA_ID = "acp1-1-frozen-baseline-index-v1"
OUTPUT_NAMES = {
    "analysis": "acp1_1_frozen_analysis.json",
    "markdown": "acp1_1_frozen_analysis.md",
    "cli_text": "acp1_1_frozen_analysis.txt",
    "baseline_index": "acp1_1_frozen_baseline_index.json",
    "experiment_manifest": "acp1_1_frozen_experiment_manifest.json",
}


class BaselineError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_spec(spec: Any, root: Path) -> dict[str, Any]:
    if not isinstance(spec, dict) or spec.get("schema_id") != "acp1-1-frozen-baseline-spec-v1":
        raise BaselineError("invalid_spec")
    for name, component in spec.get("components", {}).items():
        path = root / component["path"]
        if not path.is_file() or sha256_file(path) != component["sha256"]:
            raise BaselineError(f"component_hash_mismatch:{name}")
    upstream = _load(root / spec["components"]["upstream_baseline_index"]["path"])
    if upstream.get("baseline_id") != spec["governance"]["upstream_baseline_id"]:
        raise BaselineError("upstream_baseline_identity_mismatch")
    if upstream.get("status") != "complete_under_frozen_experiment_scope" or not all(upstream.get("gates", {}).values()):
        raise BaselineError("upstream_baseline_not_complete")
    upstream_manifest = _load(root / spec["components"]["upstream_experiment_manifest"]["path"])
    environment = upstream_manifest["environment"]
    codex_path = shutil.which("codex")
    if not codex_path or sha256_file(Path(codex_path)) != environment["host_binary_sha256"]:
        raise BaselineError("host_binary_hash_mismatch")
    version = subprocess.run([codex_path, "--version"], text=True, capture_output=True, timeout=10)
    if version.returncode != 0 or version.stdout.strip() != environment["codex_version"]:
        raise BaselineError("codex_version_mismatch")
    if platform.system() != environment["os"] or platform.machine() != environment["architecture"]:
        raise BaselineError("os_or_architecture_mismatch")
    registry = _load(root / spec["components"]["registry"]["path"])
    validation = validate_benchmark_registry.validate_registry(registry, root)
    formal = next((item for item in registry["formal_baseline_inputs"] if (
        item["input_id"] == spec["governance"]["formal_input_id"]
        and item["version"] == spec["governance"]["formal_input_version"]
    )), None)
    if not validation["valid"] or not formal or formal["admission_status"] != "active":
        raise BaselineError("governance_invalid")
    return spec


def _build(spec: dict[str, Any], root: Path) -> tuple[dict[str, Any], bytes, bytes, bytes]:
    batch = _load(root / spec["components"]["normalized_batch"]["path"])
    ledger = _load(root / spec["components"]["coverage_ledger"]["path"])
    attribution = _load(root / spec["components"]["attribution"]["path"])
    analysis = acp_repeated_evidence.build_analysis(batch, ledger, attribution)
    return (
        analysis,
        acp_repeated_evidence.canonical_bytes(analysis),
        acp_repeated_evidence_renderer.render_markdown(analysis).encode("utf-8"),
        acp_repeated_evidence_renderer.render_text(analysis).encode("utf-8"),
    )


def _expected(spec: dict[str, Any], analysis: dict[str, Any]) -> bool:
    expected = spec["expected"]
    coverage = analysis["denominator_and_coverage"]
    volume = analysis["observation_volume"]
    scope = analysis["source_and_scope"]
    return all((
        coverage["eligible_observed_call_count"] == expected["eligible_observed_call_count"],
        coverage["eligible_observed_visible_estimated_tokens"] == expected["eligible_observed_visible_estimated_tokens"],
        coverage["relation_order_coverage_status"] == expected["relation_order_coverage_status"],
        coverage["path_identity_coverage_status"] == expected["path_identity_coverage_status"],
        coverage["explicit_range_coverage_status"] == expected["explicit_range_coverage_status"],
        coverage["cycle_coverage_status"] == expected["cycle_coverage_status"],
        volume["relation_count"] == expected["relation_count"],
        volume["unique_repeated_observation_count"] == expected["unique_repeated_observation_count"],
        volume["unique_repeated_observation_tokens"] == expected["unique_repeated_observation_tokens"],
        volume["repeated_observation_share"] == expected["repeated_observation_share"],
        scope["cross_session_relations_created"] == expected["cross_session_relations_created"],
        analysis["unknowns"]["content_stability_state"] == expected["content_stability_state"],
    ))


def run_baseline(spec_path: Path, root: Path, output_dir: Path, runner_path: Path) -> dict[str, Any]:
    spec = _verify_spec(_load(spec_path), root)
    first = _build(spec, root)
    second = _build(spec, root)
    deterministic = first[1:] == second[1:]
    if not deterministic:
        raise BaselineError("determinism_failed")
    if not _expected(spec, first[0]):
        raise BaselineError("expected_baseline_mismatch")
    serialized = b"\n".join(first[1:]).decode("utf-8", errors="replace").lower()
    for forbidden in ("/users/", "wasted_tokens", "avoidable_tokens", "potential_savings", "optimization_opportunity"):
        if forbidden in serialized:
            raise BaselineError(f"privacy_or_diagnosis_violation:{forbidden}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "analysis": output_dir / OUTPUT_NAMES["analysis"],
        "markdown": output_dir / OUTPUT_NAMES["markdown"],
        "cli_text": output_dir / OUTPUT_NAMES["cli_text"],
    }
    for name, payload in zip(("analysis", "markdown", "cli_text"), first[1:]):
        output_paths[name].write_bytes(payload)

    artifacts = {
        name: {"path": item["path"], "sha256": item["sha256"]}
        for name, item in spec["components"].items()
    }
    artifacts["spec"] = {"path": str(spec_path.relative_to(root)), "sha256": sha256_file(spec_path)}
    artifacts["runner"] = {"path": str(runner_path.relative_to(root)), "sha256": sha256_file(runner_path)}
    for name, path in output_paths.items():
        artifacts[name] = {"path": str(path.relative_to(root)), "sha256": sha256_file(path)}
    index = {
        "schema_version": 1,
        "schema_id": INDEX_SCHEMA_ID,
        "baseline_id": spec["baseline_id"],
        "status": "complete_under_frozen_experiment_scope",
        "runner_version": RUNNER_VERSION,
        "upstream_baseline_id": spec["governance"]["upstream_baseline_id"],
        "governance": {
            "registry_version": spec["governance"]["registry_version"],
            "formal_input_id": spec["governance"]["formal_input_id"],
            "formal_input_version": spec["governance"]["formal_input_version"],
            "admission_status": "active",
        },
        "artifacts": dict(sorted(artifacts.items())),
        "measurement_snapshot": {
            **spec["expected"],
            "acp1_0_cross_session_exact_repeat_volume": spec["interpretation"]["acp1_0_cross_session_exact_repeat_volume_remains_unchanged"],
        },
        "gates": {
            "g1_source_and_upstream_integrity": True,
            "g2_governance_valid": True,
            "g3_relation_and_unique_volume_integrity": True,
            "g4_determinism_unknown_and_no_diagnosis": True,
            "g5_freeze_chain_integrity": True,
        },
        "policy": first[0]["policy"],
    }
    index_path = output_dir / OUTPUT_NAMES["baseline_index"]
    index_path.write_bytes(canonical_bytes(index))
    output_paths["baseline_index"] = index_path

    upstream_manifest = _load(root / spec["components"]["upstream_experiment_manifest"]["path"])
    descriptor = {
        "phase": "acp-1.1-3-frozen-baseline",
        "started_at": spec["logical_started_at"],
        "completed_at": spec["logical_completed_at"],
        "time_block": spec["time_block"],
        "environment": upstream_manifest["environment"],
        "artifacts": {
            "fixture": {"status": "produced", "path": str(root / spec["components"]["upstream_baseline_index"]["path"]), "visibility": "public"},
            "runner": {"status": "produced", "path": str(runner_path), "visibility": "public"},
            "spec": {"status": "produced", "path": str(spec_path), "visibility": "public"},
            "raw_private_artifact": {"status": "not_produced", "visibility": "private"},
            "normalized_result": {"status": "produced", "path": str(root / spec["components"]["normalized_batch"]["path"]), "visibility": "public"},
            "coverage_ledger": {"status": "produced", "path": str(root / spec["components"]["coverage_ledger"]["path"]), "visibility": "public"},
            "fact_report": {"status": "produced", "path": str(root / spec["components"]["attribution"]["path"]), "visibility": "public"},
            "public_compact_result": {"status": "produced", "path": str(index_path), "visibility": "public"},
        },
    }
    manifest = build_experiment_manifest.build_manifest(descriptor)
    if manifest["artifacts"]["public_compact_result"]["sha256"] != sha256_file(index_path):
        raise BaselineError("manifest_index_binding_failed")
    manifest_path = output_dir / OUTPUT_NAMES["experiment_manifest"]
    manifest_path.write_bytes(canonical_bytes(manifest))
    output_paths["experiment_manifest"] = manifest_path
    return {"analysis": first[0], "index": index, "manifest": manifest, "paths": output_paths}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_1_frozen_baseline_spec.json")
    parser.add_argument("--output-dir", type=Path, default=root / "resources")
    args = parser.parse_args()
    result = run_baseline(args.spec.resolve(), args.root.resolve(), args.output_dir.resolve(), Path(__file__).resolve())
    print(canonical_bytes({
        "baseline_id": result["index"]["baseline_id"],
        "status": result["index"]["status"],
        "index_sha256": sha256_file(result["paths"]["baseline_index"]),
        "manifest_sha256": sha256_file(result["paths"]["experiment_manifest"]),
        "gates": result["index"]["gates"],
    }).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
