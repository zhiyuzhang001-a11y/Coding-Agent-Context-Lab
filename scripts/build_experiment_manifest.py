#!/usr/bin/env python3
"""Build a deterministic, privacy-safe ACP experiment manifest from a local descriptor."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


GENERATOR_VERSION = "acp-experiment-manifest-v0.1"
ARTIFACT_NAMES = (
    "fixture",
    "runner",
    "spec",
    "raw_private_artifact",
    "normalized_result",
    "coverage_ledger",
    "fact_report",
    "public_compact_result",
)
ENVIRONMENT_NAMES = (
    "codex_version",
    "host_binary_sha256",
    "model_identifier",
    "reasoning_effort",
    "os",
    "architecture",
    "hook_api_version",
    "config_digest",
    "sandbox_digest",
    "environment_allowlist_digest",
    "collector_sha256",
    "normalizer_sha256",
    "reporter_sha256",
)
DESCRIPTOR_NAMES = {"phase", "started_at", "completed_at", "time_block", "environment", "artifacts"}
ARTIFACT_INPUT_NAMES = {"status", "path", "visibility"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    extra = set(value) - expected
    missing = expected - set(value)
    if extra or missing:
        raise ValueError(f"{label} keys differ: missing={sorted(missing)}, extra={sorted(extra)}")


def _build_environment(source: dict[str, Any]) -> dict[str, str]:
    allowed = set(ENVIRONMENT_NAMES) | {"host_binary_path"}
    extra = set(source) - allowed
    if extra:
        raise ValueError(f"environment contains prohibited or unknown fields: {sorted(extra)}")
    environment = {name: str(source.get(name, "unknown")) for name in ENVIRONMENT_NAMES}
    binary_path = source.get("host_binary_path")
    if binary_path is not None:
        if source.get("host_binary_sha256") not in (None, "unknown"):
            raise ValueError("provide host_binary_path or host_binary_sha256, not both")
        environment["host_binary_sha256"] = sha256_file(Path(binary_path))
    return environment


def _build_artifact(name: str, source: dict[str, Any]) -> dict[str, Any]:
    extra = set(source) - ARTIFACT_INPUT_NAMES
    if extra:
        raise ValueError(f"artifact {name} contains unknown fields: {sorted(extra)}")
    status = source.get("status")
    visibility = source.get("visibility")
    if status not in {"produced", "not_produced", "unknown"}:
        raise ValueError(f"artifact {name} has invalid status")
    if visibility not in {"public", "private"}:
        raise ValueError(f"artifact {name} has invalid visibility")
    path = source.get("path")
    if status == "produced":
        if not isinstance(path, str) or not path:
            raise ValueError(f"produced artifact {name} requires a path")
        digest: str | None = sha256_file(Path(path))
    else:
        if path is not None:
            raise ValueError(f"non-produced artifact {name} must not provide a path")
        digest = None
    return {"status": status, "sha256": digest, "visibility": visibility}


def build_manifest(descriptor: dict[str, Any]) -> dict[str, Any]:
    _require_exact_keys(descriptor, DESCRIPTOR_NAMES, "descriptor")
    environment_source = descriptor["environment"]
    artifacts_source = descriptor["artifacts"]
    if not isinstance(environment_source, dict) or not isinstance(artifacts_source, dict):
        raise ValueError("environment and artifacts must be objects")
    _require_exact_keys(artifacts_source, set(ARTIFACT_NAMES), "artifacts")

    environment = _build_environment(environment_source)
    environment_hash = sha256_bytes(canonical_bytes(environment))
    artifacts = {
        name: _build_artifact(name, artifacts_source[name])
        for name in ARTIFACT_NAMES
    }
    chain_hash = sha256_bytes(canonical_bytes({
        "environment_manifest_sha256": environment_hash,
        "artifacts": artifacts,
    }))
    identity = {
        "phase": descriptor["phase"],
        "started_at": descriptor["started_at"],
        "completed_at": descriptor["completed_at"],
        "time_block": descriptor["time_block"],
        "environment_manifest_sha256": environment_hash,
        "chain_sha256": chain_hash,
    }
    return {
        "schema_version": 1,
        "schema_id": "experiment-manifest-v1",
        "manifest_generator_version": GENERATOR_VERSION,
        "experiment_id": sha256_bytes(canonical_bytes(identity)),
        "phase": descriptor["phase"],
        "started_at": descriptor["started_at"],
        "completed_at": descriptor["completed_at"],
        "time_block": descriptor["time_block"],
        "environment": environment,
        "environment_manifest_sha256": environment_hash,
        "artifacts": artifacts,
        "chain_sha256": chain_hash,
        "privacy_policy": {
            "paths_persisted": False,
            "raw_environment_persisted": False,
            "sensitive_bodies_persisted": False,
            "hashes_only_for_artifacts": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("descriptor", type=Path, help="local descriptor JSON; paths are not persisted")
    args = parser.parse_args()
    descriptor = json.loads(args.descriptor.read_text(encoding="utf-8"))
    print(json.dumps(build_manifest(descriptor), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
