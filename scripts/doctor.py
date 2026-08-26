#!/usr/bin/env python3
"""Check the minimum local environment required by Agent Token Manager."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from workspace_data import DATA_DIR_NAME, discover_git_root, initialize_store


def check(name: str, status: str, detail: str, required: bool) -> dict[str, Any]:
    return {"name": name, "status": status, "required": required, "detail": detail}


def is_ignored(root: Path, relative: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", f"{relative.rstrip('/')}/metadata.json"],
        cwd=str(root),
        capture_output=True,
        timeout=5,
    )
    return result.returncode == 0


def run_doctor(root: Path, data_dir: Optional[Path] = None, plugin_root: Optional[Path] = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    python_ok = sys.version_info >= (3, 9)
    checks.append(check("python", "ok" if python_ok else "error", sys.version.split()[0], True))

    git_path = shutil.which("git")
    checks.append(check("git", "ok" if git_path else "error", git_path or "not found", True))
    git_root = discover_git_root(root) if git_path else None
    checks.append(
        check(
            "git_root",
            "ok" if git_root else "warn",
            str(git_root or "not found; using the requested directory identity"),
            False,
        )
    )

    store = None
    navigation_root = git_root or root.expanduser().resolve()
    if navigation_root.is_dir():
        try:
            store = initialize_store(navigation_root, data_dir)
            writable = os.access(store.data_dir, os.W_OK)
            checks.append(check("data_store", "ok" if writable else "error", str(store.database), True))
            default_store = data_dir is None and not (
                os.environ.get("AGENT_TOKEN_MANAGER_DATA") or os.environ.get("PLUGIN_DATA")
            )
            if default_store and git_root:
                ignored = is_ignored(git_root, DATA_DIR_NAME)
                checks.append(
                    check("data_ignored", "ok" if ignored else "error", f"{DATA_DIR_NAME}/", True)
                )
        except Exception as exc:  # doctor must report rather than crash
            checks.append(check("data_store", "error", str(exc), True))

    for command in ("serena", "codebase-memory-mcp", "repomix"):
        location = shutil.which(command)
        checks.append(check(command, "ok" if location else "warn", location or "optional; not found", False))

    plugin = (plugin_root or Path(__file__).resolve().parent.parent).resolve()
    mcp_config = plugin / ".mcp.json"
    if mcp_config.exists():
        raw = mcp_config.read_text(encoding="utf-8")
        home = str(Path.home())
        portable = home not in raw
        checks.append(
            check(
                "mcp_portability",
                "ok" if portable else "warn",
                "no home-directory paths" if portable else "contains machine-specific absolute paths",
                False,
            )
        )

    errors = sum(item["status"] == "error" for item in checks)
    warnings = sum(item["status"] == "warn" for item in checks)
    return {
        "status": "ok" if errors == 0 else "error",
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "workspace": store.to_dict() if store else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--plugin-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_doctor(args.root, args.data_dir, args.plugin_root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["checks"]:
            print(f"[{item['status'].upper():5}] {item['name']}: {item['detail']}")
        print(f"status={result['status']} errors={result['errors']} warnings={result['warnings']}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
