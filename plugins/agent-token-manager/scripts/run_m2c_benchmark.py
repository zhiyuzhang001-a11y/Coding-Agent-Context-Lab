#!/usr/bin/env python3
"""Compare M2b and M2c navigation on fixed real-repository tasks."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from task_navigator import Feedback, TaskNavigator


CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "optional-tool-selection",
        "task": "understand how optional tools are included or excluded from the active tool collection",
        "target": "ToolSet.apply",
        "path": "src/serena/agent.py",
        "relevant": ("ToolMarkerOptional", "ToolRegistry.__init__", "ToolRegistry", "ToolSet"),
    },
    {
        "id": "configured-tool-validation",
        "task": "check whether configured tool names are valid including aliases removed entries and unknown entries",
        "target": "ToolRegistry.check_valid_tool_name",
        "path": "src/serena/tools/tools_base.py",
        "relevant": ("ToolRegistry", "ToolRegistry.is_deleted_tool_name", "ToolRegistry.is_valid_tool_name"),
    },
    {
        "id": "read-only-tool-set",
        "task": "produce a read only tool set without editing capabilities",
        "target": "ToolSet.without_editing_tools",
        "path": "src/serena/agent.py",
        "relevant": ("ToolMarkerCanEdit", "Tool.can_edit", "ToolRegistry", "ToolSet"),
    },
    {
        "id": "symbol-reference-search",
        "task": "find symbols that reference a requested symbol and summarize each referencing location",
        "target": "FindReferencingSymbolsTool.apply",
        "path": "src/serena/tools/symbol_tools.py",
        "relevant": ("FindReferencingSymbolsTool", "ToolMarkerSymbolicRead", "Symbol.find_referencing_symbols"),
    },
    {
        "id": "project-activation",
        "task": "load a project configuration and activate its workspace for the current session",
        "target": "ActivateProjectTool.apply",
        "path": "src/serena/tools/config_tools.py",
        "relevant": ("ActivateProjectTool", "ToolMarkerDoesNotRequireActiveProject"),
    },
)


def has_code_identifier(case: dict[str, Any]) -> bool:
    task = case["task"].lower()
    names = [case["target"], *case["relevant"]]
    return any(name.lower() in task for name in names)


def run_case(
    root: Path,
    data_dir: Path,
    case: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    edge_kinds = {"contains", "imports"} if mode == "m2b" else None
    navigator = TaskNavigator(
        root,
        data_dir,
        allowed_edge_kinds=edge_kinds,
        discovery_sources={},
    )
    task_id = f"m2c-benchmark-{mode}-{case['id']}"
    state = navigator.start(
        case["task"],
        total_budget=8400,
        navigation_budget=2400,
        expansion_budget=6000,
        task_id=task_id,
    )
    markers = navigator.provider.store.load_markers(navigator.provider.name)
    symbols = {marker.id: marker.symbol for marker in markers}
    target = next(marker for marker in markers if marker.symbol == case["target"])
    relevant = set(case["relevant"])
    selected: list[str] = []
    relationship_steps = 0
    found = False
    started = time.perf_counter()
    for _ in range(8):
        choice = navigator.next(state.task_id)
        candidate = choice.get("candidate")
        if not candidate:
            break
        selected.append(candidate["symbol"])
        reasons = candidate.get("ranking", {}).get("relationship_reasons", [])
        relationship_steps += int(bool(reasons))
        navigator.expand(state.task_id, candidate["id"], 650)
        if candidate["id"] == target.id:
            navigator.stop(state.task_id, "target_found", [target.id])
            found = True
            break
        if navigator.store.load(state.task_id).stop_reason:
            break
        navigator.feedback(
            state.task_id,
            Feedback(
                candidate["id"],
                relevance="relevant" if candidate["symbol"] in relevant else "irrelevant",
                information_gain="high" if candidate["symbol"] in relevant else "low",
            ),
        )
    final = navigator.store.load(state.task_id)
    if not final.stop_reason:
        navigator.stop(state.task_id, "low_expected_gain", [final.selected[-1]] if final.selected else [])
        final = navigator.store.load(state.task_id)
    return {
        "correct": found,
        "error_stop": not found,
        "stop_reason": final.stop_reason,
        "selected_symbols": selected,
        "selected_count": len(selected),
        "relationship_steps": relationship_steps,
        "navigation_tokens": final.navigation_tokens,
        "expansion_tokens": final.expansion_tokens,
        "consumed_tokens": final.consumed_tokens,
        "within_budget": final.consumed_tokens <= final.total_budget,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def run_benchmark(root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agent-token-m2c-") as temporary:
        data_dir = Path(temporary) / "data"
        provider = TaskNavigator(root, data_dir).provider
        started = time.perf_counter()
        provider.index()
        index_ms = round((time.perf_counter() - started) * 1000, 3)
        index_stats = dict(provider.last_index_stats)
        results = []
        for case in CASES:
            result = {
                "id": case["id"],
                "task": case["task"],
                "target": case["target"],
                "contains_code_identifier": has_code_identifier(case),
                "m2b": run_case(root, data_dir, case, "m2b"),
                "m2c": run_case(root, data_dir, case, "m2c"),
            }
            results.append(result)
        database_bytes = provider.workspace.database.stat().st_size
    m2b_errors = sum(item["m2b"]["error_stop"] for item in results)
    m2c_errors = sum(item["m2c"]["error_stop"] for item in results)
    correct_not_lower = sum(item["m2c"]["correct"] for item in results) >= sum(
        item["m2b"]["correct"] for item in results
    )
    error_improved = m2c_errors <= m2b_errors - 1 or (
        m2b_errors > 0 and (m2b_errors - m2c_errors) / m2b_errors >= 0.2
    )
    passed = (
        len(results) >= 5
        and all(not item["contains_code_identifier"] for item in results)
        and all(item["m2b"]["within_budget"] and item["m2c"]["within_budget"] for item in results)
        and correct_not_lower
        and error_improved
    )
    return {
        "schema_version": 1,
        "benchmark": "m2b-vs-m2c-real-navigation",
        "status": "passed" if passed else "failed",
        "repository": str(root),
        "case_count": len(results),
        "index": {**index_stats, "elapsed_ms": index_ms, "database_bytes": database_bytes},
        "summary": {
            "m2b_errors": m2b_errors,
            "m2c_errors": m2c_errors,
            "correct_not_lower": correct_not_lower,
            "error_improved": error_improved,
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = run_benchmark(args.root.expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
