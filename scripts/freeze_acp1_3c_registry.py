#!/usr/bin/env python3
"""Validate and freeze the ACP-1.3C natural candidate qualification registry."""

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


RUNNER_VERSION = "acp1-3c-freeze-runner-v0.1"
INDEX_NAME = "acp1_3c_frozen_registry_index.json"
MANIFEST_NAME = "acp1_3c_frozen_experiment_manifest.json"
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


def private_inventory(private_root: Path) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for path in sorted(private_root.glob("*/result.json")):
        result = load(path)
        rows.append({"run_id": str(result.get("run_id")), "sha256": sha256_file(path)})
    return {
        "schema_version": 1,
        "logical_id": "acp1-3c-natural-qualification-20260818-live",
        "run_count": len(rows),
        "results": rows,
    }


def verify(spec: dict[str, Any], result: dict[str, Any], registry: dict[str, Any], root: Path, private_root: Path) -> dict[str, Any]:
    if spec.get("schema_id") != "acp1-3c-frozen-registry-spec-v1":
        raise FreezeError("invalid_spec")
    for name, component in spec["components"].items():
        path = root / component["path"]
        if not path.is_file() or sha256_file(path) != component["sha256"]:
            raise FreezeError(f"component_hash_mismatch:{name}")

    inventory = private_inventory(private_root)
    inventory_sha256 = hashlib.sha256(canonical_bytes(inventory)).hexdigest()
    if inventory["run_count"] != spec["private_source"]["run_count"]:
        raise FreezeError("private_run_count_mismatch")
    if inventory_sha256 != spec["private_source"]["inventory_sha256"]:
        raise FreezeError("private_inventory_hash_mismatch")

    if result.get("run_count") != 80 or not all(result.get("gates", {}).values()):
        raise FreezeError("result_gate_or_run_count_mismatch")
    if result.get("policy", {}).get("intervention") or not result.get("policy", {}).get("native_only"):
        raise FreezeError("native_only_policy_mismatch")
    if registry.get("status") != "qualification_complete_under_frozen_scope":
        raise FreezeError("registry_status_mismatch")
    if registry.get("source_result_sha256") != hashlib.sha256(canonical_bytes(result)).hexdigest():
        raise FreezeError("registry_result_binding_mismatch")
    if registry.get("summary") != spec["expected"]["summary"]:
        raise FreezeError("registry_summary_mismatch")

    expected_cases = {row["case_id"]: row for row in spec["expected"]["cases"]}
    actual_cases = {row["case_id"]: row for row in registry["cases"]}
    if set(expected_cases) != set(actual_cases):
        raise FreezeError("case_set_mismatch")
    for case_id, expected in expected_cases.items():
        actual = actual_cases[case_id]
        calibration = actual["native_calibration"]
        observed = {
            "case_id": case_id,
            "status": actual["status"],
            "completed_with_usage": calibration["completed_with_usage"],
            "correct": calibration["correct"],
            "candidate_recurrence": calibration["candidate_recurrence"],
            "ambiguous_candidate_matches": calibration["ambiguous_candidate_matches"],
            "dominant_path_frequency": calibration["dominant_path_frequency"],
            "eligible_for_acp1_3d": actual["eligible_for_acp1_3d"],
        }
        if observed != expected:
            raise FreezeError(f"case_snapshot_mismatch:{case_id}")

    serialized = (canonical_bytes(result) + canonical_bytes(registry)).decode("utf-8").lower()
    for prohibited in ("/users/", "final_text", "tool_response", "command\"", "wasted_tokens", "avoidable_tokens", "potential_savings"):
        if prohibited in serialized:
            raise FreezeError(f"privacy_or_verdict_violation:{prohibited}")

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


def freeze(spec_path: Path, root: Path, private_root: Path, output_dir: Path, runner_path: Path) -> dict[str, Any]:
    spec = load(spec_path)
    result_path = root / spec["components"]["public_result"]["path"]
    registry_path = root / spec["components"]["candidate_registry"]["path"]
    result, registry = load(result_path), load(registry_path)
    inventory = verify(spec, result, registry, root, private_root)
    inventory_path = private_root / INVENTORY_NAME
    inventory_path.write_bytes(canonical_bytes(inventory))

    artifacts = {name: dict(value) for name, value in spec["components"].items()}
    artifacts["freeze_spec"] = {"path": str(spec_path.relative_to(root)), "sha256": sha256_file(spec_path)}
    artifacts["freeze_runner"] = {"path": str(runner_path.relative_to(root)), "sha256": sha256_file(runner_path)}
    index = {
        "schema_version": 1,
        "schema_id": "acp1-3c-frozen-registry-index-v1",
        "baseline_id": spec["baseline_id"],
        "status": "complete_under_frozen_experiment_scope",
        "runner_version": RUNNER_VERSION,
        "source_private_artifact": {
            "logical_id": inventory["logical_id"],
            "run_count": inventory["run_count"],
            "inventory_sha256": hashlib.sha256(canonical_bytes(inventory)).hexdigest(),
            "paths_persisted": False,
        },
        "artifacts": dict(sorted(artifacts.items())),
        "registry_summary": registry["summary"],
        "qualified_case_ids": [row["case_id"] for row in registry["cases"] if row["status"] == "qualified"],
        "gates": result["gates"],
        "policy": {
            "native_only": True,
            "intervention_executed": False,
            "acp1_3d_may_consume_only_qualified": True,
            "avoidable_or_savings_claim": False,
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
        "phase": "acp-1.3c-prospective-natural-candidate-qualification",
        "started_at": spec["logical_started_at"],
        "completed_at": spec["logical_completed_at"],
        "time_block": spec["time_block"],
        "environment": environment,
        "artifacts": {
            "fixture": {"status": "produced", "path": str(root / spec["components"]["natural_fixture"]["path"]), "visibility": "public"},
            "runner": {"status": "produced", "path": str(root / spec["components"]["qualification_runner"]["path"]), "visibility": "public"},
            "spec": {"status": "produced", "path": str(spec_path), "visibility": "public"},
            "raw_private_artifact": {"status": "produced", "path": str(inventory_path), "visibility": "private"},
            "normalized_result": {"status": "produced", "path": str(result_path), "visibility": "public"},
            "coverage_ledger": {"status": "produced", "path": str(registry_path), "visibility": "public"},
            "fact_report": {"status": "produced", "path": str(registry_path), "visibility": "public"},
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
    parser.add_argument("--private-root", type=Path, default=workspace / ".agent-token-manager/acp1-3c-natural-qualification-20260818-live")
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_3c_frozen_registry_spec.json")
    parser.add_argument("--output-dir", type=Path, default=root / "resources")
    args = parser.parse_args()
    frozen = freeze(args.spec.resolve(), args.root.resolve(), args.private_root.resolve(), args.output_dir.resolve(), Path(__file__).resolve())
    print(canonical_bytes({
        "baseline_id": frozen["index"]["baseline_id"],
        "status": frozen["index"]["status"],
        "index_sha256": sha256_file(frozen["index_path"]),
        "manifest_sha256": sha256_file(frozen["manifest_path"]),
        "registry_summary": frozen["index"]["registry_summary"],
    }).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
