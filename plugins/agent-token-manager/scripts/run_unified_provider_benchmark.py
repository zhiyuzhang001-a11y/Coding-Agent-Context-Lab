#!/usr/bin/env python3
"""Produce one honest report for built-in, Serena, and Codebase-Memory providers."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from run_m2c_benchmark import run_benchmark


def git_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def serena_python(executable: str) -> str:
    first_line = Path(executable).read_text(encoding="utf-8").splitlines()[0]
    if not first_line.startswith("#!"):
        raise ValueError("Serena executable has no Python shebang")
    return first_line[2:]


def run_serena(root: Path, budget: int) -> dict:
    executable = shutil.which("serena")
    if not executable:
        return {"status": "skipped", "reason": "serena executable not installed"}
    script = Path(__file__).with_name("run_serena_provider_probe.py")
    try:
        result = subprocess.run(
            [serena_python(executable), str(script), str(root), "--budget", str(budget)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=180,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        payload["process_returncode"] = result.returncode
        return payload
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return {"status": "failed", "reason": exc.__class__.__name__}


def run_codebase_memory(root: Path) -> dict:
    executable = shutil.which("codebase-memory-mcp")
    if not executable:
        return {
            "status": "skipped",
            "reason": "codebase-memory-mcp executable not installed",
            "degraded_without_blocking_builtin": True,
        }
    return {
        "status": "skipped",
        "reason": "executable discovered but unified query adapter is not implemented",
        "degraded_without_blocking_builtin": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--budget", type=int, default=1200)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    builtin = run_benchmark(root)
    providers = {
        "builtin_python_ast": {
            "status": builtin["status"],
            "capability": "natural_language_navigation",
            "natural_language_routing": True,
            "report": builtin,
        },
        "serena": run_serena(root, args.budget),
        "codebase_memory": run_codebase_memory(root),
    }
    passed = builtin["status"] == "passed" and providers["serena"].get("status") == "completed"
    payload = {
        "schema_version": 1,
        "benchmark": "m2c-unified-provider-report",
        "status": "passed" if passed else "failed",
        "repository": str(root),
        "commit": git_commit(root),
        "shared_case_count": builtin["case_count"],
        "shared_budget_tokens": args.budget,
        "correctness_rule": "expected target evidence returned within budget; navigation quality compared only where natural-language routing exists",
        "providers": providers,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
