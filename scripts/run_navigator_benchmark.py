#!/usr/bin/env python3
"""Run deterministic natural-language Task Navigator comparisons."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from task_navigator import TaskNavigator


CASES = (
    {
        "id": "stale-login",
        "task": "stop stale login sessions from getting access",
        "entry": "process_login_request",
        "target": "reject_expired_credentials",
    },
    {
        "id": "discount-charge",
        "task": "correct the final customer charge when discounts apply",
        "entry": "process_customer_charge",
        "target": "compute_net_total",
    },
    {
        "id": "search-relevance",
        "task": "make search results honor relevance evidence",
        "entry": "process_search_results",
        "target": "blend_signal_weights",
    },
)


def write_fixture(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "decoys.py").write_text(
        "\n\n".join(f"class GenericCoordinator{index}:\n    pass" for index in range(20)) + "\n",
        encoding="utf-8",
    )
    definitions = {
        "login_flow.py": (
            "process_login_request",
            "reject_expired_credentials",
            "session",
            "session.expires_at > 0",
        ),
        "charge_flow.py": (
            "process_customer_charge",
            "compute_net_total",
            "cart",
            "cart.subtotal - cart.discount",
        ),
        "search_flow.py": (
            "process_search_results",
            "blend_signal_weights",
            "items",
            "sorted(items, key=lambda item: item.weight, reverse=True)",
        ),
    }
    padding = "_PADDING = " + repr("navigation-padding-" * 260) + "\n\n"
    for path, (entry, target, argument, expression) in definitions.items():
        (root / path).write_text(
            padding
            + f"def {entry}({argument}):\n"
            + f"    return {target}({argument})\n\n"
            + f"def {target}({argument}):\n"
            + f"    return {expression}\n",
            encoding="utf-8",
        )


def run_case(navigator: TaskNavigator, case: dict[str, str]) -> dict:
    state = navigator.start(
        case["task"],
        total_budget=3600,
        navigation_budget=1000,
        expansion_budget=2600,
    )
    markers = navigator.provider.store.load_markers(navigator.provider.name)
    symbols_by_id = {marker.id: marker.symbol for marker in markers}
    target = next(marker for marker in markers if marker.symbol == case["target"])
    static_ranked = navigator.rank(state)
    static_ids = [marker.id for _, marker, _ in static_ranked]
    static_expansions = static_ids.index(target.id) + 1

    expanded_ids: list[str] = []
    found = False
    while len(expanded_ids) < 12:
        choice = navigator.next(state.task_id)
        candidate = choice.get("candidate")
        if not candidate:
            break
        expanded_ids.append(candidate["id"])
        navigator.expand(state.task_id, candidate["id"], 700)
        if candidate["id"] == target.id:
            navigator.stop(state.task_id, "target_found", [target.id])
            found = True
            break
    final = navigator.store.load(state.task_id)
    navigator_expansions = len(expanded_ids)
    improved = found and navigator_expansions < static_expansions
    return {
        "id": case["id"],
        "task": case["task"],
        "contains_code_identifier": any(
            identifier.lower() in case["task"].lower()
            for identifier in (case["entry"], case["target"], Path(target.path).name)
        ),
        "target": {"path": target.path, "symbol": target.symbol},
        "static": {
            "correct": target.id in static_ids,
            "expansions_to_target": static_expansions,
            "top_symbols": [marker.symbol for _, marker, _ in static_ranked[:8]],
        },
        "navigator": {
            "correct": found,
            "expansions_to_target": navigator_expansions,
            "navigation_tokens": final.navigation_tokens,
            "expansion_tokens": final.expansion_tokens,
            "consumed_tokens": final.consumed_tokens,
            "remaining_budget": final.remaining_budget,
            "stop_reason": final.stop_reason,
            "expanded_symbols": [symbols_by_id[marker_id] for marker_id in expanded_ids],
        },
        "improved": improved,
    }


def run_benchmark() -> dict:
    with tempfile.TemporaryDirectory(prefix="agent-token-navigator-") as temporary:
        base = Path(temporary)
        root = base / "fixture"
        write_fixture(root)
        navigator = TaskNavigator(root, base / "data")
        navigator.provider.index()
        results = [run_case(navigator, case) for case in CASES]
    improved_count = sum(result["improved"] for result in results)
    passed = (
        len(results) >= 3
        and all(not result["contains_code_identifier"] for result in results)
        and all(result["static"]["correct"] and result["navigator"]["correct"] for result in results)
        and improved_count > len(results) / 2
    )
    return {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "case_count": len(results),
        "improved_count": improved_count,
        "comparison": "same sparse map; fewer marker expansions to the expected target",
        "results": results,
    }


def main() -> int:
    payload = run_benchmark()
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
