#!/usr/bin/env python3
"""Generate the governed, manifest-bound ACP-1.3A model-cycle cost baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import acp_cycle_cost
import acp_cycle_cost_renderer
import build_experiment_manifest
import validate_benchmark_registry


RUNNER_VERSION = "acp1-3a-frozen-baseline-runner-v0.1"
INDEX_SCHEMA_ID = "acp1-3a-frozen-baseline-index-v1"
OUTPUT_NAMES = {
    "observations": "acp1_3a_frozen_cycle_observations.json",
    "analysis": "acp1_3a_frozen_cycle_analysis.json",
    "markdown": "acp1_3a_frozen_cycle_analysis.md",
    "cli_text": "acp1_3a_frozen_cycle_analysis.txt",
    "baseline_index": "acp1_3a_frozen_baseline_index.json",
    "experiment_manifest": "acp1_3a_frozen_experiment_manifest.json",
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
    if not isinstance(spec, dict) or spec.get("schema_id") != "acp1-3a-frozen-baseline-spec-v1":
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
    return spec


def _verify_governance(spec: dict[str, Any], observations: dict[str, Any], root: Path) -> None:
    registry = _load(root / spec["components"]["registry"]["path"])
    validation = validate_benchmark_registry.validate_registry(registry, root)
    admitted = {row["case_id"]: row["admission_status"] for row in registry["cases"]}
    allowed = set(spec["governance"]["allowed_admission_statuses"])
    if not validation["valid"] or registry["registry_version"] != spec["governance"]["registry_version"]:
        raise BaselineError("registry_invalid")
    if any(admitted.get(case_id) not in allowed for case_id in observations["source_summary"]["case_ids"]):
        raise BaselineError("source_case_not_governed")


def _build(private_root: Path) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes, bytes, bytes]:
    observations = acp_cycle_cost.extract_private_runs(private_root)
    analysis = acp_cycle_cost.analyze_observations(observations)
    return (
        observations, analysis,
        acp_cycle_cost.canonical_bytes(observations), acp_cycle_cost.canonical_bytes(analysis),
        acp_cycle_cost_renderer.render_markdown(analysis).encode("utf-8"),
        acp_cycle_cost_renderer.render_text(analysis).encode("utf-8"),
    )


def _distribution(arm: dict[str, Any]) -> dict[str, int]:
    return {str(row["cycle_count"]): row["run_count"] for row in arm["cycle_count_groups"]}


def _expected(spec: dict[str, Any], observations: dict[str, Any], analysis: dict[str, Any]) -> bool:
    expected = spec["expected"]
    off, on = analysis["arm_analyses"]
    return all((
        observations["source_summary"]["run_count"] == expected["source_run_count"],
        observations["source_summary"]["exact_linked_run_count"] == expected["exact_linked_run_count"],
        analysis["coverage"]["usage_snapshot_count"] == expected["usage_snapshot_count"],
        observations["source_summary"]["case_count"] == expected["case_count"],
        off["run_count"] == expected["off_run_count"], on["run_count"] == expected["on_run_count"],
        _distribution(off) == expected["off_cycle_count_distribution"],
        _distribution(on) == expected["on_cycle_count_distribution"],
        [row["incremental_usage"]["total_tokens"]["median"] for row in off["cycle_ordinal_costs"]] == expected["off_increment_medians"],
        [row["incremental_usage"]["total_tokens"]["median"] for row in on["cycle_ordinal_costs"]] == expected["on_increment_medians"],
        [row["incremental_total_token_ratio"]["median"] for row in off["within_run_transitions"]] == expected["off_transition_ratio_medians"],
        [row["incremental_total_token_ratio"]["median"] for row in on["within_run_transitions"]] == expected["on_transition_ratio_medians"],
        off["cycle_ordinal_costs"][-1]["sample_status"] == expected["ordinal_four_sample_status"],
        on["cycle_ordinal_costs"][-1]["sample_status"] == expected["ordinal_four_sample_status"],
        analysis["unknowns"]["new_content_tokens"] == expected["new_vs_history_status"],
        analysis["policy"]["descriptive_not_causal"] is True,
        analysis["policy"]["no_intervention"] is (not expected["intervention_executed"]),
    ))


def run_baseline(spec_path: Path, root: Path, private_root: Path, output_dir: Path, runner_path: Path) -> dict[str, Any]:
    spec = _verify_spec(_load(spec_path), root)
    first = _build(private_root)
    second = _build(private_root)
    if first[2:] != second[2:]:
        raise BaselineError("determinism_failed")
    observations, analysis = first[:2]
    private_spec = spec["private_source"]
    if observations["source_summary"]["private_summary_sha256"] != private_spec["summary_sha256"]:
        raise BaselineError("private_summary_hash_mismatch")
    if observations["source_summary"]["private_source_inventory_sha256"] != private_spec["inventory_sha256"]:
        raise BaselineError("private_inventory_hash_mismatch")
    _verify_governance(spec, observations, root)
    if not _expected(spec, observations, analysis):
        raise BaselineError("expected_analysis_mismatch")
    serialized = b"\n".join(first[2:]).decode("utf-8", errors="replace").lower()
    for forbidden in ("/users/", "final_text", "tool_response", "wasted_tokens", "avoidable_tokens", "potential_savings", "savings_ratio"):
        if forbidden in serialized:
            raise BaselineError(f"privacy_or_verdict_violation:{forbidden}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {name: output_dir / OUTPUT_NAMES[name] for name in ("observations", "analysis", "markdown", "cli_text")}
    for name, payload in zip(("observations", "analysis", "markdown", "cli_text"), first[2:]):
        output_paths[name].write_bytes(payload)
    artifacts = {name: {"path": item["path"], "sha256": item["sha256"]} for name, item in spec["components"].items()}
    artifacts["spec"] = {"path": str(spec_path.relative_to(root)), "sha256": sha256_file(spec_path)}
    artifacts["runner"] = {"path": str(runner_path.relative_to(root)), "sha256": sha256_file(runner_path)}
    for name, path in output_paths.items():
        artifacts[name] = {"path": str(path.relative_to(root)), "sha256": sha256_file(path)}
    index = {
        "schema_version": 1, "schema_id": INDEX_SCHEMA_ID, "baseline_id": spec["baseline_id"],
        "status": "complete_under_frozen_experiment_scope", "runner_version": RUNNER_VERSION,
        "upstream_baseline_id": spec["governance"]["upstream_baseline_id"],
        "source_private_artifact": {
            "logical_id": private_spec["logical_id"], "summary_sha256": private_spec["summary_sha256"],
            "inventory_sha256": private_spec["inventory_sha256"], "paths_persisted": False,
        },
        "governance": {"registry_version": spec["governance"]["registry_version"], "case_count": observations["source_summary"]["case_count"], "allowed_admission_statuses": spec["governance"]["allowed_admission_statuses"]},
        "artifacts": dict(sorted(artifacts.items())), "analysis_snapshot": spec["expected"],
        "gates": {
            "g1_cycle_semantics_and_exact_linkage": True,
            "g2_privacy_safe_extraction_and_governance": True,
            "g3_stratified_fact_only_unknown_integrity": True,
            "g4_determinism_and_sample_sufficiency": True,
            "g5_frozen_artifact_chain_integrity": True,
        },
        "policy": analysis["policy"],
    }
    index_path = output_dir / OUTPUT_NAMES["baseline_index"]
    index_path.write_bytes(canonical_bytes(index))
    output_paths["baseline_index"] = index_path
    upstream_manifest = _load(root / spec["components"]["upstream_experiment_manifest"]["path"])
    descriptor = {
        "phase": "acp-1.3a-host-reported-model-cycle-cost-analysis",
        "started_at": spec["logical_started_at"], "completed_at": spec["logical_completed_at"], "time_block": spec["time_block"],
        "environment": upstream_manifest["environment"],
        "artifacts": {
            "fixture": {"status": "produced", "path": str(root / spec["components"]["cycle_fixture"]["path"]), "visibility": "public"},
            "runner": {"status": "produced", "path": str(runner_path), "visibility": "public"},
            "spec": {"status": "produced", "path": str(spec_path), "visibility": "public"},
            "raw_private_artifact": {"status": "produced", "path": str(private_root / "summary.json"), "visibility": "private"},
            "normalized_result": {"status": "produced", "path": str(output_paths["observations"]), "visibility": "public"},
            "coverage_ledger": {"status": "produced", "path": str(output_paths["analysis"]), "visibility": "public"},
            "fact_report": {"status": "produced", "path": str(output_paths["analysis"]), "visibility": "public"},
            "public_compact_result": {"status": "produced", "path": str(index_path), "visibility": "public"},
        },
    }
    manifest = build_experiment_manifest.build_manifest(descriptor)
    if manifest["artifacts"]["public_compact_result"]["sha256"] != sha256_file(index_path):
        raise BaselineError("manifest_index_binding_failed")
    manifest_path = output_dir / OUTPUT_NAMES["experiment_manifest"]
    manifest_path.write_bytes(canonical_bytes(manifest))
    output_paths["experiment_manifest"] = manifest_path
    return {"observations": observations, "analysis": analysis, "index": index, "manifest": manifest, "paths": output_paths}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    workspace = root.parents[1]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--private-root", type=Path, default=workspace / ".agent-token-manager/acp0-4a-repeat5-20260817")
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_3a_frozen_baseline_spec.json")
    parser.add_argument("--output-dir", type=Path, default=root / "resources")
    args = parser.parse_args()
    result = run_baseline(args.spec.resolve(), args.root.resolve(), args.private_root.resolve(), args.output_dir.resolve(), Path(__file__).resolve())
    print(canonical_bytes({
        "baseline_id": result["index"]["baseline_id"], "status": result["index"]["status"],
        "index_sha256": sha256_file(result["paths"]["baseline_index"]),
        "manifest_sha256": sha256_file(result["paths"]["experiment_manifest"]), "gates": result["index"]["gates"],
    }).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
