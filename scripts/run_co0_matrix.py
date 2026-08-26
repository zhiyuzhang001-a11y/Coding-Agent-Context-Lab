#!/usr/bin/env python3
"""Run the frozen CO-0 interface and retry-aware economic matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
from pathlib import Path
from typing import Any

from run_co0_gate import load_jsonl, model_tool_outputs


SUPPORTED_NAMES = ("cat", "sed", "rg", "known_symbol")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def fixture_canary(path: Path, prefix: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if prefix in stripped:
            tail = stripped.split(prefix, 1)[1]
            return tail.split('"', 1)[0].strip()
    raise ValueError(f"fixture has no {prefix!r}")


def scenarios(workspace: Path) -> dict[str, dict[str, Any]]:
    text_fixture = workspace / "plugins/agent-token-manager/resources/co0_canary_fixture.txt"
    symbol_fixture = workspace / "plugins/agent-token-manager/resources/co0_known_symbol_fixture.py"
    text_relative = text_fixture.relative_to(workspace)
    symbol_relative = symbol_fixture.relative_to(workspace)
    common_canary = fixture_canary(text_fixture, "SECRET_TOKEN: ")
    symbol_canary = fixture_canary(symbol_fixture, 'secret_token = "')
    smart_read = "plugins/agent-token-manager/scripts/smart_read.py"
    return {
        "cat": {
            "command": f"cat -- {text_relative}",
            "canary": common_canary,
            "question": "Return the first non-empty line from the tool result.",
            "expected": "CO0 interface feasibility fixture.",
            "supported": True,
        },
        "sed": {
            "command": f"sed -n '1,23p' {text_relative}",
            "canary": common_canary,
            "question": "Return the first non-empty line from the tool result.",
            "expected": "CO0 interface feasibility fixture.",
            "supported": True,
        },
        "rg": {
            "command": f"rg ':' {text_relative}",
            "canary": common_canary,
            "question": "Return only the label before the colon on the first returned match.",
            "expected": "FILLER-01",
            "supported": True,
        },
        "known_symbol": {
            "command": (
                f"python3 {smart_read} {symbol_relative} "
                "--symbol co0_known_symbol_fixture --budget 2000"
            ),
            "canary": symbol_canary,
            "question": "Return only the top-level schema_version number from the tool result.",
            "expected": "1",
            "supported": True,
        },
        "passthrough": {
            "command": f"cat -- {text_relative} | sed -n '1,23p'",
            "canary": common_canary,
            "question": "Return only the exact value on the SECRET_TOKEN line.",
            "expected": common_canary,
            "supported": False,
        },
        "code_mode": {
            "command": f"cat -- {text_relative}",
            "canary": common_canary,
            "question": (
                "Use the code-mode JavaScript exec tool, and inside it call exec_command exactly once with the "
                "specified shell command. Do not call the shell tool directly. If the SECRET_TOKEN value is visible "
                "in the nested result return it; otherwise return NOT_VISIBLE."
            ),
            "expected": "NOT_VISIBLE",
            "supported": True,
            "code_mode": True,
        },
        "fail_open": {
            "command": f"cat -- {text_relative}",
            "canary": common_canary,
            "question": "Return only the exact value on the SECRET_TOKEN line.",
            "expected": common_canary,
            "supported": False,
            "inject_failure": "error",
        },
    }


def final_message(events: list[dict[str, Any]]) -> str:
    messages = [
        event.get("item", {}).get("text", "")
        for event in events
        if isinstance(event.get("item"), dict) and event.get("item", {}).get("type") == "agent_message"
    ]
    return messages[-1].strip() if messages else ""


def final_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    for event in reversed(events):
        if event.get("type") != "turn.completed" or not isinstance(event.get("usage"), dict):
            continue
        usage = {
            key: int(value)
            for key, value in event["usage"].items()
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        }
        usage["total_tokens"] = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        return usage
    return {"total_tokens": 0}


def code_mode_used(events: list[dict[str, Any]]) -> bool:
    for event in events:
        if event.get("type") != "response_item":
            continue
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("type") == "custom_tool_call" and payload.get("name") == "exec":
            return True
    return False


def build_prompt(case: dict[str, Any]) -> str:
    command = case["command"]
    if case.get("code_mode"):
        return (
            f"{case['question']} The exact nested shell command is: {command}. "
            "Do not inspect the fixture by any other method. Your final answer must contain only the requested value."
        )
    return (
        f"Begin by running exactly this shell command: {command}. {case['question']} "
        "If the returned result is insufficient, you may make additional read/search calls, but do not use web tools "
        "or edit files. Your final answer must contain only the requested value."
    )


def run_case(
    codex: Path,
    workspace: Path,
    name: str,
    case: dict[str, Any],
    arm: str,
    output_dir: Path,
    timeout: int,
) -> dict[str, Any]:
    run_dir = output_dir / name / arm
    run_dir.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.update(
        {
            "AGENT_TOKEN_MANAGER_DATA": str(run_dir),
            "AGENT_TOKEN_MANAGER_CO0_MODE": "enforce" if arm == "co" else "observe",
            "AGENT_TOKEN_MANAGER_CO0_MIN_CHARS": "128",
            "AGENT_TOKEN_MANAGER_CO0_VISIBLE_CHARS": "256",
            "AGENT_TOKEN_MANAGER_CO0_CANARY": str(case["canary"]),
            "AGENT_TOKEN_MANAGER_CO0_RECORD_TRANSCRIPT_PATH": "1",
        }
    )
    if case.get("inject_failure"):
        environment["AGENT_TOKEN_MANAGER_CO0_TEST_MODE"] = "1"
        environment["AGENT_TOKEN_MANAGER_CO0_INJECT_FAILURE"] = str(case["inject_failure"])
    command = [
        str(codex),
        "exec",
        "--json",
        "--dangerously-bypass-hook-trust",
        "--sandbox",
        "read-only",
        "--cd",
        str(workspace),
        build_prompt(case),
    ]
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
            timeout=timeout,
        )
        timed_out = False
    except subprocess.TimeoutExpired as error:
        completed = subprocess.CompletedProcess(
            command,
            124,
            stdout=error.stdout or "",
            stderr=error.stderr or "",
        )
        timed_out = True
    stdout = completed.stdout if isinstance(completed.stdout, str) else completed.stdout.decode("utf-8", "replace")
    stderr = completed.stderr if isinstance(completed.stderr, str) else completed.stderr.decode("utf-8", "replace")
    (run_dir / "codex.jsonl").write_text(stdout, encoding="utf-8")
    (run_dir / "codex.stderr.txt").write_text(stderr, encoding="utf-8")
    exec_events = load_jsonl(run_dir / "codex.jsonl")
    optimizer_records = load_jsonl(run_dir / "context-optimizer.jsonl")
    last_record = optimizer_records[-1] if optimizer_records else {}
    transcript_value = last_record.get("transcript_path")
    transcript_path = Path(transcript_value) if isinstance(transcript_value, str) else None
    transcript_events = load_jsonl(transcript_path) if transcript_path else []
    outputs = model_tool_outputs(transcript_events)
    visible_text = "\n".join(outputs)
    read_calls = [record for record in optimizer_records if record.get("command_kind")]
    result = {
        "schema_version": 1,
        "scenario": name,
        "arm": arm,
        "status": "completed" if completed.returncode == 0 and not timed_out else "failed",
        "codex_exit_code": completed.returncode,
        "timed_out": timed_out,
        "final_text": final_message(exec_events),
        "expected": case["expected"],
        "correct": final_message(exec_events) == case["expected"],
        "usage": final_usage(exec_events),
        "model_visible_tool_output_chars": len(visible_text),
        "model_visible_tool_output_tokens": (len(visible_text) + 3) // 4,
        "model_visible_tool_output_sha256": sha256_text(visible_text),
        "model_tool_output_count": len(outputs),
        "hook_call_count": len(optimizer_records),
        "read_intent_call_count": len(read_calls),
        "same_intent_retries": max(0, len(read_calls) - 1),
        "compensation_tool_calls": max(0, len(outputs) - 1),
        "optimizer_statuses": [record.get("status") for record in optimizer_records],
        "replacement_visible": "Smart Read CO-0 optimized result" in visible_text,
        "canary_visible": str(case["canary"]) in visible_text,
        "code_mode_used": code_mode_used(transcript_events),
        "transcript_available": bool(transcript_events),
        "artifacts": {
            "codex_jsonl": str(run_dir / "codex.jsonl"),
            "codex_stderr": str(run_dir / "codex.stderr.txt"),
            "optimizer_log": str(run_dir / "context-optimizer.jsonl"),
            "transcript": str(transcript_path) if transcript_path else None,
        },
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def load_result(output_dir: Path, name: str, arm: str) -> dict[str, Any] | None:
    path = output_dir / name / arm / "result.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def interface_summary(results: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    supported_checks: dict[str, bool] = {}
    for name in (*SUPPORTED_NAMES, "code_mode"):
        result = results.get((name, "co"), {})
        supported_checks[name] = bool(
            result.get("status") == "completed"
            and result.get("transcript_available")
            and result.get("replacement_visible")
            and not result.get("canary_visible", True)
            and result.get("correct")
            and (name != "code_mode" or result.get("code_mode_used"))
        )
    native_pass = results.get(("passthrough", "native"), {})
    co_pass = results.get(("passthrough", "co"), {})
    passthrough_equal = bool(
        native_pass.get("correct")
        and co_pass.get("correct")
        and native_pass.get("canary_visible")
        and co_pass.get("canary_visible")
        and not co_pass.get("replacement_visible")
        and native_pass.get("model_visible_tool_output_sha256") == co_pass.get("model_visible_tool_output_sha256")
    )
    checks = {**supported_checks, "passthrough": passthrough_equal}
    fail_open = results.get(("fail_open", "co"), {})
    checks["fail_open"] = bool(
        fail_open.get("correct")
        and fail_open.get("canary_visible")
        and not fail_open.get("replacement_visible")
        and "fallback_optimizer_error" in fail_open.get("optimizer_statuses", [])
    )
    return {"status": "passed" if all(checks.values()) else "failed", "checks": checks}


def economic_summary(results: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for name in SUPPORTED_NAMES:
        native = results.get((name, "native"), {})
        co = results.get((name, "co"), {})
        native_visible = int(native.get("model_visible_tool_output_tokens", 0))
        co_visible = int(co.get("model_visible_tool_output_tokens", 0))
        native_total = int(native.get("usage", {}).get("total_tokens", 0))
        co_total = int(co.get("usage", {}).get("total_tokens", 0))
        pairs.append(
            {
                "scenario": name,
                "native_correct": bool(native.get("correct")),
                "co_correct": bool(co.get("correct")),
                "native_visible_tokens": native_visible,
                "co_visible_tokens_after_retries": co_visible,
                "net_visible_context_saving": native_visible - co_visible,
                "co_same_intent_retries": int(co.get("same_intent_retries", 0)),
                "co_compensation_tool_calls": int(co.get("compensation_tool_calls", 0)),
                "native_total_tokens": native_total,
                "co_total_tokens": co_total,
                "co_native_total_ratio": round(co_total / native_total, 4) if native_total else None,
            }
        )
    savings = [pair["net_visible_context_saving"] for pair in pairs]
    retries = [pair["co_same_intent_retries"] for pair in pairs]
    ratios = [pair["co_native_total_ratio"] for pair in pairs if pair["co_native_total_ratio"] is not None]
    lower_sessions = {pair["scenario"] for pair in pairs if pair["co_total_tokens"] < pair["native_total_tokens"]}
    checks = {
        "correctness_not_lower": all(pair["native_correct"] and pair["co_correct"] for pair in pairs),
        "aggregate_net_visible_saving_positive": sum(savings) > 0,
        "median_net_visible_saving_positive": statistics.median(savings) > 0,
        "median_same_intent_retries_at_most_one": statistics.median(retries) <= 1,
        "no_retry_loop": max(retries, default=0) <= 2,
        "rg_and_one_code_read_total_lower": "rg" in lower_sessions and bool(lower_sessions & {"cat", "sed", "known_symbol"}),
        "median_total_ratio_at_most_one": bool(ratios) and statistics.median(ratios) <= 1.0,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "pairs": pairs,
        "aggregate_net_visible_context_saving": sum(savings),
        "median_net_visible_context_saving": statistics.median(savings),
        "median_same_intent_retries": statistics.median(retries),
        "median_co_native_total_ratio": statistics.median(ratios) if ratios else None,
    }


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = scenarios(workspace)
    results: dict[tuple[str, str], dict[str, Any]] = {}

    if args.phase in {"interface", "all"}:
        for name in (*SUPPORTED_NAMES, "code_mode"):
            results[(name, "co")] = run_case(
                args.codex.resolve(), workspace, name, cases[name], "co", output_dir, args.timeout
            )
        for arm in ("native", "co"):
            results[("passthrough", arm)] = run_case(
                args.codex.resolve(), workspace, "passthrough", cases["passthrough"], arm, output_dir, args.timeout
            )
        results[("fail_open", "co")] = run_case(
            args.codex.resolve(), workspace, "fail_open", cases["fail_open"], "co", output_dir, args.timeout
        )
    else:
        for name in (*SUPPORTED_NAMES, "code_mode", "passthrough", "fail_open"):
            for arm in ("co", "native"):
                existing = load_result(output_dir, name, arm)
                if existing is not None:
                    results[(name, arm)] = existing

    if args.phase == "fail-open":
        results[("fail_open", "co")] = run_case(
            args.codex.resolve(), workspace, "fail_open", cases["fail_open"], "co", output_dir, args.timeout
        )

    interface = interface_summary(results)
    if args.phase == "interface" or (args.stop_on_interface_failure and interface["status"] != "passed"):
        summary = {"schema_version": 1, "interface": interface, "economic": {"status": "not_run"}}
        (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return summary

    if args.phase in {"economic", "all"}:
        for name in SUPPORTED_NAMES:
            if (name, "co") not in results:
                existing = load_result(output_dir, name, "co")
                if existing is None:
                    raise RuntimeError(f"missing interface CO result for {name}")
                results[(name, "co")] = existing
            results[(name, "native")] = run_case(
                args.codex.resolve(), workspace, name, cases[name], "native", output_dir, args.timeout
            )
    economic = economic_summary(results)
    summary = {"schema_version": 1, "interface": interface, "economic": economic}
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("interface", "economic", "fail-open", "all"), default="interface")
    parser.add_argument("--codex", type=Path, default=Path("/Applications/ChatGPT.app/Contents/Resources/codex"))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--stop-on-interface-failure", action="store_true", default=False)
    return parser


def main() -> int:
    summary = run_matrix(build_parser().parse_args())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    current = summary["interface"] if summary["economic"]["status"] == "not_run" else summary["economic"]
    return 0 if current["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
