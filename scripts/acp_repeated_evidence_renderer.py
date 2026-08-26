#!/usr/bin/env python3
"""Render canonical repeated-evidence analysis without deriving new metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_ID = "repeated-evidence-analysis-v1"
RENDERER_VERSION = "acp-repeated-evidence-renderer-v0.1"


class RenderError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def analysis_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_analysis(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_id") != SCHEMA_ID:
        raise RenderError("input_must_be_repeated_evidence_analysis_v1")
    required = {
        "engine_version", "source_and_scope", "denominator_and_coverage", "repeat_groups",
        "call_relations", "unique_repeated_observations", "path_repeat_facts",
        "range_relation_facts", "observation_volume", "unknowns", "traceability", "policy",
    }
    if required - set(value):
        raise RenderError("missing_canonical_analysis_fields")
    if not value["policy"].get("fact_only") or not value["policy"].get("no_diagnosis"):
        raise RenderError("analysis_policy_not_frozen")
    return value


def _cell(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_json(value: Any) -> bytes:
    return canonical_bytes(validate_analysis(value))


def render_markdown(value: Any) -> str:
    data = validate_analysis(value)
    scope = data["source_and_scope"]
    coverage = data["denominator_and_coverage"]
    volume = data["observation_volume"]
    path = data["path_repeat_facts"]
    ranges = data["range_relation_facts"]
    unknowns = data["unknowns"]
    lines = [
        "# ACP Repeated Evidence Map", "",
        f"- Schema: `{data['schema_id']}`",
        f"- Engine: `{data['engine_version']}`",
        f"- Renderer: `{RENDERER_VERSION}`",
        f"- Analysis SHA-256: `{analysis_sha256(data)}`",
        f"- Relation scope: `{scope['relation_scope']}`",
        "- Interpretation: repeated observations are factual relations only; no necessity or actionability conclusion is made.",
        "", "## Observation Volume", "",
        f"- Eligible observed visible estimated tokens: {volume['denominator_visible_estimated_tokens']}",
        f"- Relations: {volume['relation_count']}",
        f"- Unique repeated observations: {volume['unique_repeated_observation_count']}",
        f"- Unique repeated observation tokens: {volume['unique_repeated_observation_tokens']}",
        f"- Repeated observation share: {_cell(volume['repeated_observation_share'])}",
        f"- Counting rule: {volume['token_counting_rule']}",
        "", "## Coverage", "",
        "| Dimension | Known calls | Status |", "|---|---:|---|",
        f"| Relation order | {coverage['relation_order_eligible_call_count']} | {coverage['relation_order_coverage_status']} |",
        f"| Path identity | {coverage['path_identity_known_call_count']} | {coverage['path_identity_coverage_status']} |",
        f"| Explicit range | {coverage['explicit_range_known_call_count']} | {coverage['explicit_range_coverage_status']} |",
        f"| Model cycle | unknown | {coverage['cycle_coverage_status']} |",
        "", "## Relation Facts", "",
        "| Relation type | Count | Coverage/status |", "|---|---:|---|",
        f"| Exact payload repeat | {volume['relation_type_counts']['exact_payload_repeat']} | complete |",
        f"| Same path repeat | {path['same_path_relation_count']} | {path['status']} |",
        f"| Exact range repeat | {ranges['exact_range_relation_count']} | {ranges['status']} |",
        f"| Range contains | {ranges['range_contains_relation_count']} | {ranges['status']} |",
        f"| Range overlap | {ranges['range_overlap_relation_count']} | {ranges['status']} |",
        "", "## Unique Repeated Observations", "",
        "| Session | Call index | Call ID | Tokens | Relations | Types | Counted once |",
        "|---|---:|---|---:|---:|---|---|",
    ]
    for row in data["unique_repeated_observations"]:
        lines.append(
            f"| `{row['session_id_hash']}` | {row['call_index']} | `{row['call_id']}` | "
            f"{row['visible_estimated_tokens']} | {row['relation_count']} | {_cell(', '.join(row['relation_types']))} | "
            f"{str(row['counted_once']).lower()} |"
        )
    lines.extend([
        "", "## Call Relations", "",
        "| Type | Earlier | Later | Basis | Payload equal | Content stability | Cross-cycle |",
        "|---|---|---|---|---|---|---|",
    ])
    for row in data["call_relations"]:
        lines.append(
            f"| {row['relation_type']} | `{row['earlier_call_id']}` | `{row['later_call_id']}` | "
            f"{_cell(', '.join(row['evidence_basis']))} | {_cell(row['observed_payload_equality'])} | "
            f"{row['content_stability']} | {row['cross_cycle']} |"
        )
    lines.extend([
        "", "## Unknowns", "",
        f"- Source noneligible calls: {unknowns['source_noneligible_call_count']}",
        f"- Relation-order excluded calls: {unknowns['relation_order_excluded_call_count']}",
        f"- Path identity unknown calls: {unknowns['path_identity_unknown_call_count']}",
        f"- Explicit range unknown calls: {unknowns['explicit_range_unknown_call_count']}",
        f"- Cycle relation state: {unknowns['cycle_relation_state']}",
        f"- Content stability state: {unknowns['content_stability_state']}",
        "", "## Traceability", "",
    ])
    for row in data["traceability"]:
        refs = ", ".join(f"{ref['artifact']}:{ref['json_pointer']}" for ref in row["source_refs"])
        lines.append(f"- `{row['output_path']}` ← {refs}")
    return "\n".join(lines) + "\n"


def render_text(value: Any) -> str:
    data = validate_analysis(value)
    volume = data["observation_volume"]
    coverage = data["denominator_and_coverage"]
    return "\n".join([
        f"ACP Repeated Evidence Map [{data['schema_id']}]",
        f"scope={data['source_and_scope']['relation_scope']}",
        f"eligible_tokens={volume['denominator_visible_estimated_tokens']}",
        f"relations={volume['relation_count']}",
        f"unique_repeated_observations={volume['unique_repeated_observation_count']}",
        f"unique_repeated_observation_tokens={volume['unique_repeated_observation_tokens']}",
        f"repeated_observation_share={_cell(volume['repeated_observation_share'])}",
        f"path_coverage={coverage['path_identity_coverage_status']}",
        f"range_coverage={coverage['explicit_range_coverage_status']}",
        "interpretation=factual_relations_only",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--format", choices=("json", "markdown", "text"), default="text")
    args = parser.parse_args()
    value = json.loads(args.analysis.read_text(encoding="utf-8"))
    if args.format == "json":
        print(render_json(value).decode("utf-8"), end="")
    elif args.format == "markdown":
        print(render_markdown(value), end="")
    else:
        print(render_text(value), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
