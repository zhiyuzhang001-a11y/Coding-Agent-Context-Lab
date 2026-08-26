#!/usr/bin/env python3
"""Verify the frozen ACP-1.4F-0 contract without running an Agent."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class VerificationError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError(f"object_required:{path.name}")
    return value


def verify(root: Path, index_path: Path) -> dict[str, Any]:
    index = load(index_path)
    if index.get("schema_id") != "acp1-4f-f0-frozen-index-v1":
        raise VerificationError("invalid_index")
    if index.get("agent_run_count") != 0 or index.get("agent_runs_authorized") is not False:
        raise VerificationError("agent_run_boundary_violation")
    for name, artifact in index["artifacts"].items():
        path = root / artifact["path"]
        if not path.is_file() or sha256(path) != artifact["sha256"]:
            raise VerificationError(f"artifact_hash_mismatch:{name}")
    contract = load(root / index["artifacts"]["contract"]["path"])
    oracle = load(root / index["artifacts"]["oracle_registry"]["path"])
    if contract.get("status") != "f0_frozen_agent_runs_not_started":
        raise VerificationError("contract_status_drift")
    if len(contract.get("cases", [])) != 12 or len(oracle.get("cases", {})) != 12:
        raise VerificationError("sampling_frame_drift")
    if contract["run_budget"]["primary_agent_run_hard_max"] != 366:
        raise VerificationError("run_budget_drift")
    if any(contract["policy"].values()):
        raise VerificationError("frozen_product_boundary_violation")
    return {
        "status": "pass",
        "phase": "ACP-1.4F-0",
        "agent_run_count": 0,
        "case_count": 12,
        "index_sha256": sha256(index_path),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = verify(root, root / "resources/acp1_4f_f0_frozen_index.json")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

