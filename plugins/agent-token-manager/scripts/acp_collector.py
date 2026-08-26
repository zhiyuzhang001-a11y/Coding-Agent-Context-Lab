#!/usr/bin/env python3
"""Persist privacy-normalized, observe-only ACP PostToolUse telemetry."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = 1
ESTIMATION_METHOD = "chars_div_4_v1"
EVENT_FIELDS = {
    "schema_version", "session_id_hash", "event_id", "timestamp", "tool_family",
    "command_shape", "result_status", "path_hashes", "explicit_ranges", "raw_chars",
    "estimated_tokens", "estimation_method", "output_sha256", "code_bearing",
    "coverage_state", "coverage_reason", "duration_ms",
}
STRUCTURED_PATH_KEYS = {"file", "file_path", "path", "paths"}
READ_TOOLS = {"read", "read_file", "view_file"}
SHELL_TOOLS = {"bash", "exec_command", "shell"}
SHELL_FAMILIES = {"awk", "cat", "find", "grep", "head", "nl", "perl", "python", "python3", "rg", "sed", "tail", "wc"}
CODE_COMMAND = re.compile(
    r"(?:^|[\s;&|])(?:rg|sed|cat|awk|perl|find|python3?)(?:\s|$)|"
    r"\.(?:py|js|jsx|ts|tsx|go|rs|java|kt|swift|c|cc|cpp|h|hpp)(?:\s|$)"
)


def compact_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def response_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("output", "aggregated_output", "stdout", "result"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    return compact_json(value)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def pseudonym(secret: bytes, namespace: str, value: str) -> str:
    return hmac.new(secret, f"{namespace}\0{value}".encode("utf-8", errors="replace"), hashlib.sha256).hexdigest()


def resolve_data_dir(event: dict[str, Any]) -> Path:
    configured = os.environ.get("AGENT_TOKEN_MANAGER_DATA") or os.environ.get("PLUGIN_DATA")
    if configured:
        return Path(configured).expanduser()
    cwd = event.get("cwd")
    root = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    return root / ".agent-token-manager" / "acp"


def load_or_create_secret(data_dir: Path) -> bytes:
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    secret_path = data_dir / "collector-secret.key"
    try:
        descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        secret = secret_path.read_bytes()
        if len(secret) != 32:
            raise ValueError("invalid collector secret")
        return secret
    secret = secrets.token_bytes(32)
    try:
        os.write(descriptor, secret)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return secret


def repository_scope(event: dict[str, Any]) -> str:
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return "missing-repository-scope"
    return str(Path(cwd).expanduser().resolve(strict=False))


def tool_family(tool_name: str) -> str:
    normalized = tool_name.lower()
    if normalized in SHELL_TOOLS:
        return "bash"
    if normalized in READ_TOOLS or "read_file" in normalized:
        return "local_read"
    if normalized.startswith("mcp__") or normalized == "read_mcp_resource":
        return "mcp"
    if normalized.startswith(("web", "hosted")):
        return "hosted"
    return "other"


def shell_command(tool_input: Any) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    value = tool_input.get("command", tool_input.get("cmd"))
    return value if isinstance(value, str) else None


def command_shape(family: str, tool_input: Any) -> str:
    if family != "bash":
        return "structured_tool"
    command = shell_command(tool_input)
    if command is None:
        return "missing_command"
    if any(operator in command for operator in ("&&", "||", "|", ";", "\n")):
        return "compound_shell"
    try:
        words = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return "malformed_shell"
    if not words:
        return "empty_shell"
    executable = words[0].rsplit("/", 1)[-1]
    return executable if executable in SHELL_FAMILIES else "other_shell"


def result_status(event: dict[str, Any], response: Any) -> str:
    if event.get("tool_error") is not None:
        return "error"
    if isinstance(response, dict):
        if response.get("is_error") is True or response.get("error") is not None:
            return "error"
        exit_code = response.get("exit_code")
        if isinstance(exit_code, int) and not isinstance(exit_code, bool):
            return "success" if exit_code == 0 else "error"
    return "unknown"


def collect_structured_paths(value: Any, key: str | None = None) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            paths.extend(collect_structured_paths(child, str(child_key).lower()))
    elif isinstance(value, list):
        for child in value:
            paths.extend(collect_structured_paths(child, key))
    elif key in STRUCTURED_PATH_KEYS and isinstance(value, str) and len(value) <= 4096:
        paths.append(value)
    return paths


def normalized_relative_path(raw_path: str, repository: str) -> str | None:
    root = Path(repository)
    candidate = Path(raw_path).expanduser()
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        relative = candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (OSError, ValueError):
        return None
    normalized = PurePosixPath(relative.as_posix())
    return None if str(normalized) in {"", "."} else str(normalized)


def path_hashes(secret: bytes, repository: str, tool_input: Any) -> list[str]:
    hashes = {
        pseudonym(secret, f"path\0{repository}", relative)
        for raw in collect_structured_paths(tool_input)
        if (relative := normalized_relative_path(raw, repository)) is not None
    }
    return sorted(hashes)[:50]


def explicit_ranges(secret: bytes, repository: str, family: str, shape: str, tool_input: Any) -> list[dict[str, Any]]:
    if family != "bash" or shape != "sed":
        return []
    command = shell_command(tool_input)
    if command is None:
        return []
    try:
        words = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return []
    try:
        index = words.index("-n")
        match = re.fullmatch(r"(\d+),(\d+)p", words[index + 1])
        raw_path = words[index + 2]
    except (ValueError, IndexError):
        return []
    if match is None:
        return []
    start, end = int(match.group(1)), int(match.group(2))
    relative = normalized_relative_path(raw_path, repository)
    if relative is None or start < 1 or end < start:
        return []
    return [{"path_hash": pseudonym(secret, f"path\0{repository}", relative), "start_line": start, "end_line": end}]


def coverage(family: str, shape: str, session_missing: bool) -> tuple[str, str]:
    if family in {"mcp", "hosted"}:
        return "unsupported_tool_path", f"{family}_not_in_acp0_1_supported_boundary"
    if session_missing:
        return "observed_not_matched", "missing_session_metadata"
    if shape in {"missing_command", "malformed_shell", "empty_shell", "other_shell"}:
        return "parse_unknown", f"command_shape_{shape}"
    return "observed_not_matched", "collector_only_awaiting_transcript_correlation"


def build_record(
    event: dict[str, Any],
    secret: bytes,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
    started_ns: int | None = None,
) -> dict[str, Any]:
    started = started_ns if started_ns is not None else time.monotonic_ns()
    tool_input = event.get("tool_input", {})
    response = event.get("tool_response", event.get("tool_output", event.get("response", "")))
    raw_result = response_text(response)
    repository = repository_scope(event)
    raw_session = event.get("session_id")
    session_missing = not isinstance(raw_session, str) or not raw_session
    entropy = nonce or secrets.token_hex(16)
    session_material = entropy if session_missing else raw_session
    session_hash = pseudonym(secret, f"session\0{repository}", session_material)
    raw_tool_use = event.get("tool_use_id")
    event_material = raw_tool_use if isinstance(raw_tool_use, str) and raw_tool_use else entropy
    event_id = pseudonym(secret, f"event\0{repository}\0{session_hash}", event_material)
    family = tool_family(str(event.get("tool_name", "unknown")))
    shape = command_shape(family, tool_input)
    coverage_state, coverage_reason = coverage(family, shape, session_missing)
    command = shell_command(tool_input) or ""
    read_intent = family == "local_read" or (family == "bash" and bool(CODE_COMMAND.search(command)))
    duration_ms = round((time.monotonic_ns() - started) / 1_000_000, 3)
    record = {
        "schema_version": SCHEMA_VERSION,
        "session_id_hash": session_hash,
        "event_id": event_id,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "tool_family": family,
        "command_shape": shape,
        "result_status": result_status(event, response),
        "path_hashes": path_hashes(secret, repository, tool_input),
        "explicit_ranges": explicit_ranges(secret, repository, family, shape, tool_input),
        "raw_chars": len(raw_result),
        "estimated_tokens": (len(raw_result) + 3) // 4,
        "estimation_method": ESTIMATION_METHOD,
        "output_sha256": sha256_text(raw_result),
        "code_bearing": read_intent,
        "coverage_state": coverage_state,
        "coverage_reason": coverage_reason,
        "duration_ms": duration_ms,
    }
    if set(record) != EVENT_FIELDS:
        raise ValueError("collector event violates closed field allowlist")
    return record


def append_record(path: Path, record: dict[str, Any]) -> None:
    if set(record) != EVENT_FIELDS:
        raise ValueError("refusing non-allowlisted collector event")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
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
        data_dir = resolve_data_dir(event)
        secret = load_or_create_secret(data_dir)
        append_record(data_dir / "events.jsonl", build_record(event, secret))
    except Exception:
        # Telemetry may be lost; the host tool workflow must remain untouched.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
