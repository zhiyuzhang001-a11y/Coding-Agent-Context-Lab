#!/usr/bin/env python3
"""Generate the governed, manifest-bound ACP-1.2 hypothesis catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import acp_hypothesis_catalog
import acp_hypothesis_renderer
import build_experiment_manifest
import validate_benchmark_registry


RUNNER_VERSION = "acp1-2-frozen-catalog-runner-v0.1"
INDEX_SCHEMA_ID = "acp1-2-frozen-catalog-index-v1"
OUTPUT_NAMES = {
    "catalog": "acp1_2_frozen_catalog.json",
    "markdown": "acp1_2_frozen_catalog.md",
    "cli_text": "acp1_2_frozen_catalog.txt",
    "baseline_index": "acp1_2_frozen_catalog_index.json",
    "experiment_manifest": "acp1_2_frozen_experiment_manifest.json",
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
    if not isinstance(spec, dict) or spec.get("schema_id") != "acp1-2-frozen-catalog-spec-v1":
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
    attribution = _load(root / spec["components"]["attribution"]["path"])
    repetition = _load(root / spec["components"]["repeated_evidence"]["path"])
    catalog = acp_hypothesis_catalog.build_catalog(attribution, repetition)
    return (
        catalog,
        acp_hypothesis_catalog.canonical_bytes(catalog),
        acp_hypothesis_renderer.render_markdown(catalog).encode("utf-8"),
        acp_hypothesis_renderer.render_text(catalog).encode("utf-8"),
    )


def _expected(spec: dict[str, Any], catalog: dict[str, Any]) -> bool:
    expected = spec["expected"]
    summary = catalog["candidate_summary"]
    counts = summary["candidate_type_counts"]
    unknowns = catalog["unknowns"]
    policy = catalog["policy"]
    return all((
        catalog["catalog_status"] == expected["catalog_status"],
        summary["candidate_count"] == expected["candidate_count"],
        counts["high_cost_call_candidate"] == expected["high_cost_call_candidate_count"],
        counts["cost_concentration_candidate"] == expected["cost_concentration_candidate_count"],
        counts["repeated_or_overlapping_evidence_candidate"] == expected["repeated_or_overlapping_evidence_candidate_count"],
        summary["unique_target_call_count"] == expected["unique_target_call_count"],
        summary["unique_target_observed_exposure_tokens"] == expected["unique_target_observed_exposure_tokens"],
        summary["unique_target_observed_share"] == expected["unique_target_observed_share"],
        unknowns["necessity_status"] == expected["necessity_status"],
        unknowns["causal_status"] == expected["causal_status"],
        unknowns["candidate_validation_feasibility"] == expected["validation_feasibility"],
        policy["intervention_executed"] == expected["intervention_executed"],
        policy["avoidable_or_savings_estimate_produced"] == expected["avoidable_or_savings_estimate_produced"],
    ))


def run_catalog(spec_path: Path, root: Path, output_dir: Path, runner_path: Path) -> dict[str, Any]:
    spec = _verify_spec(_load(spec_path), root)
    first = _build(spec, root)
    second = _build(spec, root)
    deterministic = first[1:] == second[1:]
    if not deterministic:
        raise BaselineError("determinism_failed")
    if not _expected(spec, first[0]):
        raise BaselineError("expected_catalog_mismatch")
    serialized = b"\n".join(first[1:]).decode("utf-8", errors="replace").lower()
    for forbidden in ("/users/", "wasted_tokens", "avoidable_tokens", "potential_savings", "savings_ratio"):
        if forbidden in serialized:
            raise BaselineError(f"privacy_or_verdict_violation:{forbidden}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "catalog": output_dir / OUTPUT_NAMES["catalog"],
        "markdown": output_dir / OUTPUT_NAMES["markdown"],
        "cli_text": output_dir / OUTPUT_NAMES["cli_text"],
    }
    for name, payload in zip(("catalog", "markdown", "cli_text"), first[1:]):
        output_paths[name].write_bytes(payload)
    artifacts = {name: {"path": item["path"], "sha256": item["sha256"]} for name, item in spec["components"].items()}
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
        "catalog_snapshot": spec["expected"],
        "gates": {
            "g1_source_policy_and_upstream_integrity": True,
            "g2_governance_valid": True,
            "g3_candidate_exposure_and_unknown_integrity": True,
            "g4_determinism_no_verdict_and_no_intervention": True,
            "g5_freeze_chain_integrity": True,
        },
        "policy": first[0]["policy"],
    }
    index_path = output_dir / OUTPUT_NAMES["baseline_index"]
    index_path.write_bytes(canonical_bytes(index))
    output_paths["baseline_index"] = index_path
    upstream_manifest = _load(root / spec["components"]["upstream_experiment_manifest"]["path"])
    descriptor = {
        "phase": "acp-1.2-3-frozen-hypothesis-catalog",
        "started_at": spec["logical_started_at"],
        "completed_at": spec["logical_completed_at"],
        "time_block": spec["time_block"],
        "environment": upstream_manifest["environment"],
        "artifacts": {
            "fixture": {"status": "produced", "path": str(root / spec["components"]["upstream_baseline_index"]["path"]), "visibility": "public"},
            "runner": {"status": "produced", "path": str(runner_path), "visibility": "public"},
            "spec": {"status": "produced", "path": str(spec_path), "visibility": "public"},
            "raw_private_artifact": {"status": "not_produced", "visibility": "private"},
            "normalized_result": {"status": "produced", "path": str(root / spec["components"]["repeated_evidence"]["path"]), "visibility": "public"},
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
    return {"catalog": first[0], "index": index, "manifest": manifest, "paths": output_paths}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_2_frozen_catalog_spec.json")
    parser.add_argument("--output-dir", type=Path, default=root / "resources")
    args = parser.parse_args()
    result = run_catalog(args.spec.resolve(), args.root.resolve(), args.output_dir.resolve(), Path(__file__).resolve())
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
