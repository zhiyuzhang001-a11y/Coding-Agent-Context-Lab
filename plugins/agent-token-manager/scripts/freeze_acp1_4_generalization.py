#!/usr/bin/env python3
"""Freeze the stopped ACP-1.4 generalization experiment and attrition chain."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import build_experiment_manifest


INDEX_NAME = "acp1_4_frozen_generalization_index.json"
MANIFEST_NAME = "acp1_4_frozen_experiment_manifest.json"
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


def phase_inventory(phase: str, root: Path) -> dict[str, Any]:
    rows = []
    for path in sorted(root.glob("*/result.json")):
        result = load(path)
        rows.append({"run_id": str(result.get("run_id")), "sha256": sha256_file(path)})
    return {"phase": phase, "run_count": len(rows), "results": rows}


def private_inventory(qualification_root: Path, pilot_root: Path) -> dict[str, Any]:
    phases = [phase_inventory("qualification", qualification_root), phase_inventory("pilot", pilot_root)]
    return {
        "schema_version": 1,
        "logical_id": "acp1-4-natural-generalization-20260818-live",
        "run_count": sum(row["run_count"] for row in phases),
        "phases": phases,
    }


def freeze(spec_path: Path, root: Path, qualification_root: Path, pilot_root: Path, output_dir: Path, runner_path: Path) -> dict[str, Any]:
    spec = load(spec_path)
    if spec.get("schema_id") != "acp1-4-frozen-generalization-spec-v1":
        raise FreezeError("invalid_spec")
    for name, component in spec["components"].items():
        path = root / component["path"]
        if not path.is_file() or sha256_file(path) != component["sha256"]:
            raise FreezeError(f"component_hash_mismatch:{name}")
    qualification = load(root / spec["components"]["qualification_result"]["path"])
    registry = load(root / spec["components"]["candidate_registry"]["path"])
    pilot = load(root / spec["components"]["family_pilot"]["path"])
    if qualification.get("run_count") != 80 or registry.get("funnel") != spec["expected"]["funnel"]:
        raise FreezeError("qualification_or_funnel_mismatch")
    if registry.get("family_coverage") != spec["expected"]["family_coverage"] or registry.get("formal_coverage_gate") is not False:
        raise FreezeError("coverage_mismatch")
    if pilot.get("run_count") != 4 or pilot.get("status") != "inconclusive_plumbing":
        raise FreezeError("pilot_mismatch")
    if (root / "resources/acp1_4b_results.json").exists():
        raise FreezeError("formal_result_must_not_exist")

    inventory = private_inventory(qualification_root, pilot_root)
    digest = hashlib.sha256(canonical_bytes(inventory)).hexdigest()
    if inventory["run_count"] != 84 or [row["run_count"] for row in inventory["phases"]] != [80, 4]:
        raise FreezeError("private_run_count_mismatch")
    if digest != spec["private_source"]["inventory_sha256"]:
        raise FreezeError("private_inventory_hash_mismatch")
    serialized = (canonical_bytes(qualification) + canonical_bytes(registry) + canonical_bytes(pilot)).decode("utf-8").lower()
    for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "potential_savings"):
        if prohibited in serialized:
            raise FreezeError(f"privacy_or_claim_violation:{prohibited}")

    inventory_path = qualification_root / INVENTORY_NAME
    inventory_path.write_bytes(canonical_bytes(inventory))
    artifacts = {name: dict(value) for name, value in spec["components"].items()}
    artifacts["freeze_spec"] = {"path": str(spec_path.relative_to(root)), "sha256": sha256_file(spec_path)}
    artifacts["freeze_runner"] = {"path": str(runner_path.relative_to(root)), "sha256": sha256_file(runner_path)}
    index = {
        "schema_version": 1,
        "schema_id": "acp1-4-frozen-generalization-index-v1",
        "experiment_id": spec["experiment_id"],
        "status": "stopped_insufficient_coverage_under_frozen_scope",
        "generalization_verdict": "INSUFFICIENT_COVERAGE",
        "source_private_artifact": {"logical_id": inventory["logical_id"], "run_count": 84, "qualification_run_count": 80, "pilot_run_count": 4, "formal_run_count": 0, "inventory_sha256": digest, "paths_persisted": False},
        "artifacts": dict(sorted(artifacts.items())),
        "funnel": registry["funnel"],
        "family_coverage": registry["family_coverage"],
        "pilot_status": pilot["status"],
        "policy": {"formal_started": False, "failed_cases_replaced": False, "thresholds_changed": False, "production_slicing_or_replacement": False, "global_savings_claim": False},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / INDEX_NAME
    index_path.write_bytes(canonical_bytes(index))
    upstream_manifest = load(root / spec["components"]["upstream_manifest"]["path"])
    descriptor = {
        "phase": "acp-1.4-natural-ablation-generalization-stopped-insufficient-coverage",
        "started_at": "2026-08-18T00:00:00Z", "completed_at": "2026-08-18T23:59:59Z", "time_block": "2026-08-18",
        "environment": upstream_manifest["environment"],
        "artifacts": {
            "fixture": {"status": "produced", "path": str(root / spec["components"]["experiment_spec"]["path"]), "visibility": "public"},
            "runner": {"status": "produced", "path": str(root / spec["components"]["generalization_runner"]["path"]), "visibility": "public"},
            "spec": {"status": "produced", "path": str(spec_path), "visibility": "public"},
            "raw_private_artifact": {"status": "produced", "path": str(inventory_path), "visibility": "private"},
            "normalized_result": {"status": "produced", "path": str(root / spec["components"]["qualification_result"]["path"]), "visibility": "public"},
            "coverage_ledger": {"status": "produced", "path": str(root / spec["components"]["candidate_registry"]["path"]), "visibility": "public"},
            "fact_report": {"status": "produced", "path": str(root / spec["components"]["family_pilot"]["path"]), "visibility": "public"},
            "public_compact_result": {"status": "produced", "path": str(index_path), "visibility": "public"},
        },
    }
    manifest = build_experiment_manifest.build_manifest(descriptor)
    manifest_path = output_dir / MANIFEST_NAME
    manifest_path.write_bytes(canonical_bytes(manifest))
    return {"index_path": index_path, "manifest_path": manifest_path, "index": index}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    workspace = root.parents[1]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_4_frozen_generalization_spec.json")
    parser.add_argument("--qualification-root", type=Path, default=workspace / ".agent-token-manager/acp1-4-qualification-live-20260818")
    parser.add_argument("--pilot-root", type=Path, default=workspace / ".agent-token-manager/acp1-4-pilot-live-20260818")
    parser.add_argument("--output-dir", type=Path, default=root / "resources")
    args = parser.parse_args()
    frozen = freeze(args.spec.resolve(), args.root.resolve(), args.qualification_root.resolve(), args.pilot_root.resolve(), args.output_dir.resolve(), Path(__file__).resolve())
    print(canonical_bytes({"status": frozen["index"]["status"], "generalization_verdict": frozen["index"]["generalization_verdict"], "index_sha256": sha256_file(frozen["index_path"]), "manifest_sha256": sha256_file(frozen["manifest_path"])}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
