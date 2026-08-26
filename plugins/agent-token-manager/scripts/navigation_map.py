#!/usr/bin/env python3
"""Build and query the sparse semantic navigation map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ast_navigation_provider import AstNavigationProvider
from navigation_contract import QueryRequest


def emit(value: dict, pretty: bool) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="incrementally index Python structure")
    index_parser.add_argument("root", type=Path)
    index_parser.add_argument("--changed-path", action="append", default=[])

    query_parser = subparsers.add_parser("query", help="return ranked markers under a token budget")
    query_parser.add_argument("root", type=Path)
    query_parser.add_argument("--task", default="")
    query_parser.add_argument("--symbol", action="append", default=[])
    query_parser.add_argument("--path", action="append", default=[])
    query_parser.add_argument("--edge-kind", action="append", default=[])
    query_parser.add_argument("--budget", type=int, default=800)
    query_parser.add_argument("--limit", type=int, default=20)

    status_parser = subparsers.add_parser("status", help="show index counts")
    status_parser.add_argument("root", type=Path)

    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    provider = AstNavigationProvider(root, args.data_dir)
    if args.command == "index":
        result = provider.index(changed_paths=args.changed_path)
        output = {
            "schema_version": 1,
            "status": "indexed" if not result.warnings else "degraded",
            "workspace": provider.workspace.to_dict(),
            "index": provider.last_index_stats,
            "warnings": list(result.warnings),
        }
        emit(output, args.pretty)
        return 0 if not result.warnings else 2
    if args.command == "query":
        request = QueryRequest(
            task=args.task,
            budget_tokens=args.budget,
            symbols=tuple(args.symbol),
            paths=tuple(args.path),
            limit=args.limit,
            include_edge_kinds=tuple(args.edge_kind),
        )
        result = provider.query(request)
        emit(result.to_dict(), args.pretty)
        return 0
    emit(
        {
            "schema_version": 1,
            "workspace": provider.workspace.to_dict(),
            "index": provider.store.counts(),
        },
        args.pretty,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
