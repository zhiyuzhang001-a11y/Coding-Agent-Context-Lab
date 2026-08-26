#!/usr/bin/env python3
"""Persistent feedback-driven task navigation under a hard token budget."""

from __future__ import annotations

import argparse
import ast
import json
import math
import sqlite3
import textwrap
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from ast_navigation_provider import AstNavigationProvider, edge_degree_weight, estimate_tokens, tokenize
from context_router import route_read
from discovery_sources import BoundedTextSource, DiscoveryResult, normalize_query_terms
from navigation_contract import Edge, Marker, QueryRequest


STOP_REASONS = {
    "target_found",
    "evidence_sufficient",
    "budget_exhausted",
    "no_useful_candidate",
    "low_expected_gain",
    "unsupported_language",
    "user_stopped",
    "error",
    "no_profitable_candidate_source",
    "external_discovery_exhausted",
    "verification_inconclusive",
    "source_exhausted",
    "internal_limit_reached",
}
RELEVANCE_VALUES = {"relevant", "irrelevant", "uncertain"}
INFORMATION_GAIN_VALUES = {"high", "medium", "low"}


@dataclass
class Feedback:
    marker_id: str
    relevance: str = "uncertain"
    information_gain: str = "low"
    hypotheses_supported: list[str] = field(default_factory=list)
    hypotheses_rejected: list[str] = field(default_factory=list)
    new_symbols: list[str] = field(default_factory=list)
    new_paths: list[str] = field(default_factory=list)
    next_action_hint: str = ""
    tokens_consumed: int = 0
    source: str = "agent"

    def __post_init__(self) -> None:
        if self.relevance not in RELEVANCE_VALUES:
            raise ValueError(f"unsupported relevance: {self.relevance}")
        if self.information_gain not in INFORMATION_GAIN_VALUES:
            raise ValueError(f"unsupported information gain: {self.information_gain}")
        if self.tokens_consumed < 0:
            raise ValueError("tokens_consumed must be non-negative")


@dataclass
class TaskState:
    task_id: str
    repo_id: str
    task: str
    total_budget: int
    navigation_budget: int
    expansion_budget: int
    navigation_tokens: int = 0
    expansion_tokens: int = 0
    seen: list[str] = field(default_factory=list)
    selected: list[str] = field(default_factory=list)
    expanded: dict[str, dict[str, Any]] = field(default_factory=dict)
    verified: list[str] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    discovery_tokens: int = 0
    discovery_queries: list[dict[str, Any]] = field(default_factory=list)
    discovery_hits: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    unresolved_hypotheses: list[str] = field(default_factory=list)
    stop_reason: Optional[str] = None
    stop_evidence: list[str] = field(default_factory=list)
    compact_phase: str = "legacy"
    external_call_count: int = 0
    verification_used: bool = False
    model_visible_budget: int = 0
    compact_limits: dict[str, int] = field(default_factory=dict)
    compact_marker_hops: dict[str, int] = field(default_factory=dict)
    compact_evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    compact_request_hashes: dict[str, str] = field(default_factory=dict)
    compact_requests: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "stopped" if self.stop_reason else "active"

    @property
    def consumed_tokens(self) -> int:
        return self.navigation_tokens + self.expansion_tokens

    @property
    def remaining_budget(self) -> int:
        return max(0, self.total_budget - self.consumed_tokens)

    @property
    def remaining_navigation_budget(self) -> int:
        return max(0, min(self.navigation_budget - self.navigation_tokens, self.remaining_budget))

    @property
    def remaining_expansion_budget(self) -> int:
        return max(0, min(self.expansion_budget - self.expansion_tokens, self.remaining_budget))

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.update(
            {
                "status": self.status,
                "consumed_tokens": self.consumed_tokens,
                "remaining_budget": self.remaining_budget,
                "remaining_navigation_budget": self.remaining_navigation_budget,
                "remaining_expansion_budget": self.remaining_expansion_budget,
            }
        )
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TaskState":
        fields = cls.__dataclass_fields__
        return cls(**{key: item for key, item in value.items() if key in fields})


class TaskStateStore:
    def __init__(self, provider: AstNavigationProvider):
        self.provider = provider

    def save(self, state: TaskState) -> None:
        payload = json.dumps(state.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with closing(sqlite3.connect(str(self.provider.workspace.database))) as connection:
            connection.execute(
                "INSERT INTO navigation_tasks(task_id, repo_id, task_text, status, state_json) "
                "VALUES(?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET "
                "status=excluded.status, state_json=excluded.state_json, updated_at=CURRENT_TIMESTAMP",
                (state.task_id, state.repo_id, state.task, state.status, payload),
            )
            connection.commit()

    def load(self, task_id: str) -> TaskState:
        with closing(sqlite3.connect(str(self.provider.workspace.database))) as connection:
            row = connection.execute(
                "SELECT repo_id, state_json FROM navigation_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if row[0] != self.provider.workspace.repo_id:
            raise ValueError("task belongs to a different repository")
        return TaskState.from_dict(json.loads(row[1]))

    def exists(self, task_id: str) -> bool:
        with closing(sqlite3.connect(str(self.provider.workspace.database))) as connection:
            row = connection.execute(
                "SELECT 1 FROM navigation_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        return row is not None


def _append_unique(values: list[str], additions: Iterable[str]) -> None:
    existing = set(values)
    for value in additions:
        if value and value not in existing:
            values.append(value)
            existing.add(value)


def _compact_marker(marker: Marker, score: float, components: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": marker.id,
        "path": marker.path,
        "symbol": marker.symbol,
        "kind": marker.kind,
        "lines": f"{marker.start_line}-{marker.end_line}",
        "signature": marker.signature,
        "evidence_hash": marker.evidence_hash,
        "expansion_tokens": marker.expansion_tokens,
        "score": round(score, 4),
        "ranking": components,
    }


def _identifier_feedback(payload: dict[str, Any], marker: Marker, tokens: int) -> Feedback:
    names: set[str] = set()
    for region in payload.get("regions", []):
        content = region.get("content", "")
        try:
            tree = ast.parse(textwrap.dedent(content))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    names.discard(marker.symbol.rsplit(".", 1)[-1])
    public_names = sorted(name for name in names if len(name) > 2 and not name.startswith("_"))[:24]
    return Feedback(
        marker_id=marker.id,
        relevance="uncertain",
        information_gain="high" if public_names else "low",
        new_symbols=public_names,
        next_action_hint="rank newly discovered symbols" if public_names else "request agent assessment",
        tokens_consumed=tokens,
        source="automatic",
    )


class TaskNavigator:
    def __init__(
        self,
        root: Path,
        data_dir: Optional[Path] = None,
        allowed_edge_kinds: Optional[set[str]] = None,
        discovery_sources: Optional[dict[str, Any]] = None,
    ):
        self.provider = AstNavigationProvider(root, data_dir)
        self.store = TaskStateStore(self.provider)
        self.allowed_edge_kinds = allowed_edge_kinds
        self.discovery_sources = discovery_sources if discovery_sources is not None else {
            "bounded-text": BoundedTextSource(self.provider.root)
        }

    def start(
        self,
        task: str,
        total_budget: int,
        navigation_budget: int,
        expansion_budget: int,
        task_id: Optional[str] = None,
        hypotheses: Iterable[str] = (),
    ) -> TaskState:
        if not task.strip():
            raise ValueError("task text is required")
        if min(total_budget, navigation_budget, expansion_budget) < 0:
            raise ValueError("budgets must be non-negative")
        if total_budget < 128 or navigation_budget + expansion_budget > total_budget:
            raise ValueError("budgets must fit within total_budget, which must be at least 128")
        resolved_task_id = task_id or uuid.uuid4().hex
        if self.store.exists(resolved_task_id):
            raise ValueError(f"task_id already exists: {resolved_task_id}")
        state = TaskState(
            task_id=resolved_task_id,
            repo_id=self.provider.workspace.repo_id,
            task=task.strip(),
            total_budget=total_budget,
            navigation_budget=navigation_budget,
            expansion_budget=expansion_budget,
            unresolved_hypotheses=list(dict.fromkeys(hypotheses)),
        )
        self.store.save(state)
        return state

    def _feedback_adjustments(
        self,
        state: TaskState,
        marker: Marker,
        neighbor_edges: list[tuple[Edge, str, str]],
    ) -> tuple[dict[str, float], list[dict[str, Any]]]:
        components = {
            "feedback_boost": 0.0,
            "relationship_boost": 0.0,
            # Merely appearing in an internal preview must not make a strong
            # candidate lose to an unseen low-value node. Selection/expansion
            # carry the meaningful repetition penalties.
            "already_seen_penalty": 0.0,
            "already_selected_penalty": -3.0 if marker.id in state.selected else 0.0,
            "already_expanded_penalty": 0.0,
            "irrelevant_penalty": 0.0,
            "discovery_boost": 0.0,
        }
        relationship_reasons: list[dict[str, Any]] = []
        agent_assessments = {
            raw["marker_id"]: raw["relevance"]
            for raw in state.feedback
            if raw.get("source") == "agent"
        }
        hits = state.discovery_hits.get(marker.id, [])
        if hits:
            # Discovery only proposes a route. It cannot override explicit
            # negative evidence, and its contribution is capped so common
            # text matches do not become an oracle.
            best = max(float(hit.get("score", 0.0)) for hit in hits)
            components["discovery_boost"] = round(min(14.0, 2.0 + best), 4)
        current_key = f"{marker.id}:{marker.evidence_hash}:{marker.start_line}-{marker.end_line}"
        expansion = state.expanded.get(current_key)
        if expansion and not expansion.get("truncated"):
            components["already_expanded_penalty"] = -100.0
        for raw in state.feedback:
            feedback = Feedback(**raw)
            symbol_tokens = (
                set().union(*(tokenize(value) for value in feedback.new_symbols))
                if feedback.new_symbols
                else set()
            )
            candidate_tokens = tokenize(marker.symbol) | tokenize(marker.signature)
            exact = any(
                value.lower() == marker.symbol.lower()
                or value.lower() == marker.symbol.rsplit(".", 1)[-1].lower()
                for value in feedback.new_symbols
            )
            discovery_weight = {
                "relevant": 1.0,
                # Automatically extracted names are hypotheses until the
                # agent verifies them. Giving uncertain names full weight let
                # every constructor/type name outrank a proven graph path.
                "uncertain": 0.2,
                "irrelevant": 0.0,
            }[feedback.relevance]
            if (
                feedback.source in {"automatic", "compact_structural"}
                and agent_assessments.get(feedback.marker_id) == "irrelevant"
            ):
                discovery_weight = 0.0
            raw_discovery_boost = 10.0 if exact else 2.0 * len(symbol_tokens & candidate_tokens)
            components["feedback_boost"] += discovery_weight * raw_discovery_boost
            if any(path == marker.path for path in feedback.new_paths):
                components["feedback_boost"] += 8.0
            if feedback.relevance == "relevant":
                for edge, neighbor_id, direction in neighbor_edges:
                    if feedback.marker_id != neighbor_id:
                        continue
                    if edge.kind == "references":
                        base_weight = {
                            "runtime_type_check": 12.0,
                            "registration": 8.0,
                            "decorator": 4.0,
                            "symbol_import": 3.0,
                            "type_annotation": 2.0,
                        }.get(edge.metadata.get("reference_kind", ""), 4.0)
                        # Prefer a candidate that points to the relevant node
                        # ("who references this?"). Following references made
                        # by the relevant node is useful, but much less
                        # discriminating and previously caused B015 to wander.
                        weight = base_weight if direction == "outgoing" else min(3.0, base_weight / 3.0)
                    else:
                        directional_weights = {
                            "calls": (12.0, 2.0),
                            # A base class can have hundreds of subclasses; a
                            # raw inheritance fan-out is weaker than a direct
                            # use, call, or runtime type check.
                            "inherits": (2.0, 4.0),
                            # contains is stored parent -> child. From a
                            # relevant method, moving to its parent class is a
                            # strong structural step.
                            "contains": (7.0 if marker.kind == "class" else 1.0, 5.0),
                            "imports": (1.5, 1.0),
                        }
                        outgoing, incoming = directional_weights.get(edge.kind, (1.0, 1.0))
                        weight = outgoing if direction == "outgoing" else incoming
                    boost = round(weight * edge.confidence, 4)
                    components["relationship_boost"] += boost
                    relationship_reasons.append(
                        {
                            "edge_kind": edge.kind,
                            "source_marker_id": feedback.marker_id,
                            "direction": direction,
                            "confidence": edge.confidence,
                            "boost": boost,
                        }
                    )
            if feedback.marker_id == marker.id and feedback.relevance == "irrelevant":
                components["irrelevant_penalty"] -= 40.0
                components["discovery_boost"] = 0.0
            elif feedback.marker_id == marker.id and feedback.relevance == "relevant":
                components["feedback_boost"] += 6.0
        components["relationship_boost"] = round(components["relationship_boost"], 4)
        return components, relationship_reasons

    def _active_query_terms(self, state: TaskState) -> tuple[str, ...]:
        values = [state.task]
        agent_assessments = {
            raw["marker_id"]: raw["relevance"]
            for raw in state.feedback
            if raw.get("source") == "agent"
        }
        for raw in state.feedback:
            if (
                raw.get("source") in {"automatic", "compact_structural"}
                and agent_assessments.get(raw["marker_id"]) != "relevant"
            ):
                continue
            if raw.get("relevance") == "irrelevant":
                continue
            values.extend(raw.get("new_symbols", []))
        return normalize_query_terms(values)

    def _rescue_eligible(self, state: TaskState) -> tuple[bool, str]:
        assessments = [
            raw.get("relevance")
            for raw in state.feedback
            if raw.get("source") == "agent"
        ]
        if len(assessments) >= 2 and assessments[-2:] == ["irrelevant", "irrelevant"]:
            return True, "two_consecutive_irrelevant_candidates"
        return False, "insufficient_failure_evidence"

    def discover(
        self,
        task_id: str,
        source_name: str = "bounded-text",
        budget_tokens: int = 400,
        limit: int = 8,
        trigger: str = "explicit",
    ) -> dict[str, Any]:
        state = self.store.load(task_id)
        if state.stop_reason:
            return {"status": "stopped", "task": state.to_dict()}
        source = self.discovery_sources.get(source_name)
        if source is None:
            raise KeyError(f"unknown discovery source: {source_name}")
        terms = self._active_query_terms(state)
        query_key = f"{source_name}:{'|'.join(terms)}"
        if any(item.get("query_key") == query_key for item in state.discovery_queries):
            return {
                "status": "duplicate_suppressed",
                "query_key": query_key,
                "tokens_consumed": 0,
                "task": state.to_dict(),
            }
        if len(state.discovery_queries) >= 2:
            return {
                "status": "external_discovery_exhausted",
                "tokens_consumed": 0,
                "task": state.to_dict(),
            }
        allocation = min(budget_tokens, state.remaining_navigation_budget, state.remaining_budget)
        if allocation < 64:
            return {"status": "insufficient_budget", "tokens_consumed": 0, "task": state.to_dict()}
        markers = self.provider.store.load_markers(self.provider.name)
        result: DiscoveryResult = source.discover(terms, markers, limit, allocation)
        payload = result.to_dict()
        consumed = estimate_tokens(payload)
        if consumed > allocation:
            payload = {
                "schema_version": 1,
                "provider": source_name,
                "status": "omitted",
                "reason": "discovery_metadata_exceeds_budget",
                "hits": [],
            }
            consumed = estimate_tokens(payload)
        state.navigation_tokens += consumed
        state.discovery_tokens += consumed
        query_record = {
            "query_key": query_key,
            "provider": source_name,
            "query_terms": list(terms),
            "trigger": trigger,
            "tokens": consumed,
            "elapsed_ms": payload.get("elapsed_ms", 0.0),
            "returned_candidates": len(payload.get("hits", [])),
        }
        state.discovery_queries.append(query_record)
        for hit in payload.get("hits", []):
            state.discovery_hits.setdefault(hit["marker_id"], []).append(hit)
        self.store.save(state)
        status = "completed" if payload.get("hits") else "no_profitable_candidate_source"
        return {
            "status": status,
            "discovery": payload,
            "query": query_record,
            "tokens_consumed": consumed,
            "task": state.to_dict(),
        }

    def rank(self, state: TaskState) -> list[tuple[float, Marker, dict[str, Any]]]:
        markers = self.provider.store.load_markers(self.provider.name)
        edges = self.provider.store.load_edges(self.provider.name)
        if self.allowed_edge_kinds is not None:
            edges = [edge for edge in edges if edge.kind in self.allowed_edge_kinds]
        degree: dict[str, float] = {}
        landmark_value: dict[str, float] = {}
        neighbors: dict[str, list[tuple[Edge, str, str]]] = {}
        for edge in edges:
            if edge.kind in {"contains", "imports"}:
                weight = edge_degree_weight(edge)
                degree[edge.source_id] = degree.get(edge.source_id, 0.0) + weight
                degree[edge.target_id] = degree.get(edge.target_id, 0.0) + weight
            else:
                if edge.kind == "references":
                    value = {
                        "runtime_type_check": 1.0,
                        "registration": 0.75,
                        "decorator": 0.25,
                        "symbol_import": 0.1,
                        "type_annotation": 0.05,
                    }.get(edge.metadata.get("reference_kind", ""), 0.05)
                else:
                    value = {"inherits": 0.15, "calls": 0.05}.get(edge.kind, 0.0)
                value *= edge.confidence
                landmark_value[edge.source_id] = landmark_value.get(edge.source_id, 0.0) + value
                landmark_value[edge.target_id] = landmark_value.get(edge.target_id, 0.0) + value
            neighbors.setdefault(edge.source_id, []).append((edge, edge.target_id, "outgoing"))
            neighbors.setdefault(edge.target_id, []).append((edge, edge.source_id, "incoming"))
        request = QueryRequest(
            task=state.task,
            budget_tokens=max(64, state.navigation_budget or 64),
            limit=100000,
        )
        ranked = []
        for marker in markers:
            base_score, base_components = self.provider._score(marker, request, degree.get(marker.id, 0))
            feedback_components, relationship_reasons = self._feedback_adjustments(
                state, marker, neighbors.get(marker.id, [])
            )
            feedback_components["semantic_landmark"] = round(
                min(2.0, math.log1p(landmark_value.get(marker.id, 0.0))), 4
            )
            components = {**base_components, **feedback_components}
            discovery_hits = state.discovery_hits.get(marker.id, [])
            if discovery_hits:
                components["discovery_reasons"] = [
                    {
                        "provider": hit.get("provider"),
                        "confidence": hit.get("confidence"),
                        "matched_terms": hit.get("matched_terms", []),
                    }
                    for hit in discovery_hits
                ]
            if relationship_reasons:
                components["relationship_reasons"] = relationship_reasons
            ranked.append((base_score + sum(feedback_components.values()), marker, components))
        ranked.sort(key=lambda item: (-item[0], item[1].expansion_tokens, item[1].path, item[1].symbol))
        return ranked

    def next(self, task_id: str, preview_limit: int = 8) -> dict[str, Any]:
        state = self.store.load(task_id)
        if state.stop_reason:
            return {"status": "stopped", "task": state.to_dict()}
        if state.remaining_navigation_budget < 32 or state.remaining_budget < 32:
            self.stop(task_id, "budget_exhausted")
            return {"status": "stopped", "task": self.store.load(task_id).to_dict()}
        discovery_payload = None
        eligible, trigger = self._rescue_eligible(state)
        if eligible and not state.discovery_queries and "bounded-text" in self.discovery_sources:
            discovery_payload = self.discover(
                task_id,
                "bounded-text",
                min(400, state.remaining_navigation_budget),
                trigger=trigger,
            )
            state = self.store.load(task_id)
        ranked = self.rank(state)
        _append_unique(state.seen, [marker.id for _, marker, _ in ranked[:preview_limit]])
        candidate_payload = None
        unselected_candidate_exists = False
        for score, marker, components in ranked:
            if marker.id in state.selected:
                continue
            evidence_key = f"{marker.id}:{marker.evidence_hash}:{marker.start_line}-{marker.end_line}"
            prior = state.expanded.get(evidence_key)
            if prior and not prior.get("truncated"):
                continue
            unselected_candidate_exists = True
            trial = _compact_marker(marker, score, components)
            cost = estimate_tokens(trial)
            if cost <= state.remaining_navigation_budget and cost <= state.remaining_budget:
                candidate_payload = trial
                state.navigation_tokens += cost
                _append_unique(state.selected, [marker.id])
                break
        if candidate_payload is None:
            if not ranked:
                state.stop_reason = "unsupported_language"
            elif unselected_candidate_exists:
                state.stop_reason = "budget_exhausted"
            else:
                state.stop_reason = "no_useful_candidate"
        self.store.save(state)
        result = {"status": state.status, "candidate": candidate_payload, "task": state.to_dict()}
        if discovery_payload is not None:
            result["discovery"] = discovery_payload.get("discovery", {})
            result["discovery_trigger"] = trigger
        return result

    def expand(self, task_id: str, marker_id: str, budget_tokens: int, force: bool = False) -> dict[str, Any]:
        state = self.store.load(task_id)
        if state.stop_reason:
            return {"status": "stopped", "task": state.to_dict()}
        marker = next(
            (item for item in self.provider.store.load_markers(self.provider.name) if item.id == marker_id),
            None,
        )
        if marker is None:
            raise KeyError(f"unknown marker_id: {marker_id}")
        evidence_key = f"{marker.id}:{marker.evidence_hash}:{marker.start_line}-{marker.end_line}"
        prior = state.expanded.get(evidence_key)
        if prior and not prior.get("truncated") and not force:
            return {
                "status": "duplicate_suppressed",
                "evidence_key": evidence_key,
                "tokens_consumed": 0,
                "task": state.to_dict(),
            }
        allocation = min(budget_tokens, state.remaining_expansion_budget, state.remaining_budget)
        if allocation < 128:
            state.stop_reason = "budget_exhausted"
            self.store.save(state)
            return {"status": "stopped", "task": state.to_dict()}
        path = self.provider.root / marker.path
        symbols = [] if marker.kind in {"file", "module"} else [marker.symbol]
        try:
            payload = route_read(
                path,
                state.task if not symbols else "",
                symbols,
                allocation,
                force_symbol=bool(symbols),
            )
        except (OSError, ValueError) as exc:
            # The structural index may expose nested/local definitions that a
            # source-region backend cannot address by qualified name. Keep the
            # task alive with explicit missing evidence instead of crashing.
            payload = {
                "schema_version": 1,
                "status": "unavailable",
                "marker_id": marker.id,
                "path": marker.path,
                "requested_symbol": marker.symbol,
                "budget_tokens": allocation,
                "reason": "symbol_region_unavailable",
                "error_type": exc.__class__.__name__,
                "truncated": False,
                "regions": [],
            }
        consumed = estimate_tokens(payload)
        if consumed > allocation:
            # A path/route metadata envelope can itself exceed a very small
            # allocation after all source regions have been removed. Return a
            # compact, explicit omission rather than either overspending or
            # crashing the navigation loop.
            payload = {
                "schema_version": 1,
                "status": "omitted",
                "marker_id": marker.id,
                "path": marker.path,
                "requested_region": f"{marker.start_line}-{marker.end_line}",
                "budget_tokens": allocation,
                "reason": "metadata_exceeds_budget",
                "truncated": True,
                "regions": [],
            }
            consumed = estimate_tokens(payload)
            if consumed > allocation:
                payload = {
                    "status": "omitted",
                    "reason": "budget_too_small",
                    "truncated": True,
                    "regions": [],
                }
                consumed = estimate_tokens(payload)
        state.expansion_tokens += consumed
        truncated = bool(payload.get("truncated")) or any(
            region.get("truncated") for region in payload.get("regions", [])
        )
        state.expanded[evidence_key] = {
            "marker_id": marker.id,
            "evidence_hash": marker.evidence_hash,
            "region": f"{marker.start_line}-{marker.end_line}",
            "tokens": consumed,
            "truncated": truncated,
            "force": force,
        }
        feedback = _identifier_feedback(payload, marker, consumed)
        state.feedback.append(asdict(feedback))
        if state.remaining_budget == 0 or state.remaining_expansion_budget == 0:
            state.stop_reason = "budget_exhausted"
        self.store.save(state)
        return {
            "status": state.status,
            "evidence_key": evidence_key,
            "tokens_consumed": consumed,
            "evidence": payload,
            "feedback": asdict(feedback),
            "task": state.to_dict(),
        }

    def feedback(
        self,
        task_id: str,
        feedback: Feedback,
        resolved: bool = False,
    ) -> TaskState:
        state = self.store.load(task_id)
        if state.stop_reason:
            raise ValueError("cannot add feedback to a stopped task")
        if not any(
            marker.id == feedback.marker_id
            for marker in self.provider.store.load_markers(self.provider.name)
        ):
            raise KeyError(f"unknown marker_id: {feedback.marker_id}")
        state.feedback.append(asdict(feedback))
        if feedback.relevance != "uncertain":
            _append_unique(state.verified, [feedback.marker_id])
        for hypothesis in feedback.hypotheses_supported + feedback.hypotheses_rejected:
            if hypothesis in state.unresolved_hypotheses:
                state.unresolved_hypotheses.remove(hypothesis)
        if resolved:
            state.stop_reason = "evidence_sufficient"
            _append_unique(state.stop_evidence, [feedback.marker_id])
        self.store.save(state)
        return state

    def stop(self, task_id: str, reason: str, evidence: Iterable[str] = ()) -> TaskState:
        if reason not in STOP_REASONS:
            raise ValueError(f"unsupported stop reason: {reason}")
        state = self.store.load(task_id)
        eligible, _ = self._rescue_eligible(state)
        if (
            reason == "low_expected_gain"
            and eligible
            and not state.discovery_queries
            and self.discovery_sources
            and state.remaining_navigation_budget >= 64
        ):
            raise ValueError("low_expected_gain is premature while a discovery rescue is eligible")
        if state.stop_reason and state.stop_reason != reason:
            raise ValueError(f"task already stopped: {state.stop_reason}")
        state.stop_reason = reason
        _append_unique(state.stop_evidence, evidence)
        self.store.save(state)
        return state


def emit(value: dict[str, Any], pretty: bool) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("root", type=Path)
    start_parser.add_argument("--task", required=True)
    start_parser.add_argument("--task-id")
    start_parser.add_argument("--total-budget", type=int, default=3000)
    start_parser.add_argument("--navigation-budget", type=int, default=800)
    start_parser.add_argument("--expansion-budget", type=int, default=2200)
    start_parser.add_argument("--hypothesis", action="append", default=[])

    for command in ("next", "status"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("root", type=Path)
        command_parser.add_argument("--task-id", required=True)

    discover_parser = subparsers.add_parser("discover")
    discover_parser.add_argument("root", type=Path)
    discover_parser.add_argument("--task-id", required=True)
    discover_parser.add_argument("--source", default="bounded-text")
    discover_parser.add_argument("--budget", type=int, default=400)
    discover_parser.add_argument("--limit", type=int, default=8)

    expand_parser = subparsers.add_parser("expand")
    expand_parser.add_argument("root", type=Path)
    expand_parser.add_argument("--task-id", required=True)
    expand_parser.add_argument("--marker-id", required=True)
    expand_parser.add_argument("--budget", type=int, default=1000)
    expand_parser.add_argument("--force", action="store_true")

    feedback_parser = subparsers.add_parser("feedback")
    feedback_parser.add_argument("root", type=Path)
    feedback_parser.add_argument("--task-id", required=True)
    feedback_parser.add_argument("--marker-id", required=True)
    feedback_parser.add_argument("--relevance", choices=sorted(RELEVANCE_VALUES), default="uncertain")
    feedback_parser.add_argument("--information-gain", choices=sorted(INFORMATION_GAIN_VALUES), default="low")
    feedback_parser.add_argument("--support", action="append", default=[])
    feedback_parser.add_argument("--reject", action="append", default=[])
    feedback_parser.add_argument("--new-symbol", action="append", default=[])
    feedback_parser.add_argument("--new-path", action="append", default=[])
    feedback_parser.add_argument("--next-action", default="")
    feedback_parser.add_argument("--resolved", action="store_true")

    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("root", type=Path)
    stop_parser.add_argument("--task-id", required=True)
    stop_parser.add_argument("--reason", required=True, choices=sorted(STOP_REASONS))
    stop_parser.add_argument("--evidence", action="append", default=[])

    args = parser.parse_args()
    navigator = TaskNavigator(args.root, args.data_dir)
    if args.command == "start":
        state = navigator.start(
            args.task,
            args.total_budget,
            args.navigation_budget,
            args.expansion_budget,
            args.task_id,
            args.hypothesis,
        )
        emit(state.to_dict(), args.pretty)
    elif args.command == "next":
        emit(navigator.next(args.task_id), args.pretty)
    elif args.command == "expand":
        emit(navigator.expand(args.task_id, args.marker_id, args.budget, args.force), args.pretty)
    elif args.command == "discover":
        emit(
            navigator.discover(args.task_id, args.source, args.budget, args.limit),
            args.pretty,
        )
    elif args.command == "feedback":
        state = navigator.feedback(
            args.task_id,
            Feedback(
                marker_id=args.marker_id,
                relevance=args.relevance,
                information_gain=args.information_gain,
                hypotheses_supported=args.support,
                hypotheses_rejected=args.reject,
                new_symbols=args.new_symbol,
                new_paths=args.new_path,
                next_action_hint=args.next_action,
            ),
            args.resolved,
        )
        emit(state.to_dict(), args.pretty)
    elif args.command == "stop":
        emit(navigator.stop(args.task_id, args.reason, args.evidence).to_dict(), args.pretty)
    else:
        emit(navigator.store.load(args.task_id).to_dict(), args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
