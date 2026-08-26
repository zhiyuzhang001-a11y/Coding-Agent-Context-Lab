#!/usr/bin/env python3
"""Run exact-target Serena retrieval probes for the unified M2c report."""

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

from mcp import ClientSession
from mcp.client.stdio import stdio_client

from run_m2c_benchmark import CASES
from serena_adapter_server import backend_parameters, result_text


def estimate_tokens(value: object) -> int:
    return (len(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) + 3) // 4


async def probe(root: Path, budget_tokens: int) -> dict:
    started = time.perf_counter()
    results = []
    previous_home = os.environ.get("SERENA_HOME")
    previous_path = os.environ.get("PATH", "")
    optional_node_bin = os.environ.get("SERENA_NODE_BIN", "")
    with tempfile.TemporaryDirectory(prefix="agent-token-serena-probe-") as temporary:
        temporary_root = Path(temporary)
        temporary_home = temporary_root / "home"
        workspace = temporary_root / "project"
        shutil.copytree(
            root,
            workspace,
            ignore=shutil.ignore_patterns(
                ".git", ".agent-token-manager", ".venv", "node_modules", "__pycache__"
            ),
        )
        project_config = workspace / ".serena" / "project.yml"
        project_config.write_text(
            project_config.read_text(encoding="utf-8").replace("  - typescript\n", ""),
            encoding="utf-8",
        )
        os.environ["SERENA_HOME"] = str(temporary_home)
        os.environ["PATH"] = os.pathsep.join(
            entry for entry in (optional_node_bin, previous_path) if entry
        )
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
                        query_started = time.perf_counter()
                        name_path = case["target"].replace(".", "/")
                        try:
                            response = await session.call_tool(
                                "find_symbol",
                                {
                                    "name_path_pattern": name_path,
                                    "relative_path": case["path"],
                                    "include_body": True,
                                    "max_matches": 1,
                                    "max_answer_chars": budget_tokens * 4,
                                },
                            )
                            text = result_text(response)
                            tokens = estimate_tokens(text)
                            correct = case["target"].rsplit(".", 1)[-1] in text and tokens <= budget_tokens
                            error = ""
                        except Exception as exc:  # backend failures belong in the report
                            text = ""
                            tokens = 0
                            correct = False
                            error = exc.__class__.__name__
                        results.append(
                            {
                                "id": case["id"],
                                "task": case["task"],
                                "target": case["target"],
                                "path": case["path"],
                                "correct": correct,
                                "error_stop": not correct,
                                "result_tokens": tokens,
                                "within_budget": tokens <= budget_tokens,
                                "elapsed_ms": round((time.perf_counter() - query_started) * 1000, 3),
                                "error": error,
                            }
                        )
        finally:
            if previous_home is None:
                os.environ.pop("SERENA_HOME", None)
            else:
                os.environ["SERENA_HOME"] = previous_home
            os.environ["PATH"] = previous_path
    return {
        "status": "completed" if all(item["correct"] for item in results) else "failed",
        "capability": "exact_symbol_retrieval",
        "natural_language_routing": False,
        "target_hints": "benchmark oracle path and symbol; retrieval metrics are not a navigation-quality comparison",
        "startup_ms": startup_ms,
        "budget_tokens": budget_tokens,
        "case_count": len(results),
        "correct_count": sum(item["correct"] for item in results),
        "error_stops": sum(item["error_stop"] for item in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--budget", type=int, default=1200)
    args = parser.parse_args()
    payload = asyncio.run(probe(args.root.expanduser().resolve(), args.budget))
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if payload["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
