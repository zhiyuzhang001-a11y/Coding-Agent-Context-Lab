#!/usr/bin/env python3
"""Run the command-independent CO-1.4b host replaceability canary probe."""

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
from run_co1_1_pilot import assistant_cycles, cumulative_usage_series
from run_co1_gate2 import final_message, final_usage, git_output, new_transcript, sha256_text, transcript_calls
from run_co1_4_host_probe import cli_calls


ARMS = ("observe", "canary")


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    cases = value.get("cases") if isinstance(value, dict) else None
    if value.get("schema_version") != 1 or not isinstance(cases, list) or len(cases) != 4:
        raise ValueError("CO-1.4b manifest must contain four schema-v1 cases")
    if sum(case.get("order") == ["observe", "canary"] for case in cases) != 2:
        raise ValueError("CO-1.4b must contain two observe-canary orders")
    if sum(case.get("order") == ["canary", "observe"] for case in cases) != 2:
        raise ValueError("CO-1.4b must contain two canary-observe orders")
    return value


def prepare_homes(lab: Path, artifacts: Path, codex: Path, source_home: Path) -> dict[str, Path]:
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
            "[marketplaces.co1-hook-lab]\n"
            'source_type = "local"\n'
            f"source = {json.dumps(str(lab))}\n",
            encoding="utf-8",
        )
        config.chmod(0o600)
        environment = dict(os.environ, CODEX_HOME=str(home))
        installed = subprocess.run(
            [str(codex), "plugin", "add", "hook-only-cost-probe@co1-hook-lab"],
            env=environment, text=True, capture_output=True, timeout=90,
        )
        if installed.returncode != 0:
            raise RuntimeError(installed.stderr.strip() or installed.stdout.strip())
        homes[arm] = home
    return homes


def run_one(
    repository: Path, commit: str, case: dict[str, Any], arm: str, canary: str,
    codex: Path, home: Path, artifacts: Path, model: str, reasoning: str, timeout: int,
) -> dict[str, Any]:
    run_id = f"{case['id']}-{arm}"
    run_dir = artifacts / run_id
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix=f"co14b-{run_id}-"))
    worktree = parent / "worktree"
    added = False
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), commit], cwd=repository,
            check=True, text=True, capture_output=True, timeout=60,
        )
        added = True
        prompt = (
            f"Run exactly this shell command once: {case['command']}. Do not run any other command or tool. "
            f"Use its complete result to answer: {case['question']}"
        )
        before = set(home.rglob("*.jsonl"))
        environment = dict(os.environ)
        environment.update({
            "CODEX_HOME": str(home), "CO11_DATA": str(run_dir),
            "CO11_HOOK_MODE": "observe" if arm == "observe" else "host-canary",
        })
        command = [
            str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust",
            "--sandbox", "read-only", "--model", model, "--cd", str(worktree),
            "--config", f'model_reasoning_effort="{reasoning}"',
            "--config", "features.multi_agent=false", prompt,
        ]
        started = time.perf_counter()
        completed = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=timeout)
        elapsed = round(time.perf_counter() - started, 3)
        (run_dir / "codex.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        exec_events = load_jsonl(run_dir / "codex.jsonl")
        records = load_jsonl(run_dir / "hook-probe.jsonl")
        transcript = next(
            (Path(record["transcript_path"]) for record in reversed(records) if isinstance(record.get("transcript_path"), str)),
            None,
        ) or new_transcript(home, before)
        transcript_events = load_jsonl(transcript) if transcript else []
        calls = transcript_calls(transcript_events)
        visible = "\n".join(str(call.get("output", "")) for call in calls)
        raw_outputs = [str(row.get("output", "")) for row in cli_calls(run_dir / "codex.jsonl")]
        usage_series = cumulative_usage_series(transcript_events)
        final = final_message(exec_events)
        result = {
            "schema_version": 1, "run_id": run_id, "case_id": case["id"], "arm": arm,
            "commit": commit, "status": "completed" if completed.returncode == 0 else "failed",
            "correct": completed.returncode == 0 and final == case["expected"],
            "final_text": final, "expected": case["expected"], "usage": final_usage(exec_events),
            "model_cycles": len(usage_series), "assistant_message_count": assistant_cycles(transcript_events),
            "tool_call_count": len(calls), "hook_record_count": len(records),
            "canary_visible": canary in visible,
            "raw_result_preserved": bool(raw_outputs) and all(not raw or raw in visible for raw in raw_outputs),
            "success_semantics_preserved": "Script failed" not in visible and "Script error:" not in visible,
            "hook_decisions": [record.get("decision") for record in records],
            "visible_chars": len(visible), "visible_sha256": sha256_text(visible),
            "elapsed_seconds": elapsed, "transcript_available": bool(transcript_events),
        }
    except Exception as error:
        result = {"schema_version": 1, "run_id": run_id, "case_id": case.get("id"), "arm": arm,
                  "commit": commit, "status": "failed", "correct": False,
                  "error": f"{type(error).__name__}: {error}"}
    finally:
        if added:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repository,
                           text=True, capture_output=True, timeout=60)
        shutil.rmtree(parent, ignore_errors=True)
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def summarize(cases: list[dict[str, Any]], results: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    pairs = []
    for case in cases:
        observe = results[(case["id"], "observe")]
        canary = results[(case["id"], "canary")]
        pairs.append({
            "case_id": case["id"], "observe_correct": bool(observe.get("correct")),
            "canary_correct": bool(canary.get("correct")), "canary_visible": bool(canary.get("canary_visible")),
            "raw_result_preserved": bool(canary.get("raw_result_preserved")),
            "success_semantics_preserved": bool(canary.get("success_semantics_preserved")),
            "observe_canary_absent": not bool(observe.get("canary_visible")),
            "observe_model_cycles": int(observe.get("model_cycles", 0)),
            "canary_model_cycles": int(canary.get("model_cycles", 0)),
            "observe_tool_calls": int(observe.get("tool_call_count", 0)),
            "canary_tool_calls": int(canary.get("tool_call_count", 0)),
            "canary_block_decisions": canary.get("hook_decisions", []).count("block"),
        })
    replaceable = [pair for pair in pairs if pair["canary_visible"] and pair["canary_block_decisions"] == 1]
    coverage = len(replaceable) / len(pairs) if pairs else 0.0
    cycle_deltas = [pair["canary_model_cycles"] - pair["observe_model_cycles"] for pair in pairs]
    checks = {
        "correctness_zero_regression": all(
            not pair["observe_correct"] or pair["canary_correct"] for pair in pairs
        ),
        "replaceability_at_least_0_80": coverage >= 0.80,
        "canary_only_in_treatment": all(pair["canary_visible"] and pair["observe_canary_absent"] for pair in pairs),
        "raw_result_preserved": all(pair["raw_result_preserved"] for pair in pairs),
        "success_semantics_preserved": all(pair["success_semantics_preserved"] for pair in pairs),
        "one_tool_call_each": all(pair["observe_tool_calls"] == pair["canary_tool_calls"] == 1 for pair in pairs),
        "model_cycles_not_increased": max(cycle_deltas, default=1) <= 0,
    }
    return {
        "schema_version": 1, "status": "passed" if all(checks.values()) else "failed",
        "checks": checks, "replaceability_coverage": coverage,
        "median_model_cycle_delta": statistics.median(cycle_deltas) if cycle_deltas else None,
        "pairs": pairs,
    }


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    repository = plugin.parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=plugin / "resources/co1_4_replace_cases.json")
    parser.add_argument("--artifacts", type=Path, default=repository / ".agent-token-manager/co1-4b")
    parser.add_argument("--codex", type=Path, default=Path("/Applications/ChatGPT.app/Contents/Resources/codex"))
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    commit = git_output(repository, "rev-parse", manifest["subject_commit"])
    plugin_commit = git_output(repository, "rev-parse", manifest["plugin_commit"])
    artifacts = args.artifacts.resolve()
    if artifacts.exists() and any(artifacts.iterdir()):
        raise RuntimeError(f"refusing non-empty artifacts directory: {artifacts}")
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    plugin_parent = Path(tempfile.mkdtemp(prefix="co14b-plugin-"))
    plugin_root = plugin_parent / "source"
    plugin_added = False
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(plugin_root), plugin_commit], cwd=repository,
            check=True, text=True, capture_output=True, timeout=60,
        )
        plugin_added = True
        homes = prepare_homes(
            plugin_root / "experiments/co1-hook-only", artifacts, args.codex.resolve(),
            Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve(),
        )
        results: dict[tuple[str, str], dict[str, Any]] = {}
        for case in manifest["cases"]:
            for arm in case["order"]:
                results[(case["id"], arm)] = run_one(
                    repository, commit, case, arm, manifest["canary"], args.codex.resolve(), homes[arm],
                    artifacts, args.model, args.reasoning_effort, args.timeout,
                )
        summary = summarize(manifest["cases"], results)
        summary.update({
            "commit": commit, "plugin_commit": plugin_commit, "plugin_version": manifest["plugin_version"],
            "model": args.model, "reasoning_effort": args.reasoning_effort,
            "manifest_sha256": sha256_text(args.manifest.read_text(encoding="utf-8")),
        })
        (artifacts / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["status"] == "passed" else 1
    finally:
        if plugin_added:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(plugin_root)], cwd=repository,
                text=True, capture_output=True, timeout=60,
            )
        shutil.rmtree(plugin_parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
