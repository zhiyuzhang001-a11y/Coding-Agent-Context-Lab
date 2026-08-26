#!/usr/bin/env python3
"""Run deterministic local Smart Read smoke benchmarks."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from context_router import route_read
from smart_read import cache_directory_from_environment
from workspace_data import initialize_store


def estimated_tokens(value: Any) -> int:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (len(text) + 3) // 4


def run_case(root: Path, case: dict[str, Any]) -> dict[str, Any]:
    path = root / case["path"]
    started = time.perf_counter()
    payload = route_read(
        path=path,
        symbols=list(case.get("symbols", [])),
        query=str(case.get("query", "")),
        budget_tokens=int(case["budget_tokens"]),
        cache_dir=cache_directory_from_environment(),
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    names = {region.get("name") for region in payload.get("regions", [])}
    expected = set(case.get("expected_regions", []))
    missing = sorted(expected - names)
    return {
        "id": case["id"],
        "passed": not missing and not payload.get("truncated", False),
        "missing_regions": missing,
        "elapsed_ms": elapsed_ms,
        "result_tokens": estimated_tokens(payload),
        "selected_regions": sorted(name for name in names if name),
        "route_reason": payload.get("route", {}).get("reason"),
        "cache_status": payload.get("cache_status"),
        "budget_tokens": case["budget_tokens"],
    }


def run_benchmarks(root: Path, cases_path: Path, data_dir: Optional[Path] = None) -> dict[str, Any]:
    store = initialize_store(root, data_dir)
    previous = os.environ.get("AGENT_TOKEN_MANAGER_DATA")
    os.environ["AGENT_TOKEN_MANAGER_DATA"] = str(store.data_dir)
    try:
        document = json.loads(cases_path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 1 or not isinstance(document.get("cases"), list):
            raise ValueError("unsupported benchmark case schema")
        results = [run_case(root, case) for case in document["cases"]]
    finally:
        if previous is None:
            os.environ.pop("AGENT_TOKEN_MANAGER_DATA", None)
        else:
            os.environ["AGENT_TOKEN_MANAGER_DATA"] = previous
    return {
        "schema_version": 1,
        "status": "passed" if all(item["passed"] for item in results) else "failed",
        "case_count": len(results),
        "passed_count": sum(item["passed"] for item in results),
        "workspace": store.to_dict(),
        "results": results,
    }


def main() -> int:
    plugin_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=plugin_root)
    parser.add_argument("--cases", type=Path, default=plugin_root / "resources" / "benchmark_cases.json")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = run_benchmarks(args.root.resolve(), args.cases.resolve(), args.data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
