#!/usr/bin/env python3
"""SQLite persistence for sparse navigation markers and edges."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

from navigation_contract import Edge, Marker
from workspace_data import WorkspaceStore


class NavigationStore:
    def __init__(self, workspace: WorkspaceStore):
        self.workspace = workspace

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(str(self.workspace.database), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def file_states(self, provider: str) -> dict[str, dict[str, Any]]:
        with self.connect() as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    "SELECT path, content_hash, metadata_json FROM indexed_files "
                    "WHERE repo_id=? AND provider=?",
                    (self.workspace.repo_id, provider),
                )
            ]
        return {
            row["path"]: {
                "content_hash": row["content_hash"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        }

    def _delete_path(self, connection: sqlite3.Connection, path: str, provider: str) -> int:
        ids = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM markers WHERE repo_id=? AND path=? AND provider=?",
                (self.workspace.repo_id, path, provider),
            )
        ]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            connection.execute(
                f"DELETE FROM edges WHERE repo_id=? AND (source_id IN ({placeholders}) OR target_id IN ({placeholders}))",
                (self.workspace.repo_id, *ids, *ids),
            )
        connection.execute(
            "DELETE FROM markers WHERE repo_id=? AND path=? AND provider=?",
            (self.workspace.repo_id, path, provider),
        )
        connection.execute(
            "DELETE FROM indexed_files WHERE repo_id=? AND path=? AND provider=?",
            (self.workspace.repo_id, path, provider),
        )
        connection.execute(
            "DELETE FROM unresolved_relations WHERE repo_id=? AND path=? AND provider=?",
            (self.workspace.repo_id, path, provider),
        )
        return len(ids)

    def replace_file(
        self,
        path: str,
        content_hash: str,
        provider: str,
        markers: Iterable[Marker],
        edges: Iterable[Edge],
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        # Repeated definitions are valid Python (notably @overload stubs followed
        # by a runtime implementation). IDs represent semantic nodes rather than
        # source occurrences, so retain the final occurrence transactionally.
        marker_values = list({marker.id: marker for marker in markers}.values())
        edge_values = list({edge.id: edge for edge in edges}.values())
        with self.connect() as connection:
            self._delete_path(connection, path, provider)
            connection.executemany(
                "INSERT INTO markers(id, repo_id, path, symbol, kind, start_line, end_line, signature, "
                "evidence_hash, confidence, base_value, expansion_tokens, provider, metadata_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        marker.id,
                        marker.repo_id,
                        marker.path,
                        marker.symbol,
                        marker.kind,
                        marker.start_line,
                        marker.end_line,
                        marker.signature,
                        marker.evidence_hash,
                        marker.confidence,
                        marker.base_value,
                        marker.expansion_tokens,
                        marker.provider,
                        json.dumps(marker.metadata, ensure_ascii=False, separators=(",", ":")),
                    )
                    for marker in marker_values
                ],
            )
            connection.executemany(
                "INSERT OR REPLACE INTO edges(id, repo_id, source_id, target_id, kind, evidence_hash, "
                "confidence, provider, metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
                [
                    (
                        edge.id,
                        edge.repo_id,
                        edge.source_id,
                        edge.target_id,
                        edge.kind,
                        edge.evidence_hash,
                        edge.confidence,
                        edge.provider,
                        json.dumps(edge.metadata, ensure_ascii=False, separators=(",", ":")),
                    )
                    for edge in edge_values
                ],
            )
            connection.execute(
                "INSERT INTO indexed_files(repo_id, path, content_hash, provider, metadata_json) "
                "VALUES(?,?,?,?,?) ON CONFLICT(repo_id,path,provider) DO UPDATE SET "
                "content_hash=excluded.content_hash, metadata_json=excluded.metadata_json, "
                "indexed_at=CURRENT_TIMESTAMP",
                (
                    self.workspace.repo_id,
                    path,
                    content_hash,
                    provider,
                    json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def delete_paths(self, paths: Iterable[str], provider: str) -> int:
        removed = 0
        with self.connect() as connection:
            for path in paths:
                removed += self._delete_path(connection, path, provider)
        return removed

    def replace_relation_edges(self, provider: str, kind: str, edges: Iterable[Edge]) -> int:
        values = list({edge.id: edge for edge in edges}.values())
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM edges WHERE repo_id=? AND provider=? AND kind=?",
                (self.workspace.repo_id, provider, kind),
            )
            connection.executemany(
                "INSERT INTO edges(id, repo_id, source_id, target_id, kind, evidence_hash, "
                "confidence, provider, metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
                [
                    (
                        edge.id,
                        edge.repo_id,
                        edge.source_id,
                        edge.target_id,
                        edge.kind,
                        edge.evidence_hash,
                        edge.confidence,
                        edge.provider,
                        json.dumps(edge.metadata, ensure_ascii=False, separators=(",", ":")),
                    )
                    for edge in values
                ],
            )
        return len(values)

    def replace_unresolved_relations(
        self, provider: str, relations: Iterable[dict[str, Any]]
    ) -> int:
        values = list({relation["id"]: relation for relation in relations}.values())
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM unresolved_relations WHERE repo_id=? AND provider=?",
                (self.workspace.repo_id, provider),
            )
            connection.executemany(
                "INSERT INTO unresolved_relations(id, repo_id, path, source_id, source_symbol, "
                "target_name, kind, line, evidence_hash, confidence, provider, metadata_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        relation["id"],
                        self.workspace.repo_id,
                        relation["path"],
                        relation["source_id"],
                        relation["source_symbol"],
                        relation["target_name"],
                        relation["kind"],
                        relation["line"],
                        relation["evidence_hash"],
                        relation["confidence"],
                        provider,
                        json.dumps(
                            relation.get("metadata", {}),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )
                    for relation in values
                ],
            )
        return len(values)

    def load_unresolved_relations(self, provider: Optional[str] = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM unresolved_relations WHERE repo_id=?"
        parameters: list[Any] = [self.workspace.repo_id]
        if provider:
            query += " AND provider=?"
            parameters.append(provider)
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(query, parameters)]
        for row in rows:
            row["metadata"] = json.loads(row.pop("metadata_json"))
        return rows

    def load_markers(self, provider: Optional[str] = None) -> list[Marker]:
        query = "SELECT * FROM markers WHERE repo_id=?"
        parameters: list[Any] = [self.workspace.repo_id]
        if provider:
            query += " AND provider=?"
            parameters.append(provider)
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(query, parameters)]
        return [
            Marker(
                id=row["id"],
                repo_id=row["repo_id"],
                path=row["path"],
                symbol=row["symbol"],
                kind=row["kind"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                signature=row["signature"],
                evidence_hash=row["evidence_hash"],
                confidence=row["confidence"],
                base_value=row["base_value"],
                expansion_tokens=row["expansion_tokens"],
                provider=row["provider"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def load_edges(self, provider: Optional[str] = None) -> list[Edge]:
        query = "SELECT * FROM edges WHERE repo_id=?"
        parameters: list[Any] = [self.workspace.repo_id]
        if provider:
            query += " AND provider=?"
            parameters.append(provider)
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(query, parameters)]
        return [
            Edge(
                repo_id=row["repo_id"],
                source_id=row["source_id"],
                target_id=row["target_id"],
                kind=row["kind"],
                evidence_hash=row["evidence_hash"],
                confidence=row["confidence"],
                provider=row["provider"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def counts(self) -> dict[str, int]:
        with self.connect() as connection:
            marker_count = connection.execute(
                "SELECT COUNT(*) FROM markers WHERE repo_id=?", (self.workspace.repo_id,)
            ).fetchone()[0]
            edge_count = connection.execute(
                "SELECT COUNT(*) FROM edges WHERE repo_id=?", (self.workspace.repo_id,)
            ).fetchone()[0]
            file_count = connection.execute(
                "SELECT COUNT(*) FROM indexed_files WHERE repo_id=?", (self.workspace.repo_id,)
            ).fetchone()[0]
            unresolved_count = connection.execute(
                "SELECT COUNT(*) FROM unresolved_relations WHERE repo_id=?",
                (self.workspace.repo_id,),
            ).fetchone()[0]
        return {
            "files": file_count,
            "markers": marker_count,
            "edges": edge_count,
            "unresolved_relations": unresolved_count,
        }
