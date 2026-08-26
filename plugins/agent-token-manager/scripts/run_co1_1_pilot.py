#!/usr/bin/env python3
"""Run the CO-1.1 Native/observe/equivalent-rewrite cost-isolation pilot."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from run_co0_gate import load_jsonl
from run_co1_gate2 import (
    case_command,
    final_message,
    final_usage,
    git_output,
    new_transcript,
    sha256_text,
    transcript_calls,
)


ARMS = ("native", "observe", "rewrite")


def prepare_homes(repository: Path, lab: Path, artifacts: Path, codex: Path, source_home: Path) -> dict[str, Path]:
    auth = source_home / "auth.json"
    if not auth.is_file():
        raise RuntimeError(f"Codex auth missing: {auth}")
    homes: dict[str, Path] = {}
    for arm in ARMS:
        home = artifacts / f"codex-home-{arm}"
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        auth_link = home / "auth.json"
        if not auth_link.exists():
            auth_link.symlink_to(auth)
        config = home / "config.toml"
        config.write_text(
            (
                "[marketplaces.co1-hook-lab]\n"
                'source_type = "local"\n'
                f"source = {json.dumps(str(lab))}\n"
            )
            if arm != "native"
            else "",
            encoding="utf-8",
        )
        config.chmod(0o600)
        if arm != "native":
            environment = dict(os.environ)
            environment["CODEX_HOME"] = str(home)
            installed = subprocess.run(
                [str(codex), "plugin", "add", "hook-only-cost-probe@co1-hook-lab"],
                env=environment, text=True, capture_output=True, timeout=90
            )
            if installed.returncode != 0:
                raise RuntimeError(installed.stderr.strip() or installed.stdout.strip())
        homes[arm] = home
    return homes


def cumulative_usage_series(events: list[dict[str, Any]]) -> list[dict[str, int]]:
    result: list[dict[str, int]] = []
    for event in events:
        payload = event.get("payload")
        if event.get("type") != "event_msg" or not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        info = payload.get("info")
        usage = info.get("total_token_usage") if isinstance(info, dict) else None
        if not isinstance(usage, dict):
            continue
        result.append({key: int(value) for key, value in usage.items() if isinstance(value, int)})
    return result


def assistant_cycles(events: list[dict[str, Any]]) -> int:
    return sum(
        event.get("type") == "response_item"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("type") == "message"
        and event["payload"].get("role") == "assistant"
        for event in events
    )


def run_one(
    repository: Path, commit: str, fixture: Path, case_id: str, expected: str,
    canary: str, arm: str, repetition: int, codex: Path, home: Path,
    artifacts: Path, model: str, reasoning: str, timeout: int,
) -> dict[str, Any]:
    run_id = f"r{repetition}-{arm}"
    run_dir = artifacts / run_id
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix=f"co11-{run_id}-"))
    worktree = parent / "worktree"
    added = False
    try:
        subprocess.run(["git", "worktree", "add", "--detach", str(worktree), commit], cwd=repository,
                       check=True, text=True, capture_output=True, timeout=60)
        added = True
        command = case_command(worktree, fixture, case_id)
        prompt = (
            f"Run exactly this shell command once: {command}. Do not run any other command or tool. "
            "Inspect the returned result and reply only with the exact value returned by "
            "normalize_name('  Ada Lovelace  ')."
        )
        before = set(home.rglob("*.jsonl"))
        environment = dict(os.environ)
        environment.update({"CODEX_HOME": str(home), "CO11_HOOK_MODE": arm, "CO11_DATA": str(run_dir)})
        cmd = [str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust",
               "--sandbox", "read-only", "--model", model, "--cd", str(worktree),
               "--config", f'model_reasoning_effort="{reasoning}"',
               "--config", "features.multi_agent=false", prompt]
        started = time.perf_counter()
        completed = subprocess.run(cmd, env=environment, text=True, capture_output=True, timeout=timeout)
        elapsed = round(time.perf_counter() - started, 3)
        (run_dir / "codex.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        exec_events = load_jsonl(run_dir / "codex.jsonl")
        records = load_jsonl(run_dir / "hook-probe.jsonl")
        transcript: Path | None = None
        for record in reversed(records):
            if isinstance(record.get("transcript_path"), str):
                transcript = Path(record["transcript_path"])
                break
        if transcript is None:
            transcript = new_transcript(home, before)
        events = load_jsonl(transcript) if transcript else []
        calls = transcript_calls(events)
        visible = "\n".join(str(call.get("output", "")) for call in calls)
        usage_series = cumulative_usage_series(events)
        result = {
            "arm": arm, "repetition": repetition, "commit": commit,
            "status": "completed" if completed.returncode == 0 else "failed",
            "correct": final_message(exec_events) == expected,
            "final_text": final_message(exec_events), "usage": final_usage(exec_events),
            "model_cycles": len(usage_series), "assistant_message_count": assistant_cycles(events),
            "tool_call_count": len(calls),
            "canary_visible": canary in visible, "visible_output_chars": len(visible),
            "visible_output_sha256": sha256_text(visible),
            "hook_records": len(records), "hook_decisions": [record.get("decision") for record in records],
            "cumulative_usage_series": usage_series, "elapsed_seconds": elapsed,
            "transcript_available": bool(events),
        }
    except Exception as error:
        result = {"arm": arm, "repetition": repetition, "commit": commit, "status": "failed",
                  "correct": False, "error": f"{type(error).__name__}: {error}"}
    finally:
        if added:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repository,
                           text=True, capture_output=True, timeout=60)
        shutil.rmtree(parent, ignore_errors=True)
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {arm: [item for item in results if item["arm"] == arm] for arm in ARMS}
    medians = {
        arm: statistics.median(int(item.get("usage", {}).get("total_tokens", 0)) for item in items)
        for arm, items in groups.items()
    }
    pairs = []
    for repetition in sorted({int(item["repetition"]) for item in results}):
        row = {item["arm"]: item for item in results if int(item["repetition"]) == repetition}
        pairs.append({
            "repetition": repetition,
            "native_total": row["native"]["usage"]["total_tokens"],
            "observe_total": row["observe"]["usage"]["total_tokens"],
            "rewrite_total": row["rewrite"]["usage"]["total_tokens"],
            "observe_minus_native": row["observe"]["usage"]["total_tokens"] - row["native"]["usage"]["total_tokens"],
            "rewrite_minus_observe": row["rewrite"]["usage"]["total_tokens"] - row["observe"]["usage"]["total_tokens"],
        })
    checks = {
        "all_completed_correct": all(item.get("status") == "completed" and item.get("correct") for item in results),
        "one_tool_call_each": all(item.get("tool_call_count") == 1 for item in results),
        "two_model_cycles_each": all(item.get("model_cycles") == 2 for item in results),
        "canary_visible_each": all(item.get("canary_visible") for item in results),
        "observe_has_no_decision": all(item.get("hook_decisions") == ["none"] for item in groups["observe"]),
        "rewrite_has_block_decision": all(item.get("hook_decisions") == ["block"] for item in groups["rewrite"]),
    }
    observe_deltas = [pair["observe_minus_native"] for pair in pairs]
    rewrite_deltas = [pair["rewrite_minus_observe"] for pair in pairs]
    return {
        "status": "passed" if all(checks.values()) else "failed", "checks": checks,
        "medians": medians, "pairs": pairs,
        "median_observe_minus_native": statistics.median(observe_deltas),
        "median_rewrite_minus_observe": statistics.median(rewrite_deltas),
        "observe_direction_consistent": len(set(delta > 0 for delta in observe_deltas)) == 1,
        "rewrite_direction_consistent": len(set(delta > 0 for delta in rewrite_deltas)) == 1,
        "runs": results,
    }


def main() -> int:
    repository = Path(git_output(Path(__file__).resolve().parent, "rev-parse", "--show-toplevel"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--artifacts", type=Path, default=repository / ".agent-token-manager" / "co1-1-pilot")
    parser.add_argument("--codex", type=Path, default=Path("/Applications/ChatGPT.app/Contents/Resources/codex"))
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    commit = git_output(repository, "rev-parse", args.commit)
    artifacts = args.artifacts.resolve(); artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    lab = repository / "experiments" / "co1-hook-only"
    homes = prepare_homes(repository, lab, artifacts, args.codex.resolve(), Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))))
    fixture = Path("plugins/agent-token-manager/resources/co1_gate2_fixture.py")
    schedule = [(1, "native"), (1, "observe"), (1, "rewrite"), (2, "observe"), (2, "rewrite"), (2, "native")]
    results = [run_one(repository, commit, fixture, "function_answer", "ada-lovelace", "CO1_CANARY_FUNCTION_91A7",
                       arm, repetition, args.codex.resolve(), homes[arm], artifacts, args.model,
                       args.reasoning_effort, args.timeout) for repetition, arm in schedule]
    summary = summarize(results)
    summary.update({"commit": commit, "model": args.model, "reasoning_effort": args.reasoning_effort})
    (artifacts / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
