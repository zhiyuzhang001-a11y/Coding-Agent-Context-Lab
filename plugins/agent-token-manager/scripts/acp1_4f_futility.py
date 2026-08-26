#!/usr/bin/env python3
"""Pure futility calculations for a future ACP-1.4F Native runner."""

from __future__ import annotations

from collections import Counter
from typing import Any


def case_can_still_qualify(
    observed: int,
    total: int,
    correct: int,
    recurrence: int,
    ambiguous: int,
    dominant_path_frequency: int,
    correct_min: int,
    recurrence_min: int,
    ambiguous_max: int,
    dominant_path_min: int,
) -> bool:
    remaining = max(0, total - observed)
    return (
        observed <= total
        and correct + remaining >= correct_min
        and recurrence + remaining >= recurrence_min
        and ambiguous <= ambiguous_max
        and dominant_path_frequency + remaining >= dominant_path_min
    )


def coverage_maximum(
    frozen_cases: list[dict[str, Any]],
    case_states: dict[str, str],
    minimum_total: int,
    minimum_per_family: int,
) -> dict[str, Any]:
    families = sorted({str(case["family"]) for case in frozen_cases})
    maximum_by_family: Counter[str] = Counter()
    for case in frozen_cases:
        state = case_states.get(str(case["case_id"]), "unresolved")
        if state in {"qualified", "unresolved"}:
            maximum_by_family[str(case["family"])] += 1
    overall_maximum = sum(maximum_by_family.values())
    impossible_families = [family for family in families if maximum_by_family[family] < minimum_per_family]
    can_pass = overall_maximum >= minimum_total and not impossible_families
    return {
        "maximum_qualified_by_family": {family: maximum_by_family[family] for family in families},
        "overall_maximum_qualified": overall_maximum,
        "minimum_total": minimum_total,
        "minimum_per_family": minimum_per_family,
        "impossible_families": impossible_families,
        "native_coverage_gate_can_still_pass": can_pass,
        "stop_reason": None if can_pass else "STOP_FUTILITY",
    }
