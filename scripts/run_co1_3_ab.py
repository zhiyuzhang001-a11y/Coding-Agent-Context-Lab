#!/usr/bin/env python3
"""Run the frozen CO-1.3 natural-behavior Native versus Hook+Gate A/B."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from run_co0_gate import load_jsonl
from run_co1_1_pilot import assistant_cycles, cumulative_usage_series
from run_co1_gate2 import (
    command_shape,
    final_message,
    final_usage,
    git_output,
    new_transcript,
    normalize_command,
    sha256_text,
    transcript_calls,
)


ARMS = ("native", "co")
READ_KINDS = {"cat", "sed", "rg", "known_symbol"}
PACKAGE_MARKER = "Smart Read CO-1.2 gated syntax slice"


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    cases = value.get("cases") if isinstance(value, dict) else None
    if value.get("schema_version") != 1 or not isinstance(cases, list) or len(cases) != 12:
        raise ValueError("CO-1.3 manifest must contain exactly 12 schema-v1 cases")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != 12 or len(set(ids)) != 12 or not all(isinstance(item, str) and item for item in ids):
        raise ValueError("CO-1.3 case ids must be unique non-empty strings")
    cohorts = Counter(case.get("cohort") for case in cases)
    if cohorts != Counter({"expected_hit": 6, "expected_fail_open": 6}):
        raise ValueError("CO-1.3 requires six expected-hit and six expected-fail-open cases")
    orders = Counter(tuple(case.get("order", ())) for case in cases)
    if orders != Counter({("native", "co"): 6, ("co", "native"): 6}):
        raise ValueError("CO-1.3 requires six AB and six BA pairs")
    required = {"id", "cohort", "target_path", "symbol", "question", "expected", "order"}
    if any(not required.issubset(case) for case in cases):
        raise ValueError("CO-1.3 case is missing required fields")
    return value


def load_gate(subject_root: Path):
    path = subject_root / "experiments/co1-hook-only/plugins/hook-only-cost-probe/scripts/compensation_risk_gate.py"
    spec = importlib.util.spec_from_file_location("co13_frozen_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen gate: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def symbol_span(gate: Any, path: Path, symbol: str) -> tuple[int, int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches = []
    for node, owner in gate.definitions(tree):
        name = f"{owner.name}.{node.name}" if owner else node.name
        if name == symbol:
            matches.append((gate.start_line(node), node.end_lineno or node.lineno))
    if len(matches) != 1:
        raise ValueError(f"expected one frozen symbol {symbol}, found {len(matches)}")
    return matches[0]


def preflight(subject_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    gate = load_gate(subject_root)
    rows: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        path = subject_root / case["target_path"]
        first, last = symbol_span(gate, path, case["symbol"])
        raw = path.read_text(encoding="utf-8")
        decision = gate.evaluate(path, first, last, raw, task_intent=case.get("task_intent"))
        expected_reason = "low_compensation_risk" if case["cohort"] == "expected_hit" else case["expected_gate_reason"]
        rows.append({
            "case_id": case["id"], "target_lines": [first, last],
            "expected_reason": expected_reason, "actual_reason": decision.reason,
            "activate_slice": decision.activate_slice, "passed": decision.reason == expected_reason,
            "estimated_saving_tokens": decision.details.get("estimated_saving_tokens"),
            "estimated_saving_ratio": decision.details.get("estimated_saving_ratio"),
        })
    return rows


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
            "" if arm == "native" else (
                "[marketplaces.co1-hook-lab]\n"
                'source_type = "local"\n'
                f"source = {json.dumps(str(lab))}\n"
            ),
            encoding="utf-8",
        )
        config.chmod(0o600)
        if arm == "co":
            environment = dict(os.environ, CODEX_HOME=str(home))
            installed = subprocess.run(
                [str(codex), "plugin", "add", "hook-only-cost-probe@co1-hook-lab"],
                env=environment, text=True, capture_output=True, timeout=90,
            )
            if installed.returncode != 0:
                raise RuntimeError(installed.stderr.strip() or installed.stdout.strip())
        homes[arm] = home
    return homes


def build_prompt(case: dict[str, Any]) -> str:
    return (
        "Work only from the local repository. Do not use web tools, Smart Read, Task Navigator, "
        "context_router, navigation_map, or subagents. Do not modify files. "
        f"Inspect {case['target_path']} and the symbol {case['symbol']} as needed. "
        f"{case['question']}"
    )


def call_metrics(calls: list[dict[str, Any]], target_path: str) -> dict[str, Any]:
    reads: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    for index, call in enumerate(calls):
        command = str(call.get("command", ""))
        kind, path = command_shape(command)
        normalized = normalize_command(command)
        if kind not in READ_KINDS:
            continue
        seen[normalized] += 1
        output = str(call.get("output", ""))
        reads.append({
            "index": index, "call_id": call.get("call_id"), "kind": kind, "path": path,
            "targets_case_file": bool(path and (path == target_path or Path(path).name == Path(target_path).name)),
            "visible_tokens": (len(output) + 3) // 4,
            "contains_package": PACKAGE_MARKER in output,
            "command_sha256": sha256_text(normalized),
        })
    return {
        "read_calls": reads,
        "model_visible_code_tokens": sum(item["visible_tokens"] for item in reads),
        "exact_read_retries": sum(max(0, count - 1) for count in seen.values()),
        "target_file_read_count": sum(item["targets_case_file"] for item in reads),
        "package_visible": any(item["contains_package"] for item in reads),
    }


def run_case(
    repository: Path, subject_commit: str, case: dict[str, Any], arm: str, codex: Path,
    home: Path, artifacts: Path, model: str, reasoning: str, timeout: int,
) -> dict[str, Any]:
    run_id = f"{case['id']}-{arm}"
    run_dir = artifacts / run_id
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix=f"co13-{run_id}-"))
    worktree = parent / "worktree"
    added = False
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), subject_commit],
            cwd=repository, check=True, text=True, capture_output=True, timeout=60,
        )
        added = True
        before = set(home.rglob("*.jsonl"))
        environment = dict(os.environ)
        environment.update({"CODEX_HOME": str(home), "CO11_HOOK_MODE": "gated", "CO11_DATA": str(run_dir)})
        if case.get("task_intent"):
            environment["CO12_TASK_INTENT"] = str(case["task_intent"])
        command = [
            str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust",
            "--sandbox", "read-only", "--model", model, "--cd", str(worktree),
            "--config", f'model_reasoning_effort="{reasoning}"',
            "--config", "features.multi_agent=false", build_prompt(case),
        ]
        started = time.perf_counter()
        completed = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=timeout)
        elapsed = round(time.perf_counter() - started, 3)
        (run_dir / "codex.jsonl").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        exec_events = load_jsonl(run_dir / "codex.jsonl")
        records = load_jsonl(run_dir / "hook-probe.jsonl") if arm == "co" else []
        transcript = next(
            (Path(record["transcript_path"]) for record in reversed(records) if isinstance(record.get("transcript_path"), str)),
            None,
        )
        if transcript is None:
            transcript = new_transcript(home, before)
        transcript_events = load_jsonl(transcript) if transcript else []
        calls = transcript_calls(transcript_events)
        metrics = call_metrics(calls, case["target_path"])
        usage_series = cumulative_usage_series(transcript_events)
        final = final_message(exec_events)
        reasons = [record.get("reason") for record in records if isinstance(record.get("reason"), str)]
        activated_ids = {record.get("tool_use_id") for record in records if record.get("activate_slice") is True}
        activated_positions = [index for index, call in enumerate(calls) if call.get("call_id") in activated_ids]
        first_activation = min(activated_positions) if activated_positions else None
        recovery_reads = sum(
            item["index"] > first_activation and item["targets_case_file"]
            for item in metrics["read_calls"]
        ) if first_activation is not None else 0
        result = {
            "schema_version": 1, "run_id": run_id, "case_id": case["id"], "cohort": case["cohort"],
            "arm": arm, "subject_commit": subject_commit, "model": model, "reasoning_effort": reasoning,
            "status": "completed" if completed.returncode == 0 else "failed",
            "correct": completed.returncode == 0 and final == case["expected"],
            "final_text": final, "expected": case["expected"], "elapsed_seconds": elapsed,
            "usage": final_usage(exec_events), "model_cycles": len(usage_series),
            "assistant_message_count": assistant_cycles(transcript_events), "tool_call_count": len(calls),
            **metrics, "gate_attempts": len(records), "gate_reasons": reasons,
            "supported_read_attempts": sum(
                not (
                    record.get("reason") == "analysis_uncertain"
                    and record.get("risk_evidence") == ["unsupported_request"]
                )
                for record in records
            ),
            "gate_activations": sum(record.get("activate_slice") is True for record in records),
            "gate_fail_open_count": sum(record.get("activate_slice") is False for record in records),
            "recovery_reads_after_activation": recovery_reads,
            "cumulative_usage_series": usage_series,
            "transcript_available": bool(transcript_events),
            "transcript_sha256": sha256_text(transcript.read_text(encoding="utf-8", errors="replace")) if transcript and transcript.exists() else None,
        }
    except Exception as error:
        result = {
            "schema_version": 1, "run_id": run_id, "case_id": case.get("id"), "cohort": case.get("cohort"),
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


def ratio(co: int, native: int) -> float | None:
    return co / native if native > 0 else None


def summarize(cases: list[dict[str, Any]], results: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for case in cases:
        native = results[(case["id"], "native")]
        co = results[(case["id"], "co")]
        native_total = int(native.get("usage", {}).get("total_tokens", 0))
        co_total = int(co.get("usage", {}).get("total_tokens", 0))
        native_visible = int(native.get("model_visible_code_tokens", 0))
        co_visible = int(co.get("model_visible_code_tokens", 0))
        pairs.append({
            "case_id": case["id"], "cohort": case["cohort"],
            "native_correct": bool(native.get("correct")), "co_correct": bool(co.get("correct")),
            "native_total_tokens": native_total, "co_total_tokens": co_total,
            "total_token_delta": co_total - native_total, "total_token_ratio": ratio(co_total, native_total),
            "native_visible_code_tokens": native_visible, "co_visible_code_tokens": co_visible,
            "visible_code_ratio": ratio(co_visible, native_visible),
            "native_model_cycles": int(native.get("model_cycles", 0)), "co_model_cycles": int(co.get("model_cycles", 0)),
            "native_tool_calls": int(native.get("tool_call_count", 0)), "co_tool_calls": int(co.get("tool_call_count", 0)),
            "native_retries": int(native.get("exact_read_retries", 0)), "co_retries": int(co.get("exact_read_retries", 0)),
            "co_recovery_reads": int(co.get("recovery_reads_after_activation", 0)),
            "co_gate_activations": int(co.get("gate_activations", 0)), "co_gate_reasons": co.get("gate_reasons", []),
            "co_package_visible": bool(co.get("package_visible")),
        })

    def group(rows: list[dict[str, Any]]) -> dict[str, Any]:
        ratios = [row["total_token_ratio"] for row in rows if row["total_token_ratio"] is not None]
        native_sum = sum(row["native_total_tokens"] for row in rows)
        co_sum = sum(row["co_total_tokens"] for row in rows)
        visible_ratios = [row["visible_code_ratio"] for row in rows if row["visible_code_ratio"] is not None]
        return {
            "count": len(rows), "median_paired_total_ratio": statistics.median(ratios) if ratios else None,
            "pooled_total_ratio": ratio(co_sum, native_sum),
            "median_visible_code_ratio": statistics.median(visible_ratios) if visible_ratios else None,
            "cycle_delta_sum": sum(row["co_model_cycles"] - row["native_model_cycles"] for row in rows),
            "tool_call_delta_sum": sum(row["co_tool_calls"] - row["native_tool_calls"] for row in rows),
            "retry_delta_sum": sum(row["co_retries"] - row["native_retries"] for row in rows),
            "recovery_reads_sum": sum(row["co_recovery_reads"] for row in rows),
        }

    all_stats = group(pairs)
    activated = [row for row in pairs if row["co_gate_activations"] > 0]
    fail_open = [row for row in pairs if row["co_gate_activations"] == 0]
    activated_stats = group(activated)
    fail_open_stats = group(fail_open)
    correctness = all(row["native_correct"] and row["co_correct"] for row in pairs)
    no_compensation = all_stats["retry_delta_sum"] <= 0 and all_stats["recovery_reads_sum"] == 0
    no_cycle_increase = all_stats["cycle_delta_sum"] <= 0
    mechanism = bool(activated) and activated_stats["median_visible_code_ratio"] is not None and activated_stats["median_visible_code_ratio"] <= 0.60
    strong = correctness and no_compensation and no_cycle_increase and mechanism and all_stats["median_paired_total_ratio"] <= 0.95 and all_stats["pooled_total_ratio"] <= 0.95
    weak = (
        correctness and no_compensation and bool(activated)
        and all_stats["median_paired_total_ratio"] < 1.0
        and all_stats["pooled_total_ratio"] < 1.0
    )
    verdict = "strong_pass" if strong else "weak_signal" if weak else "fail"
    return {
        "schema_version": 1, "verdict": verdict,
        "checks": {
            "correctness_zero_regression": correctness, "retry_recovery_not_increased": no_compensation,
            "model_cycles_not_increased": no_cycle_increase, "actual_activation_nonzero": bool(activated),
            "activated_visible_code_ratio_at_most_0_60": mechanism,
            "overall_median_total_ratio_at_most_0_95": all_stats["median_paired_total_ratio"] <= 0.95,
            "overall_pooled_total_ratio_at_most_0_95": all_stats["pooled_total_ratio"] <= 0.95,
        },
        "all_tasks": all_stats, "actual_activated": activated_stats, "actual_fail_open": fail_open_stats,
        "pairs": pairs,
    }


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    repository = Path(git_output(plugin, "rev-parse", "--show-toplevel"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=plugin / "resources/co1_3_cases.json")
    parser.add_argument("--artifacts", type=Path, default=repository / ".agent-token-manager/co1-3")
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
    subject_parent = Path(tempfile.mkdtemp(prefix="co13-subject-"))
    subject_root = subject_parent / "subject"
    added = False
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(subject_root), subject_commit], cwd=repository,
            check=True, text=True, capture_output=True, timeout=60,
        )
        added = True
        preflight_rows = preflight(subject_root, manifest)
        preflight_result = {
            "subject_commit": subject_commit, "manifest_sha256": sha256_text(args.manifest.read_text(encoding="utf-8")),
            "all_expected_classifications_match": all(row["passed"] for row in preflight_rows), "cases": preflight_rows,
        }
        (artifacts / "preflight.json").write_text(json.dumps(preflight_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not preflight_result["all_expected_classifications_match"]:
            print(json.dumps(preflight_result, ensure_ascii=False, indent=2))
            return 1
        if args.preflight_only:
            print(json.dumps(preflight_result, ensure_ascii=False, indent=2))
            return 0
        homes = prepare_homes(
            subject_root / "experiments/co1-hook-only", artifacts, args.codex.resolve(),
            Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve(),
        )
        results: dict[tuple[str, str], dict[str, Any]] = {}
        for case in manifest["cases"]:
            for arm in case["order"]:
                result = run_case(
                    repository, subject_commit, case, arm, args.codex.resolve(), homes[arm], artifacts,
                    args.model, args.reasoning_effort, args.timeout,
                )
                results[(case["id"], arm)] = result
        summary = summarize(manifest["cases"], results)
        summary.update({
            "subject_commit": subject_commit, "harness_commit": git_output(repository, "rev-parse", "HEAD"),
            "manifest_sha256": preflight_result["manifest_sha256"], "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "token_count_method": "Codex cumulative usage for full session; chars_div_4_v1 for model-visible read outputs",
        })
        (artifacts / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["verdict"] == "strong_pass" else 1
    finally:
        if added:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(subject_root)], cwd=repository,
                text=True, capture_output=True, timeout=60,
            )
        shutil.rmtree(subject_parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
