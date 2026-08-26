#!/usr/bin/env python3
"""Run isolated Native/M2d Codex calibration pairs and retain private raw artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from m2e_events import parse_codex_jsonl


ARMS = ("native", "m2d")


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unsupported M2e calibration manifest")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest must contain cases")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("case ids must be unique non-empty strings")
        seen.add(case_id)
        if case.get("kind") not in {"locate", "edit"}:
            raise ValueError(f"unsupported case kind: {case.get('kind')}")
        if not isinstance(case.get("prompt"), str) or not case["prompt"]:
            raise ValueError(f"case {case_id} has no prompt")
    return value


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> tuple[int, bool, float]:
    stdout_target: Any = subprocess.PIPE
    stderr_target: Any = subprocess.PIPE
    stdout_handle = None
    stderr_handle = None
    if stdout_path is not None:
        stdout_handle = stdout_path.open("wb")
        stdout_target = stdout_handle
    if stderr_path is not None:
        stderr_handle = stderr_path.open("wb")
        stderr_target = stderr_handle
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout_target,
        stderr=stderr_target,
        start_new_session=True,
    )
    timed_out = False
    try:
        process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
    finally:
        if stdout_handle is not None:
            stdout_handle.close()
        if stderr_handle is not None:
            stderr_handle.close()
    return process.returncode, timed_out, round(time.perf_counter() - started, 3)


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def prepare_codex_homes(
    artifacts: Path,
    repository: Path,
    codex: str,
    source_codex_home: Path,
) -> tuple[dict[str, Path], dict[str, Any]]:
    auth = source_codex_home / "auth.json"
    if not auth.is_file():
        raise RuntimeError(f"Codex authentication file not found: {auth}")
    homes: dict[str, Path] = {}
    diagnostics: dict[str, Any] = {}
    for arm in ARMS:
        home = _private_directory(artifacts / f"codex-home-{arm}")
        auth_link = home / "auth.json"
        if not auth_link.exists():
            auth_link.symlink_to(auth)
        config = home / "config.toml"
        if arm == "m2d":
            config.write_text(
                "[marketplaces.personal]\n"
                "source_type = \"local\"\n"
                f"source = {json.dumps(str(repository))}\n",
                encoding="utf-8",
            )
            environment = dict(os.environ)
            environment["CODEX_HOME"] = str(home)
            install = subprocess.run(
                [codex, "plugin", "add", "agent-token-manager@personal", "--json"],
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if install.returncode != 0:
                raise RuntimeError(
                    "failed to install isolated M2d plugin: "
                    + (install.stderr.strip() or install.stdout.strip())
                )
        else:
            config.write_text("", encoding="utf-8")
        config.chmod(0o600)
        homes[arm] = home

        environment = dict(os.environ)
        environment["CODEX_HOME"] = str(home)
        probe = subprocess.run(
            [codex, "debug", "prompt-input", "isolation probe"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        marker_present = "agent-token-manager:budgeted-code-reading" in probe.stdout
        expected = arm == "m2d"
        diagnostics[arm] = {
            "returncode": probe.returncode,
            "smart_read_skill_present": marker_present,
            "expected": expected,
            "compliant": probe.returncode == 0 and marker_present == expected,
            "prompt_input_sha256": hashlib.sha256(probe.stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(probe.stderr.encode("utf-8")).hexdigest(),
        }
    if not all(item["compliant"] for item in diagnostics.values()):
        raise RuntimeError(f"Codex home isolation failed: {diagnostics}")
    return homes, diagnostics


def _json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _task_evaluation(
    case: dict[str, Any],
    workspace: Path,
    final_message: dict[str, Any] | None,
    run_dir: Path,
) -> dict[str, Any]:
    changed_paths = [
        line
        for line in git_output(workspace, "diff", "--name-only", "--relative").splitlines()
        if line
    ]
    diff_path = run_dir / "worktree.diff"
    diff_result = subprocess.run(
        ["git", "diff", "--binary", "--relative"],
        cwd=str(workspace),
        capture_output=True,
        timeout=30,
    )
    diff_path.write_bytes(diff_result.stdout)
    try:
        diff_path.chmod(0o600)
    except OSError:
        pass

    target_path = str((final_message or {}).get("target_path", ""))
    target_symbol = str((final_message or {}).get("target_symbol", ""))
    path_match = any(target_path.endswith(path) for path in case.get("expected_paths", []))
    symbol_match = any(symbol in target_symbol for symbol in case.get("expected_symbols", []))
    allowed = set(case.get("allowed_changes", []))
    changes_allowed = not changed_paths if case["kind"] == "locate" else bool(changed_paths) and set(changed_paths) <= allowed

    test_result: dict[str, Any] | None = None
    test_command = case.get("test_command")
    if isinstance(test_command, list) and test_command:
        test_stdout = run_dir / "test.stdout"
        test_stderr = run_dir / "test.stderr"
        returncode, timed_out, elapsed = _run(
            [str(value) for value in test_command],
            cwd=workspace,
            timeout=120,
            stdout_path=test_stdout,
            stderr_path=test_stderr,
        )
        test_result = {
            "command": test_command,
            "returncode": returncode,
            "timed_out": timed_out,
            "elapsed_seconds": elapsed,
            "stdout_sha256": _sha256_file(test_stdout),
            "stderr_sha256": _sha256_file(test_stderr),
        }

    tests_passed = test_result is None or (
        test_result["returncode"] == 0 and not test_result["timed_out"]
    )
    structured_complete = bool(
        final_message
        and final_message.get("status") == "completed"
        and final_message.get("stop_reason")
    )
    return {
        "correct": bool(path_match and symbol_match and changes_allowed and tests_passed and structured_complete),
        "path_match": path_match,
        "symbol_match": symbol_match,
        "changes_allowed": changes_allowed,
        "changed_paths": changed_paths,
        "tests_passed": tests_passed,
        "test": test_result,
        "structured_result_complete": structured_complete,
        "reported_stop_reason": (final_message or {}).get("stop_reason"),
        "diff_chars": diff_path.stat().st_size,
        "diff_sha256": _sha256_file(diff_path),
    }


def codex_command(
    codex: str,
    arm: str,
    case: dict[str, Any],
    workspace: Path,
    schema: Path,
    final_message: Path,
    model: str,
    reasoning_effort: str,
    manager_data: Path,
) -> list[str]:
    command = [
        codex,
        "exec",
        "--ephemeral",
        "--ignore-rules",
        "--dangerously-bypass-hook-trust",
        "--json",
        "--model",
        model,
        "--cd",
        str(workspace),
        "--add-dir",
        str(manager_data),
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(final_message),
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--config",
        "features.multi_agent=false",
        "--approve-for-me",
    ]
    command.append(case["prompt"])
    return command


def run_one(
    *,
    repository: Path,
    plugin_relative: Path,
    commit: str,
    case: dict[str, Any],
    arm: str,
    repetition: int,
    artifacts: Path,
    codex: str,
    schema: Path,
    model: str,
    reasoning_effort: str,
    codex_home: Path,
) -> dict[str, Any]:
    run_id = f"{case['id']}-r{repetition}-{arm}"
    run_dir = _private_directory(artifacts / run_id)
    raw_jsonl = run_dir / "codex.jsonl"
    raw_stderr = run_dir / "codex.stderr"
    final_message_path = run_dir / "final-message.json"
    worktree_parent = Path(tempfile.mkdtemp(prefix=f"m2e-{run_id}-"))
    worktree = worktree_parent / "worktree"
    worktree_added = False
    cleanup_error: str | None = None
    result: dict[str, Any]
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), commit],
            cwd=str(repository),
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        worktree_added = True
        workspace = (worktree / plugin_relative / case["workspace"]).resolve()
        if not workspace.is_dir():
            raise RuntimeError(f"case workspace not found: {workspace}")
        command = codex_command(
            codex,
            arm,
            case,
            workspace,
            schema,
            final_message_path,
            model,
            reasoning_effort,
            _private_directory(run_dir / "manager-data"),
        )
        environment = dict(os.environ)
        environment["CODEX_HOME"] = str(codex_home)
        environment["AGENT_TOKEN_MANAGER_DATA"] = str(run_dir / "manager-data")
        environment["CODEX_M2E_RUN_ID"] = run_id
        returncode, timed_out, elapsed = _run(
            command,
            cwd=workspace,
            timeout=int(case.get("timeout_seconds", 300)),
            env=environment,
            stdout_path=raw_jsonl,
            stderr_path=raw_stderr,
        )
        parsed = parse_codex_jsonl(raw_jsonl, arm)
        final_message = _json_file(final_message_path)
        evaluation = _task_evaluation(case, workspace, final_message, run_dir)
        infra_ok = returncode == 0 and not timed_out and parsed["usage"]["status"] == "valid"
        result = {
            "schema_version": 1,
            "run_id": run_id,
            "case_id": case["id"],
            "kind": case["kind"],
            "arm": arm,
            "repetition": repetition,
            "commit": commit,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "codex_returncode": returncode,
            "timed_out": timed_out,
            "elapsed_seconds": elapsed,
            "infra_ok": infra_ok,
            "success": bool(infra_ok and parsed["treatment"]["compliant"] and evaluation["correct"]),
            "prompt_sha256": hashlib.sha256(case["prompt"].encode("utf-8")).hexdigest(),
            "events": parsed,
            "evaluation": evaluation,
            "raw_artifacts": {
                "directory": str(run_dir),
                "jsonl_sha256": _sha256_file(raw_jsonl),
                "stderr_sha256": _sha256_file(raw_stderr),
                "final_message_sha256": _sha256_file(final_message_path),
            },
        }
    except Exception as exc:
        result = {
            "schema_version": 1,
            "run_id": run_id,
            "case_id": case["id"],
            "kind": case["kind"],
            "arm": arm,
            "repetition": repetition,
            "commit": commit,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "infra_ok": False,
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if worktree_added:
            removal = subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=str(repository),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if removal.returncode != 0:
                cleanup_error = removal.stderr.strip() or f"returncode {removal.returncode}"
        if not worktree_added or not worktree.exists():
            shutil.rmtree(worktree_parent, ignore_errors=True)
    result["cleanup_error"] = cleanup_error
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        summary_path.chmod(0o600)
    except OSError:
        pass
    return result


def balanced_schedule(
    cases: list[dict[str, Any]],
    repetitions: int,
    repetition_start: int = 1,
) -> list[tuple[dict[str, Any], str, int]]:
    schedule: list[tuple[dict[str, Any], str, int]] = []
    for case_index, case in enumerate(cases):
        for repetition in range(repetition_start, repetition_start + repetitions):
            arms = ARMS if (case_index + repetition) % 2 else tuple(reversed(ARMS))
            schedule.extend((case, arm, repetition) for arm in arms)
    return schedule


def main() -> int:
    plugin = Path(__file__).resolve().parent.parent
    repository = Path(git_output(plugin, "rev-parse", "--show-toplevel"))
    plugin_relative = plugin.relative_to(repository)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=plugin / "resources" / "m2e_calibration_cases.json")
    parser.add_argument("--schema", type=Path, default=plugin / "resources" / "m2e_output_schema.json")
    parser.add_argument("--artifacts", type=Path, default=repository / ".agent-token-manager" / "m2e-calibration")
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--repetition-start", type=int, default=1)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--codex", default=shutil.which("codex") or "codex")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    if args.repetition_start < 1:
        parser.error("--repetition-start must be positive")

    manifest = load_manifest(args.manifest.resolve())
    cases = manifest["cases"]
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case["id"] in selected]
        missing = selected - {case["id"] for case in cases}
        if missing:
            parser.error(f"unknown cases: {', '.join(sorted(missing))}")
    commit = git_output(repository, "rev-parse", args.commit)
    schedule = balanced_schedule(cases, args.repetitions, args.repetition_start)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "benchmark": manifest["benchmark"],
                    "commit": commit,
                    "schedule": [
                        {"case_id": case["id"], "arm": arm, "repetition": repetition}
                        for case, arm, repetition in schedule
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    artifacts = _private_directory(
        args.artifacts.resolve()
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    source_codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    codex_homes, isolation = prepare_codex_homes(
        artifacts,
        repository,
        args.codex,
        source_codex_home,
    )
    results = []
    for case, arm, repetition in schedule:
        results.append(
            run_one(
                repository=repository,
                plugin_relative=plugin_relative,
                commit=commit,
                case=case,
                arm=arm,
                repetition=repetition,
                artifacts=artifacts,
                codex=args.codex,
                schema=args.schema.resolve(),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                codex_home=codex_homes[arm],
            )
        )
    passed = sum(result["success"] for result in results)
    payload = {
        "schema_version": 1,
        "benchmark": manifest["benchmark"],
        "status": "passed" if passed == len(results) else "failed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "codex_version": subprocess.run(
            [args.codex, "--version"], capture_output=True, text=True, timeout=10
        ).stdout.strip(),
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "repetitions": args.repetitions,
        "repetition_start": args.repetition_start,
        "run_count": len(results),
        "passed_count": passed,
        "artifacts": str(artifacts),
        "isolation": isolation,
        "results": results,
    }
    output = artifacts / "calibration-summary.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
