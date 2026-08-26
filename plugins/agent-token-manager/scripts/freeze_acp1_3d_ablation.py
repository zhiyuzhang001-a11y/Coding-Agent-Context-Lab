#!/usr/bin/env python3
"""Validate and freeze the ACP-1.3D controlled-ablation experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import build_experiment_manifest


RUNNER_VERSION = "acp1-3d-freeze-runner-v0.1"
INDEX_NAME = "acp1_3d_frozen_ablation_index.json"
MANIFEST_NAME = "acp1_3d_frozen_experiment_manifest.json"
INVENTORY_NAME = "private_inventory.json"


class FreezeError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FreezeError(f"object_required:{path.name}")
    return value


def phase_inventory(phase: str, private_root: Path) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for path in sorted(private_root.glob("*/result.json")):
        result = load(path)
        rows.append({"run_id": str(result.get("run_id")), "sha256": sha256_file(path)})
    return {"phase": phase, "run_count": len(rows), "results": rows}


def private_inventory(pilot_root: Path, formal_root: Path) -> dict[str, Any]:
    phases = [phase_inventory("pilot", pilot_root), phase_inventory("formal", formal_root)]
    return {
        "schema_version": 1,
        "logical_id": "acp1-3d-controlled-ablation-20260818-live",
        "run_count": sum(row["run_count"] for row in phases),
        "phases": phases,
    }


def verify(
    spec: dict[str, Any], result: dict[str, Any], pilot: dict[str, Any], registry: dict[str, Any],
    root: Path, pilot_root: Path, formal_root: Path,
) -> dict[str, Any]:
    if spec.get("schema_id") != "acp1-3d-frozen-ablation-spec-v1":
        raise FreezeError("invalid_spec")
    for name, component in spec["components"].items():
        path = root / component["path"]
        if not path.is_file() or sha256_file(path) != component["sha256"]:
            raise FreezeError(f"component_hash_mismatch:{name}")

    inventory = private_inventory(pilot_root, formal_root)
    inventory_sha256 = hashlib.sha256(canonical_bytes(inventory)).hexdigest()
    if inventory["run_count"] != spec["private_source"]["run_count"]:
        raise FreezeError("private_run_count_mismatch")
    if inventory_sha256 != spec["private_source"]["inventory_sha256"]:
        raise FreezeError("private_inventory_hash_mismatch")
    if [row["run_count"] for row in inventory["phases"]] != [4, 80]:
        raise FreezeError("phase_run_count_mismatch")

    if pilot.get("run_count") != 4 or pilot.get("status") != "pass":
        raise FreezeError("pilot_mismatch")
    if result.get("run_count") != 80 or result.get("summary") != spec["expected"]["summary"]:
        raise FreezeError("formal_summary_mismatch")
    if result.get("policy") != spec["expected"]["policy"]:
        raise FreezeError("formal_policy_mismatch")

    qualified = [row["case_id"] for row in registry["cases"] if row["status"] == "qualified"]
    if qualified != spec["expected"]["eligible_case_ids"]:
        raise FreezeError("eligible_case_set_mismatch")
    actual_cases = {row["case_id"]: row for row in result["cases"]}
    if list(actual_cases) != qualified:
        raise FreezeError("formal_case_order_or_set_mismatch")
    for expected in spec["expected"]["cases"]:
        actual = actual_cases[expected["case_id"]]
        snapshot = {
            "case_id": actual["case_id"],
            "verdict": actual["verdict"],
            "control_correct": actual["counts"]["control_correct"],
            "treatment_correct": actual["counts"]["treatment_correct"],
            "treatment_only_failures": actual["counts"]["treatment_only_failures"],
            "median_evidence_reduction": actual["activation"]["evidence_reduction_ratio"]["median"],
            "session_cost_effect": actual["session_cost"]["effect"],
            "pooled_treatment_control_ratio": actual["session_cost"]["pooled_treatment_control_ratio"],
        }
        if snapshot != expected:
            raise FreezeError(f"case_snapshot_mismatch:{actual['case_id']}")
        if set(actual["gates"].values()) != {True}:
            raise FreezeError(f"gate_failure:{actual['case_id']}")

    serialized = (canonical_bytes(result) + canonical_bytes(pilot)).decode("utf-8").lower()
    for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "potential_savings", "production_replacement"):
        if prohibited in serialized:
            raise FreezeError(f"privacy_or_claim_violation:{prohibited}")
    policy = result["policy"]
    if policy["global_savings_claim"] or policy["production_slicing_or_replacement"] or policy["collector_or_hook_mutation"]:
        raise FreezeError("policy_boundary_violation")

    environment = load(root / spec["components"]["upstream_manifest"]["path"])["environment"]
    codex_path = shutil.which("codex")
    if not codex_path or sha256_file(Path(codex_path)) != environment["host_binary_sha256"]:
        raise FreezeError("host_binary_hash_mismatch")
    version = subprocess.run([codex_path, "--version"], text=True, capture_output=True, timeout=10)
    if version.returncode or version.stdout.strip() != environment["codex_version"]:
        raise FreezeError("codex_version_mismatch")
    if platform.system() != environment["os"] or platform.machine() != environment["architecture"]:
        raise FreezeError("os_or_architecture_mismatch")
    return inventory


def freeze(
    spec_path: Path, root: Path, pilot_root: Path, formal_root: Path, output_dir: Path, runner_path: Path,
) -> dict[str, Any]:
    spec = load(spec_path)
    result = load(root / spec["components"]["formal_result"]["path"])
    pilot = load(root / spec["components"]["pilot_result"]["path"])
    registry = load(root / spec["components"]["candidate_registry"]["path"])
    inventory = verify(spec, result, pilot, registry, root, pilot_root, formal_root)
    inventory_path = formal_root / INVENTORY_NAME
    inventory_path.write_bytes(canonical_bytes(inventory))

    artifacts = {name: dict(value) for name, value in spec["components"].items()}
    artifacts["freeze_spec"] = {"path": str(spec_path.relative_to(root)), "sha256": sha256_file(spec_path)}
    artifacts["freeze_runner"] = {"path": str(runner_path.relative_to(root)), "sha256": sha256_file(runner_path)}
    index = {
        "schema_version": 1,
        "schema_id": "acp1-3d-frozen-ablation-index-v1",
        "baseline_id": spec["baseline_id"],
        "status": "complete_under_frozen_experiment_scope",
        "runner_version": RUNNER_VERSION,
        "source_private_artifact": {
            "logical_id": inventory["logical_id"],
            "run_count": inventory["run_count"],
            "pilot_run_count": inventory["phases"][0]["run_count"],
            "formal_run_count": inventory["phases"][1]["run_count"],
            "inventory_sha256": hashlib.sha256(canonical_bytes(inventory)).hexdigest(),
            "paths_persisted": False,
        },
        "artifacts": dict(sorted(artifacts.items())),
        "formal_summary": result["summary"],
        "case_verdicts": [
            {
                "case_id": row["case_id"],
                "verdict": row["verdict"],
                "median_evidence_reduction": row["activation"]["evidence_reduction_ratio"]["median"],
                "session_cost_effect": row["session_cost"]["effect"],
                "pooled_treatment_control_ratio": row["session_cost"]["pooled_treatment_control_ratio"],
            }
            for row in result["cases"]
        ],
        "gates": {row["case_id"]: row["gates"] for row in result["cases"]},
        "policy": {
            "experimental_harness_only": True,
            "production_slicing_or_replacement": False,
            "global_savings_claim": False,
            "historical_candidates_validated": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / INDEX_NAME
    index_path.write_bytes(canonical_bytes(index))

    upstream_environment = load(root / spec["components"]["upstream_manifest"]["path"])["environment"]
    environment = dict(upstream_environment)
    environment["model_identifier"] = spec["environment"]["model_identifier"]
    environment["reasoning_effort"] = spec["environment"]["reasoning_effort"]
    descriptor = {
        "phase": "acp-1.3d-candidate-specific-controlled-ablation",
        "started_at": spec["logical_started_at"],
        "completed_at": spec["logical_completed_at"],
        "time_block": spec["time_block"],
        "environment": environment,
        "artifacts": {
            "fixture": {"status": "produced", "path": str(root / spec["components"]["experiment_spec"]["path"]), "visibility": "public"},
            "runner": {"status": "produced", "path": str(root / spec["components"]["ablation_runner"]["path"]), "visibility": "public"},
            "spec": {"status": "produced", "path": str(spec_path), "visibility": "public"},
            "raw_private_artifact": {"status": "produced", "path": str(inventory_path), "visibility": "private"},
            "normalized_result": {"status": "produced", "path": str(root / spec["components"]["formal_result"]["path"]), "visibility": "public"},
            "coverage_ledger": {"status": "produced", "path": str(root / spec["components"]["formal_result"]["path"]), "visibility": "public"},
            "fact_report": {"status": "produced", "path": str(root / spec["components"]["formal_result"]["path"]), "visibility": "public"},
            "public_compact_result": {"status": "produced", "path": str(index_path), "visibility": "public"},
        },
    }
    manifest = build_experiment_manifest.build_manifest(descriptor)
    manifest_path = output_dir / MANIFEST_NAME
    manifest_path.write_bytes(canonical_bytes(manifest))
    return {"index": index, "manifest": manifest, "index_path": index_path, "manifest_path": manifest_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    workspace = root.parents[1]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--pilot-root", type=Path, default=workspace / ".agent-token-manager/acp1-3d-pilot-20260818")
    parser.add_argument("--formal-root", type=Path, default=workspace / ".agent-token-manager/acp1-3d-formal-20260818")
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_3d_frozen_ablation_spec.json")
    parser.add_argument("--output-dir", type=Path, default=root / "resources")
    args = parser.parse_args()
    frozen = freeze(
        args.spec.resolve(), args.root.resolve(), args.pilot_root.resolve(), args.formal_root.resolve(),
        args.output_dir.resolve(), Path(__file__).resolve(),
    )
    print(canonical_bytes({
        "baseline_id": frozen["index"]["baseline_id"],
        "status": frozen["index"]["status"],
        "index_sha256": sha256_file(frozen["index_path"]),
        "manifest_sha256": sha256_file(frozen["manifest_path"]),
        "formal_summary": frozen["index"]["formal_summary"],
    }).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
