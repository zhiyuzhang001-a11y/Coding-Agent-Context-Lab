#!/usr/bin/env python3
"""Project identity and private persistent storage for navigation data."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from navigation_contract import SCHEMA_VERSION


DATA_DIR_NAME = ".agent-token-manager"
DATABASE_NAME = "navigation-v1.sqlite3"


class WorkspaceError(RuntimeError):
    pass


def _git(args: list[str], cwd: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True, timeout=5
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def discover_git_root(start: Path) -> Optional[Path]:
    value = _git(["rev-parse", "--show-toplevel"], start.resolve())
    return Path(value).resolve() if value else None


def repository_identity(root: Path) -> str:
    root = root.resolve()
    remote = _git(["config", "--get", "remote.origin.url"], root)
    initial_commit = _git(["rev-list", "--max-parents=0", "HEAD"], root)
    stable_part = remote or initial_commit or str(root)
    material = f"{root.name}\0{stable_part}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def resolve_data_dir(root: Path, explicit: Optional[Path] = None, create: bool = True) -> Path:
    root = root.resolve()
    repo_id = repository_identity(root)
    if explicit is not None:
        target = explicit.expanduser().resolve()
    else:
        configured = os.environ.get("AGENT_TOKEN_MANAGER_DATA") or os.environ.get("PLUGIN_DATA")
        target = Path(configured).expanduser().resolve() / "projects" / repo_id if configured else root / DATA_DIR_NAME
    if create:
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            target.chmod(0o700)
        except OSError:
            pass
    return target


@dataclass(frozen=True)
class WorkspaceStore:
    root: Path
    repo_id: str
    data_dir: Path
    database: Path

    def to_dict(self) -> dict[str, str | int]:
        return {
            "schema_version": SCHEMA_VERSION,
            "root": str(self.root),
            "repo_id": self.repo_id,
            "data_dir": str(self.data_dir),
            "database": str(self.database),
        }


def initialize_store(root: Path, data_dir: Optional[Path] = None) -> WorkspaceStore:
    root = root.resolve()
    target = resolve_data_dir(root, data_dir, create=True)
    database = target / DATABASE_NAME
    connection = sqlite3.connect(str(database), timeout=5)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS markers (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                path TEXT NOT NULL,
                symbol TEXT NOT NULL,
                kind TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                signature TEXT NOT NULL,
                evidence_hash TEXT NOT NULL,
                confidence REAL NOT NULL,
                base_value REAL NOT NULL,
                expansion_tokens INTEGER NOT NULL,
                provider TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS markers_path_idx ON markers(repo_id, path);
            CREATE INDEX IF NOT EXISTS markers_symbol_idx ON markers(repo_id, symbol);
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                evidence_hash TEXT NOT NULL,
                confidence REAL NOT NULL,
                provider TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS edges_source_idx ON edges(repo_id, source_id);
            CREATE INDEX IF NOT EXISTS edges_target_idx ON edges(repo_id, target_id);
            CREATE TABLE IF NOT EXISTS unresolved_relations (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                path TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                target_name TEXT NOT NULL,
                kind TEXT NOT NULL,
                line INTEGER NOT NULL,
                evidence_hash TEXT NOT NULL,
                confidence REAL NOT NULL,
                provider TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS unresolved_relations_path_idx
                ON unresolved_relations(repo_id, path, provider);
            CREATE TABLE IF NOT EXISTS indexed_files (
                repo_id TEXT NOT NULL,
                path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                provider TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(repo_id, path, provider)
            );
            CREATE INDEX IF NOT EXISTS indexed_files_provider_idx
                ON indexed_files(repo_id, provider);
            CREATE TABLE IF NOT EXISTS navigation_tasks (
                task_id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                task_text TEXT NOT NULL,
                status TEXT NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS navigation_tasks_repo_idx
                ON navigation_tasks(repo_id, status);
            """
        )
        repo_id = repository_identity(root)
        metadata = {
            "schema_version": str(SCHEMA_VERSION),
            "repo_id": repo_id,
            "root": str(root),
        }
        connection.executemany(
            "INSERT INTO schema_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            metadata.items(),
        )
        connection.commit()
    finally:
        connection.close()
    try:
        database.chmod(0o600)
    except OSError:
        pass
    metadata_path = target / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        metadata_path.chmod(0o600)
    except OSError:
        pass
    return WorkspaceStore(root=root, repo_id=metadata["repo_id"], data_dir=target, database=database)


def persistent_cache_directory(target: Path) -> Path:
    """Return the repository-scoped parse cache for a source target."""
    resolved = target.expanduser().resolve()
    start = resolved.parent if resolved.is_file() else resolved
    root = discover_git_root(start) or start
    try:
        return initialize_store(root).data_dir / "parse-cache"
    except (OSError, sqlite3.Error) as exc:
        fallback_root = (
            Path(tempfile.gettempdir())
            / "agent-token-manager-workspace-cache"
            / repository_identity(root)
        )
        try:
            fallback_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            fallback_root.chmod(0o700)
            return fallback_root / "parse-cache"
        except OSError as fallback_error:
            raise WorkspaceError(
                f"persistent cache unavailable: {exc}; private fallback unavailable: {fallback_error}"
            ) from fallback_error
