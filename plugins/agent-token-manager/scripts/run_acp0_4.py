#!/usr/bin/env python3
"""Run ACP-0.4 deterministic host probes and natural collector OFF/ON pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from run_co0_gate import load_jsonl
from run_co1_1_pilot import cumulative_usage_series
from run_co1_gate2 import final_message, final_usage, git_output, new_transcript, normalize_command, transcript_calls


ARMS = ("off", "on")
REQUIRED_CATEGORIES = {
    "single_file_location", "multi_file_search", "bash_or_tests", "debugging",
    "cross_file_reasoning", "large_output_read", "tool_failure",
}
RUNNER_SCHEMA_ID = "acp0-4-no-interference-v1"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8", errors="replace"))


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if manifest.get("schema_version") != 1 or not isinstance(cases, list) or not 10 <= len(cases) <= 20:
        raise ValueError("ACP-0.4 requires 10-20 schema-v1 natural cases")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or len(set(ids)) != len(ids) or not all(isinstance(item, str) and item for item in ids):
        raise ValueError("ACP-0.4 case ids must be unique non-empty strings")
    required = {"id", "category", "question", "expected", "order"}
    if any(not required.issubset(case) for case in cases):
        raise ValueError("ACP-0.4 case is missing required fields")
    categories = {case["category"] for case in cases}
    if not REQUIRED_CATEGORIES.issubset(categories):
        raise ValueError("ACP-0.4 category coverage is incomplete")
    orders = Counter(tuple(case["order"]) for case in cases)
    if abs(orders[("off", "on")] - orders[("on", "off")]) > 1 or sum(orders.values()) != len(cases):
        raise ValueError("ACP-0.4 requires balanced OFF/ON and ON/OFF order")
    ceiling = manifest.get("token_ratio_ceiling")
    if not isinstance(ceiling, (int, float)) or isinstance(ceiling, bool) or ceiling < 1:
        raise ValueError("ACP-0.4 token ratio ceiling must be at least 1")
    return manifest


def host_probe_event() -> dict[str, Any]:
    return {
        "hook_event_name": "PostToolUse", "session_id": "acp04-controlled-session",
        "tool_use_id": "acp04-controlled-call", "cwd": "/tmp/acp04-controlled-repository",
        "tool_name": "Bash", "tool_input": {"command": "printf controlled"},
        "tool_response": {"output": "controlled-result\n", "exit_code": 0},
    }


def invoke_collector(collector: Path, payload: bytes, data_dir: Path) -> dict[str, Any]:
    environment = dict(os.environ, AGENT_TOKEN_MANAGER_DATA=str(data_dir))
    completed = subprocess.run(
        [str(collector)], input=payload, capture_output=True, env=environment, timeout=10,
    )
    return {
        "returncode": completed.returncode,
        "stdout_sha256": sha256_bytes(completed.stdout), "stdout_bytes": len(completed.stdout),
        "stderr_sha256": sha256_bytes(completed.stderr), "stderr_bytes": len(completed.stderr),
    }


def run_host_probes(collector: Path, workspace: Path) -> dict[str, Any]:
    event = host_probe_event()
    encoded = (json.dumps(event, separators=(",", ":")) + "\n").encode()
    cases = []
    controlled_dir = workspace / "controlled"
    controlled = invoke_collector(collector, encoded, controlled_dir)
    records = load_jsonl(controlled_dir / "events.jsonl")
    expected_hash = sha256_text("controlled-result\n")
    controlled.update({
        "case": "controlled_success", "record_count": len(records),
        "recorded_result_sha256": records[0].get("output_sha256") if len(records) == 1 else None,
        "host_visible_result_sha256_off": expected_hash, "host_visible_result_sha256_on": expected_hash,
    })
    cases.append(controlled)

    unknown = dict(event, tool_name="UnknownFutureTool", tool_use_id="acp04-unknown-call")
    cases.append({"case": "unknown_tool", **invoke_collector(
        collector, (json.dumps(unknown, separators=(",", ":")) + "\n").encode(), workspace / "unknown"
    )})
    missing = {key: value for key, value in event.items() if key not in {"session_id", "tool_use_id"}}
    cases.append({"case": "missing_metadata", **invoke_collector(
        collector, (json.dumps(missing, separators=(",", ":")) + "\n").encode(), workspace / "missing"
    )})
    cases.append({"case": "malformed_json", **invoke_collector(collector, b"{malformed\n", workspace / "malformed")})
    blocker = workspace / "not-a-directory"
    blocker.write_text("block", encoding="utf-8")
    cases.append({"case": "audit_unwritable", **invoke_collector(collector, encoded, blocker)})
    checks = {
        "collector_returns_success": all(case["returncode"] == 0 for case in cases),
        "collector_stdout_empty": all(case["stdout_bytes"] == 0 for case in cases),
        "collector_stderr_empty": all(case["stderr_bytes"] == 0 for case in cases),
        "controlled_result_hash_preserved": (
            controlled["host_visible_result_sha256_off"] == controlled["host_visible_result_sha256_on"]
            == controlled["recorded_result_sha256"]
        ),
        "controlled_event_recorded_once": controlled["record_count"] == 1,
    }
    return {"status": "passed" if all(checks.values()) else "failed", "checks": checks, "cases": cases}


def prepare_marketplace(
    artifacts: Path, collector: Path, collector_hash: str, hooks_manifest: Path, hooks_hash: str
) -> Path:
    lab = artifacts / "collector-marketplace"
    plugin = lab / "plugins" / "acp-observe-only"
    scripts = plugin / "scripts"
    hooks = plugin / "hooks"
    marketplace_dir = lab / ".agents" / "plugins"
    for directory in (scripts, hooks, marketplace_dir):
        directory.mkdir(parents=True, exist_ok=True)
    copied = scripts / "acp_collector.py"
    shutil.copy2(collector, copied)
    copied.chmod(0o755)
    if sha256_bytes(copied.read_bytes()) != collector_hash:
        raise RuntimeError("collector copy hash drift")
    (plugin / ".codex-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text(json.dumps({
        "name": "acp-observe-only", "version": "0.1.0", "description": "ACP-0.4 frozen collector probe.",
        "author": {"name": "Local developer"},
        "interface": {
            "displayName": "ACP Observe Only", "shortDescription": "Measure without changing tool results.",
            "longDescription": "Minimal ACP-0.4 observe-only collector with no skills, apps, MCP, prompts, or rewrite hooks.",
            "developerName": "Local developer", "category": "Productivity", "capabilities": ["Hooks"], "defaultPrompt": []
        }
    }, indent=2) + "\n", encoding="utf-8")
    copied_hooks = hooks / "hooks.json"
    shutil.copy2(hooks_manifest, copied_hooks)
    if sha256_bytes(copied_hooks.read_bytes()) != hooks_hash:
        raise RuntimeError("hooks manifest copy hash drift")
    (marketplace_dir / "marketplace.json").write_text(json.dumps({
        "name": "acp0-4-lab", "interface": {"displayName": "ACP-0.4 Lab"},
        "plugins": [{
            "name": "acp-observe-only", "source": {"source": "local", "path": "./plugins/acp-observe-only"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"
        }]
    }, indent=2) + "\n", encoding="utf-8")
    return lab


def prepare_homes(lab: Path, artifacts: Path, codex: Path, source_home: Path) -> dict[str, Path]:
    auth = source_home / "auth.json"
    if not auth.is_file():
        raise RuntimeError(f"Codex auth missing: {auth}")
    homes = {}
    for arm in ARMS:
        home = artifacts / f"codex-home-{arm}"
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        (home / "auth.json").symlink_to(auth)
        config = "" if arm == "off" else (
            "[marketplaces.acp0-4-lab]\n" f"source_type = \"local\"\nsource = {json.dumps(str(lab))}\n"
        )
        (home / "config.toml").write_text(config, encoding="utf-8")
        if arm == "on":
            completed = subprocess.run(
                [str(codex), "plugin", "add", "acp-observe-only@acp0-4-lab"],
                env=dict(os.environ, CODEX_HOME=str(home)), text=True, capture_output=True, timeout=90,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        homes[arm] = home
    return homes


def build_prompt(case: dict[str, Any]) -> str:
    return (
        "Work only from the local repository. Do not use web tools, plugins, skills, Task Navigator, "
        "Smart Read, context_router, navigation_map, or subagents. Do not modify repository files. "
        + case["question"]
    )


def run_case(
    repository: Path, subject_commit: str, case: dict[str, Any], arm: str, codex: Path,
    home: Path, artifacts: Path, model: str, reasoning: str, timeout: int,
) -> dict[str, Any]:
    run_id = f"{case['id']}-{arm}"
    run_dir = artifacts / run_id
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix=f"acp04-{run_id}-"))
    worktree = parent / "worktree"
    added = False
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), subject_commit], cwd=repository,
            check=True, text=True, capture_output=True, timeout=60,
        )
        added = True
        before = set(home.rglob("*.jsonl"))
        environment = dict(os.environ, CODEX_HOME=str(home), AGENT_TOKEN_MANAGER_DATA=str(parent / "collector-data"))
        environment["PWD"] = str(worktree)
        environment["_"] = str(codex)
        command = [
            str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust",
            "--sandbox", "read-only", "--model", model, "--cd", str(worktree),
            "--config", f'model_reasoning_effort="{reasoning}"', "--config", "features.multi_agent=false",
            build_prompt(case),
        ]
        started = time.perf_counter()
        # The host tool worker inherits the process cwd before applying --cd. Keep that cwd on the
        # ASCII-only temporary worktree so repositories whose parent path is non-ASCII do not
        # trigger host path-decoding failures in nested command execution.
        completed = subprocess.run(
            command, cwd=worktree, env=environment, text=True, capture_output=True, timeout=timeout,
        )
        elapsed = round(time.perf_counter() - started, 3)
        (run_dir / "codex.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        exec_events = load_jsonl(run_dir / "codex.jsonl")
        transcript = new_transcript(home, before)
        transcript_events = load_jsonl(transcript) if transcript else []
        calls = transcript_calls(transcript_events)
        events_path = parent / "collector-data" / "events.jsonl"
        collector_events = load_jsonl(events_path) if events_path.is_file() else []
        if events_path.is_file():
            shutil.copy2(events_path, run_dir / "collector-events.jsonl")
        final = final_message(exec_events)
        result = {
            "schema_version": 1, "run_id": run_id, "case_id": case["id"], "category": case["category"],
            "arm": arm, "subject_commit": subject_commit, "model": model, "reasoning_effort": reasoning,
            "status": "completed" if completed.returncode == 0 else "failed",
            "correct": completed.returncode == 0 and final == case["expected"],
            "final_text": final, "expected": case["expected"], "elapsed_seconds": elapsed,
            "usage": final_usage(exec_events), "model_cycles": len(cumulative_usage_series(transcript_events)),
            "tool_call_count": len(calls),
            "tool_request_hashes": [sha256_text(normalize_command(call["command"])) for call in calls],
            "tool_result_hashes": [sha256_text(call["output"]) for call in calls],
            "tool_families": [call["tool_name"] for call in calls],
            "collector_event_count": len(collector_events),
            "collector_total_duration_ms": round(sum(
                event.get("duration_ms", 0) for event in collector_events if isinstance(event.get("duration_ms"), (int, float))
            ), 3),
            "collector_invoked_tool": any("acp_collector.py" in call["command"] for call in calls),
            "transcript_available": bool(transcript_events),
        }
    except Exception as error:
        result = {
            "schema_version": 1, "run_id": run_id, "case_id": case.get("id"), "category": case.get("category"),
            "arm": arm, "subject_commit": subject_commit, "status": "failed", "correct": False,
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        if added:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)], cwd=repository,
                text=True, capture_output=True, timeout=60,
            )
        shutil.rmtree(parent, ignore_errors=True)
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def ratio(on: int, off: int) -> float | None:
    return on / off if off > 0 else None


def direction(values: list[int]) -> dict[str, int]:
    return {
        "on_lower": sum(value < 0 for value in values),
        "equal": sum(value == 0 for value in values),
        "on_higher": sum(value > 0 for value in values),
    }


def summarize(
    manifest: dict[str, Any], results: dict[tuple[str, str], dict[str, Any]], host_probes: dict[str, Any]
) -> dict[str, Any]:
    pairs = []
    for case in manifest["cases"]:
        off, on = results[(case["id"], "off")], results[(case["id"], "on")]
        off_tokens = int(off.get("usage", {}).get("total_tokens", 0))
        on_tokens = int(on.get("usage", {}).get("total_tokens", 0))
        pairs.append({
            "case_id": case["id"], "category": case["category"],
            "off_correct": bool(off.get("correct")), "on_correct": bool(on.get("correct")),
            "off_total_tokens": off_tokens, "on_total_tokens": on_tokens,
            "total_token_delta": on_tokens - off_tokens, "total_token_ratio": ratio(on_tokens, off_tokens),
            "off_model_cycles": int(off.get("model_cycles", 0)), "on_model_cycles": int(on.get("model_cycles", 0)),
            "model_cycle_delta": int(on.get("model_cycles", 0)) - int(off.get("model_cycles", 0)),
            "off_tool_calls": int(off.get("tool_call_count", 0)), "on_tool_calls": int(on.get("tool_call_count", 0)),
            "tool_call_delta": int(on.get("tool_call_count", 0)) - int(off.get("tool_call_count", 0)),
            "request_sequence_equal": off.get("tool_request_hashes") == on.get("tool_request_hashes"),
            "result_sequence_equal": off.get("tool_result_hashes") == on.get("tool_result_hashes"),
            "collector_event_count": int(on.get("collector_event_count", 0)),
            "collector_duration_ms": on.get("collector_total_duration_ms"),
        })
    token_ratios = [row["total_token_ratio"] for row in pairs if row["total_token_ratio"] is not None]
    cycle_deltas = [row["model_cycle_delta"] for row in pairs]
    call_deltas = [row["tool_call_delta"] for row in pairs]
    token_deltas = [row["total_token_delta"] for row in pairs]
    off_total = sum(row["off_total_tokens"] for row in pairs)
    on_total = sum(row["on_total_tokens"] for row in pairs)
    median_token_ratio = statistics.median(token_ratios) if token_ratios else None
    pooled_token_ratio = ratio(on_total, off_total)
    half = len(pairs) // 2
    checks = {
        "all_runs_completed_with_usage": all(
            results[(case["id"], arm)].get("status") == "completed"
            and int(results[(case["id"], arm)].get("usage", {}).get("total_tokens", 0)) > 0
            for case in manifest["cases"] for arm in ARMS
        ),
        "host_hard_gates_pass": host_probes["status"] == "passed",
        "correctness_zero_regression": all(row["off_correct"] and row["on_correct"] for row in pairs),
        "collector_observed_every_on_tool_call": all(
            int(results[(case["id"], "on")].get("collector_event_count", 0))
            == int(results[(case["id"], "on")].get("tool_call_count", 0))
            for case in manifest["cases"]
        ),
        "collector_never_invokes_tools": all(not results[(case["id"], "on")].get("collector_invoked_tool", False) for case in manifest["cases"]),
        "model_cycle_no_systematic_increase": statistics.median(cycle_deltas) <= 0 and sum(value > 0 for value in cycle_deltas) <= half,
        "tool_call_no_systematic_increase": statistics.median(call_deltas) <= 0 and sum(value > 0 for value in call_deltas) <= half,
        "median_token_ratio_within_ceiling": median_token_ratio is not None and median_token_ratio <= manifest["token_ratio_ceiling"],
        "pooled_token_ratio_within_ceiling": pooled_token_ratio is not None and pooled_token_ratio <= manifest["token_ratio_ceiling"],
    }
    return {
        "schema_version": 1, "schema_id": RUNNER_SCHEMA_ID,
        "verdict": "pass" if all(checks.values()) else "fail", "checks": checks,
        "thresholds": {
            "token_ratio_ceiling": manifest["token_ratio_ceiling"],
            "positive_cycle_or_call_direction_max": half,
        },
        "aggregate": {
            "pair_count": len(pairs), "correct_pair_count": sum(row["off_correct"] and row["on_correct"] for row in pairs),
            "median_paired_total_ratio": median_token_ratio, "pooled_total_ratio": pooled_token_ratio,
            "median_total_token_delta": statistics.median(token_deltas), "token_delta_directions": direction(token_deltas),
            "median_model_cycle_delta": statistics.median(cycle_deltas), "model_cycle_delta_directions": direction(cycle_deltas),
            "median_tool_call_delta": statistics.median(call_deltas), "tool_call_delta_directions": direction(call_deltas),
            "request_sequence_equal_count": sum(row["request_sequence_equal"] for row in pairs),
            "result_sequence_equal_count": sum(row["result_sequence_equal"] for row in pairs),
            "collector_event_count": sum(row["collector_event_count"] for row in pairs),
            "collector_duration_ms": round(sum(row["collector_duration_ms"] or 0 for row in pairs), 3),
        },
        "host_probes": host_probes,
        "pairs": pairs,
        "interpretation": {
            "sequence_equality_is_observational_not_a_hard_gate": True,
            "natural_pair_differences_are_not_causally_attributed_individually": True,
            "unknown_dimensions_must_not_be_filled": True,
        },
    }


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    repository = Path(git_output(plugin, "rev-parse", "--show-toplevel"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=plugin / "resources" / "acp0_4_cases.json")
    parser.add_argument("--artifacts", type=Path, default=repository / ".agent-token-manager" / "acp0-4")
    parser.add_argument("--codex", type=Path, default=Path("/Applications/ChatGPT.app/Contents/Resources/codex"))
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    subject_commit = git_output(repository, "rev-parse", manifest["subject_commit"])
    artifacts = args.artifacts.resolve()
    if artifacts.exists() and any(artifacts.iterdir()) and not args.preflight_only:
        raise RuntimeError(f"refusing to mix runs in non-empty artifacts directory: {artifacts}")
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    contract = json.loads((plugin / "resources" / "acp0_contract.json").read_text(encoding="utf-8"))
    collector = plugin / contract["acp0_1_collector_audit"]["collector_path"]
    collector_hash = contract["acp0_1_collector_audit"]["collector_sha256"]
    hooks_manifest = plugin / contract["acp0_1_collector_audit"]["hooks_manifest_path"]
    hooks_hash = contract["acp0_1_collector_audit"]["hooks_manifest_sha256"]
    if sha256_bytes(collector.read_bytes()) != collector_hash:
        raise RuntimeError("frozen collector hash does not match ACP contract")
    if sha256_bytes(hooks_manifest.read_bytes()) != hooks_hash:
        raise RuntimeError("frozen hooks manifest does not match ACP contract")
    host_probes = run_host_probes(collector, artifacts / "host-probes")
    preflight = {
        "schema_version": 1, "fixture_id": manifest["fixture_id"], "subject_commit": subject_commit,
        "manifest_sha256": sha256_bytes(args.manifest.read_bytes()), "collector_sha256": collector_hash,
        "hooks_manifest_sha256": hooks_hash,
        "case_count": len(manifest["cases"]), "categories": sorted({case["category"] for case in manifest["cases"]}),
        "balanced_order": Counter(tuple(case["order"]) for case in manifest["cases"]) == Counter({("off", "on"): 6, ("on", "off"): 6}),
        "host_probes": host_probes,
    }
    (artifacts / "preflight.json").write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.preflight_only:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0 if host_probes["status"] == "passed" else 1
    # Keep the executable Hook root ASCII-only. The current host can fail before invoking a hook
    # when a local marketplace command path contains non-ASCII parent components.
    lab_parent = Path(tempfile.mkdtemp(prefix="acp04-marketplace-", dir="/private/tmp"))
    lab = prepare_marketplace(lab_parent, collector, collector_hash, hooks_manifest, hooks_hash)
    homes = prepare_homes(
        lab, artifacts, args.codex.resolve(), Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    )
    results = {}
    for case in manifest["cases"]:
        for arm in case["order"]:
            results[(case["id"], arm)] = run_case(
                repository, subject_commit, case, arm, args.codex.resolve(), homes[arm], artifacts,
                args.model, args.reasoning_effort, args.timeout,
            )
    summary = summarize(manifest, results, host_probes)
    summary.update({
        "fixture_id": manifest["fixture_id"], "subject_commit": subject_commit,
        "harness_commit": git_output(repository, "rev-parse", "HEAD"),
        "manifest_sha256": preflight["manifest_sha256"], "collector_sha256": collector_hash,
        "hooks_manifest_sha256": hooks_hash,
        "model": args.model, "reasoning_effort": args.reasoning_effort,
        "usage_source": "Codex cumulative turn.completed usage; cycle count from cumulative usage events",
    })
    (artifacts / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
