#!/usr/bin/env python3
"""Render canonical model-cycle cost facts without adding metrics or verdicts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


RENDERER_VERSION = "acp-cycle-cost-renderer-v0.1"


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    if report.get("schema_id") != "model-cycle-cost-analysis-v1":
        raise ValueError("renderer_requires_model_cycle_cost_analysis_v1")
    lines = [
        "# Host-Reported Model-Cycle Cost Baseline", "",
        f"- Schema: `{report['schema_id']}`", f"- Analyzer: `{report['analyzer_version']}`",
        f"- Renderer: `{RENDERER_VERSION}`", f"- Coverage: `{report['coverage']['status']}` ({report['coverage']['exact_linked_run_count']}/{report['coverage']['source_run_count']} exact-linked runs)",
        "- Interpretation: descriptive host usage facts; no causal, waste, necessity, or savings verdict", "",
    ]
    for arm in report["arm_analyses"]:
        lines.extend((f"## {arm['arm'].upper()} — {arm['role']}", "", "### Cycle count and session total", "", "| Cycles | Runs | Sample status | Median total Tokens | Mean total Tokens |", "|---:|---:|---|---:|---:|"))
        for row in arm["cycle_count_groups"]:
            stats = row["session_total_tokens"]
            lines.append(f"| {row['cycle_count']} | {row['run_count']} | {row['sample_status']} | {_fmt(stats['median'])} | {_fmt(stats['mean'])} |")
        lines.extend(("", "### Cycle ordinal cost", "", "| Ordinal | Runs | Sample status | Increment median | Increment mean | Cumulative median |", "|---:|---:|---|---:|---:|---:|"))
        for row in arm["cycle_ordinal_costs"]:
            inc = row["incremental_usage"]["total_tokens"]
            cum = row["cumulative_usage"]["total_tokens"]
            lines.append(f"| {row['ordinal']} | {row['run_count']} | {row['sample_status']} | {_fmt(inc['median'])} | {_fmt(inc['mean'])} | {_fmt(cum['median'])} |")
        lines.extend(("", "### Within-run adjacent increments", "", "| Transition | Runs | Sample status | Median delta | Median ratio |", "|---|---:|---|---:|---:|"))
        for row in arm["within_run_transitions"]:
            lines.append(f"| {row['from_ordinal']}→{row['to_ordinal']} | {row['run_count']} | {row['sample_status']} | {_fmt(row['incremental_total_token_delta']['median'])} | {_fmt(row['incremental_total_token_ratio']['median'])} |")
        lines.append("")
    lines.extend(("## Unknowns", ""))
    for key, value in report["unknowns"].items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def render_text(report: dict[str, Any]) -> str:
    if report.get("schema_id") != "model-cycle-cost-analysis-v1":
        raise ValueError("renderer_requires_model_cycle_cost_analysis_v1")
    lines = [f"Model-cycle cost facts | coverage {report['coverage']['exact_linked_run_count']}/{report['coverage']['source_run_count']}"]
    for arm in report["arm_analyses"]:
        lines.append(f"{arm['arm'].upper()} ({arm['role']}): {arm['run_count']} runs")
        for row in arm["cycle_ordinal_costs"]:
            inc = row["incremental_usage"]["total_tokens"]
            lines.append(f"  cycle {row['ordinal']}: n={row['run_count']} increment_median={_fmt(inc['median'])} status={row['sample_status']}")
    lines.append("Fact-only; new-vs-history, causality, necessity, avoidability, and savings remain unknown.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--format", choices=("markdown", "text"), default="markdown")
    args = parser.parse_args()
    report = json.loads(args.analysis.read_text(encoding="utf-8"))
    print(render_markdown(report) if args.format == "markdown" else render_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
