#!/usr/bin/env python3
"""Budgeted, progressive source reader with no runtime dependencies."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


TOKEN_METHOD = "chars_div_4_v1"
DEFAULT_BUDGET = 1200
MAX_FILE_BYTES = 2_000_000
CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Region:
    name: str
    kind: str
    start_line: int
    end_line: int
    signature: str
    content: str
    score: int = 0


def estimate_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def signature_from_content(content: str) -> str:
    pieces: list[str] = []
    depth = 0
    for line in content.splitlines()[:20]:
        pieces.append(line.strip())
        for char in line:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            elif char == ":" and depth == 0:
                return " ".join(piece for piece in pieces if piece)
    return " ".join(piece for piece in pieces if piece)


def query_terms(query: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+", query)]


def header_for_node(lines: list[str], node: ast.AST) -> str:
    start = max(0, int(getattr(node, "lineno", 1)) - 1)
    pieces: list[str] = []
    depth = 0
    for line in lines[start : min(len(lines), start + 20)]:
        pieces.append(line.strip())
        for char in line:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            elif char == ":" and depth == 0:
                return " ".join(piece for piece in pieces if piece)
    return " ".join(piece for piece in pieces if piece)


def python_regions(text: str) -> tuple[list[Region], str]:
    tree = ast.parse(text)
    lines = text.splitlines()
    regions: list[Region] = []

    def visit(nodes: Iterable[ast.stmt], prefix: str = "") -> None:
        for node in nodes:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            name = f"{prefix}.{node.name}" if prefix else node.name
            start = int(node.lineno)
            end = int(getattr(node, "end_lineno", node.lineno))
            content = "\n".join(lines[start - 1 : end])
            regions.append(
                Region(
                    name=name,
                    kind=kind,
                    start_line=start,
                    end_line=end,
                    signature=header_for_node(lines, node),
                    content=content,
                )
            )
            if isinstance(node, ast.ClassDef):
                visit(node.body, name)

    visit(tree.body)
    return regions, "ast"


GENERIC_SYMBOL = re.compile(
    r"^\s*(?:(?:export|public|private|protected|static|async)\s+)*"
    r"(?P<kind>class|interface|def|function|fn|func)\s+"
    r"(?P<name>[A-Za-z_$][A-Za-z0-9_.$]*)"
)


def generic_regions(text: str) -> tuple[list[Region], str]:
    lines = text.splitlines()
    starts: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines, start=1):
        match = GENERIC_SYMBOL.match(line)
        if match:
            starts.append((index, match.group("name"), match.group("kind")))
    regions: list[Region] = []
    for position, (start, name, kind) in enumerate(starts):
        end = starts[position + 1][0] - 1 if position + 1 < len(starts) else len(lines)
        regions.append(Region(name, kind, start, end, lines[start - 1].strip(), "\n".join(lines[start - 1 : end])))
    return regions, "pattern"


def extract_regions(path: Path, text: str) -> tuple[list[Region], str]:
    if path.suffix.lower() == ".py":
        try:
            return python_regions(text)
        except SyntaxError:
            pass
    return generic_regions(text)


def cache_directory_from_environment() -> Path | None:
    configured = os.environ.get("AGENT_TOKEN_MANAGER_DATA") or os.environ.get("PLUGIN_DATA")
    if configured:
        return Path(configured).expanduser() / "parse-cache"
    return Path(tempfile.gettempdir()) / "agent-token-manager-parse-cache"


def restore_cached_regions(value: Any, text: str) -> tuple[list[Region], str] | None:
    if not isinstance(value, dict) or value.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None
    parser = value.get("parser")
    entries = value.get("regions")
    if not isinstance(parser, str) or not isinstance(entries, list):
        return None
    lines = text.splitlines()
    regions: list[Region] = []
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        try:
            name = str(entry["name"])
            kind = str(entry["kind"])
            start = int(entry["start_line"])
            end = int(entry["end_line"])
        except (KeyError, TypeError, ValueError):
            return None
        if start < 1 or end < start or end > len(lines):
            return None
        content = "\n".join(lines[start - 1 : end])
        regions.append(Region(name, kind, start, end, signature_from_content(content), content))
    return regions, parser


def write_region_cache(cache_file: Path, digest: str, parser: str, regions: list[Region]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(cache_file.parent, 0o700)
    value = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "content_sha256": digest,
        "parser": parser,
        "regions": [
            {
                "name": region.name,
                "kind": region.kind,
                "start_line": region.start_line,
                "end_line": region.end_line,
            }
            for region in regions
        ],
    }
    encoded = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor = os.open(cache_file, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, encoded)
    finally:
        os.close(descriptor)


def extract_regions_cached(path: Path, text: str, cache_dir: Path | None) -> tuple[list[Region], str, str]:
    if cache_dir is None:
        regions, parser = extract_regions(path, text)
        return regions, parser, "disabled"
    digest = source_hash(text)
    cache_file = cache_dir.expanduser() / f"{digest}.regions-v{CACHE_SCHEMA_VERSION}.json"
    try:
        if cache_file.is_file():
            restored = restore_cached_regions(json.loads(cache_file.read_text(encoding="utf-8")), text)
            if restored is not None:
                regions, parser = restored
                return regions, parser, "hit"
    except (OSError, json.JSONDecodeError):
        pass
    regions, parser = extract_regions(path, text)
    try:
        write_region_cache(cache_file, digest, parser, regions)
        return regions, parser, "miss"
    except OSError:
        return regions, parser, "write_failed"


def score_region(region: Region, terms: list[str]) -> Region:
    if not terms:
        return region
    name = region.name.lower()
    haystack = f"{region.signature}\n{region.content}".lower()
    score = 0
    for term in terms:
        if term == name or name.endswith(f".{term}"):
            score += 100
        elif term in name:
            score += 50
        score += min(haystack.count(term), 5) * 4
    return Region(**{**region.__dict__, "score": score})


def outline(regions: list[Region]) -> str:
    return "\n".join(
        f"{region.kind} {region.name} (lines {region.start_line}-{region.end_line}): {region.signature}"
        for region in regions
    )


def truncate_lines(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    if max_chars <= 32:
        return "", True
    kept: list[str] = []
    used = 0
    marker = "\n… omitted by token budget …"
    for line in text.splitlines(keepends=True):
        if used + len(line) + len(marker) > max_chars:
            break
        kept.append(line)
        used += len(line)
    return "".join(kept).rstrip() + marker, True


def fit_payload(payload: dict[str, Any], budget_tokens: int) -> dict[str, Any]:
    limit = budget_tokens * 4
    payload["estimated_output_tokens"] = 0
    payload["token_count_method"] = TOKEN_METHOD
    for _ in range(8):
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        estimate = estimate_tokens(serialized)
        payload["estimated_output_tokens"] = estimate
        if len(serialized) <= limit:
            return payload
        overflow = len(serialized) - limit + 16
        regions = payload.get("regions", [])
        target = next((region for region in reversed(regions) if region.get("content")), None)
        if target is None:
            payload["budget_exceeded_by_metadata"] = True
            return payload
        content = str(target["content"])
        target["content"], was_truncated = truncate_lines(content, max(0, len(content) - overflow))
        target["truncated"] = bool(target.get("truncated")) or was_truncated
        payload["truncated"] = True
        if not target["content"] and len(regions) > 1:
            regions.remove(target)
            payload["omitted_region_count"] = int(payload.get("omitted_region_count", 0)) + 1
    return payload


def smart_read(
    path: Path,
    query: str,
    budget_tokens: int,
    mode: str,
    symbols: list[str] | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Not a regular file: {resolved}")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds {MAX_FILE_BYTES} bytes: {resolved}")
    raw = resolved.read_bytes()
    if b"\x00" in raw:
        raise ValueError(f"Binary file is not supported: {resolved}")
    text = raw.decode("utf-8", errors="replace")
    regions, parser, cache_status = extract_regions_cached(resolved, text, cache_dir)
    scored = sorted((score_region(region, query_terms(query)) for region in regions), key=lambda item: (-item.score, item.start_line))

    requested_symbols = symbols or []
    selected_mode = "symbol" if requested_symbols else mode
    if mode == "auto" and not requested_symbols:
        selected_mode = "symbol" if query and scored and scored[0].score > 0 else "outline"

    selected: list[Region]
    if requested_symbols:
        selected = []
        for requested in requested_symbols:
            exact = next((region for region in regions if region.name == requested), None)
            suffix_matches = [region for region in regions if region.name.endswith(f".{requested}")]
            match = exact or (suffix_matches[0] if len(suffix_matches) == 1 else None)
            if match and match.name not in {region.name for region in selected}:
                selected.append(match)
        if not selected:
            raise ValueError(f"No exact symbols found: {', '.join(requested_symbols)}")
    elif selected_mode == "full":
        selected = [Region(resolved.name, "file", 1, max(1, len(text.splitlines())), resolved.name, text)]
    elif selected_mode == "symbol":
        selected = [region for region in scored if region.score > 0][:3]
        if not selected:
            selected_mode = "outline"
            selected = []
    else:
        selected = []

    if selected_mode == "outline":
        outline_text = outline(regions) or "No class/function symbols detected."
        selected = [Region(resolved.name, "outline", 1, max(1, len(text.splitlines())), resolved.name, outline_text)]

    selected_names = {region.name for region in selected}
    payload: dict[str, Any] = {
        "schema_version": 1,
        "path": str(resolved),
        "content_sha256": source_hash(text),
        "mode": selected_mode,
        "parser": parser,
        "confidence": "high" if parser == "ast" else "medium",
        "cache_status": cache_status,
        "budget_tokens": budget_tokens,
        "query": query,
        "requested_symbols": requested_symbols,
        "region_count": len(regions),
        "omitted_region_count": sum(1 for region in regions if region.name not in selected_names),
        "truncated": False,
        "regions": [
            {
                "name": region.name,
                "kind": region.kind,
                "lines": f"{region.start_line}-{region.end_line}",
                "score": region.score,
                "content": region.content,
                "truncated": False,
            }
            for region in selected
        ],
    }
    return fit_payload(payload, budget_tokens)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--query", default="")
    parser.add_argument("--symbol", action="append", default=[], help="Return an exact symbol; repeat for multiple symbols")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Persist structure-only parse cache")
    parser.add_argument("--no-cache", action="store_true", help="Disable environment-provided parse cache")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--mode", choices=("auto", "outline", "symbol", "full"), default="auto")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if args.budget < 128:
        parser.error("--budget must be at least 128 tokens")
    try:
        cache_dir = None if args.no_cache else (args.cache_dir or cache_directory_from_environment())
        result = smart_read(args.path, args.query, args.budget, args.mode, args.symbol, cache_dir)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
