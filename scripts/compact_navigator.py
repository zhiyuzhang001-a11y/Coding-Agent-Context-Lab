#!/usr/bin/env python3
"""Run Task Navigator behind a two-call, budgeted compact context protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Optional

from ast_navigation_provider import estimate_tokens, tokenize
from discovery_sources import normalize_query_terms
from task_navigator import Feedback, TaskNavigator, TaskState


SCHEMA_VERSION = 1
COMPACT_PHASES = {"new", "navigating", "needs_verification", "completed"}
PROTOCOL_ERRORS = {
    "invalid_phase",
    "external_call_limit_reached",
    "stale_evidence",
    "invalid_feedback",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _stable_task_id(repo_id: str, request_id: str) -> str:
    return hashlib.sha256(f"compact:{repo_id}:{request_id}".encode()).hexdigest()[:32]


def _parse_lines(value: str) -> tuple[int, int]:
    start, _, end = value.partition("-")
    return int(start), int(end or start)


def _protocol_error(state: Optional[TaskState], error: str, message: str) -> dict[str, Any]:
    if error not in PROTOCOL_ERRORS:
        raise ValueError(f"unsupported protocol error: {error}")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "protocol_error",
        "error": error,
        "message": message,
        "task_id": state.task_id if state else None,
        "phase": state.compact_phase if state else "new",
        "external_call_count": state.external_call_count if state else 0,
        "stop_reason": state.stop_reason if state else None,
    }


class CompactNavigator:
    def __init__(self, root: Path, data_dir: Optional[Path] = None):
        self.navigator = TaskNavigator(root, data_dir)

    def _limits(
        self,
        max_steps: int,
        max_fanout: int,
        max_hops: int,
        max_source_reads: int,
        max_elapsed_ms: int,
    ) -> dict[str, int]:
        limits = {
            "max_steps": max_steps,
            "max_fanout": max_fanout,
            "max_hops": max_hops,
            "max_source_reads": max_source_reads,
            "max_elapsed_ms": max_elapsed_ms,
        }
        if min(limits.values()) < 1:
            raise ValueError("all compact limits must be positive")
        return limits

    def _evidence_from_expansion(
        self,
        state: TaskState,
        candidate: dict[str, Any],
        expansion: dict[str, Any],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        payload = expansion.get("evidence", {})
        ranking = candidate.get("ranking", {})
        signals = [
            name
            for name in (
                "task",
                "symbol",
                "path",
                "relationship_boost",
                "feedback_boost",
                "discovery_boost",
                "semantic_landmark",
            )
            if float(ranking.get(name, 0.0) or 0.0) > 0
        ]
        records: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for region in payload.get("regions", []):
            code = str(region.get("content", ""))
            if not code:
                continue
            lines = str(region.get("lines", candidate.get("lines", "1-1")))
            start_line, end_line = _parse_lines(lines)
            truncated = bool(payload.get("truncated") or region.get("truncated"))
            complete = not truncated
            evidence_id = hashlib.sha256(
                f"{candidate['id']}:{candidate.get('evidence_hash','')}:{lines}".encode()
            ).hexdigest()[:24]
            structural_confidence = (
                "high"
                if complete and ("task" in signals or "relationship_boost" in signals)
                else "medium"
                if signals
                else "low"
            )
            public = {
                "evidence_id": evidence_id,
                "path": candidate["path"],
                "symbol": region.get("name", candidate["symbol"]),
                "lines": lines,
                "hash": _sha256_text(code),
                "complete": complete,
                "truncated": truncated,
                "source": payload.get("route", {}).get("reason", "builtin_graph"),
                "reason": "selected_by_" + ("_and_".join(signals[:3]) if signals else "sparse_rank"),
                "structural_confidence": structural_confidence,
                "code": code,
            }
            private = {
                key: value for key, value in public.items() if key != "code"
            }
            private.update(
                {
                    "marker_id": candidate["id"],
                    "marker_evidence_hash": candidate.get("evidence_hash", ""),
                    "start_line": start_line,
                    "end_line": end_line,
                    "code_endswith_newline": code.endswith("\n"),
                    "internal_tokens": int(expansion.get("tokens_consumed", 0)),
                }
            )
            records.append((public, private))
        return records

    def _reconstruct_evidence(self, state: TaskState, evidence_id: str) -> dict[str, Any] | None:
        metadata = state.compact_evidence.get(evidence_id)
        if not metadata or metadata.get("truncated"):
            return None
        path = self.navigator.provider.root / metadata["path"]
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        code = "\n".join(lines[metadata["start_line"] - 1 : metadata["end_line"]])
        if metadata.get("code_endswith_newline"):
            code += "\n"
        if _sha256_text(code) != metadata["hash"]:
            return None
        public = {
            key: metadata[key]
            for key in (
                "evidence_id",
                "path",
                "symbol",
                "lines",
                "hash",
                "complete",
                "truncated",
                "source",
                "reason",
                "structural_confidence",
            )
        }
        public["code"] = code
        return public

    def _package(
        self,
        state: TaskState,
        decision: str,
        evidence: Iterable[dict[str, Any]],
        uncertainties: list[str],
        omissions: list[str],
        verification_request: Optional[dict[str, Any]],
        budget_snapshot: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        selected: list[dict[str, Any]] = []
        package = {
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "idempotent_replay": False,
            "task_id": state.task_id,
            "phase": state.compact_phase,
            "decision": decision,
            "evidence": selected,
            "why_it_matters": [],
            "confidence": "low",
            "uncertainties": list(dict.fromkeys(uncertainties))[:4],
            "omissions": list(dict.fromkeys(omissions))[:8],
            "budget": budget_snapshot
            or {
                "internal_exploration_budget": state.total_budget,
                "internal_exploration_tokens": state.consumed_tokens,
                "internal_remaining_tokens": state.remaining_budget,
                "model_visible_budget": state.model_visible_budget,
                "model_visible_tokens": 0,
            },
            "stop_reason": state.stop_reason,
            "verification_request": verification_request,
        }
        for item in evidence:
            trial = [*selected, item]
            package["evidence"] = trial
            if estimate_tokens(package) <= state.model_visible_budget:
                selected.append(item)
            else:
                package["omissions"].append(f"{item['evidence_id']}:model_visible_budget")
        package["evidence"] = selected
        package["why_it_matters"] = [
            {
                "evidence_id": item["evidence_id"],
                "reason": item["reason"],
                "structural_confidence": item["structural_confidence"],
            }
            for item in selected
        ]
        confidences = {item["structural_confidence"] for item in selected}
        package["confidence"] = (
            "high" if "high" in confidences and not package["uncertainties"] else "medium" if selected else "low"
        )
        for _ in range(4):
            visible = estimate_tokens(package)
            package["budget"]["model_visible_tokens"] = visible
        while estimate_tokens(package) > state.model_visible_budget and package["evidence"]:
            removed = package["evidence"].pop()
            package["why_it_matters"] = [
                item for item in package["why_it_matters"] if item["evidence_id"] != removed["evidence_id"]
            ]
            package["omissions"].append(f"{removed['evidence_id']}:package_envelope")
            package["budget"]["model_visible_tokens"] = estimate_tokens(package)
        package["budget"]["model_visible_tokens"] = estimate_tokens(package)
        if package["budget"]["model_visible_tokens"] > state.model_visible_budget:
            package["uncertainties"] = ["package_metadata_exceeds_model_visible_budget"]
            package["omissions"] = package["omissions"][:2]
            package["verification_request"] = None
            package["budget"]["model_visible_tokens"] = estimate_tokens(package)
        return package

    def _record_response(
        self,
        state: TaskState,
        request_id: str,
        package: dict[str, Any],
    ) -> None:
        state.compact_requests[request_id] = {
            "phase": package["phase"],
            "decision": package["decision"],
            "evidence_ids": [item["evidence_id"] for item in package["evidence"]],
            "uncertainties": package["uncertainties"],
            "omissions": package["omissions"],
            "stop_reason": package["stop_reason"],
            "verification_request": package["verification_request"],
            "budget": package["budget"],
            "response_sha256": _sha256_text(
                json.dumps(package, ensure_ascii=False, separators=(",", ":"))
            ),
        }
        self.navigator.store.save(state)

    def _replay(self, state: TaskState, request_id: str) -> dict[str, Any]:
        record = state.compact_requests[request_id]
        evidence: list[dict[str, Any]] = []
        for evidence_id in record["evidence_ids"]:
            rebuilt = self._reconstruct_evidence(state, evidence_id)
            if rebuilt is None:
                return _protocol_error(state, "stale_evidence", f"evidence changed: {evidence_id}")
            evidence.append(rebuilt)
        replay_state = replace(
            state,
            compact_phase=record["phase"],
            stop_reason=record["stop_reason"],
        )
        package = self._package(
            replay_state,
            record["decision"],
            evidence,
            list(record["uncertainties"]),
            list(record["omissions"]),
            record["verification_request"],
            dict(record["budget"]),
        )
        package["idempotent_replay"] = True
        return package

    def _structural_assessment(
        self,
        state: TaskState,
        candidate: dict[str, Any],
        expansion: dict[str, Any],
        public_evidence: list[dict[str, Any]],
    ) -> tuple[str, str, bool]:
        task_terms = set(normalize_query_terms([state.task]))
        code_tokens: set[str] = set()
        for item in public_evidence:
            code_tokens |= tokenize(item["code"])
        matched = task_terms & code_tokens
        ranking = candidate.get("ranking", {})
        structural_signal = any(
            float(ranking.get(name, 0.0) or 0.0) > 0
            for name in ("task", "relationship_boost", "feedback_boost", "discovery_boost")
        )
        automatic = expansion.get("feedback", {})
        discovered_symbols = automatic.get("new_symbols", [])
        complete = bool(public_evidence) and all(item["complete"] for item in public_evidence)
        relevant = bool(matched or structural_signal)
        relevance = "relevant" if relevant else "irrelevant"
        information_gain = "high" if discovered_symbols else "medium" if relevant else "low"
        symbol_terms = set(
            normalize_query_terms([candidate.get("symbol", "").rsplit(".", 1)[-1]])
        )
        explicit_symbol = bool(symbol_terms) and symbol_terms.issubset(task_terms)
        sufficient = explicit_symbol and complete and not discovered_symbols
        return relevance, information_gain, sufficient

    @staticmethod
    def _candidate_hop(state: TaskState, candidate: dict[str, Any]) -> int:
        reasons = candidate.get("ranking", {}).get("relationship_reasons", [])
        source_hops = [
            state.compact_marker_hops.get(str(reason.get("source_marker_id", "")), 0)
            for reason in reasons
            if reason.get("source_marker_id")
        ]
        return min(source_hops) + 1 if source_hops else 0

    def navigate(
        self,
        task: str,
        request_id: str,
        total_budget: int = 3000,
        navigation_budget: int = 800,
        expansion_budget: int = 2200,
        model_visible_budget: int = 1600,
        max_steps: int = 4,
        max_fanout: int = 8,
        max_hops: int = 2,
        max_source_reads: int = 4,
        max_elapsed_ms: int = 5000,
    ) -> dict[str, Any]:
        if not request_id.strip():
            raise ValueError("request_id is required")
        if model_visible_budget < 256:
            raise ValueError("model_visible_budget must be at least 256")
        limits = self._limits(max_steps, max_fanout, max_hops, max_source_reads, max_elapsed_ms)
        request_hash = _sha256_text(
            json.dumps(
                {
                    "task": task.strip(),
                    "total_budget": total_budget,
                    "navigation_budget": navigation_budget,
                    "expansion_budget": expansion_budget,
                    "model_visible_budget": model_visible_budget,
                    "limits": limits,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        task_id = _stable_task_id(self.navigator.provider.workspace.repo_id, request_id)
        if self.navigator.store.exists(task_id):
            state = self.navigator.store.load(task_id)
            if request_id in state.compact_requests:
                if state.compact_request_hashes.get(request_id) != request_hash:
                    return _protocol_error(
                        state, "invalid_feedback", "request_id reused with a different navigate payload"
                    )
                return self._replay(state, request_id)
            return _protocol_error(state, "invalid_phase", "compact_navigate already accepted")
        self.navigator.provider.index()
        state = self.navigator.start(
            task,
            total_budget,
            navigation_budget,
            expansion_budget,
            task_id=task_id,
        )
        state.compact_phase = "navigating"
        state.external_call_count = 1
        state.model_visible_budget = model_visible_budget
        state.compact_limits = limits
        state.compact_request_hashes[request_id] = request_hash
        self.navigator.store.save(state)

        started = time.perf_counter()
        public_evidence: list[dict[str, Any]] = []
        omissions: list[str] = []
        uncertainties: list[str] = []
        source_reads = 0
        sufficient = False
        navigate_step_limit = max(1, max_steps // 4)
        navigate_source_limit = max(1, max_source_reads // 4)
        for _ in range(navigate_step_limit):
            if (time.perf_counter() - started) * 1000 >= max_elapsed_ms:
                uncertainties.append("max_elapsed_ms_reached")
                break
            if source_reads >= navigate_source_limit:
                uncertainties.append("max_source_reads_reached")
                break
            choice = self.navigator.next(task_id, preview_limit=max_fanout)
            candidate = choice.get("candidate")
            if not candidate:
                uncertainties.append("no_additional_candidate")
                break
            candidate_hop = self._candidate_hop(self.navigator.store.load(task_id), candidate)
            if candidate_hop > max_hops:
                omissions.append(f"{candidate['id']}:max_hops")
                continue
            allocation = min(650, self.navigator.store.load(task_id).remaining_expansion_budget)
            expansion = self.navigator.expand(task_id, candidate["id"], allocation)
            source_reads += 1
            state = self.navigator.store.load(task_id)
            state.compact_marker_hops[candidate["id"]] = candidate_hop
            records = self._evidence_from_expansion(state, candidate, expansion)
            current_public = [public for public, _ in records if public["complete"]]
            for public, private in records:
                if public["complete"]:
                    state.compact_evidence[public["evidence_id"]] = private
                    public_evidence.append(public)
                else:
                    omissions.append(f"{public['evidence_id']}:truncated")
            self.navigator.store.save(state)
            relevance, information_gain, sufficient = self._structural_assessment(
                state, candidate, expansion, current_public
            )
            feedback = Feedback(
                marker_id=candidate["id"],
                relevance=relevance,
                information_gain=information_gain,
                new_symbols=list(expansion.get("feedback", {}).get("new_symbols", [])),
                next_action_hint="compact structural assessment",
                tokens_consumed=int(expansion.get("tokens_consumed", 0)),
                source="compact_structural",
            )
            if not state.stop_reason:
                self.navigator.feedback(task_id, feedback, resolved=sufficient)
            state = self.navigator.store.load(task_id)
            if sufficient or state.stop_reason:
                break

        state = self.navigator.store.load(task_id)
        if state.stop_reason:
            state.compact_phase = "completed"
            decision = "target_context_found" if state.stop_reason == "evidence_sufficient" else "navigation_stopped"
            verification_request = None
        elif public_evidence:
            state.compact_phase = "needs_verification"
            decision = "verification_required"
            uncertainties.append("semantic_relevance_requires_codex_confirmation")
            verification_request = {
                "evidence_refs": [
                    {"evidence_id": item["evidence_id"], "hash": item["hash"]}
                    for item in public_evidence[:4]
                ],
                "max_missing_questions": 2,
                "accepted_fields": [
                    "accepted_evidence",
                    "rejected_evidence",
                    "uncertain_evidence",
                    "missing_questions",
                ],
            }
        else:
            state.stop_reason = state.stop_reason or "source_exhausted"
            state.compact_phase = "completed"
            decision = "no_actionable_context"
            verification_request = None
        self.navigator.store.save(state)
        package = self._package(
            state,
            decision,
            public_evidence,
            uncertainties,
            omissions,
            verification_request,
        )
        self._record_response(state, request_id, package)
        return package

    def verify(
        self,
        task_id: str,
        request_id: str,
        accepted_evidence: Iterable[str] = (),
        rejected_evidence: Iterable[str] = (),
        uncertain_evidence: Iterable[str] = (),
        missing_questions: Iterable[str] = (),
    ) -> dict[str, Any]:
        state = self.navigator.store.load(task_id)
        try:
            accepted = _parse_evidence_values(accepted_evidence)
            rejected = _parse_evidence_values(rejected_evidence)
            uncertain = _parse_evidence_values(uncertain_evidence)
        except ValueError as exc:
            return _protocol_error(state, "invalid_feedback", str(exc))
        questions = [value.strip() for value in missing_questions if value.strip()]
        request_hash = _sha256_text(
            json.dumps(
                {
                    "accepted": sorted(accepted.items()),
                    "rejected": sorted(rejected.items()),
                    "uncertain": sorted(uncertain.items()),
                    "missing_questions": questions,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        if request_id in state.compact_requests:
            if state.compact_request_hashes.get(request_id) != request_hash:
                return _protocol_error(
                    state, "invalid_feedback", "request_id reused with a different verify payload"
                )
            return self._replay(state, request_id)
        if state.external_call_count >= 2:
            return _protocol_error(state, "external_call_limit_reached", "compact call limit reached")
        if state.compact_phase != "needs_verification":
            return _protocol_error(state, "invalid_phase", "compact_verify requires needs_verification")
        groups = [set(accepted), set(rejected), set(uncertain)]
        if any(groups[index] & groups[other] for index in range(3) for other in range(index + 1, 3)):
            return _protocol_error(state, "invalid_feedback", "evidence groups must be disjoint")
        referenced = set().union(*groups)
        if not referenced.issubset(state.compact_evidence):
            return _protocol_error(state, "invalid_feedback", "feedback references unknown evidence")
        if len(questions) > 2 or any(len(value) > 240 for value in questions):
            return _protocol_error(state, "invalid_feedback", "missing_questions exceeds limits")

        for evidence_id, supplied_hash in [
            *accepted.items(),
            *rejected.items(),
            *uncertain.items(),
        ]:
            if state.compact_evidence[evidence_id]["hash"] != supplied_hash:
                return _protocol_error(state, "stale_evidence", f"evidence changed: {evidence_id}")
            if self._reconstruct_evidence(state, evidence_id) is None:
                return _protocol_error(state, "stale_evidence", f"evidence changed: {evidence_id}")

        state.external_call_count += 1
        state.verification_used = True
        state.compact_request_hashes[request_id] = request_hash
        self.navigator.store.save(state)
        for evidence_id, relevance in [
            *((value, "relevant") for value in accepted),
            *((value, "irrelevant") for value in rejected),
            *((value, "uncertain") for value in uncertain),
        ]:
            metadata = state.compact_evidence[evidence_id]
            if not state.stop_reason:
                self.navigator.feedback(
                    task_id,
                    Feedback(
                        marker_id=metadata["marker_id"],
                        relevance=relevance,
                        information_gain="high" if relevance == "relevant" else "low",
                        next_action_hint="batched compact semantic feedback",
                        source="agent",
                    ),
                )
            state = self.navigator.store.load(task_id)

        supplemental_evidence: list[dict[str, Any]] = []
        state = self.navigator.store.load(task_id)
        limits = state.compact_limits
        started = time.perf_counter()
        while (
            (not accepted or questions)
            and not state.stop_reason
            and len(state.selected) < limits.get("max_steps", 1)
            and len(state.expanded) < limits.get("max_source_reads", 1)
            and state.remaining_expansion_budget > 0
            and (time.perf_counter() - started) * 1000 < limits.get("max_elapsed_ms", 1)
        ):
            choice = self.navigator.next(task_id, preview_limit=limits.get("max_fanout", 1))
            candidate = choice.get("candidate")
            state = self.navigator.store.load(task_id)
            if not candidate:
                break
            candidate_hop = self._candidate_hop(state, candidate)
            if candidate_hop > limits.get("max_hops", 1):
                continue
            allocation = min(650, state.remaining_expansion_budget)
            expansion = self.navigator.expand(task_id, candidate["id"], allocation)
            state = self.navigator.store.load(task_id)
            state.compact_marker_hops[candidate["id"]] = candidate_hop
            records = self._evidence_from_expansion(state, candidate, expansion)
            current_supplement: list[dict[str, Any]] = []
            for public, private in records:
                if public["complete"]:
                    state.compact_evidence[public["evidence_id"]] = private
                    supplemental_evidence.append(public)
                    current_supplement.append(public)
            self.navigator.store.save(state)
            relevance, information_gain, _ = self._structural_assessment(
                state, candidate, expansion, current_supplement
            )
            if not state.stop_reason:
                self.navigator.feedback(
                    task_id,
                    Feedback(
                        marker_id=candidate["id"],
                        relevance=relevance,
                        information_gain=information_gain,
                        new_symbols=list(expansion.get("feedback", {}).get("new_symbols", [])),
                        next_action_hint="compact verification supplement",
                        tokens_consumed=int(expansion.get("tokens_consumed", 0)),
                        source="compact_structural",
                    ),
                )
            state = self.navigator.store.load(task_id)

        state = self.navigator.store.load(task_id)
        final_evidence: list[dict[str, Any]] = list(reversed(supplemental_evidence))
        for evidence_id in [*accepted, *uncertain]:
            rebuilt = self._reconstruct_evidence(state, evidence_id)
            if rebuilt is not None:
                final_evidence.append(rebuilt)
        if accepted and not questions:
            reason = "evidence_sufficient"
            evidence_markers = [state.compact_evidence[value]["marker_id"] for value in accepted]
        elif state.remaining_budget == 0:
            reason = "budget_exhausted"
            evidence_markers = []
        else:
            reason = "verification_inconclusive"
            evidence_markers = []
        if not state.stop_reason:
            self.navigator.stop(task_id, reason, evidence_markers)
        state = self.navigator.store.load(task_id)
        state.compact_phase = "completed"
        self.navigator.store.save(state)
        package = self._package(
            state,
            "target_context_confirmed" if accepted and not questions else "verification_inconclusive",
            final_evidence,
            [] if accepted and not questions else [*questions, "additional semantic confirmation required"],
            [f"{value}:rejected" for value in rejected],
            None,
        )
        self._record_response(state, request_id, package)
        return package


def _parse_evidence_values(values: Iterable[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        evidence_id, separator, evidence_hash = value.partition("=")
        if not separator or not evidence_id or not evidence_hash:
            raise ValueError("evidence feedback must use evidence_id=hash")
        if evidence_id in parsed and parsed[evidence_id] != evidence_hash:
            raise ValueError("evidence feedback contains conflicting hashes")
        parsed[evidence_id] = evidence_hash
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    navigate = subparsers.add_parser("navigate")
    navigate.add_argument("root", type=Path)
    navigate.add_argument("--task", required=True)
    navigate.add_argument("--request-id", required=True)
    navigate.add_argument("--total-budget", type=int, default=3000)
    navigate.add_argument("--navigation-budget", type=int, default=800)
    navigate.add_argument("--expansion-budget", type=int, default=2200)
    navigate.add_argument("--model-visible-budget", type=int, default=1600)
    navigate.add_argument("--max-steps", type=int, default=4)
    navigate.add_argument("--max-fanout", type=int, default=8)
    navigate.add_argument("--max-hops", type=int, default=2)
    navigate.add_argument("--max-source-reads", type=int, default=4)
    navigate.add_argument("--max-elapsed-ms", type=int, default=5000)

    verify = subparsers.add_parser("verify")
    verify.add_argument("root", type=Path)
    verify.add_argument("--task-id", required=True)
    verify.add_argument("--request-id", required=True)
    verify.add_argument("--accept", action="append", default=[])
    verify.add_argument("--reject", action="append", default=[])
    verify.add_argument("--uncertain", action="append", default=[])
    verify.add_argument("--missing-question", action="append", default=[])

    args = parser.parse_args()
    compact = CompactNavigator(args.root, args.data_dir)
    if args.command == "navigate":
        result = compact.navigate(
            args.task,
            args.request_id,
            args.total_budget,
            args.navigation_budget,
            args.expansion_budget,
            args.model_visible_budget,
            args.max_steps,
            args.max_fanout,
            args.max_hops,
            args.max_source_reads,
            args.max_elapsed_ms,
        )
    else:
        result = compact.verify(
            args.task_id,
            args.request_id,
            args.accept,
            args.reject,
            args.uncertain,
            args.missing_question,
        )
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0 if result.get("status") != "protocol_error" else 2


if __name__ == "__main__":
    raise SystemExit(main())
