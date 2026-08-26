#!/usr/bin/env python3
"""Render a canonical ACP hypothesis catalog without generating new candidates or metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_ID = "cost-necessity-hypothesis-catalog-v1"
RENDERER_VERSION = "acp-hypothesis-renderer-v0.1"


class RenderError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def catalog_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_catalog(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_id") != SCHEMA_ID:
        raise RenderError("input_must_be_cost_necessity_hypothesis_catalog_v1")
    required = {
        "source_and_scope", "candidate_generation_policy", "catalog_status",
        "hypothesis_candidates", "candidate_summary", "unknowns", "traceability", "policy",
    }
    if required - set(value):
        raise RenderError("missing_canonical_catalog_fields")
    if value["policy"].get("intervention_executed") or value["policy"].get("online_effect"):
        raise RenderError("catalog_policy_not_offline")
    return value


def _cell(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_json(value: Any) -> bytes:
    return canonical_bytes(validate_catalog(value))


def render_markdown(value: Any) -> str:
    data = validate_catalog(value)
    summary = data["candidate_summary"]
    unknowns = data["unknowns"]
    policy = data["candidate_generation_policy"]
    lines = [
        "# ACP Cost Necessity Hypothesis Catalog", "",
        f"- Schema: `{data['schema_id']}`",
        f"- Generator: `{data['generator_version']}`",
        f"- Renderer: `{RENDERER_VERSION}`",
        f"- Catalog SHA-256: `{catalog_sha256(data)}`",
        f"- Status: `{data['catalog_status']}`",
        "- Meaning: entries are offline experiment candidates, not anomaly, necessity, or actionability conclusions.",
        "", "## Frozen Candidate Policy", "",
        f"- High-cost minimum share: {policy['high_cost_min_visible_token_share']}",
        f"- High-cost minimum observed exposure: {policy['high_cost_min_observed_exposure_tokens']}",
        f"- High-cost candidate cap: {policy['high_cost_max_candidates']}",
        f"- Concentration minimum call HHI: {policy['concentration_min_call_hhi']}",
        f"- Concentration minimum Top-3 share: {policy['concentration_min_top3_share']}",
        "", "## Candidate Summary", "",
        f"- Candidate count: {summary['candidate_count']}",
        f"- Unique target calls: {summary['unique_target_call_count']}",
        f"- Unique target observed exposure tokens: {summary['unique_target_observed_exposure_tokens']}",
        f"- Unique target observed share: {_cell(summary['unique_target_observed_share'])}",
        f"- Counting rule: {summary['target_exposure_counting_rule']}",
        "", "## Hypothesis Candidates", "",
        "| ID | Type | Targets | Observed exposure | Share | Necessity | Causal | Feasibility |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for row in data["hypothesis_candidates"]:
        lines.append(
            f"| `{row['hypothesis_id']}` | {row['hypothesis_type']} | {len(row['target_call_ids'])} | "
            f"{row['observed_exposure_tokens']} | {_cell(row['observed_share'])} | "
            f"{row['necessity_status']} | {row['causal_status']} | {row['validation_feasibility']['status']} |"
        )
    lines.extend([
        "", "## Required Validation", "",
    ])
    required = data["hypothesis_candidates"][0]["required_validation"] if data["hypothesis_candidates"] else []
    for step in required:
        lines.append(f"- `{step}`")
    lines.extend([
        "", "## Unknowns and Blocking Conditions", "",
        f"- Necessity status: {unknowns['necessity_status']}",
        f"- Causal status: {unknowns['causal_status']}",
        f"- Validation feasibility: {unknowns['candidate_validation_feasibility']}",
        f"- Blocking reasons: {_cell(unknowns['blocking_reason_codes'])}",
        "", "## Traceability", "",
    ])
    for row in data["traceability"]:
        refs = ", ".join(f"{ref['artifact']}:{ref['json_pointer']}" for ref in row["source_refs"])
        lines.append(f"- `{row['output_path']}` ← {refs}")
    return "\n".join(lines) + "\n"


def render_text(value: Any) -> str:
    data = validate_catalog(value)
    summary = data["candidate_summary"]
    unknowns = data["unknowns"]
    return "\n".join([
        f"ACP Cost Necessity Hypothesis Catalog [{data['schema_id']}]",
        f"status={data['catalog_status']}",
        f"candidates={summary['candidate_count']}",
        f"high_cost_candidates={summary['candidate_type_counts']['high_cost_call_candidate']}",
        f"concentration_candidates={summary['candidate_type_counts']['cost_concentration_candidate']}",
        f"repeated_evidence_candidates={summary['candidate_type_counts']['repeated_or_overlapping_evidence_candidate']}",
        f"unique_target_exposure_tokens={summary['unique_target_observed_exposure_tokens']}",
        f"necessity_status={unknowns['necessity_status']}",
        f"causal_status={unknowns['causal_status']}",
        f"validation_feasibility={unknowns['candidate_validation_feasibility']}",
        "interpretation=offline_experiment_candidates_only",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--format", choices=("json", "markdown", "text"), default="text")
    args = parser.parse_args()
    value = json.loads(args.catalog.read_text(encoding="utf-8"))
    if args.format == "json":
        print(render_json(value).decode("utf-8"), end="")
    elif args.format == "markdown":
        print(render_markdown(value), end="")
    else:
        print(render_text(value), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
