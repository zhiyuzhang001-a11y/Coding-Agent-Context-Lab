#!/usr/bin/env python3
"""Run isolated Native/CO CO-1 Gate 2 pairs and attribute compensation reads."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from run_co0_gate import load_jsonl


ARMS = ("native", "co")
READ_EXECUTABLES = {"cat", "sed", "rg"}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True, timeout=60
    )
    return result.stdout.strip()


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unsupported CO-1 Gate 2 manifest")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != 6:
        raise ValueError("CO-1 Gate 2 manifest must contain exactly six cases")
    if sum(bool(case.get("activated")) for case in cases if isinstance(case, dict)) != 4:
        raise ValueError("CO-1 Gate 2 manifest must contain exactly four activated cases")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(set(ids)) or not all(isinstance(case_id, str) and case_id for case_id in ids):
        raise ValueError("case ids must be unique non-empty strings")
    return value


def marker_range(path: Path, case_id: str) -> tuple[int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start_marker = f"# CASE {case_id} START"
    end_marker = f"# CASE {case_id} END"
    starts = [index for index, line in enumerate(lines, start=1) if line == start_marker]
    ends = [index for index, line in enumerate(lines, start=1) if line == end_marker]
    if len(starts) != 1 or len(ends) != 1 or starts[0] > ends[0]:
        raise ValueError(f"invalid fixture markers for {case_id}")
    return starts[0], ends[0]


def case_command(workspace: Path, fixture_relative: Path, case_id: str) -> str:
    start, end = marker_range(workspace / fixture_relative, case_id)
    return f"sed -n '{start},{end}p' {fixture_relative}"


def build_prompt(case: dict[str, Any], command: str) -> str:
    return (
        f"Begin by running exactly this shell command: {command}. "
        "Do not use Smart Read, Task Navigator, context_router, navigation_map, or web tools. "
        "Use ordinary shell read/search commands only if the first result is insufficient. "
        f"{case['question']}"
    )


def final_message(events: list[dict[str, Any]]) -> str:
    messages = [
        event.get("item", {}).get("text", "")
        for event in events
        if isinstance(event.get("item"), dict) and event.get("item", {}).get("type") == "agent_message"
    ]
    return messages[-1].strip() if messages else ""


def final_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    for event in reversed(events):
        usage = event.get("usage")
        if event.get("type") == "turn.completed" and isinstance(usage, dict):
            values = {
                key: int(value)
                for key, value in usage.items()
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            }
            values["total_tokens"] = values.get("input_tokens", 0) + values.get("output_tokens", 0)
            return values
    return {"total_tokens": 0}


def parse_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def custom_exec_arguments(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    marker = "tools.exec_command("
    start = value.find(marker)
    if start < 0:
        return {}
    start += len(marker)
    end = value.find(");", start)
    if end < 0:
        return {}
    raw = value[start:end]
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        # Current code mode emits a JavaScript object literal with unquoted keys.
        # Extract only the JSON string assigned to cmd/command; do not evaluate JS.
        match = re.search(r'\b(?:cmd|command)\s*:\s*("(?:\\.|[^"\\])*")', raw)
        if not match:
            return {}
        try:
            command = json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
        return {"cmd": command} if isinstance(command, str) else {}
    return loaded if isinstance(loaded, dict) else {}


def model_output_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        texts = [
            item.get("text", "")
            for item in value
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if texts:
            return "".join(texts)
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def transcript_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in events:
        if event.get("type") != "response_item" or not isinstance(event.get("payload"), dict):
            continue
        payload = event["payload"]
        payload_type = payload.get("type")
        if payload_type in {"function_call", "custom_tool_call", "local_shell_call"}:
            call_id = payload.get("call_id", payload.get("id"))
            if not isinstance(call_id, str):
                continue
            raw_input = payload.get("arguments", payload.get("input"))
            arguments = parse_arguments(raw_input)
            if not arguments and payload_type == "custom_tool_call":
                arguments = custom_exec_arguments(raw_input)
            command = arguments.get("cmd", arguments.get("command", payload.get("command")))
            calls[call_id] = {
                "call_id": call_id,
                "tool_name": payload.get("name", payload_type),
                "command": command if isinstance(command, str) else "",
                "output": "",
            }
            order.append(call_id)
        elif payload_type in {"function_call_output", "custom_tool_call_output"}:
            call_id = payload.get("call_id", payload.get("id"))
            if not isinstance(call_id, str) or call_id not in calls:
                continue
            calls[call_id]["output"] = model_output_text(payload.get("output"))
    return [calls[call_id] for call_id in order if call_id in calls]


def command_shape(command: str) -> tuple[str, str | None]:
    try:
        words = shlex.split(command, comments=False, posix=True)
    except ValueError:
        return "other", None
    if not words:
        return "other", None
    executable = words[0].rsplit("/", 1)[-1]
    if executable in READ_EXECUTABLES:
        path = words[-1] if len(words) > 1 else None
        return executable, path
    basenames = {word.rsplit("/", 1)[-1] for word in words}
    if {"smart_read.py", "context_router.py"} & basenames:
        return "known_symbol", next((word for word in words if word.endswith(".py")), None)
    if executable in {"python", "python3", "pytest", "make", "npm", "cargo"}:
        return "test_or_build", None
    if executable in {"apply_patch", "perl"}:
        return "edit", None
    return "other", None


def normalize_command(command: str) -> str:
    try:
        return " ".join(shlex.split(command, comments=False, posix=True))
    except ValueError:
        return command.strip()


def attribute_calls(calls: list[dict[str, Any]], initial_command: str, fixture: str) -> list[dict[str, Any]]:
    attributed: list[dict[str, Any]] = []
    normalized_initial = normalize_command(initial_command)
    initial_seen = False
    for call in calls:
        command = str(call.get("command", ""))
        kind, path = command_shape(command)
        normalized = normalize_command(command)
        if not initial_seen and normalized == normalized_initial:
            category = "initial_activated_read"
            initial_seen = True
        elif normalized == normalized_initial:
            category = "same_intent_retry"
        elif kind in {*READ_EXECUTABLES, "known_symbol"} and path and (
            path == fixture or Path(path).name == Path(fixture).name
        ):
            category = "adjacent_context_compensation"
        elif kind in {*READ_EXECUTABLES, "known_symbol"}:
            category = "other_read_or_search"
        else:
            category = kind
        output = str(call.get("output", ""))
        attributed.append(
            {
                "call_id": call.get("call_id"),
                "tool_name": call.get("tool_name"),
                "category": category,
                "command_kind": kind,
                "path": path,
                "command_sha256": sha256_text(normalized),
                "output_chars": len(output),
                "visible_tokens": (len(output) + 3) // 4,
                "output_sha256": sha256_text(output),
                "contains_syntax_package": "Smart Read CO-1 syntax slice" in output,
            }
        )
    return attributed


def read_visible_tokens(attributed: list[dict[str, Any]]) -> int:
    categories = {
        "initial_activated_read",
        "same_intent_retry",
        "adjacent_context_compensation",
        "other_read_or_search",
    }
    return sum(int(item["visible_tokens"]) for item in attributed if item["category"] in categories)


def new_transcript(home: Path, before: set[Path]) -> Path | None:
    candidates = [path for path in home.rglob("*.jsonl") if path not in before and path.is_file()]
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


def prepare_homes(repository: Path, artifacts: Path, codex: Path, source_home: Path) -> dict[str, Path]:
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
                "[marketplaces.personal]\n"
                'source_type = "local"\n'
                f"source = {json.dumps(str(repository))}\n"
            )
            if arm == "co"
            else "",
            encoding="utf-8",
        )
        config.chmod(0o600)
        if arm == "co":
            environment = dict(os.environ)
            environment["CODEX_HOME"] = str(home)
            install = subprocess.run(
                [str(codex), "plugin", "add", "agent-token-manager@personal"],
                env=environment,
                text=True,
                capture_output=True,
                timeout=90,
            )
            if install.returncode != 0:
                raise RuntimeError(install.stderr.strip() or install.stdout.strip())
        homes[arm] = home
    return homes


def run_case(
    *,
    repository: Path,
    commit: str,
    fixture_relative: Path,
    case: dict[str, Any],
    arm: str,
    codex: Path,
    codex_home: Path,
    artifacts: Path,
    model: str,
    reasoning_effort: str,
    syntax_budget: int,
    timeout: int,
) -> dict[str, Any]:
    run_id = f"{case['id']}-{arm}"
    run_dir = artifacts / run_id
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix=f"co1-gate2-{run_id}-"))
    worktree = parent / "worktree"
    added = False
    result: dict[str, Any]
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), commit],
            cwd=repository,
            text=True,
            capture_output=True,
            check=True,
            timeout=60,
        )
        added = True
        command = case_command(worktree, fixture_relative, str(case["id"]))
        prompt = build_prompt(case, command)
        before = set(codex_home.rglob("*.jsonl"))
        environment = dict(os.environ)
        environment.update(
            {
                "CODEX_HOME": str(codex_home),
                "AGENT_TOKEN_MANAGER_DATA": str(run_dir / "manager-data"),
                "AGENT_TOKEN_MANAGER_CO0_MODE": "enforce" if arm == "co" else "observe",
                "AGENT_TOKEN_MANAGER_CO0_MIN_CHARS": "128",
                "AGENT_TOKEN_MANAGER_CO0_VISIBLE_CHARS": "256",
                "AGENT_TOKEN_MANAGER_CO1_MODE": "enforce" if arm == "co" else "observe",
                "AGENT_TOKEN_MANAGER_CO1_VISIBLE_CHARS": str(syntax_budget),
                "AGENT_TOKEN_MANAGER_CO0_CANARY": str(case["canary"]),
                "AGENT_TOKEN_MANAGER_CO0_RECORD_TRANSCRIPT_PATH": "1",
            }
        )
        exec_command = [
            str(codex), "exec", "--json", "--ignore-rules", "--dangerously-bypass-hook-trust",
            "--sandbox", "workspace-write", "--model", model, "--cd", str(worktree),
            "--config", f'model_reasoning_effort="{reasoning_effort}"',
            "--config", "features.multi_agent=false", prompt,
        ]
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                exec_command, env=environment, text=True, capture_output=True, timeout=timeout
            )
            timed_out = False
        except subprocess.TimeoutExpired as error:
            completed = subprocess.CompletedProcess(
                exec_command, 124, error.stdout or "", error.stderr or ""
            )
            timed_out = True
        elapsed = round(time.perf_counter() - started, 3)
        stdout = completed.stdout if isinstance(completed.stdout, str) else completed.stdout.decode("utf-8", "replace")
        stderr = completed.stderr if isinstance(completed.stderr, str) else completed.stderr.decode("utf-8", "replace")
        (run_dir / "codex.jsonl").write_text(stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(stderr, encoding="utf-8")
        exec_events = load_jsonl(run_dir / "codex.jsonl")
        optimizer_records = load_jsonl(run_dir / "manager-data" / "context-optimizer.jsonl")
        transcript_path: Path | None = None
        for record in reversed(optimizer_records):
            value = record.get("transcript_path")
            if isinstance(value, str):
                transcript_path = Path(value)
                break
        if transcript_path is None:
            transcript_path = new_transcript(codex_home, before)
        transcript_events = load_jsonl(transcript_path) if transcript_path else []
        calls = transcript_calls(transcript_events)
        attributed = attribute_calls(calls, command, str(fixture_relative))
        visible_text = "\n".join(
            str(call.get("output", "")) for call in calls if call.get("output")
        )
        final = final_message(exec_events)
        changed = git_output(worktree, "diff", "--name-only", "--relative").splitlines()
        test_ok = True
        if case.get("kind") == "edit":
            test = subprocess.run(
                shlex.split(str(case["test_command"])), cwd=worktree, text=True,
                capture_output=True, timeout=60
            )
            test_ok = test.returncode == 0
            (run_dir / "verification-test.txt").write_text(test.stdout + test.stderr, encoding="utf-8")
        allowed = case.get("allowed_path")
        diff_ok = not allowed or changed == [allowed]
        correct = final == case["expected"] and test_ok and diff_ok
        replacement_visible = "Smart Read CO-1 syntax slice" in visible_text
        result = {
            "schema_version": 1,
            "run_id": run_id,
            "case_id": case["id"],
            "arm": arm,
            "activated": bool(case["activated"]),
            "commit": commit,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "status": "completed" if completed.returncode == 0 and not timed_out else "failed",
            "correct": correct,
            "final_text": final,
            "expected": case["expected"],
            "test_ok": test_ok,
            "diff_ok": diff_ok,
            "changed_paths": changed,
            "elapsed_seconds": elapsed,
            "usage": final_usage(exec_events),
            "transcript_available": bool(transcript_events),
            "initial_command_sha256": sha256_text(normalize_command(command)),
            "attributed_calls": attributed,
            "read_visible_tokens": read_visible_tokens(attributed),
            "same_intent_retries": sum(item["category"] == "same_intent_retry" for item in attributed),
            "compensation_reads": sum(item["category"] == "adjacent_context_compensation" for item in attributed),
            "other_reads": sum(item["category"] == "other_read_or_search" for item in attributed),
            "canary_visible": str(case["canary"]) in visible_text,
            "replacement_visible": replacement_visible,
            "visible_output_sha256": sha256_text(visible_text),
            "optimizer_statuses": [record.get("status") for record in optimizer_records],
            "optimizer_reasons": [record.get("reason") for record in optimizer_records],
            "optimizer_attempts": len(optimizer_records),
            "optimizer_successes": sum(record.get("status") == "optimized" for record in optimizer_records),
            "optimizer_fail_open_count": sum(record.get("status") != "optimized" for record in optimizer_records),
            "artifacts": {
                "directory": str(run_dir),
                "transcript_sha256": sha256_text(transcript_path.read_text(encoding="utf-8", errors="replace"))
                if transcript_path and transcript_path.exists() else None,
            },
        }
        (run_dir / "worktree.diff").write_text(
            subprocess.run(["git", "diff", "--relative"], cwd=worktree, text=True, capture_output=True).stdout,
            encoding="utf-8",
        )
    except Exception as error:
        result = {
            "schema_version": 1, "run_id": run_id, "case_id": case.get("id"), "arm": arm,
            "activated": bool(case.get("activated")), "commit": commit, "status": "failed",
            "correct": False, "error": f"{type(error).__name__}: {error}",
        }
    finally:
        if added:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=repository, text=True, capture_output=True, timeout=60
            )
        shutil.rmtree(parent, ignore_errors=True)
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def summarize(cases: list[dict[str, Any]], results: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for case in cases:
        native = results.get((case["id"], "native"), {})
        co = results.get((case["id"], "co"), {})
        native_visible = int(native.get("read_visible_tokens", 0))
        co_visible = int(co.get("read_visible_tokens", 0))
        saving = native_visible - co_visible
        pairs.append(
            {
                "case_id": case["id"],
                "activated": bool(case["activated"]),
                "native_correct": bool(native.get("correct")),
                "co_correct": bool(co.get("correct")),
                "native_visible_tokens": native_visible,
                "co_visible_tokens_after_compensation": co_visible,
                "net_activated_read_saving": saving,
                "net_saving_percent": round(100 * saving / native_visible, 2) if native_visible else None,
                "co_same_intent_retries": int(co.get("same_intent_retries", 0)),
                "co_compensation_reads": int(co.get("compensation_reads", 0)),
                "native_total_tokens": int(native.get("usage", {}).get("total_tokens", 0)),
                "co_total_tokens": int(co.get("usage", {}).get("total_tokens", 0)),
                "native_canary_visible": bool(native.get("canary_visible")),
                "co_canary_visible": bool(co.get("canary_visible")),
                "co_replacement_visible": bool(co.get("replacement_visible")),
                "co_optimizer_reasons": co.get("optimizer_reasons", []),
                "visible_output_equal": native.get("visible_output_sha256") == co.get("visible_output_sha256"),
            }
        )
    activated = [pair for pair in pairs if pair["activated"]]
    fail_open = [pair for pair in pairs if not pair["activated"]]
    saving_percentages = [float(pair["net_saving_percent"]) for pair in activated if pair["net_saving_percent"] is not None]
    retries = [int(pair["co_same_intent_retries"]) for pair in activated]
    expected_reasons = {case["id"]: case.get("expected_fail_open_reason") for case in cases if not case["activated"]}
    checks = {
        "correctness_equal": all(pair["native_correct"] and pair["co_correct"] for pair in pairs),
        "activated_model_visibility": all(
            pair["native_canary_visible"] and not pair["co_canary_visible"] and pair["co_replacement_visible"]
            for pair in activated
        ),
        "median_net_saving_at_least_40_percent": bool(saving_percentages) and statistics.median(saving_percentages) >= 40,
        "median_same_intent_retries_zero": bool(retries) and statistics.median(retries) == 0,
        "no_task_more_than_one_retry": max(retries, default=0) <= 1,
        "three_of_four_activated_net_positive": sum(pair["net_activated_read_saving"] > 0 for pair in activated) >= 3,
        "fail_open_native_equivalent": all(pair["visible_output_equal"] for pair in fail_open),
        "fail_open_reasons_match": all(
            expected_reasons[pair["case_id"]] in pair["co_optimizer_reasons"] for pair in fail_open
        ),
        "one_complete_session_lower": any(pair["co_total_tokens"] < pair["native_total_tokens"] for pair in activated),
    }
    return {
        "schema_version": 1,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "pairs": pairs,
        "median_net_saving_percent": statistics.median(saving_percentages) if saving_percentages else None,
        "median_same_intent_retries": statistics.median(retries) if retries else None,
    }


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    repository = Path(git_output(plugin, "rev-parse", "--show-toplevel"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=plugin / "resources" / "co1_gate2_cases.json")
    parser.add_argument("--artifacts", type=Path, default=repository / ".agent-token-manager" / "co1-gate2")
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--codex", type=Path, default=Path("/Applications/ChatGPT.app/Contents/Resources/codex"))
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    cases = [case for case in manifest["cases"] if not args.case_ids or case["id"] in args.case_ids]
    commit = git_output(repository, "rev-parse", args.commit)
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    homes = prepare_homes(repository, artifacts, args.codex.resolve(), source_home)
    fixture_relative = Path(manifest["fixture"])
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for index, case in enumerate(cases):
        arms = ARMS if index % 2 == 0 else tuple(reversed(ARMS))
        for arm in arms:
            result = run_case(
                repository=repository, commit=commit, fixture_relative=fixture_relative,
                case=case, arm=arm, codex=args.codex.resolve(), codex_home=homes[arm],
                artifacts=artifacts, model=args.model, reasoning_effort=args.reasoning_effort,
                syntax_budget=int(manifest["syntax_budget_chars"]), timeout=args.timeout,
            )
            results[(case["id"], arm)] = result
    summary = summarize(cases, results)
    summary.update(
        {
            "commit": commit,
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "plugin_version": json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())["version"],
            "manifest_sha256": sha256_text(args.manifest.read_text(encoding="utf-8")),
            "token_count_method": "chars_div_4_v1 for model-visible tool outputs; Codex usage for full session",
        }
    )
    (artifacts / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
