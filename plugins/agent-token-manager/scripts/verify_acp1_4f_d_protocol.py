#!/usr/bin/env python3
"""Verify the frozen ACP-1.4F-D protocol and 24-case pool."""

from __future__ import annotations

import json
from pathlib import Path

from run_acp1_4f_d_development import canonical_bytes, load, sha256_file, subject_inventory_digest


def verify(plugin: Path) -> dict[str, object]:
    index_path = plugin / "resources/acp1_4f_d_frozen_protocol_index.json"
    index = load(index_path)
    if index.get("schema_id") != "acp1-4f-d-frozen-protocol-index-v1":
        raise ValueError("invalid_index_schema")
    if index.get("agent_run_count_at_freeze") != 0:
        raise ValueError("nonzero_agent_runs_at_freeze")
    for artifact in index["artifacts"].values():
        path = plugin / artifact["path"]
        if not path.is_file() or sha256_file(path) != artifact["sha256"]:
            raise ValueError(f"artifact_mismatch:{artifact['path']}")
    subject_root = plugin / index["subjects"]["path"]
    count, digest = subject_inventory_digest(subject_root)
    if count != index["subjects"]["file_count"] or digest != index["subjects"]["inventory_sha256"]:
        raise ValueError("subject_inventory_mismatch")
    contract = load(plugin / index["artifacts"]["development_contract"]["path"])
    pool = load(plugin / index["artifacts"]["case_pool"]["path"])
    if contract["protocol_id"] != index["protocol_id"] or pool["pool_id"] != index["pool_id"]:
        raise ValueError("protocol_or_pool_identity_mismatch")
    if len(pool["cases"]) != 24 or contract["execution"]["screen_run_count"] != 72:
        raise ValueError("invalid_frozen_design")
    upstream = plugin / index["upstream"]["f_r_index_path"]
    if not upstream.is_file() or sha256_file(upstream) != index["upstream"]["f_r_index_sha256"]:
        raise ValueError("upstream_f_r_index_mismatch")
    return {
        "status": "pass",
        "protocol_id": index["protocol_id"],
        "pool_id": index["pool_id"],
        "case_count": len(pool["cases"]),
        "agent_run_count_at_freeze": 0,
        "index_sha256": sha256_file(index_path),
    }


if __name__ == "__main__":
    plugin_root = Path(__file__).resolve().parents[1]
    print(canonical_bytes(verify(plugin_root)).decode("utf-8"), end="")
