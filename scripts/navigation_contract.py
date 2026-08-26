#!/usr/bin/env python3
"""Versioned contracts shared by navigation-map providers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, Iterable, Protocol


SCHEMA_VERSION = 1
ALLOWED_MARKER_KINDS = {"repository", "module", "file", "class", "function", "method", "interface", "data"}
ALLOWED_EDGE_KINDS = {"contains", "imports", "calls", "references", "inherits", "implements", "tests", "depends_on"}


class ContractError(ValueError):
    """Raised when a provider returns data outside the shared contract."""


def _relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ContractError(f"path must be repository-relative: {value!r}")
    return str(path)


def marker_id(repo_id: str, path: str, symbol: str, kind: str) -> str:
    material = "\0".join((repo_id, _relative_path(path), symbol, kind))
    return sha256(material.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class Marker:
    repo_id: str
    path: str
    symbol: str
    kind: str
    start_line: int
    end_line: int
    evidence_hash: str
    confidence: float
    base_value: float
    expansion_tokens: int
    provider: str
    signature: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    id: str = ""

    def __post_init__(self) -> None:
        path = _relative_path(self.path)
        object.__setattr__(self, "path", path)
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(f"unsupported marker schema: {self.schema_version}")
        if not self.repo_id or not self.symbol or not self.provider:
            raise ContractError("repo_id, symbol, and provider are required")
        if self.kind not in ALLOWED_MARKER_KINDS:
            raise ContractError(f"unsupported marker kind: {self.kind}")
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ContractError("invalid marker line range")
        if not 0.0 <= self.confidence <= 1.0:
            raise ContractError("confidence must be between 0 and 1")
        if self.base_value < 0 or self.expansion_tokens < 0:
            raise ContractError("base_value and expansion_tokens must be non-negative")
        if not self.id:
            object.__setattr__(self, "id", marker_id(self.repo_id, path, self.symbol, self.kind))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Marker":
        return cls(**value)


@dataclass(frozen=True)
class Edge:
    repo_id: str
    source_id: str
    target_id: str
    kind: str
    evidence_hash: str
    confidence: float
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(f"unsupported edge schema: {self.schema_version}")
        if not self.repo_id or not self.source_id or not self.target_id or not self.provider:
            raise ContractError("repo_id, source_id, target_id, and provider are required")
        if self.kind not in ALLOWED_EDGE_KINDS:
            raise ContractError(f"unsupported edge kind: {self.kind}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ContractError("confidence must be between 0 and 1")

    @property
    def id(self) -> str:
        material = "\0".join((self.repo_id, self.source_id, self.target_id, self.kind, self.provider))
        return sha256(material.encode("utf-8")).hexdigest()[:24]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["id"] = self.id
        return value


@dataclass(frozen=True)
class QueryRequest:
    task: str
    budget_tokens: int
    symbols: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    limit: int = 20
    include_edge_kinds: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(f"unsupported query schema: {self.schema_version}")
        if not self.task.strip() and not self.symbols and not self.paths:
            raise ContractError("query needs a task, symbol, or path")
        if self.budget_tokens < 64 or self.limit < 1:
            raise ContractError("budget_tokens must be >= 64 and limit must be positive")
        normalized_paths = tuple(_relative_path(path) for path in self.paths)
        object.__setattr__(self, "paths", normalized_paths)
        unknown = set(self.include_edge_kinds) - ALLOWED_EDGE_KINDS
        if unknown:
            raise ContractError(f"unsupported edge kinds: {sorted(unknown)}")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["symbols"] = list(self.symbols)
        value["paths"] = list(self.paths)
        value["include_edge_kinds"] = list(self.include_edge_kinds)
        return value


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    markers: tuple[Marker, ...] = ()
    edges: tuple[Edge, ...] = ()
    omitted_count: int = 0
    estimated_tokens: int = 0
    warnings: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(f"unsupported result schema: {self.schema_version}")
        if not self.provider or self.omitted_count < 0 or self.estimated_tokens < 0:
            raise ContractError("invalid provider result metadata")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "markers": [marker.to_dict() for marker in self.markers],
            "edges": [edge.to_dict() for edge in self.edges],
            "omitted_count": self.omitted_count,
            "estimated_tokens": self.estimated_tokens,
            "warnings": list(self.warnings),
        }


class NavigationProvider(Protocol):
    name: str

    def index(self, root: str, changed_paths: Iterable[str] = ()) -> ProviderResult: ...

    def query(self, request: QueryRequest) -> ProviderResult: ...

    def expand(self, marker_ids: Iterable[str], budget_tokens: int) -> ProviderResult: ...

    def invalidate(self, paths: Iterable[str]) -> int: ...
