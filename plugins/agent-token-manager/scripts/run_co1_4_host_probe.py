#!/usr/bin/env python3
"""Reconstruct raw -> Hook -> model-visible host paths from CO-1.3 artifacts."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from collections import Counter
from pathlib import Path
from typing import Any

from run_co0_gate import load_jsonl
from run_co1_gate2 import normalize_command, sha256_text, transcript_calls


CODE_WORD = re.compile(r"(?:^|[\s;&|])(?:rg|sed|cat|awk|perl|find|python3?)(?:\s|$)|\.(?:py|js|ts|tsx|go|rs|java)(?:\s|$)")


def unwrap_cli_command(command: str) -> str:
    try:
        words = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return command.strip()
    if len(words) >= 3 and words[0].endswith(("/zsh", "/bash", "/sh")) and words[1] == "-lc":
        return words[2]
    return command.strip()


def command_family(command: str) -> str:
    value = command.strip()
    if "&&" in value or "||" in value or "|" in value or ";" in value:
        return "compound_shell"
    try:
        words = shlex.split(value, comments=False, posix=True)
    except ValueError:
        return "other"
    if not words:
        return "other"
    executable = words[0].rsplit("/", 1)[-1]
    return executable if executable in {"rg", "sed", "cat", "awk", "perl", "find", "python", "python3"} else "other"


def code_bearing(command: str) -> bool:
    return bool(CODE_WORD.search(command))


def cli_calls(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in load_jsonl(path):
        item = event.get("item")
        if event.get("type") != "item.completed" or not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        command = unwrap_cli_command(str(item.get("command", "")))
        output = str(item.get("aggregated_output", ""))
        rows.append({"command": command, "output": output, "exit_code": item.get("exit_code")})
    return rows


def transcript_path(records: list[dict[str, Any]]) -> Path | None:
    for record in reversed(records):
        value = record.get("transcript_path")
        if isinstance(value, str):
            return Path(value)
    return None


def analyze_run(run_dir: Path) -> dict[str, Any]:
    cli = cli_calls(run_dir / "codex.jsonl")
    records = load_jsonl(run_dir / "hook-probe.jsonl")
    transcript = transcript_path(records)
    visible = transcript_calls(load_jsonl(transcript)) if transcript and transcript.is_file() else []
    count = max(len(cli), len(records), len(visible))
    calls: list[dict[str, Any]] = []
    for index in range(count):
        raw = cli[index] if index < len(cli) else {}
        hook = records[index] if index < len(records) else {}
        shown = visible[index] if index < len(visible) else {}
        command = str(raw.get("command", shown.get("command", "")))
        raw_output = str(raw.get("output", ""))
        visible_output = str(shown.get("output", ""))
        raw_hash = sha256_text(raw_output)
        command_match = bool(raw and shown) and normalize_command(command) == normalize_command(str(shown.get("command", "")))
        hook_match = bool(raw and hook) and hook.get("original_sha256") == raw_hash
        raw_in_visible = bool(raw_output) and raw_output in visible_output
        calls.append({
            "call_index": index, "family": command_family(command), "code_bearing": code_bearing(command),
            "request_sha256": sha256_text(normalize_command(command)), "raw_sha256": raw_hash,
            "raw_chars": len(raw_output), "model_visible_chars": len(visible_output),
            "model_visible_tokens": (len(visible_output) + 3) // 4,
            "command_correlated": command_match, "hook_observed": hook_match,
            "raw_present_in_model_visible": raw_in_visible,
            "hook_tool_name": hook.get("tool_name"), "hook_decision": hook.get("decision"),
        })
    return {
        "run_id": run_dir.name.removesuffix("-co"), "cli_call_count": len(cli),
        "hook_record_count": len(records), "model_visible_call_count": len(visible), "calls": calls,
    }


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [call for run in runs for call in run["calls"] if call["code_bearing"]]
    visible_tokens = sum(call["model_visible_tokens"] for call in calls)
    observed = [call for call in calls if call["hook_observed"]]
    correlated = [
        call for call in calls
        if call["command_correlated"] and call["hook_observed"] and call["raw_present_in_model_visible"]
    ]
    observed_tokens = sum(call["model_visible_tokens"] for call in observed)
    families = Counter(call["family"] for call in calls)
    family_tokens = Counter()
    for call in calls:
        family_tokens[call["family"]] += call["model_visible_tokens"]
    call_coverage = len(observed) / len(calls) if calls else 0.0
    weighted_coverage = observed_tokens / visible_tokens if visible_tokens else 0.0
    correlation = len(correlated) / len(calls) if calls else 0.0
    checks = {
        "call_coverage_at_least_0_90": call_coverage >= 0.90,
        "weighted_coverage_at_least_0_90": weighted_coverage >= 0.90,
        "correlation_at_least_0_95": correlation >= 0.95,
        "observation_is_command_independent": len(families) >= 2 and all(call["hook_tool_name"] == "Bash" for call in observed),
    }
    return {
        "schema_version": 1, "status": "passed" if all(checks.values()) else "failed",
        "checks": checks, "run_count": len(runs), "code_bearing_call_count": len(calls),
        "model_visible_code_tokens": visible_tokens, "hook_observed_call_count": len(observed),
        "hook_observed_model_visible_tokens": observed_tokens,
        "call_coverage": round(call_coverage, 6), "weighted_coverage": round(weighted_coverage, 6),
        "end_to_end_correlation": round(correlation, 6),
        "family_call_counts": dict(sorted(families.items())),
        "family_model_visible_tokens": dict(sorted(family_tokens.items())),
        "runs": runs,
    }


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    repository = plugin.parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=repository / ".agent-token-manager/co1-3")
    parser.add_argument("--output", type=Path, default=plugin / "resources/co1_4_observe_results.json")
    args = parser.parse_args()
    run_dirs = sorted(path for path in args.artifacts.glob("*-co") if (path / "codex.jsonl").is_file())
    if len(run_dirs) != 12:
        raise RuntimeError(f"expected 12 CO-1.3 CO runs, found {len(run_dirs)}")
    result = summarize([analyze_run(path) for path in run_dirs])
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
