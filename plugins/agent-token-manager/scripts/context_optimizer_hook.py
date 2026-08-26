#!/usr/bin/env python3
"""CO-0 PostToolUse feasibility hook with strict, fail-open matching."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from python_syntax_slice import SliceResult, build_slice


SCHEMA_VERSION = 1
DEFAULT_MIN_CHARS = 4000
DEFAULT_VISIBLE_CHARS = 1600
DEFAULT_CO1_VISIBLE_CHARS = 4000
SUPPORTED_SHELL_TOOLS = {"bash", "exec_command", "shell"}
SHELL_CONTROL_CHARS = frozenset("|;&<>`")
RANGE_PATTERN = re.compile(r"^[1-9][0-9]*,[1-9][0-9]*p$")
GLOB_CHARS = frozenset("*?[")
STATUSES = {
    "optimized",
    "passthrough_unsupported",
    "passthrough_not_beneficial",
    "passthrough_observe",
    "fallback_optimizer_error",
    "fallback_budget_or_timeout",
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def env_int(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name, "")
    try:
        return max(minimum, int(raw)) if raw else default
    except ValueError:
        return default


def command_from_input(tool_input: Any) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command", tool_input.get("cmd"))
    return command if isinstance(command, str) else None


def is_literal_path(value: str) -> bool:
    return value != "-" and not value.startswith("-") and not any(character in value for character in GLOB_CHARS)


def classify_command(tool_name: str, tool_input: Any) -> tuple[str | None, str]:
    """Return a strict whitelist kind and a privacy-safe reason."""
    if tool_name.lower() not in SUPPORTED_SHELL_TOOLS:
        return None, "unsupported_tool"
    command = command_from_input(tool_input)
    if not command:
        return None, "missing_command"
    if "\n" in command or "\r" in command:
        return None, "multiline_command"
    if any(character in command for character in SHELL_CONTROL_CHARS) or "$(" in command:
        return None, "shell_control_syntax"
    try:
        words = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return None, "invalid_shell_quoting"
    if not words:
        return None, "empty_command"

    executable = words[0].rsplit("/", 1)[-1]
    if executable == "cat":
        path = words[1] if len(words) == 2 else words[2] if len(words) == 3 and words[1] == "--" else None
        if path and is_literal_path(path):
            return "cat", "strict_cat"
        return None, "unsupported_cat_shape"

    if executable == "sed":
        if len(words) == 4 and words[1] == "-n" and RANGE_PATTERN.fullmatch(words[2]):
            start_text, end_and_p = words[2].split(",", 1)
            end_text = end_and_p[:-1]
            if int(start_text) <= int(end_text) and is_literal_path(words[3]):
                return "sed_range", "strict_sed_range"
        return None, "unsupported_sed_shape"

    if executable == "rg":
        if len(words) == 3 and not words[1].startswith("-") and is_literal_path(words[2]):
            return "rg", "strict_rg"
        return None, "unsupported_rg_shape"

    basenames = {word.rsplit("/", 1)[-1] for word in words}
    if {"smart_read.py", "context_router.py"} & basenames and "--symbol" in words:
        return "known_symbol", "manager_symbol_read"
    return None, "command_not_whitelisted"


def parsed_words(tool_input: Any) -> list[str] | None:
    command = command_from_input(tool_input)
    if not command or "\n" in command or "\r" in command:
        return None
    if any(character in command for character in SHELL_CONTROL_CHARS) or "$(" in command:
        return None
    try:
        return shlex.split(command, comments=False, posix=True)
    except ValueError:
        return None


def syntax_request(kind: str, tool_input: Any) -> dict[str, object] | None:
    words = parsed_words(tool_input)
    if not words:
        return None
    if kind == "sed_range" and len(words) == 4 and words[3].endswith(".py"):
        start_text, end_and_p = words[2].split(",", 1)
        return {"path": words[3], "start_line": int(start_text), "end_line": int(end_and_p[:-1])}
    if kind != "known_symbol" or words.count("--symbol") != 1:
        return None
    script_indexes = [
        index for index, word in enumerate(words) if word.rsplit("/", 1)[-1] in {"smart_read.py", "context_router.py"}
    ]
    symbol_index = words.index("--symbol")
    if len(script_indexes) != 1 or symbol_index + 1 >= len(words):
        return None
    script_index = script_indexes[0]
    if script_index + 1 >= len(words):
        return None
    path = words[script_index + 1]
    symbol_values: list[str] = []
    for word in words[symbol_index + 1 :]:
        if word.startswith("-"):
            break
        symbol_values.append(word)
    if len(symbol_values) != 1:
        return None
    symbol = symbol_values[0]
    if not is_literal_path(path) or not path.endswith(".py") or symbol.startswith("-"):
        return None
    return {"path": path, "symbol": symbol}


def resolve_request_path(event: dict[str, Any], value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    cwd = event.get("cwd")
    base = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    return base / path


def response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        for key in ("output", "aggregated_output", "stdout", "result"):
            value = response.get(key)
            if isinstance(value, str):
                return value
    return json.dumps(response, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def clipped_prefix(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    newline = clipped.rfind("\n")
    return clipped[:newline] if newline >= limit // 2 else clipped


def compress_payload(kind: str, original: str, visible_chars: int) -> str:
    header = (
        "[Smart Read CO-0 optimized result]\n"
        f"kind: {kind}\n"
        f"original_chars: {len(original)}\n"
        f"original_sha256: {sha256_text(original)}\n"
    )
    room = max(64, visible_chars - len(header) - 80)
    preview = clipped_prefix(original, room)
    omitted = max(0, len(original) - len(preview))
    return f"{header}omitted_chars: {omitted}\npreview:\n{preview}\n[CO-0 preview ended]"


def base_record(
    event: dict[str, Any], kind: str | None, status: str, reason: str, *, mode: str | None = None
) -> dict[str, Any]:
    record = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": event.get("session_id"),
        "turn_id": event.get("turn_id"),
        "tool_use_id": event.get("tool_use_id"),
        "tool_name": str(event.get("tool_name", "unknown")),
        "mode": (mode or os.environ.get("AGENT_TOKEN_MANAGER_CO0_MODE", "observe")).lower(),
        "status": status,
        "command_kind": kind,
        "reason": reason,
    }
    transcript_path = event.get("transcript_path")
    if os.environ.get("AGENT_TOKEN_MANAGER_CO0_RECORD_TRANSCRIPT_PATH") == "1" and isinstance(
        transcript_path, str
    ):
        record["transcript_path"] = transcript_path
    if status.startswith("fallback_"):
        record["fallback_reason"] = reason
    return record


def evaluate_event(
    event: dict[str, Any],
    *,
    mode: str | None = None,
    min_chars: int | None = None,
    visible_chars: int | None = None,
    syntax_mode: str | None = None,
    syntax_budget_chars: int | None = None,
    force_failure: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return an audit record and optional PostToolUse replacement decision."""
    selected_mode = (mode or os.environ.get("AGENT_TOKEN_MANAGER_CO0_MODE", "observe")).lower()
    if force_failure is None and os.environ.get("AGENT_TOKEN_MANAGER_CO0_TEST_MODE") == "1":
        injected = os.environ.get("AGENT_TOKEN_MANAGER_CO0_INJECT_FAILURE")
        force_failure = injected if injected in {"error", "timeout"} else None
    event_for_record = dict(event)
    kind, match_reason = classify_command(str(event.get("tool_name", "unknown")), event.get("tool_input", {}))
    if kind is None:
        return base_record(event_for_record, None, "passthrough_unsupported", match_reason, mode=selected_mode), None

    original = response_text(event.get("tool_response", event.get("tool_output", event.get("response", ""))))
    original_chars = len(original)
    threshold = min_chars if min_chars is not None else env_int("AGENT_TOKEN_MANAGER_CO0_MIN_CHARS", DEFAULT_MIN_CHARS, 128)
    budget = visible_chars if visible_chars is not None else env_int(
        "AGENT_TOKEN_MANAGER_CO0_VISIBLE_CHARS", DEFAULT_VISIBLE_CHARS, 256
    )

    selected_syntax_mode = (syntax_mode or os.environ.get("AGENT_TOKEN_MANAGER_CO1_MODE", "observe")).lower()
    request = syntax_request(kind, event.get("tool_input", {})) if kind in {"sed_range", "known_symbol"} else None

    if selected_mode != "enforce":
        record = base_record(event_for_record, kind, "passthrough_observe", "optimizer_not_enforced", mode=selected_mode)
        record.update({"original_chars": original_chars, "original_sha256": sha256_text(original)})
        return record, None
    if original_chars < threshold or original_chars <= budget:
        record = base_record(
            event_for_record, kind, "passthrough_not_beneficial", "below_optimization_threshold", mode=selected_mode
        )
        record.update({"original_chars": original_chars, "original_sha256": sha256_text(original)})
        return record, None
    if force_failure == "timeout":
        record = base_record(
            event_for_record, kind, "fallback_budget_or_timeout", "injected_timeout", mode=selected_mode
        )
        record.update({"original_chars": original_chars, "original_sha256": sha256_text(original)})
        return record, None
    if force_failure == "error":
        record = base_record(
            event_for_record, kind, "fallback_optimizer_error", "injected_optimizer_error", mode=selected_mode
        )
        record.update({"original_chars": original_chars, "original_sha256": sha256_text(original)})
        return record, None

    if selected_syntax_mode == "enforce" and kind in {"sed_range", "known_symbol"}:
        if request is None:
            record = base_record(
                event_for_record, kind, "passthrough_unsupported", "syntax_request_ambiguous", mode=selected_mode
            )
            record.update({"original_chars": original_chars, "original_sha256": sha256_text(original)})
            return record, None
        source_path = resolve_request_path(event, request.get("path"))
        if source_path is None:
            result = SliceResult(None, "syntax_source_unavailable", {"optimizer_strategy": "python_syntax_slice"})
        else:
            syntax_budget = syntax_budget_chars if syntax_budget_chars is not None else env_int(
                "AGENT_TOKEN_MANAGER_CO1_VISIBLE_CHARS", DEFAULT_CO1_VISIBLE_CHARS, 256
            )
            result = build_slice(
                source_path,
                symbol=request.get("symbol") if isinstance(request.get("symbol"), str) else None,
                start_line=request.get("start_line") if isinstance(request.get("start_line"), int) else None,
                end_line=request.get("end_line") if isinstance(request.get("end_line"), int) else None,
                budget_chars=syntax_budget,
            )
        if result.replacement is None:
            status = "fallback_budget_or_timeout" if result.reason == "syntax_slice_over_budget" else "passthrough_unsupported"
            record = base_record(event_for_record, kind, status, result.reason, mode=selected_mode)
            record.update({"original_chars": original_chars, "original_sha256": sha256_text(original), **result.metadata})
            return record, None
        if len(result.replacement) >= original_chars:
            record = base_record(
                event_for_record, kind, "passthrough_not_beneficial", "syntax_replacement_not_smaller", mode=selected_mode
            )
            record.update({"original_chars": original_chars, "original_sha256": sha256_text(original), **result.metadata})
            return record, None
        canary = os.environ.get("AGENT_TOKEN_MANAGER_CO0_CANARY", "")
        record = base_record(event_for_record, kind, "optimized", result.reason, mode=selected_mode)
        record.update(
            {
                "original_chars": original_chars,
                "original_sha256": sha256_text(original),
                "replacement_chars": len(result.replacement),
                "replacement_sha256": sha256_text(result.replacement),
                "estimated_visible_tokens": (len(result.replacement) + 3) // 4,
                "token_count_method": "chars_div_4_v1",
                "canary_in_original": bool(canary and canary in original),
                "canary_in_replacement": bool(canary and canary in result.replacement),
                **result.metadata,
            }
        )
        return record, {"decision": "block", "reason": result.replacement}

    try:
        replacement = compress_payload(kind, original, budget)
        if len(replacement) >= original_chars:
            record = base_record(
                event_for_record, kind, "fallback_budget_or_timeout", "replacement_not_smaller", mode=selected_mode
            )
            record.update({"original_chars": original_chars, "original_sha256": sha256_text(original)})
            return record, None
        canary = os.environ.get("AGENT_TOKEN_MANAGER_CO0_CANARY", "")
        record = base_record(event_for_record, kind, "optimized", match_reason, mode=selected_mode)
        record.update(
            {
                "original_chars": original_chars,
                "original_sha256": sha256_text(original),
                "replacement_chars": len(replacement),
                "replacement_sha256": sha256_text(replacement),
                "estimated_visible_tokens": (len(replacement) + 3) // 4,
                "token_count_method": "chars_div_4_v1",
                "canary_in_original": bool(canary and canary in original),
                "canary_in_replacement": bool(canary and canary in replacement),
            }
        )
        return record, {"decision": "block", "reason": replacement}
    except Exception as error:
        record = base_record(
            event_for_record, kind, "fallback_optimizer_error", type(error).__name__, mode=selected_mode
        )
        record.update({"original_chars": original_chars, "original_sha256": sha256_text(original)})
        return record, None


def resolve_data_dir(event: dict[str, Any]) -> Path:
    configured = os.environ.get("AGENT_TOKEN_MANAGER_DATA") or os.environ.get("PLUGIN_DATA")
    if configured:
        return Path(configured).expanduser()
    cwd = event.get("cwd")
    return Path(cwd if isinstance(cwd, str) and cwd else os.getcwd()) / ".agent-token-manager"


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)


def main() -> int:
    event: dict[str, Any] | None = None
    try:
        loaded = json.load(sys.stdin)
        if not isinstance(loaded, dict):
            return 0
        event = loaded
        record, decision = evaluate_event(event)
        if record.get("status") not in STATUSES:
            return 0
        append_record(resolve_data_dir(event) / "context-optimizer.jsonl", record)
        if decision is not None:
            print(json.dumps(decision, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        # Any parser, optimizer, or log failure leaves the original tool result untouched.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
