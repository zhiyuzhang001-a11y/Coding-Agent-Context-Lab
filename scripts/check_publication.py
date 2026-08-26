#!/usr/bin/env python3
"""Fail when the public tree contains common local-path or credential leaks."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", ".pytest_cache", "__pycache__", ".agent-token-manager"}
FORBIDDEN_NAMES = {".DS_Store"}
FORBIDDEN_SUFFIXES = {".pyc", ".sqlite", ".sqlite3"}
TEXT_SUFFIXES = {".cff", ".json", ".md", ".py", ".txt", ".yml", ".yaml"}

PATTERNS = {
    "personal_home_path": re.compile(r"/(?:Users|home)/(?!user(?:name)?(?:/|\b)|<)[A-Za-z0-9._-]+/"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
}


def tracked_candidates() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if not any(part in IGNORED_PARTS for part in path.relative_to(ROOT).parts)
    )


def main() -> int:
    failures: list[str] = []
    for path in tracked_candidates():
        relative = path.relative_to(ROOT)
        if path.is_symlink():
            if not path.exists():
                failures.append(f"broken_symlink:{relative}")
            continue
        if not path.is_file():
            continue
        if path.name in FORBIDDEN_NAMES or path.suffix in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden_artifact:{relative}")
            continue
        if path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                failures.append(f"invalid_json:{relative}:{exc}")
                continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label}:{relative}")

    if failures:
        print("publication check failed", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("publication check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
