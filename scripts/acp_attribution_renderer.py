#!/usr/bin/env python3
"""Render canonical ACP attribution JSON without deriving analytical metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_ID = "cost-attribution-baseline-v1"
RENDERER_VERSION = "acp-attribution-renderer-v0.1"


class RenderError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def attribution_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_attribution(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_id") != SCHEMA_ID:
        raise RenderError("input_must_be_cost_attribution_baseline_v1")
    required = {
        "generator_version", "source_fact_report_sha256", "scope_and_denominators",
        "coverage_summary", "session_attribution", "tool_family_attribution",
        "call_attribution", "top_calls_and_concentration", "cycle_structure_or_unknown",
        "objective_repetition_facts", "unknown_volume_and_reasons", "traceability_index",
    }
    missing = required - set(value)
    if missing:
        raise RenderError(f"missing_canonical_fields:{','.join(sorted(missing))}")
    return value


def _value(metric: dict[str, Any]) -> str:
    value = metric.get("value")
    return "unknown" if value is None else str(value)


def _cell(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_json(attribution: Any) -> bytes:
    return canonical_bytes(validate_attribution(attribution))


def render_markdown(attribution: Any) -> str:
    data = validate_attribution(attribution)
    scope = data["scope_and_denominators"]
    coverage = data["coverage_summary"]
    concentration = data["top_calls_and_concentration"]
    unknown = data["unknown_volume_and_reasons"]
    repetition = data["objective_repetition_facts"]
    lines = [
        "# ACP Cost Attribution Map",
        "",
        f"- Schema: `{data['schema_id']}`",
        f"- Engine: `{data['generator_version']}`",
        f"- Renderer: `{RENDERER_VERSION}`",
        f"- Attribution input SHA-256: `{attribution_sha256(data)}`",
        f"- Source fact report SHA-256: `{data['source_fact_report_sha256']}`",
        "",
        "## Session Summary",
        "",
        f"- Observed calls: {_value(scope['observed_calls'])} [{scope['observed_calls']['status']}]",
        f"- Attributed visible estimated tokens: {_value(scope['observed_matched_model_visible_estimated_tokens'])} [{scope['observed_matched_model_visible_estimated_tokens']['status']}]",
        f"- Unknown visible estimated tokens: {unknown['estimated_model_visible_tokens']}",
        f"- Eligible calls: {concentration['eligible_call_count']}",
        f"- Attribution coverage status: {coverage['status']}",
        f"- Session total tokens: {_value(scope['session_total_tokens'])} [{scope['session_total_tokens']['status']}]",
        f"- Model cycles: {_value(scope['model_cycles'])} [{scope['model_cycles']['status']}]",
        "",
        "### Sessions",
        "",
        "| Session ID | Observed events | Denominator tokens | Attributed tokens | Unattributed tokens | Coverage | Status |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in data["session_attribution"]:
        lines.append(
            f"| `{_cell(row['session_id_hash'])}` | {_cell(row['observed_event_count'])} | "
            f"{_cell(row['denominator_visible_estimated_tokens'])} | {_cell(row['attributed_visible_estimated_tokens'])} | "
            f"{_cell(row['unattributed_visible_estimated_tokens'])} | {_cell(row['attribution_coverage'])} | {_cell(row['status'])} |"
        )
    lines.extend([
        "",
        "## Cost Concentration",
        "",
        "| Measure | Value | Status |",
        "|---|---:|---|",
    ])
    for label, key in (
        ("Top-1 share", "top1_share"),
        ("Top-3 share", "top3_share"),
        ("Top-10 share", "topk_share"),
        ("Top 10% share", "top10_percent_share"),
        ("Top 20% share", "top20_percent_share"),
        ("Call HHI", "call_hhi"),
        ("Tool-family HHI", "tool_family_hhi"),
    ):
        item = concentration[key]
        lines.append(f"| {label} | {_cell(item['value'])} | {_cell(item['status'])} |")
    lines.extend([
        "",
        "## Tool-family Map",
        "",
        "| Tool family | Calls | Visible tokens | Share | Median | p90 | Max | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ])
    for row in data["tool_family_attribution"]:
        distribution = row["distribution"]
        lines.append(
            f"| {_cell(row['tool_family'])} | {_cell(row['call_count']['value'])} | "
            f"{_cell(row['visible_estimated_tokens']['value'])} | {_cell(row['visible_token_share']['value'])} | "
            f"{_cell(distribution['median'])} | {_cell(distribution['p90'])} | {_cell(distribution['max'])} | "
            f"{_cell(row['visible_estimated_tokens']['status'])} |"
        )
    lines.extend([
        "",
        "## Top Calls",
        "",
        "| Rank | Call index | Stable call ID | Tool family | Visible tokens | Share |",
        "|---:|---:|---|---|---:|---:|",
    ])
    for row in concentration["top_calls"]:
        lines.append(
            f"| {_cell(row['rank'])} | {_cell(row['call_index'])} | `{_cell(row['call_id'])}` | "
            f"{_cell(row['tool_family'])} | {_cell(row['visible_estimated_tokens'])} | {_cell(row['visible_token_share'])} |"
        )
    lines.extend([
        "",
        "## Repetition Facts",
        "",
        "Factual relationships only; no necessity or actionability conclusion is made.",
        "",
        "| Relationship | Status | Relation count | Listed observations | Known observations | Group observation visible tokens |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for label, key in (
        ("Exact repeated evidence", "exact_payload_duplicate"),
        ("Same-file repeated evidence", "same_file_repeat"),
        ("Range-overlap evidence", "range_overlap"),
    ):
        item = repetition[key]
        lines.append(
            f"| {label} | {_cell(item['status'])} | {_cell(item['relationship_count'])} | "
            f"{_cell(item['listed_observation_count'])} | {_cell(item['known_attributed_observation_count'])} | "
            f"{_cell(item['group_observation_visible_estimated_tokens'])} |"
        )
    lines.extend([
        "",
        "## Coverage / Unknown",
        "",
        f"- Status: {coverage['status']}",
        f"- Unknown observations: {unknown['count']}",
        f"- Unknown visible estimated tokens: {unknown['estimated_model_visible_tokens']}",
        "",
        "| Unknown reason | Count |",
        "|---|---:|",
    ])
    for reason, count in sorted(unknown["reason_counts"].items()):
        lines.append(f"| {_cell(reason)} | {_cell(count)} |")
    lines.extend([
        "",
        "### Non-complete Call Evidence",
        "",
        "| Stable call ID | Tool family | Coverage state | Attributed tokens | Unattributed tokens | Status |",
        "|---|---|---|---:|---:|---|",
    ])
    for row in data["call_attribution"]:
        if row["status"] != "complete":
            lines.append(
                f"| `{_cell(row['call_id'])}` | {_cell(row['tool_family'])} | {_cell(row['coverage_state'])} | "
                f"{_cell(row['attributed_visible_estimated_tokens'])} | {_cell(row['unattributed_visible_estimated_tokens'])} | "
                f"{_cell(row['status'])} |"
            )
    lines.extend([
        "",
        "## Traceability",
        "",
        "| Output metric path | Canonical source pointer(s) |",
        "|---|---|",
    ])
    for item in data["traceability_index"]:
        pointers = ", ".join(source["json_pointer"] for source in item["source_refs"])
        lines.append(f"| `{_cell(item['metric_path'])}` | `{_cell(pointers)}` |")
    return "\n".join(lines) + "\n"


def render_text(attribution: Any) -> str:
    data = validate_attribution(attribution)
    scope = data["scope_and_denominators"]
    coverage = data["coverage_summary"]
    concentration = data["top_calls_and_concentration"]
    unknown = data["unknown_volume_and_reasons"]
    repetition = data["objective_repetition_facts"]
    lines = [
        "ACP COST ATTRIBUTION MAP",
        f"schema={data['schema_id']}",
        f"engine={data['generator_version']}",
        f"renderer={RENDERER_VERSION}",
        f"attribution_input_sha256={attribution_sha256(data)}",
        f"source_fact_report_sha256={data['source_fact_report_sha256']}",
        "",
        "SESSION SUMMARY",
        f"observed_calls={_value(scope['observed_calls'])} status={scope['observed_calls']['status']}",
        f"attributed_visible_estimated_tokens={_value(scope['observed_matched_model_visible_estimated_tokens'])}",
        f"unknown_visible_estimated_tokens={unknown['estimated_model_visible_tokens']}",
        f"eligible_calls={concentration['eligible_call_count']}",
        f"coverage_status={coverage['status']}",
        f"session_total_tokens={_value(scope['session_total_tokens'])}",
        f"model_cycles={_value(scope['model_cycles'])}",
        "",
        "CONCENTRATION",
    ]
    for key in ("top1_share", "top3_share", "topk_share", "top10_percent_share", "top20_percent_share", "call_hhi", "tool_family_hhi"):
        lines.append(f"{key}={_value(concentration[key])} status={concentration[key]['status']}")
    lines.extend(["", "TOOL FAMILIES"])
    for row in data["tool_family_attribution"]:
        distribution = row["distribution"]
        lines.append(
            f"{row['tool_family']} calls={_value(row['call_count'])} tokens={_value(row['visible_estimated_tokens'])} "
            f"share={_value(row['visible_token_share'])} median={_cell(distribution['median'])} "
            f"p90={_cell(distribution['p90'])} max={_cell(distribution['max'])}"
        )
    lines.extend(["", "TOP CALLS"])
    for row in concentration["top_calls"]:
        lines.append(
            f"rank={row['rank']} call_index={_cell(row['call_index'])} call_id={_cell(row['call_id'])} "
            f"family={row['tool_family']} tokens={row['visible_estimated_tokens']} share={row['visible_token_share']}"
        )
    lines.extend(["", "REPETITION FACTS", "Factual relationships only; no necessity or actionability conclusion is made."])
    for key in ("exact_payload_duplicate", "same_file_repeat", "range_overlap"):
        item = repetition[key]
        lines.append(
            f"{key} status={item['status']} relations={item['relationship_count']} "
            f"group_observation_visible_tokens={_cell(item['group_observation_visible_estimated_tokens'])}"
        )
    lines.extend(["", "COVERAGE / UNKNOWN", f"status={coverage['status']}", f"unknown_count={unknown['count']}", f"unknown_visible_estimated_tokens={unknown['estimated_model_visible_tokens']}"])
    for reason, count in sorted(unknown["reason_counts"].items()):
        lines.append(f"reason={reason} count={count}")
    lines.extend(["", "NON-COMPLETE CALL EVIDENCE"])
    for row in data["call_attribution"]:
        if row["status"] != "complete":
            lines.append(
                f"call_id={_cell(row['call_id'])} family={row['tool_family']} coverage_state={row['coverage_state']} "
                f"attributed_tokens={_cell(row['attributed_visible_estimated_tokens'])} "
                f"unattributed_tokens={_cell(row['unattributed_visible_estimated_tokens'])} status={row['status']}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attribution_json", type=Path)
    parser.add_argument("--format", choices=("markdown", "text", "json"), default="text")
    args = parser.parse_args()
    data = json.loads(args.attribution_json.read_text(encoding="utf-8"))
    if args.format == "markdown":
        print(render_markdown(data), end="")
    elif args.format == "json":
        print(render_json(data).decode("utf-8"), end="")
    else:
        print(render_text(data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
