#!/usr/bin/env python3
"""Route a file read to full, outline, or symbol-focused output."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from smart_read import cache_directory_from_environment, fit_payload, smart_read
from workspace_data import WorkspaceError, persistent_cache_directory


DEFAULT_DIRECT_MAX_TOKENS = 800


def route_read(
    path: Path,
    query: str,
    symbols: list[str],
    budget_tokens: int,
    direct_max_tokens: int = DEFAULT_DIRECT_MAX_TOKENS,
    cache_dir: Path | None = None,
    force_symbol: bool = False,
) -> dict:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Not a regular file: {resolved}")
    source_estimated_tokens = (resolved.stat().st_size + 3) // 4
    if symbols and force_symbol:
        mode = "symbol"
        reason = "forced_named_symbols"
    elif source_estimated_tokens <= direct_max_tokens:
        mode = "full"
        reason = "small_file"
    elif symbols:
        mode = "symbol"
        reason = "named_symbols"
    elif query:
        mode = "auto"
        reason = "task_query"
    else:
        mode = "outline"
        reason = "large_file_without_target"

    routed_symbols = symbols if mode != "full" else []
    result = smart_read(resolved, query, budget_tokens, mode, routed_symbols, cache_dir)
    result["route"] = {
        "mode": result["mode"],
        "reason": reason,
        "source_estimated_tokens": source_estimated_tokens,
        "direct_max_tokens": direct_max_tokens,
    }
    return fit_payload(result, budget_tokens)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--query", default="")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--budget", type=int, default=1200)
    parser.add_argument("--direct-max-tokens", type=int, default=DEFAULT_DIRECT_MAX_TOKENS)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if args.budget < 128:
        parser.error("--budget must be at least 128 tokens")
    if args.direct_max_tokens < 128:
        parser.error("--direct-max-tokens must be at least 128 tokens")
    if args.no_cache:
        cache_dir = None
    elif args.cache_dir:
        cache_dir = args.cache_dir
    elif "AGENT_TOKEN_MANAGER_DATA" in os.environ or "PLUGIN_DATA" in os.environ:
        cache_dir = cache_directory_from_environment()
    else:
        try:
            cache_dir = persistent_cache_directory(args.path)
        except (OSError, WorkspaceError):
            cache_dir = cache_directory_from_environment()
    try:
        result = route_read(args.path, args.query, args.symbol, args.budget, args.direct_max_tokens, cache_dir)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
