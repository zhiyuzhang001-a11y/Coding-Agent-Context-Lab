#!/usr/bin/env python3
"""Parse Codex JSONL without double-counting cumulative usage or storing source text."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


SMART_READ_MARKERS = (
    "budgeted-code-reading",
    "context_router.py",
    "navigation_map.py",
    "smart_read.py",
    "task_navigator.py",
    "compact_navigator.py",
)
READ_COMMANDS = {"cat", "grep", "head", "nl", "rg", "sed", "tail", "wc"}
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


@dataclass(frozen=True)
class UsageCandidate:
    sequence: int
    source: str
    cumulative: bool
    values: dict[str, int]


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    invalid_lines = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines += 1
                continue
            if isinstance(value, dict):
                events.append(value)
            else:
                invalid_lines += 1
    return events, invalid_lines


def _token_values(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    tokens: dict[str, int] = {}
    for field in TOKEN_FIELDS:
        candidate = value.get(field)
        if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate >= 0:
            tokens[field] = candidate
    if "input_tokens" not in tokens or "output_tokens" not in tokens:
        return None
    return tokens


def usage_candidates(events: Iterable[dict[str, Any]]) -> list[UsageCandidate]:
    candidates: list[UsageCandidate] = []
    for sequence, event in enumerate(events):
        payload = event.get("payload")
        if (
            event.get("type") == "event_msg"
            and isinstance(payload, dict)
            and payload.get("type") == "token_count"
        ):
            info = payload.get("info")
            usage = info.get("total_token_usage") if isinstance(info, dict) else None
            values = _token_values(usage)
            if values is not None:
                candidates.append(UsageCandidate(sequence, "rollout.token_count", True, values))
                continue

        if event.get("type") in {"turn.completed", "turn_completed"}:
            values = _token_values(event.get("usage"))
            if values is None and isinstance(payload, dict):
                values = _token_values(payload.get("usage"))
            if values is not None:
                candidates.append(UsageCandidate(sequence, "exec.turn.completed", True, values))
    return candidates


def summarize_usage(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    candidates = usage_candidates(events)
    if not candidates:
        return {
            "status": "missing",
            "candidate_count": 0,
            "errors": ["no cumulative usage event found"],
        }

    final = candidates[-1]
    values = dict(final.values)
    derived_total = "total_tokens" not in values
    if derived_total:
        values["total_tokens"] = values["input_tokens"] + values["output_tokens"]

    errors: list[str] = []
    if values["total_tokens"] != values["input_tokens"] + values["output_tokens"]:
        errors.append("total_tokens must equal input_tokens + output_tokens")
    if values.get("cached_input_tokens", 0) > values["input_tokens"]:
        errors.append("cached_input_tokens exceeds input_tokens")
    if values.get("reasoning_output_tokens", 0) > values["output_tokens"]:
        errors.append("reasoning_output_tokens exceeds output_tokens")

    previous: dict[str, int] | None = None
    monotonic = True
    for candidate in candidates:
        if not candidate.cumulative:
            continue
        if previous is not None:
            for field in ("input_tokens", "output_tokens", "total_tokens"):
                current = candidate.values.get(field)
                old = previous.get(field)
                if current is not None and old is not None and current < old:
                    monotonic = False
        previous = candidate.values
    if not monotonic:
        errors.append("cumulative usage events are not monotonic")

    return {
        "status": "valid" if not errors else "invalid",
        "source": final.source,
        "candidate_count": len(candidates),
        "selection": "last cumulative event; intermediate events are not summed",
        "total_derived": derived_total,
        "cached_input_is_subset": True,
        "reasoning_output_is_subset": True,
        **values,
        "errors": errors,
    }


def _walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _event_text(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, separators=(",", ":"))


def _action_text(event: dict[str, Any]) -> str:
    command_item = _command_item(event)
    if command_item is not None:
        return command_item[0]
    if event.get("type") == "response_item":
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("type") in {
            "custom_tool_call",
            "function_call",
            "local_shell_call",
        }:
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    item = event.get("item")
    if isinstance(item, dict) and item.get("type") in {
        "tool_call",
        "mcp_tool_call",
        "command_execution",
    }:
        return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
    return ""


def smart_read_marker_counts(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {marker: 0 for marker in SMART_READ_MARKERS}
    for event in events:
        text = _action_text(event).lower()
        if not text:
            continue
        for marker in SMART_READ_MARKERS:
            if marker.lower() in text:
                counts[marker] += 1
    return {marker: count for marker, count in counts.items() if count}


def evaluate_treatment(events: Iterable[dict[str, Any]], arm: str) -> dict[str, Any]:
    event_list = list(events)
    counts = smart_read_marker_counts(event_list)
    marker_events = sum(counts.values())
    smart_command_failures = 0
    manager_write_failures = 0
    for event in event_list:
        item = _completed_command(event)
        if item is None:
            continue
        command = str(item.get("command", ""))
        if not any(marker.lower() in command.lower() for marker in SMART_READ_MARKERS):
            continue
        if item.get("exit_code") not in {None, 0}:
            smart_command_failures += 1
        output = str(item.get("aggregated_output", item.get("output", "")))
        if "write_failed" in output or "permissionerror" in output.lower():
            manager_write_failures += 1
    if arm == "native":
        compliant = marker_events == 0
        reason = "no Smart Read marker observed" if compliant else "Smart Read marker observed in Native arm"
    elif arm == "m2d":
        compliant = marker_events > 0 and smart_command_failures == 0 and manager_write_failures == 0
        if marker_events == 0:
            reason = "no Smart Read marker observed in M2d arm"
        elif smart_command_failures:
            reason = "Smart Read command failed"
        elif manager_write_failures:
            reason = "Smart Read data/cache write failed"
        else:
            reason = "Smart Read marker observed without integration failure"
    else:
        raise ValueError(f"unsupported arm: {arm}")
    return {
        "arm": arm,
        "compliant": compliant,
        "reason": reason,
        "marker_event_count": marker_events,
        "markers": counts,
        "smart_command_failures": smart_command_failures,
        "manager_write_failures": manager_write_failures,
    }


def _completed_command(event: dict[str, Any]) -> dict[str, Any] | None:
    item: Any = None
    if event.get("type") in {"item.completed", "item_completed"}:
        item = event.get("item")
    else:
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("type") in {
            "item.completed",
            "item_completed",
        }:
            item = payload.get("item")
    if not isinstance(item, dict) or item.get("type") not in {
        "command_execution",
        "command_execution_output",
    }:
        return None
    return item


def _command_item(event: dict[str, Any]) -> tuple[str, str] | None:
    item = _completed_command(event)
    if item is None:
        return None
    command = item.get("command")
    output = item.get("aggregated_output", item.get("output", ""))
    return (str(command or ""), str(output or ""))


def _rollout_tool_output(event: dict[str, Any]) -> str | None:
    if event.get("type") != "response_item":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("type") not in {
        "custom_tool_call_output",
        "function_call_output",
    }:
        return None
    output = payload.get("output")
    if isinstance(output, str):
        return output
    texts: list[str] = []
    for value in _walk(output):
        if isinstance(value, dict) and isinstance(value.get("text"), str):
            texts.append(value["text"])
    return "\n".join(texts)


def _read_like_command(command: str) -> bool:
    lowered = command.lower()
    if any(marker.lower() in lowered for marker in SMART_READ_MARKERS):
        return True
    words = lowered.replace("|", " ").replace(";", " ").split()
    return any(word.rsplit("/", 1)[-1] in READ_COMMANDS for word in words)


def summarize_tools(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    outputs: list[tuple[str, bool]] = []
    command_calls = 0
    for event in events:
        command_item = _command_item(event)
        if command_item is not None:
            command, output = command_item
            command_calls += 1
            outputs.append((output, _read_like_command(command)))
            continue
        output = _rollout_tool_output(event)
        if output is not None:
            outputs.append((output, False))

    hashes: dict[str, int] = {}
    result_tokens = 0
    read_result_tokens = 0
    for output, read_like in outputs:
        result_tokens += (len(output) + 3) // 4
        if read_like:
            read_result_tokens += (len(output) + 3) // 4
        digest = hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest()
        hashes[digest] = hashes.get(digest, 0) + 1
    duplicates = sum(count - 1 for count in hashes.values() if count > 1)
    return {
        "completed_output_events": len(outputs),
        "command_calls": command_calls,
        "estimated_tool_result_tokens": result_tokens,
        "estimated_read_result_tokens": read_result_tokens,
        "duplicate_result_count": duplicates,
        "token_count_method": "chars_div_4_v1",
    }


def parse_codex_jsonl(path: Path, arm: str) -> dict[str, Any]:
    events, invalid_lines = load_jsonl(path)
    return {
        "schema_version": 1,
        "event_count": len(events),
        "invalid_line_count": invalid_lines,
        "usage": summarize_usage(events),
        "tools": summarize_tools(events),
        "treatment": evaluate_treatment(events, arm),
    }
