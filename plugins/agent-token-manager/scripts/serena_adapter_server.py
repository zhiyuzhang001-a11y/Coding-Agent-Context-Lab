#!/usr/bin/env python3
"""Expose one budgeted context-bundle tool backed by Serena MCP."""

from __future__ import annotations

import json
import os
import shutil
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp import Context, FastMCP

from serena_bundle import build_bundle


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERENA_CONTEXT = PLUGIN_ROOT / "resources" / "serena-token-context.yml"
DEFAULT_SERENA_COMMAND = shutil.which("serena") or "serena"


@dataclass
class AdapterState:
    project_root: Path
    session: ClientSession


def result_text(result: object) -> str:
    if bool(getattr(result, "isError", False)):
        raise RuntimeError("Serena backend tool failed")
    texts = [str(getattr(block, "text")) for block in getattr(result, "content", []) if getattr(block, "type", None) == "text"]
    if not texts:
        raise RuntimeError("Serena backend returned no text")
    return "\n".join(texts)


def backend_parameters(project_root: Path) -> StdioServerParameters:
    command = os.environ.get("SERENA_COMMAND", DEFAULT_SERENA_COMMAND)
    return StdioServerParameters(
        command=command,
        cwd=str(project_root),
        env=dict(os.environ),
        args=[
            "start-mcp-server",
            "--context",
            str(SERENA_CONTEXT),
            "--project",
            str(project_root),
            "--mode",
            "no-onboarding",
            "--add-mode",
            "no-memories",
            "--enable-web-dashboard",
            "false",
            "--open-web-dashboard",
            "false",
            "--enable-gui-log-window",
            "false",
            "--log-level",
            "ERROR",
        ],
    )


@asynccontextmanager
async def adapter_lifespan(_: FastMCP) -> AsyncIterator[AdapterState]:
    project_root = Path.cwd().resolve()
    async with stdio_client(backend_parameters(project_root)) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=120)) as session:
            await session.initialize()
            yield AdapterState(project_root=project_root, session=session)


mcp = FastMCP(name="Serena Context Adapter", instructions=None, log_level="ERROR", lifespan=adapter_lifespan)


async def call_backend(
    state: AdapterState,
    relative_path: str,
    name_path: str,
    include_references: bool,
    body_max_chars: int,
    references_max_chars: int,
) -> tuple[str, str | None, int]:
    target_result = await state.session.call_tool(
        "find_symbol",
        {
            "name_path_pattern": name_path,
            "relative_path": relative_path,
            "include_body": True,
            "max_matches": 1,
            "max_answer_chars": body_max_chars,
        },
    )
    target_text = result_text(target_result)
    if not include_references:
        return target_text, None, 1
    references_result = await state.session.call_tool(
        "find_referencing_symbols",
        {
            "name_path": name_path,
            "relative_path": relative_path,
            "max_answer_chars": references_max_chars,
        },
    )
    return target_text, result_text(references_result), 2


@mcp.tool(
    description="Return one symbol body and its reference summary from Serena within a total token budget.",
    structured_output=False,
)
async def context_bundle(
    ctx: Context,
    project_root: str,
    relative_path: str,
    name_path: str,
    include_references: bool = True,
    budget_tokens: int = 1400,
) -> str:
    if budget_tokens < 256 or budget_tokens > 8000:
        raise ValueError("budget_tokens must be between 256 and 8000")
    resolved_root = Path(project_root).expanduser().resolve()
    if not resolved_root.is_dir():
        raise ValueError(f"Not a project directory: {resolved_root}")
    state = ctx.request_context.lifespan_context
    if not isinstance(state, AdapterState):
        raise RuntimeError("Serena adapter lifespan is unavailable")
    if resolved_root != state.project_root:
        raise ValueError(f"project_root must match adapter workspace: {state.project_root}")
    body_max_chars = max(512, int(budget_tokens * 4 * 0.7))
    references_max_chars = max(256, int(budget_tokens * 4 * 0.3))
    target, references, calls = await call_backend(
        state, relative_path, name_path, include_references, body_max_chars, references_max_chars
    )
    bundle = build_bundle(target, references, budget_tokens, calls)
    return json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    mcp.run(transport="stdio")
