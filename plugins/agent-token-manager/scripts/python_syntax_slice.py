#!/usr/bin/env python3
"""Build complete, budgeted Python syntax slices without persisting source."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@dataclass(frozen=True)
class Definition:
    node: ast.AST
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    enclosing_class: ast.ClassDef | None = None


@dataclass(frozen=True)
class SliceResult:
    replacement: str | None
    reason: str
    metadata: dict[str, object]


def node_start(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", ())
    return min([getattr(node, "lineno", 1), *(getattr(item, "lineno", 1) for item in decorators)])


def node_kind(node: ast.AST, enclosing_class: ast.ClassDef | None) -> str:
    if isinstance(node, ast.ClassDef):
        return "class"
    prefix = "async_" if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}method" if enclosing_class is not None else f"{prefix}function"


def definitions(tree: ast.Module) -> list[Definition]:
    result: list[Definition] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.append(
                Definition(
                    node=node,
                    name=node.name,
                    qualified_name=node.name,
                    kind=node_kind(node, None),
                    start_line=node_start(node),
                    end_line=node.end_lineno or node.lineno,
                )
            )
        elif isinstance(node, ast.ClassDef):
            result.append(
                Definition(
                    node=node,
                    name=node.name,
                    qualified_name=node.name,
                    kind="class",
                    start_line=node_start(node),
                    end_line=node.end_lineno or node.lineno,
                )
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result.append(
                        Definition(
                            node=child,
                            name=child.name,
                            qualified_name=f"{node.name}.{child.name}",
                            kind=node_kind(child, node),
                            start_line=node_start(child),
                            end_line=child.end_lineno or child.lineno,
                            enclosing_class=node,
                        )
                    )
    return result


def resolve_symbol(items: list[Definition], symbol: str) -> tuple[Definition | None, str]:
    normalized = symbol.strip()
    if not normalized:
        return None, "syntax_missing_symbol"
    if "." in normalized:
        matches = [item for item in items if item.qualified_name == normalized]
    else:
        matches = [item for item in items if item.name == normalized]
    if not matches:
        return None, "syntax_symbol_not_found"
    if len(matches) != 1:
        return None, "syntax_symbol_ambiguous"
    return matches[0], "syntax_explicit_symbol"


def intersects(item: Definition, start_line: int, end_line: int) -> bool:
    return item.start_line <= end_line and start_line <= item.end_line


def resolve_range(
    items: list[Definition], start_line: int, end_line: int
) -> tuple[Definition | None, str]:
    # Functions/methods are more specific than their enclosing class. A range that
    # crosses sibling functions is deliberately ambiguous rather than guessed.
    functions = [item for item in items if item.kind != "class" and intersects(item, start_line, end_line)]
    if len(functions) == 1:
        return functions[0], "syntax_unique_range"
    if len(functions) > 1:
        return None, "syntax_range_ambiguous"
    classes = [item for item in items if item.kind == "class" and intersects(item, start_line, end_line)]
    if len(classes) == 1:
        return classes[0], "syntax_unique_range"
    return None, "syntax_range_ambiguous" if classes else "syntax_range_not_found"


def source_segment(lines: list[str], start_line: int, end_line: int) -> str:
    return "".join(lines[start_line - 1 : end_line]).rstrip("\n")


def class_header_span(node: ast.ClassDef) -> tuple[int, int]:
    start = node_start(node)
    first_body_line = min((node_start(child) for child in node.body), default=(node.end_lineno or node.lineno) + 1)
    return start, max(node.lineno, first_body_line - 1)


def names_in(nodes: Iterable[ast.AST | None]) -> set[str]:
    names: set[str] = set()
    for node in nodes:
        if node is None:
            continue
        names.update(item.id for item in ast.walk(node) if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load))
    return names


def signature_nodes(node: ast.AST) -> list[ast.AST | None]:
    selected: list[ast.AST | None] = list(getattr(node, "decorator_list", ()))
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        arguments = node.args
        selected.extend(argument.annotation for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs])
        if arguments.vararg:
            selected.append(arguments.vararg.annotation)
        if arguments.kwarg:
            selected.append(arguments.kwarg.annotation)
        selected.extend(arguments.defaults)
        selected.extend(arguments.kw_defaults)
        selected.append(node.returns)
        selected.extend(getattr(node, "type_params", ()))
    elif isinstance(node, ast.ClassDef):
        selected.extend(node.bases)
        selected.extend(keyword.value for keyword in node.keywords)
        selected.extend(getattr(node, "type_params", ()))
    return selected


def import_bindings(node: ast.Import | ast.ImportFrom) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.asname or alias.name.split(".", 1)[0] for alias in node.names}
    return {alias.asname or alias.name for alias in node.names if alias.name != "*"}


def support_imports(
    tree: ast.Module, target: Definition, lines: list[str]
) -> tuple[list[tuple[int, int, str]], set[str]]:
    support_nodes = signature_nodes(target.node)
    if target.enclosing_class is not None:
        support_nodes.extend(signature_nodes(target.enclosing_class))
    needed = names_in(support_nodes)
    selected: list[tuple[int, int, str]] = []
    bound: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        bindings = import_bindings(node)
        is_future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
        if is_future or bindings & needed:
            end = node.end_lineno or node.lineno
            selected.append((node.lineno, end, source_segment(lines, node.lineno, end)))
            bound.update(bindings)
    return selected, needed - bound


def merged_line_count(spans: list[tuple[int, int]]) -> int:
    if not spans:
        return 0
    total = 0
    current_start, current_end = sorted(spans)[0]
    for start, end in sorted(spans)[1:]:
        if start <= current_end + 1:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start + 1
            current_start, current_end = start, end
    return total + current_end - current_start + 1


def build_slice(
    path: Path,
    *,
    symbol: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    budget_chars: int = 4000,
) -> SliceResult:
    metadata: dict[str, object] = {"optimizer_strategy": "python_syntax_slice"}
    try:
        if path.suffix != ".py":
            return SliceResult(None, "syntax_not_python", metadata)
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
    except (OSError, UnicodeError):
        return SliceResult(None, "syntax_source_unavailable", metadata)
    except SyntaxError:
        return SliceResult(None, "syntax_parse_error", metadata)

    lines = text.splitlines(keepends=True)
    items = definitions(tree)
    if symbol is not None:
        target, reason = resolve_symbol(items, symbol)
    elif start_line is not None and end_line is not None:
        target, reason = resolve_range(items, start_line, end_line)
    else:
        return SliceResult(None, "syntax_missing_target", metadata)
    if target is None:
        return SliceResult(None, reason, metadata)

    imports, unresolved = support_imports(tree, target, lines)
    spans = [(start, end) for start, end, _ in imports]
    body = source_segment(lines, target.start_line, target.end_line)
    enclosing_header = ""
    class_header_lines: tuple[int, int] | None = None
    if target.enclosing_class is not None:
        class_header_lines = class_header_span(target.enclosing_class)
        enclosing_header = source_segment(lines, *class_header_lines)
        spans.append(class_header_lines)
    spans.append((target.start_line, target.end_line))

    import_text = "\n".join(item[2] for item in imports)
    code_parts = [part for part in (import_text, enclosing_header, body) if part]
    code = "\n\n".join(code_parts)
    represented = merged_line_count(spans)
    omitted_lines = max(0, len(lines) - represented)
    file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    support = ", ".join(sorted(unresolved)) or "none"
    enclosing = target.enclosing_class.name if target.enclosing_class is not None else "none"
    package = (
        "[Smart Read CO-1 syntax slice]\n"
        f"path: {path}\n"
        f"symbol: {target.qualified_name}\n"
        f"kind: {target.kind}\n"
        f"lines: {target.start_line}-{target.end_line}\n"
        f"enclosing_class: {enclosing}\n"
        f"complete_syntax_unit: true\n"
        f"file_sha256: {file_hash}\n"
        f"omitted_lines: {omitted_lines}\n"
        f"support_names_not_included: {support}\n"
        "continuation: use an explicit symbol or a non-ambiguous line range for more context\n"
        "source:\n"
        f"{code}\n"
        "[CO-1 syntax slice ended]"
    )
    metadata.update(
        {
            "syntax_symbol": target.qualified_name,
            "syntax_kind": target.kind,
            "syntax_start_line": target.start_line,
            "syntax_end_line": target.end_line,
            "syntax_enclosing_class": target.enclosing_class.name if target.enclosing_class else None,
            "syntax_file_sha256": file_hash,
            "syntax_omitted_lines": omitted_lines,
            "syntax_required_chars": len(package),
            "syntax_support_name_count": len(unresolved),
        }
    )
    if len(package) > budget_chars:
        return SliceResult(None, "syntax_slice_over_budget", metadata)
    return SliceResult(package, reason, metadata)
