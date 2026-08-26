#!/usr/bin/env python3
"""Deterministic, no-oracle ACP-1.4F treatment builder contract.

This module is offline-only. It does not register Hooks, read benchmark files, or
execute tools. The outer experiment harness is responsible for converting a tool
result into structural records and for keeping traceability identifiers separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "acp1-4f-treatment-builder-v1"
ALLOWED_FIELDS = (
    "tool_family",
    "request_shape",
    "requested_path_identity",
    "requested_range",
    "query_shape",
    "command_shape",
    "structural_result",
    "frozen_template_params",
)
PROHIBITED_KEYS = frozenset(
    {
        "answer",
        "case_id",
        "correctness",
        "expected",
        "ground_truth",
        "historical_correctness",
        "pilot_result",
        "scorer",
        "target_line",
        "target_regex",
    }
)


class ContractViolation(ValueError):
    """Raised when the structural no-oracle contract is violated."""


def _assert_no_oracle(value: Any, location: str) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().casefold()
            if normalized in PROHIBITED_KEYS:
                raise ContractViolation(f"prohibited_oracle_key:{location}.{normalized}")
            _assert_no_oracle(nested, f"{location}.{normalized}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_no_oracle(nested, f"{location}[{index}]")


def _normalized_records(records: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    normalized = []
    for ordinal, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ContractViolation(f"structural_record_required:{ordinal}")
        row = {str(key): value for key, value in record.items()}
        row.setdefault("ordinal", ordinal)
        normalized.append(row)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class TreatmentBuilderInput:
    tool_family: str
    request_shape: Mapping[str, Any]
    requested_path_identity: str | None
    requested_range: tuple[int, int] | None
    query_shape: Mapping[str, Any]
    command_shape: Mapping[str, Any]
    structural_result: Sequence[Mapping[str, Any]]
    frozen_template_params: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.tool_family not in {"read", "search", "bash"}:
            raise ContractViolation(f"unsupported_tool_family:{self.tool_family}")
        if self.requested_range is not None:
            start, end = self.requested_range
            if start < 1 or end < start:
                raise ContractViolation("invalid_inclusive_requested_range")
        for field in ALLOWED_FIELDS:
            _assert_no_oracle(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class TreatmentBuilderOutput:
    contract_version: str
    template_id: str
    disposition: str
    records: tuple[dict[str, Any], ...]
    reason: str


def _passthrough(template_id: str, records: tuple[dict[str, Any], ...], reason: str) -> TreatmentBuilderOutput:
    return TreatmentBuilderOutput(CONTRACT_VERSION, template_id, "passthrough", records, reason)


def _read_window(value: TreatmentBuilderInput, records: tuple[dict[str, Any], ...]) -> TreatmentBuilderOutput:
    template_id = "R1-read-structural-window-v1"
    anchors = tuple(str(item).casefold() for item in value.request_shape.get("anchors", ()) if str(item).strip())
    before = int(value.frozen_template_params.get("context_before", 2))
    after = int(value.frozen_template_params.get("context_after", 3))
    if not records or not anchors:
        return _passthrough(template_id, records, "missing_records_or_request_anchor")
    matches = []
    for index, row in enumerate(records):
        haystack = " ".join(str(row.get(key, "")) for key in ("key", "text", "symbol")).casefold()
        if any(anchor in haystack for anchor in anchors):
            matches.append(index)
    if len(matches) != 1:
        return _passthrough(template_id, records, "anchor_not_unique")
    selected = set(range(max(0, matches[0] - before), min(len(records), matches[0] + after + 1)))
    selected.update(index for index, row in enumerate(records) if row.get("kind") in {"header", "import"})
    output = tuple(row for index, row in enumerate(records) if index in selected)
    return TreatmentBuilderOutput(CONTRACT_VERSION, template_id, "projected", output, "unique_structural_anchor")


def _search_grouping(value: TreatmentBuilderInput, records: tuple[dict[str, Any], ...]) -> TreatmentBuilderOutput:
    template_id = "S1-search-structural-grouping-v1"
    first_n = int(value.frozen_template_params.get("first_n_per_group", 1))
    if first_n < 1 or not records:
        return _passthrough(template_id, records, "invalid_limit_or_empty_result")
    ordered = sorted(
        records,
        key=lambda row: (
            str(row.get("path_identity", "")),
            str(row.get("structural_key", "")),
            int(row.get("ordinal", 0)),
        ),
    )
    counts: dict[tuple[str, str], int] = {}
    selected = []
    for row in ordered:
        group = (str(row.get("path_identity", "")), str(row.get("structural_key", "")))
        if counts.get(group, 0) < first_n or bool(row.get("conflict")) or bool(row.get("ambiguous")):
            selected.append(row)
        counts[group] = counts.get(group, 0) + 1
    if len(selected) == len(records):
        return _passthrough(template_id, records, "no_structural_reduction")
    return TreatmentBuilderOutput(CONTRACT_VERSION, template_id, "projected", tuple(selected), "stable_path_key_first_n")


def _bash_projection(value: TreatmentBuilderInput, records: tuple[dict[str, Any], ...]) -> TreatmentBuilderOutput:
    template_id = "B1-bash-structured-projection-v1"
    if not records:
        return _passthrough(template_id, records, "empty_result")
    supported = {"exit", "failure", "error", "summary", "requested_field"}
    selected = tuple(row for row in records if str(row.get("kind", "")) in supported)
    if not selected:
        return _passthrough(template_id, records, "unsupported_free_text_or_shape")
    if len(selected) == len(records):
        return _passthrough(template_id, records, "no_structural_reduction")
    return TreatmentBuilderOutput(CONTRACT_VERSION, template_id, "projected", selected, "frozen_structural_kinds")


def build_treatment(value: TreatmentBuilderInput) -> TreatmentBuilderOutput:
    """Build one deterministic structural projection without benchmark identity."""

    records = _normalized_records(value.structural_result)
    if value.tool_family == "read":
        return _read_window(value, records)
    if value.tool_family == "search":
        return _search_grouping(value, records)
    return _bash_projection(value, records)

