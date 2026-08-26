#!/usr/bin/env python3
"""Freeze the ACP-1.4D activation audit and its 60-run source subset."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import build_experiment_manifest


INDEX_NAME = "acp1_4d_frozen_activation_audit_index.json"
MANIFEST_NAME = "acp1_4d_frozen_experiment_manifest.json"
INVENTORY_NAME = "acp1_4d_private_inventory.json"
CASE_IDS = ("read_context_router_limit_v1", "search_budget_stop_v1", "search_token_router_v1")


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
    rows = []
    for case_id in CASE_IDS:
        for arm in ("control", "treatment"):
            for ordinal in range(1, 11):
                run_dir = private_root / f"formal__{case_id}__r{ordinal:02d}-{arm}"
                result = run_dir / "result.json"
                transcripts = sorted((run_dir / "codex-home" / "sessions").rglob("*.jsonl"))
                if not result.is_file() or len(transcripts) != 1:
                    raise FreezeError(f"private_source_missing:{case_id}:{arm}:{ordinal}")
                rows.append({
                    "logical_run": f"{case_id}:r{ordinal:02d}:{arm}",
                    "result_sha256": sha256_file(result),
                    "transcript_sha256": sha256_file(transcripts[0]),
                })
    return {
        "schema_version": 1,
        "logical_id": "acp1-4d-activation-audit-source-subset-20260819",
        "run_count": len(rows),
        "runs": rows,
    }


def freeze(spec_path: Path, root: Path, private_root: Path, output_dir: Path, runner_path: Path) -> dict[str, Any]:
    spec = load(spec_path)
    if spec.get("schema_id") != "acp1-4d-frozen-activation-audit-spec-v1":
        raise FreezeError("invalid_spec")
    for name, component in spec["components"].items():
        path = root / component["path"]
        if not path.is_file() or sha256_file(path) != component["sha256"]:
            raise FreezeError(f"component_hash_mismatch:{name}")
    audit = load(root / spec["components"]["audit_result"]["path"])
    if audit.get("agent_run_count") != 0 or audit.get("private_formal_runs_audited") != 60:
        raise FreezeError("audit_scope_mismatch")
    if audit.get("summary") != spec["expected"]["summary"]:
        raise FreezeError("summary_mismatch")
    observed = {row["case_id"]: row["primary_classification"] for row in audit["cases"]}
    if observed != spec["expected"]["classifications"]:
        raise FreezeError("classification_mismatch")

    inventory = private_inventory(private_root)
    digest = hashlib.sha256(canonical_bytes(inventory)).hexdigest()
    if inventory["run_count"] != 60 or digest != spec["private_source"]["inventory_sha256"]:
        raise FreezeError("private_inventory_mismatch")
    serialized = canonical_bytes(audit).decode("utf-8").casefold()
    for prohibited in ("/users/", "final_text", "tool_response", "wasted_tokens", "potential_savings"):
        if prohibited in serialized:
            raise FreezeError(f"privacy_or_claim_violation:{prohibited}")

    inventory_path = private_root / INVENTORY_NAME
    inventory_path.write_bytes(canonical_bytes(inventory))
    artifacts = {name: dict(value) for name, value in spec["components"].items()}
    artifacts["freeze_spec"] = {"path": str(spec_path.relative_to(root)), "sha256": sha256_file(spec_path)}
    artifacts["freeze_runner"] = {"path": str(runner_path.relative_to(root)), "sha256": sha256_file(runner_path)}
    index = {
        "schema_version": 1,
        "schema_id": "acp1-4d-frozen-activation-audit-index-v1",
        "experiment_id": spec["experiment_id"],
        "status": "complete_under_frozen_audit_scope",
        "agent_run_count": 0,
        "private_source": {"logical_id": inventory["logical_id"], "run_count": 60, "inventory_sha256": digest, "paths_persisted": False},
        "artifacts": dict(sorted(artifacts.items())),
        "summary": audit["summary"],
        "classifications": observed,
        "policy": audit["policy"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / INDEX_NAME
    index_path.write_bytes(canonical_bytes(index))

    upstream = load(root / spec["components"]["upstream_manifest"]["path"])
    descriptor = {
        "phase": "acp-1.4d-read-search-treatment-activation-audit",
        "started_at": "2026-08-19T00:00:00Z",
        "completed_at": "2026-08-19T23:59:59Z",
        "time_block": "2026-08-19",
        "environment": upstream["environment"],
        "artifacts": {
            "fixture": {"status": "produced", "path": str(root / spec["components"]["audit_spec"]["path"]), "visibility": "public"},
            "runner": {"status": "produced", "path": str(root / spec["components"]["audit_runner"]["path"]), "visibility": "public"},
            "spec": {"status": "produced", "path": str(spec_path), "visibility": "public"},
            "raw_private_artifact": {"status": "produced", "path": str(inventory_path), "visibility": "private"},
            "normalized_result": {"status": "not_produced", "path": None, "visibility": "public"},
            "coverage_ledger": {"status": "produced", "path": str(root / spec["components"]["audit_result"]["path"]), "visibility": "public"},
            "fact_report": {"status": "produced", "path": str(root / spec["components"]["audit_result"]["path"]), "visibility": "public"},
            "public_compact_result": {"status": "produced", "path": str(index_path), "visibility": "public"},
        },
    }
    manifest = build_experiment_manifest.build_manifest(descriptor)
    manifest_path = output_dir / MANIFEST_NAME
    manifest_path.write_bytes(canonical_bytes(manifest))
    return {"index": index, "index_path": index_path, "manifest_path": manifest_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    workspace = root.parents[1]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--spec", type=Path, default=root / "resources/acp1_4d_frozen_activation_audit_spec.json")
    parser.add_argument("--private-root", type=Path, default=workspace / ".agent-token-manager/acp1-4c-formal-live-20260819")
    parser.add_argument("--output-dir", type=Path, default=root / "resources")
    args = parser.parse_args()
    frozen = freeze(args.spec.resolve(), args.root.resolve(), args.private_root.resolve(), args.output_dir.resolve(), Path(__file__).resolve())
    print(canonical_bytes({"status": frozen["index"]["status"], "index_sha256": sha256_file(frozen["index_path"]), "manifest_sha256": sha256_file(frozen["manifest_path"])}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
