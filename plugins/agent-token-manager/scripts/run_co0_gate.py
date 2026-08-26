#!/usr/bin/env python3
"""Run one isolated Codex CO-0 model-visible canary gate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def fixture_canary(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("SECRET_TOKEN: "):
            return line.split(": ", 1)[1]
    raise ValueError("fixture has no SECRET_TOKEN line")


def model_tool_outputs(events: list[dict[str, Any]]) -> list[str]:
    """Extract rollout tool-result messages that are candidates for model input."""
    outputs: list[str] = []
    for event in events:
        if event.get("type") != "response_item":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("type") not in {
            "custom_tool_call_output",
            "function_call_output",
        }:
            continue
        output = payload.get("output")
        if isinstance(output, str):
            outputs.append(output)
        elif output is not None:
            outputs.append(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    return outputs


def run_gate(
    codex: Path,
    workspace: Path,
    fixture: Path,
    output_dir: Path,
    timeout: int,
    *,
    persist_session: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    canary = fixture_canary(fixture)
    relative_fixture = fixture.relative_to(workspace)
    prompt = (
        f"Run exactly this one shell command: cat -- {relative_fixture}. "
        "Do not run any other command or tool. Then inspect only the returned tool result. "
        "If the exact value on the SECRET_TOKEN line is visible, reply with that value; "
        "otherwise reply exactly NOT_VISIBLE."
    )
    environment = dict(os.environ)
    environment.update(
        {
            "AGENT_TOKEN_MANAGER_DATA": str(output_dir),
            "AGENT_TOKEN_MANAGER_CO0_MODE": "enforce",
            "AGENT_TOKEN_MANAGER_CO0_MIN_CHARS": "128",
            "AGENT_TOKEN_MANAGER_CO0_VISIBLE_CHARS": "256",
            "AGENT_TOKEN_MANAGER_CO0_CANARY": canary,
            "AGENT_TOKEN_MANAGER_CO0_RECORD_TRANSCRIPT_PATH": "1",
        }
    )
    command = [
        str(codex),
        "exec",
        "--json",
        "--dangerously-bypass-hook-trust",
        "--sandbox",
        "read-only",
        "--cd",
        str(workspace),
        prompt,
    ]
    if not persist_session:
        command.insert(3, "--ephemeral")
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
            timeout=timeout,
        )
        timed_out = False
    except subprocess.TimeoutExpired as error:
        result = subprocess.CompletedProcess(
            command,
            124,
            stdout=error.stdout or "",
            stderr=error.stderr or "",
        )
        timed_out = True

    stdout = result.stdout if isinstance(result.stdout, str) else result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode("utf-8", errors="replace")
    (output_dir / "codex.jsonl").write_text(stdout, encoding="utf-8")
    (output_dir / "codex.stderr.txt").write_text(stderr, encoding="utf-8")
    events = load_jsonl(output_dir / "codex.jsonl")
    event_text = json.dumps(events, ensure_ascii=False, separators=(",", ":"))

    optimizer_records = load_jsonl(output_dir / "context-optimizer.jsonl")
    optimized = [record for record in optimizer_records if record.get("status") == "optimized"]
    relevant = optimized[-1] if optimized else {}
    transcript_path_text = relevant.get("transcript_path")
    transcript_path = Path(transcript_path_text) if isinstance(transcript_path_text, str) else None
    transcript_events = load_jsonl(transcript_path) if transcript_path is not None else []
    model_outputs = model_tool_outputs(transcript_events)
    model_output_text = "\n".join(model_outputs)
    final_messages = [
        event.get("item", {}).get("text", "")
        for event in events
        if isinstance(event.get("item"), dict) and event.get("item", {}).get("type") == "agent_message"
    ]
    final_text = final_messages[-1].strip() if final_messages else ""
    checks = {
        "codex_exit_zero": result.returncode == 0,
        "not_timed_out": not timed_out,
        "optimized_record_present": bool(optimized),
        "canary_present_in_original": relevant.get("canary_in_original") is True,
        "canary_absent_from_replacement": relevant.get("canary_in_replacement") is False,
        "transcript_available": bool(transcript_events),
        "replacement_present_in_model_tool_output": "Smart Read CO-0 optimized result" in model_output_text,
        "canary_absent_from_model_tool_output": canary not in model_output_text,
        "model_reports_not_visible": final_text == "NOT_VISIBLE",
    }
    report = {
        "schema_version": 1,
        "status": "passed" if all(checks.values()) else "failed",
        "workspace": str(workspace),
        "fixture": str(relative_fixture),
        "codex_exit_code": result.returncode,
        "checks": checks,
        "optimizer_statuses": [record.get("status") for record in optimizer_records],
        "final_text": final_text,
        "diagnostics": {
            "raw_canary_recorded_in_codex_exec_events": canary in event_text,
            "model_tool_output_count": len(model_outputs),
        },
        "artifacts": {
            "codex_jsonl": str(output_dir / "codex.jsonl"),
            "codex_stderr": str(output_dir / "codex.stderr.txt"),
            "optimizer_log": str(output_dir / "context-optimizer.jsonl"),
            "transcript": str(transcript_path) if transcript_path is not None else None,
        },
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--codex", type=Path, default=Path("/Applications/ChatGPT.app/Contents/Resources/codex"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--persist-session", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = run_gate(
        args.codex.resolve(),
        args.workspace.resolve(),
        args.fixture.resolve(),
        args.output_dir.resolve(),
        args.timeout,
        persist_session=args.persist_session,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
