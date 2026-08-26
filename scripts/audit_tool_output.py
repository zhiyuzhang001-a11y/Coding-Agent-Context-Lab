#!/usr/bin/env python3
"""Record privacy-preserving metadata about a Codex PostToolUse event."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PATH_KEYS = {"file", "file_path", "path", "paths", "workdir", "working_directory"}
READ_LIKE_TOOLS = {
    "read",
    "read_file",
    "read_mcp_resource",
    "view_file",
    "view_image",
}
READ_LIKE_COMMANDS = {"cat", "grep", "head", "nl", "rg", "sed", "tail", "wc"}
DEFAULT_LARGE_READ_TOKENS = 1000


def compact_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def parse_json_output(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if "cache_status" in value or "route" in value or value.get("backend") == "serena":
            return value
        for key in ("output", "aggregated_output", "stdout", "result"):
            if key in value:
                parsed = parse_json_output(value[key])
                if parsed is not None:
                    return parsed
        return None
    if not isinstance(value, str):
        return None
    candidates = [value.strip(), *reversed([line.strip() for line in value.splitlines() if line.strip().startswith("{")])]
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and ("cache_status" in parsed or "route" in parsed or parsed.get("backend") == "serena"):
            return parsed
    return None


def collect_manager_metadata(response: Any) -> dict[str, Any]:
    parsed = parse_json_output(response)
    if parsed is None:
        return {}
    metadata: dict[str, Any] = {}
    cache_status = parsed.get("cache_status")
    if cache_status in {"disabled", "hit", "miss", "write_failed"}:
        metadata["cache_status"] = cache_status
    manager_tokens = parsed.get("estimated_output_tokens")
    if isinstance(manager_tokens, int) and manager_tokens >= 0:
        metadata["estimated_output_tokens"] = manager_tokens
    if parsed.get("backend") == "serena":
        metadata["backend"] = "serena"
    backend_calls = parsed.get("backend_calls")
    if isinstance(backend_calls, int) and backend_calls >= 0:
        metadata["backend_calls"] = backend_calls
    route = parsed.get("route")
    if isinstance(route, dict):
        for source_key, target_key in (
            ("mode", "route_mode"),
            ("reason", "route_reason"),
            ("source_estimated_tokens", "source_estimated_tokens"),
            ("direct_max_tokens", "direct_max_tokens"),
        ):
            value = route.get(source_key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                metadata[target_key] = value
    return metadata


def collect_explicit_paths(value: Any, key: str | None = None) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            paths.extend(collect_explicit_paths(child_value, str(child_key).lower()))
    elif isinstance(value, list):
        for child in value:
            paths.extend(collect_explicit_paths(child, key))
    elif key in PATH_KEYS and isinstance(value, (str, int, float)):
        text = str(value)
        if len(text) <= 1024:
            paths.append(text)
    return sorted(set(paths))[:50]


def is_read_like(tool_name: str, tool_input: Any) -> bool:
    normalized = tool_name.lower()
    if normalized in READ_LIKE_TOOLS or "read_file" in normalized:
        return True
    if any(marker in normalized for marker in ("find_symbol", "find_referencing_symbols", "get_symbols_overview", "context_bundle")):
        return True
    if normalized not in {"bash", "exec_command", "shell"} or not isinstance(tool_input, dict):
        return False
    command = tool_input.get("command") or tool_input.get("cmd")
    if not isinstance(command, str):
        return False
    if any(
        marker in command
        for marker in ("smart_read.py", "context_router.py", "task_navigator.py", "compact_navigator.py")
    ):
        return True
    try:
        words = shlex.split(command, comments=False, posix=True)
    except ValueError:
        words = command.split()
    return any(word.rsplit("/", 1)[-1] in READ_LIKE_COMMANDS for word in words)


def resolve_data_dir(event: dict[str, Any]) -> Path:
    configured = os.environ.get("AGENT_TOKEN_MANAGER_DATA") or os.environ.get("PLUGIN_DATA")
    if configured:
        return Path(configured).expanduser()
    cwd = event.get("cwd")
    return Path(cwd if isinstance(cwd, str) and cwd else os.getcwd()) / ".agent-token-manager"


def large_read_threshold() -> int:
    raw = os.environ.get("AGENT_TOKEN_MANAGER_LARGE_READ_TOKENS", "")
    try:
        return max(128, int(raw)) if raw else DEFAULT_LARGE_READ_TOKENS
    except ValueError:
        return DEFAULT_LARGE_READ_TOKENS


def build_record(event: dict[str, Any]) -> dict[str, Any]:
    tool_input = event.get("tool_input", {})
    response = event.get("tool_response", event.get("tool_output", event.get("response", "")))
    input_text = compact_json(tool_input)
    response_text = compact_json(response)
    response_bytes = len(response_text.encode("utf-8", errors="replace"))
    tool_name = str(event.get("tool_name", "unknown"))
    estimated_tokens = (len(response_text) + 3) // 4
    read_like = is_read_like(tool_name, tool_input)
    threshold = large_read_threshold()

    return {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": event.get("session_id"),
        "turn_id": event.get("turn_id"),
        "model": event.get("model"),
        "tool_use_id": event.get("tool_use_id"),
        "tool_name": tool_name,
        "read_like": read_like,
        "explicit_paths": collect_explicit_paths(tool_input),
        "input_chars": len(input_text),
        "input_sha256": sha256_text(input_text),
        "response_chars": len(response_text),
        "response_bytes": response_bytes,
        "estimated_response_tokens": estimated_tokens,
        "token_count_method": "chars_div_4_v1",
        "large_read_threshold_tokens": threshold,
        "large_read_candidate": read_like and estimated_tokens >= threshold,
        "manager_read": collect_manager_metadata(response),
        "response_sha256": sha256_text(response_text),
    }


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return 0
        append_record(resolve_data_dir(event) / "tool-output-audit.jsonl", build_record(event))
    except Exception:
        # Auditing is deliberately fail-open and emits no model-visible output.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
