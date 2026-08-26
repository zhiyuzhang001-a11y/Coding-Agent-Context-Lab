#!/usr/bin/env python3
"""Low-cost, source-body-free candidate discovery for Task Navigator."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Protocol, Sequence

from ast_navigation_provider import estimate_tokens, tokenize
from navigation_contract import Marker


DISCOVERY_SCHEMA_VERSION = 1
MAX_QUERY_TERMS = 16
GENERIC_QUERY_TERMS = {
    "and",
    "are",
    "about",
    "after",
    "before",
    "check",
    "code",
    "current",
    "find",
    "from",
    "for",
    "including",
    "into",
    "its",
    "logic",
    "produce",
    "requested",
    "that",
    "the",
    "summarize",
    "through",
    "understand",
    "whether",
    "with",
}


@dataclass(frozen=True)
class DiscoveryHit:
    marker_id: str
    provider: str
    score: float
    confidence: float
    matched_terms: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        value = asdict(self)
        value["matched_terms"] = list(self.matched_terms)
        return value


@dataclass(frozen=True)
class DiscoveryResult:
    provider: str
    query_terms: tuple[str, ...]
    hits: tuple[DiscoveryHit, ...]
    scanned_markers: int
    elapsed_ms: float
    estimated_tokens: int = 0
    omitted_count: int = 0
    warning: str = ""
    schema_version: int = DISCOVERY_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "query_terms": list(self.query_terms),
            "hits": [hit.to_dict() for hit in self.hits],
            "scanned_markers": self.scanned_markers,
            "elapsed_ms": self.elapsed_ms,
            "estimated_tokens": self.estimated_tokens,
            "omitted_count": self.omitted_count,
            "warning": self.warning,
        }


class DiscoverySource(Protocol):
    name: str

    def discover(
        self,
        query_terms: Sequence[str],
        markers: Sequence[Marker],
        limit: int,
        budget_tokens: int,
    ) -> DiscoveryResult: ...


def _normalize_term(term: str) -> str:
    if term in {"alias", "analysis", "status"}:
        return term
    if len(term) > 4 and term.endswith("ies"):
        return term[:-3] + "y"
    if len(term) > 4 and term.endswith("ses"):
        return term[:-2]
    if len(term) > 3 and term.endswith("s") and not term.endswith("ss"):
        return term[:-1]
    return term


def _normalized_tokens(value: str) -> set[str]:
    return {_normalize_term(term) for term in tokenize(value)}


def normalize_query_terms(values: Sequence[str]) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        for term in sorted(_normalized_tokens(value)):
            if len(term) < 3 or term in GENERIC_QUERY_TERMS or term in seen:
                continue
            terms.append(term)
            seen.add(term)
            if len(terms) == MAX_QUERY_TERMS:
                return tuple(terms)
    return tuple(terms)


class BoundedTextSource:
    """Rank existing Markers by bounded source-region term evidence.

    Source text is scanned locally but never stored in DiscoveryResult or TaskState.
    """

    name = "bounded-text"

    def __init__(self, root: Path):
        self.root = root.resolve()

    def discover(
        self,
        query_terms: Sequence[str],
        markers: Sequence[Marker],
        limit: int = 8,
        budget_tokens: int = 400,
    ) -> DiscoveryResult:
        started = time.perf_counter()
        terms = normalize_query_terms(query_terms)
        if not terms or budget_tokens < 64 or limit < 1:
            return DiscoveryResult(
                provider=self.name,
                query_terms=terms,
                hits=(),
                scanned_markers=0,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                warning="no_eligible_query_terms" if not terms else "insufficient_budget",
            )

        lines_by_path: dict[str, list[str]] = {}
        marker_terms: list[tuple[Marker, set[str], set[str]]] = []
        document_frequency = {term: 0 for term in terms}
        for marker in markers:
            if marker.kind in {"file", "module"}:
                continue
            if "test" not in terms and (
                marker.path.startswith("tests/") or "/test" in marker.path
            ):
                continue
            lines = lines_by_path.get(marker.path)
            if lines is None:
                try:
                    lines = (self.root / marker.path).read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                except OSError:
                    lines = []
                lines_by_path[marker.path] = lines
            region = "\n".join(lines[marker.start_line - 1 : marker.end_line])
            region_tokens = _normalized_tokens(region)
            matched = set(terms) & region_tokens
            if not matched:
                continue
            symbol_tokens = _normalized_tokens(marker.symbol) | _normalized_tokens(marker.signature)
            marker_terms.append((marker, matched, symbol_tokens))
            for term in matched:
                document_frequency[term] += 1

        population = max(1, len(marker_terms))
        ranked: list[tuple[float, Marker, tuple[str, ...], float]] = []
        for marker, matched, symbol_tokens in marker_terms:
            idf_score = sum(
                math.log1p(population / (1 + document_frequency[term])) for term in matched
            )
            symbol_overlap = matched & symbol_tokens
            coverage = len(matched) / len(terms)
            region_lines = marker.end_line - marker.start_line + 1
            specificity_penalty = min(4.0, math.log1p(region_lines / 20.0))
            score = (
                idf_score
                + 3.5 * len(symbol_overlap)
                + 4.0 * coverage
                - specificity_penalty
            )
            confidence = min(0.95, 0.25 + 0.12 * len(matched) + 0.08 * len(symbol_overlap))
            ranked.append((score, marker, tuple(sorted(matched)), confidence))
        ranked.sort(key=lambda item: (-item[0], item[1].expansion_tokens, item[1].path, item[1].symbol))

        selected: list[DiscoveryHit] = []
        for score, marker, matched, confidence in ranked:
            hit = DiscoveryHit(
                marker_id=marker.id,
                provider=self.name,
                score=round(score, 4),
                confidence=round(confidence, 4),
                matched_terms=matched,
                reason="source_region_term_evidence",
            )
            trial = DiscoveryResult(
                provider=self.name,
                query_terms=terms,
                hits=tuple([*selected, hit]),
                scanned_markers=len(marker_terms),
                elapsed_ms=0.0,
                omitted_count=max(0, len(ranked) - len(selected) - 1),
            )
            if estimate_tokens(trial.to_dict()) > budget_tokens:
                break
            selected.append(hit)
            if len(selected) == limit:
                break

        result = DiscoveryResult(
            provider=self.name,
            query_terms=terms,
            hits=tuple(selected),
            scanned_markers=len(marker_terms),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            omitted_count=max(0, len(ranked) - len(selected)),
        )
        return replace(result, estimated_tokens=estimate_tokens(result.to_dict()))
