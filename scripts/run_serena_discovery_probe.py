#!/usr/bin/env python3
"""Probe Serena substring discovery without benchmark path or symbol hints."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from discovery_sources import normalize_query_terms
from run_m2c_benchmark import CASES


def _select_terms(task: str, limit: int = 4) -> list[str]:
    terms = list(normalize_query_terms([task]))
    # Longer terms are usually more selective. Preserve one short code-like
    # concept because names such as "valid" can be more useful than prose.
    ranked = sorted(terms, key=lambda value: (-len(value), value))
    selected = ranked[: max(0, limit - 1)]
    short = next((term for term in terms if 4 <= len(term) <= 6 and term not in selected), None)
    if short:
        selected.append(short)
    return selected[:limit]


def _parse_symbols(text: str) -> list[dict[str, str]]:
    candidate = text.strip()
    if "Shortened result:" in candidate:
        candidate = candidate.split("Shortened result:", 1)[1].strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    results: list[dict[str, str]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("relative_path") and item.get("name_path"):
                results.append(
                    {"path": str(item["relative_path"]), "symbol": str(item["name_path"]).replace("/", ".")}
                )
    elif isinstance(payload, dict):
        for path, names in payload.items():
            if isinstance(names, list):
                for name in names:
                    results.append({"path": str(path), "symbol": str(name).replace("/", ".")})
    return results


async def probe(root: Path, budget_tokens: int, max_queries: int) -> dict[str, Any]:
    # Serena/MCP are optional runtime dependencies. Keep pure parsing and
    # benchmark-manifest helpers importable by the core plugin Python.
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    from serena_adapter_server import backend_parameters, result_text

    started = time.perf_counter()
    previous_home = os.environ.get("SERENA_HOME")
    with tempfile.TemporaryDirectory(prefix="agent-token-serena-discovery-") as temporary:
        temporary_root = Path(temporary)
        workspace = temporary_root / "project"
        shutil.copytree(
            root,
            workspace,
            ignore=shutil.ignore_patterns(
                ".git", ".agent-token-manager", ".venv", "node_modules", "__pycache__"
            ),
        )
        project_config = workspace / ".serena" / "project.yml"
        if project_config.is_file():
            project_config.write_text(
                project_config.read_text(encoding="utf-8").replace("  - typescript\n", ""),
                encoding="utf-8",
            )
        os.environ["SERENA_HOME"] = str(temporary_root / "home")
        results = []
        try:
            async with stdio_client(backend_parameters(workspace)) as (read_stream, write_stream):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(seconds=120),
                ) as session:
                    await session.initialize()
                    startup_ms = round((time.perf_counter() - started) * 1000, 3)
                    for case in CASES:
                        case_started = time.perf_counter()
                        terms = _select_terms(case["task"], max_queries)
                        symbols: list[dict[str, str]] = []
                        payload_tokens = 0
                        for term in terms:
                            response = await session.call_tool(
                                "find_symbol",
                                {
                                    "name_path_pattern": term,
                                    "substring_matching": True,
                                    "include_body": False,
                                    "max_matches": 12,
                                    "max_answer_chars": max(512, budget_tokens * 4 // max(1, len(terms))),
                                },
                            )
                            text = result_text(response)
                            payload_tokens += (len(text) + 3) // 4
                            symbols.extend(_parse_symbols(text))
                        unique = {
                            (item["path"], item["symbol"]): item for item in symbols
                        }
                        target = case["target"]
                        target_path = case["path"]
                        found = any(
                            path == target_path
                            and (symbol == target or symbol.endswith("." + target))
                            for path, symbol in unique
                        )
                        results.append(
                            {
                                "id": case["id"],
                                "task": case["task"],
                                "target": target,
                                "queries": terms,
                                "candidate_count": len(unique),
                                "target_found": found,
                                "payload_tokens": payload_tokens,
                                "within_budget": payload_tokens <= budget_tokens,
                                "elapsed_ms": round((time.perf_counter() - case_started) * 1000, 3),
                            }
                        )
        finally:
            if previous_home is None:
                os.environ.pop("SERENA_HOME", None)
            else:
                os.environ["SERENA_HOME"] = previous_home
    return {
        "schema_version": 1,
        "benchmark": "serena-no-oracle-discovery-probe",
        "status": "completed",
        "repository": str(root),
        "startup_ms": startup_ms,
        "budget_tokens": budget_tokens,
        "max_queries": max_queries,
        "case_count": len(results),
        "target_recall": sum(item["target_found"] for item in results) / len(results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--budget", type=int, default=800)
    parser.add_argument("--max-queries", type=int, default=4)
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(probe(args.root.expanduser().resolve(), args.budget, args.max_queries)),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
