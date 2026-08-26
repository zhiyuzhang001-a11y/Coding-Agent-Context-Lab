#!/usr/bin/env python3
"""Validate and freeze the ACP-1.3B controlled-intervention feasibility result."""

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


RUNNER_VERSION = "acp1-3b-freeze-runner-v0.1"
INDEX_NAME = "acp1_3b_frozen_feasibility_index.json"
MANIFEST_NAME = "acp1_3b_frozen_experiment_manifest.json"
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
        "logical_id": "acp1-3b-controlled-evidence-20260818-live",
        "run_count": len(rows),
        "results": rows,
    }


def verify(spec: dict[str, Any], result: dict[str, Any], root: Path, private_root: Path) -> dict[str, Any]:
    if spec.get("schema_id") != "acp1-3b-frozen-feasibility-spec-v1":
        raise FreezeError("invalid_spec")
    for name, component in spec["components"].items():
        path = root / component["path"]
        if not path.is_file() or sha256_file(path) != component["sha256"]:
            raise FreezeError(f"component_hash_mismatch:{name}")

    inventory = private_inventory(private_root)
    if inventory["run_count"] != spec["private_source"]["run_count"]:
        raise FreezeError("private_run_count_mismatch")
    if hashlib.sha256(canonical_bytes(inventory)).hexdigest() != spec["private_source"]["inventory_sha256"]:
        raise FreezeError("private_inventory_hash_mismatch")

    expected = spec["expected"]
    qualification = result["replay_qualification"]
    paired = result["paired_feasibility"]
    control = paired["arms"]["control"]
    treatment = paired["arms"]["treatment"]
    checks = (
        result.get("status") == expected["status"],
        all(result.get("gates", {}).values()),
        qualification.get("run_count") == expected["qualification_run_count"],
        qualification.get("correct_count") == expected["qualification_correct_count"],
        qualification.get("exact_single_command_count") == expected["qualification_exact_single_command_count"],
        paired.get("run_count") == expected["paired_run_count"],
        control.get("correct_count") == expected["control_correct_count"],
        treatment.get("correct_count") == expected["treatment_correct_count"],
        control.get("success_semantics_count") == expected["control_success_semantics_count"],
        treatment.get("success_semantics_count") == expected["treatment_success_semantics_count"],
        control["target_visible_token_distribution"]["median"] == expected["control_target_visible_median"],
        treatment["target_visible_token_distribution"]["median"] == expected["treatment_target_visible_median"],
        control["total_token_distribution"]["median"] == expected["control_total_token_median"],
        treatment["total_token_distribution"]["median"] == expected["treatment_total_token_median"],
        paired.get("observed_visible_estimate_reduction_ratio") == expected["observed_visible_estimate_reduction_ratio"],
        result["conclusions"].get("general_savings_claim") is False,
        result["conclusions"].get("historical_candidate_validation") == "not_performed",
        result["conclusions"].get("production_intervention_availability") == "blocked_host_interface_unchanged",
    )
    if not all(checks):
        raise FreezeError("expected_result_mismatch")

    serialized = canonical_bytes(result).decode("utf-8").lower()
    for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "avoidable_tokens", "potential_savings"):
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
    result = load(result_path)
    inventory = verify(spec, result, root, private_root)
    inventory_path = private_root / INVENTORY_NAME
    inventory_path.write_bytes(canonical_bytes(inventory))

    artifacts = {name: dict(value) for name, value in spec["components"].items()}
    artifacts["freeze_spec"] = {"path": str(spec_path.relative_to(root)), "sha256": sha256_file(spec_path)}
    artifacts["freeze_runner"] = {"path": str(runner_path.relative_to(root)), "sha256": sha256_file(runner_path)}
    index = {
        "schema_version": 1,
        "schema_id": "acp1-3b-frozen-feasibility-index-v1",
        "baseline_id": spec["baseline_id"],
        "status": "complete_under_synthetic_frozen_experiment_scope",
        "runner_version": RUNNER_VERSION,
        "source_private_artifact": {
            "logical_id": inventory["logical_id"],
            "run_count": inventory["run_count"],
            "inventory_sha256": hashlib.sha256(canonical_bytes(inventory)).hexdigest(),
            "paths_persisted": False,
        },
        "artifacts": dict(sorted(artifacts.items())),
        "result_snapshot": spec["expected"],
        "gates": result["gates"],
        "scope": {
            "mechanism_feasibility": "proved_for_synthetic_frozen_case",
            "historical_high_cost_candidates": "not_validated",
            "production_host_intervention": "blocked",
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
        "phase": "acp-1.3b-controlled-intervention-feasibility",
        "started_at": spec["logical_started_at"],
        "completed_at": spec["logical_completed_at"],
        "time_block": spec["time_block"],
        "environment": environment,
        "artifacts": {
            "fixture": {"status": "produced", "path": str(root / spec["components"]["experiment_spec"]["path"]), "visibility": "public"},
            "runner": {"status": "produced", "path": str(root / spec["components"]["feasibility_runner"]["path"]), "visibility": "public"},
            "spec": {"status": "produced", "path": str(spec_path), "visibility": "public"},
            "raw_private_artifact": {"status": "produced", "path": str(inventory_path), "visibility": "private"},
            "normalized_result": {"status": "produced", "path": str(result_path), "visibility": "public"},
            "coverage_ledger": {"status": "produced", "path": str(result_path), "visibility": "public"},
            "fact_report": {"status": "produced", "path": str(result_path), "visibility": "public"},
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
    parser.add_argument("--private-root", type=Path, default=workspace / ".agent-token-manager/acp1-3b-controlled-evidence-20260818-live")
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_3b_frozen_feasibility_spec.json")
    parser.add_argument("--output-dir", type=Path, default=root / "resources")
    args = parser.parse_args()
    frozen = freeze(args.spec.resolve(), args.root.resolve(), args.private_root.resolve(), args.output_dir.resolve(), Path(__file__).resolve())
    print(canonical_bytes({
        "baseline_id": frozen["index"]["baseline_id"],
        "status": frozen["index"]["status"],
        "index_sha256": sha256_file(frozen["index_path"]),
        "manifest_sha256": sha256_file(frozen["manifest_path"]),
        "gates": frozen["index"]["gates"],
    }).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
