#!/usr/bin/env python3
"""Python AST provider for the sparse navigation map."""

from __future__ import annotations

import ast
import json
import math
import re
import subprocess
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Optional

from navigation_contract import Edge, Marker, ProviderResult, QueryRequest, marker_id
from navigation_store import NavigationStore
from workspace_data import WorkspaceStore, initialize_store


PROVIDER_NAME = "python-ast"
INDEXER_VERSION = 2
IGNORED_DIRECTORY_NAMES = {
    ".agent-token-manager",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]+")
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
GENERIC_CODE_TOKENS = {
    "active",
    "apply",
    "code",
    "file",
    "get",
    "project",
    "set",
    "symbol",
    "tool",
    "tools",
}


def estimate_tokens(value: Any) -> int:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (len(text) + 3) // 4


def tokenize(value: str) -> set[str]:
    expanded = (
        CAMEL_BOUNDARY.sub(" ", value)
        .replace("/", " ")
        .replace(".", " ")
        .replace("-", " ")
        .replace("_", " ")
    )
    return {token.lower() for token in TOKEN_PATTERN.findall(expanded) if len(token) > 1}


def module_name(path: str, root: Path) -> str:
    relative = Path(path)
    package_parts: list[str] = []
    parent = (root / relative).parent
    while parent != root and (parent / "__init__.py").is_file():
        package_parts.insert(0, parent.name)
        parent = parent.parent
    if relative.name != "__init__.py":
        package_parts.append(relative.stem)
    return ".".join(package_parts) or root.name.replace("-", "_")


def discover_python_files(root: Path) -> list[Path]:
    root = root.resolve()
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=str(root),
            check=True,
            capture_output=True,
            timeout=20,
        )
        values = [value for value in result.stdout.decode("utf-8", errors="surrogateescape").split("\0") if value]
        files = []
        for value in values:
            candidate = (root / value).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if candidate.suffix == ".py" and candidate.is_file():
                files.append(candidate)
        return sorted(set(files))
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return sorted(
            path
            for path in root.rglob("*.py")
            if path.is_file() and not any(part in IGNORED_DIRECTORY_NAMES for part in path.relative_to(root).parts)
        )


def node_signature(node: ast.AST, qualified_name: str) -> str:
    short_name = qualified_name.rsplit(".", 1)[-1]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        try:
            arguments = ast.unparse(node.args)
        except Exception:
            arguments = "..."
        returns = ""
        if node.returns is not None:
            try:
                returns = f" -> {ast.unparse(node.returns)}"
            except Exception:
                returns = ""
        return f"{prefix} {short_name}({arguments}){returns}"
    if isinstance(node, ast.ClassDef):
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                continue
        return f"class {short_name}" + (f"({', '.join(bases)})" if bases else "")
    return short_name


def imported_names(tree: ast.AST, current_module: str, is_package: bool) -> list[str]:
    results: set[str] = set()
    current_parts = current_module.split(".") if current_module else []
    package_parts = current_parts if is_package else current_parts[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            results.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = max(0, len(package_parts) - (node.level - 1))
                base_parts = package_parts[:keep]
            else:
                base_parts = []
            if node.module:
                base_parts.extend(node.module.split("."))
            base = ".".join(base_parts)
            if base:
                results.add(base)
            for alias in node.names:
                if alias.name != "*":
                    candidate = ".".join([part for part in (base, alias.name) if part])
                    if candidate:
                        results.add(candidate)
    return sorted(results)


def expression_name(node: Optional[ast.AST]) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = expression_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Subscript):
        return expression_name(node.value)
    return None


def _import_base(current_module: str, is_package: bool, level: int, module: Optional[str]) -> str:
    current_parts = current_module.split(".") if current_module else []
    package_parts = current_parts if is_package else current_parts[:-1]
    if level:
        keep = max(0, len(package_parts) - (level - 1))
        parts = package_parts[:keep]
    else:
        parts = []
    if module:
        parts.extend(module.split("."))
    return ".".join(parts)


def import_aliases(
    tree: ast.Module, current_module: str, is_package: bool
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    aliases: dict[str, str] = {}
    references: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                aliases[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(current_module, is_package, node.level, node.module)
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                target = ".".join(part for part in (base, alias.name) if part)
                aliases[local] = target
                references.append(
                    {
                        "source_symbol": current_module,
                        "kind": "references",
                        "target_name": target,
                        "line": int(node.lineno),
                        "confidence": 0.95,
                        "reference_kind": "symbol_import",
                    }
                )
    return aliases, references


def referenced_names(node: Optional[ast.AST]) -> list[str]:
    if node is None:
        return []
    results: set[str] = set()
    attribute_parts: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute):
            name = expression_name(child)
            if name:
                results.add(name)
                attribute_parts.update(name.split("."))
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id not in attribute_parts:
            results.add(child.id)
    return sorted(results)


class _ScopeRelationVisitor(ast.NodeVisitor):
    def __init__(self, source_symbol: str, source_class: Optional[str]):
        self.source_symbol = source_symbol
        self.source_class = source_class
        self.facts: list[dict[str, Any]] = []

    def _fact(
        self,
        kind: str,
        target_name: str,
        line: int,
        confidence: float,
        reference_kind: str = "",
    ) -> None:
        if target_name:
            self.facts.append(
                {
                    "source_symbol": self.source_symbol,
                    "kind": kind,
                    "target_name": target_name,
                    "line": line,
                    "confidence": confidence,
                    "reference_kind": reference_kind,
                }
            )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        for name in referenced_names(node.annotation):
            self._fact("references", name, int(node.lineno), 0.85, "type_annotation")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = expression_name(node.func)
        if target:
            if self.source_class and target.startswith(("self.", "cls.")):
                target = f"{self.source_class}.{target.split('.', 1)[1]}"
                confidence = 0.98
            elif "." not in target:
                confidence = 0.9
            else:
                confidence = 0.75
            self._fact("calls", target, int(node.lineno), confidence)
        call_name = (target or "").rsplit(".", 1)[-1].lower()
        if call_name in {"issubclass", "isinstance"} or call_name.startswith(("register", "add_")):
            reference_kind = "runtime_type_check" if call_name in {"issubclass", "isinstance"} else "registration"
            for argument in [*node.args, *[keyword.value for keyword in node.keywords]]:
                name = expression_name(argument)
                if name:
                    self._fact("references", name, int(node.lineno), 0.85, reference_kind)
        self.generic_visit(node)


def base_value(kind: str, symbol: str, top_level: bool) -> float:
    value = {"file": 1.0, "module": 1.5, "class": 3.0, "function": 2.0, "method": 1.5}.get(kind, 1.0)
    short = symbol.rsplit(".", 1)[-1]
    if not short.startswith("_"):
        value += 1.0
    elif short.startswith("__") and short.endswith("__"):
        value -= 0.5
    if top_level:
        value += 0.5
    return max(0.1, value)


def edge_degree_weight(edge: Edge) -> float:
    """Bound hub influence so adding noisy facts cannot erase task relevance."""
    return {
        "contains": 1.0,
        "imports": 0.5,
        "inherits": 0.5,
        "calls": 0.75,
        "references": 0.25,
    }.get(edge.kind, 0.25) * edge.confidence


class _MarkerBuilder:
    def __init__(self, workspace: WorkspaceStore, path: str, text: str, digest: str):
        self.workspace = workspace
        self.path = path
        self.lines = text.splitlines()
        self.digest = digest
        self.markers: list[Marker] = []
        self.edges: list[Edge] = []
        self.relation_facts: list[dict[str, Any]] = []
        self.module = module_name(path, workspace.root)
        self.file_marker = self._marker(path, "file", 1, max(1, len(self.lines)), f"python file {path}", True)
        self.module_marker = self._marker(
            self.module,
            "module",
            1,
            max(1, len(self.lines)),
            f"module {self.module}",
            True,
        )
        self.edges.append(self._edge(self.file_marker.id, self.module_marker.id, "contains", 1))

    def _marker(
        self,
        symbol: str,
        kind: str,
        start: int,
        end: int,
        signature: str,
        top_level: bool,
    ) -> Marker:
        content_chars = sum(len(line) + 1 for line in self.lines[start - 1 : end])
        marker = Marker(
            repo_id=self.workspace.repo_id,
            path=self.path,
            symbol=symbol,
            kind=kind,
            start_line=start,
            end_line=end,
            signature=signature,
            evidence_hash=sha256(f"{self.digest}:{start}:{end}".encode("utf-8")).hexdigest(),
            confidence=1.0,
            base_value=base_value(kind, symbol, top_level),
            expansion_tokens=(content_chars + 3) // 4,
            provider=PROVIDER_NAME,
            metadata={"public": not symbol.rsplit(".", 1)[-1].startswith("_"), "top_level": top_level},
        )
        self.markers.append(marker)
        return marker

    def _edge(self, source: str, target: str, kind: str, line: int) -> Edge:
        return Edge(
            repo_id=self.workspace.repo_id,
            source_id=source,
            target_id=target,
            kind=kind,
            evidence_hash=sha256(f"{self.digest}:{line}:{kind}".encode("utf-8")).hexdigest(),
            confidence=1.0,
            provider=PROVIDER_NAME,
            metadata={"path": self.path, "line": line},
        )

    def build(self, tree: ast.Module) -> tuple[list[Marker], list[Edge]]:
        def add_reference_facts(
            source_symbol: str,
            nodes: Iterable[Optional[ast.AST]],
            line: int,
            reference_kind: str,
            confidence: float,
        ) -> None:
            for reference_node in nodes:
                for name in referenced_names(reference_node):
                    self.relation_facts.append(
                        {
                            "source_symbol": source_symbol,
                            "kind": "references",
                            "target_name": name,
                            "line": line,
                            "confidence": confidence,
                            "reference_kind": reference_kind,
                        }
                    )

        def definition_facts(node: ast.AST, marker: Marker, parent: Marker) -> None:
            decorators = getattr(node, "decorator_list", [])
            decorator_nodes = [item.func if isinstance(item, ast.Call) else item for item in decorators]
            add_reference_facts(
                marker.symbol,
                decorator_nodes,
                marker.start_line,
                "decorator",
                0.9,
            )
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    name = expression_name(base)
                    if name:
                        self.relation_facts.append(
                            {
                                "source_symbol": marker.symbol,
                                "kind": "inherits",
                                "target_name": name,
                                "line": int(node.lineno),
                                "confidence": 1.0,
                                "reference_kind": "base_class",
                            }
                        )
                for statement in node.body:
                    if isinstance(statement, ast.AnnAssign):
                        add_reference_facts(
                            marker.symbol,
                            [statement.annotation],
                            int(statement.lineno),
                            "type_annotation",
                            0.85,
                        )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                annotation_nodes: list[Optional[ast.AST]] = [argument.annotation for argument in arguments]
                annotation_nodes.extend(
                    [
                        node.args.vararg.annotation if node.args.vararg else None,
                        node.args.kwarg.annotation if node.args.kwarg else None,
                        node.returns,
                    ]
                )
                add_reference_facts(
                    marker.symbol,
                    annotation_nodes,
                    int(node.lineno),
                    "type_annotation",
                    0.85,
                )
            source_class = parent.symbol if parent.kind == "class" else None
            visitor = _ScopeRelationVisitor(marker.symbol, source_class)
            for statement in getattr(node, "body", []):
                visitor.visit(statement)
            self.relation_facts.extend(visitor.facts)

        def visit_statements(statements: list[ast.stmt], parent: Marker, prefix: str, top_level: bool) -> None:
            for node in statements:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    qualified = f"{prefix}.{node.name}" if prefix else node.name
                    kind = "class" if isinstance(node, ast.ClassDef) else ("method" if parent.kind == "class" else "function")
                    end = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
                    marker = self._marker(
                        qualified,
                        kind,
                        int(node.lineno),
                        end,
                        node_signature(node, qualified),
                        top_level,
                    )
                    self.edges.append(self._edge(parent.id, marker.id, "contains", int(node.lineno)))
                    definition_facts(node, marker, parent)
                    visit_statements(node.body, marker, qualified, False)

        module_visitor = _ScopeRelationVisitor(self.module_marker.symbol, None)
        for statement in tree.body:
            module_visitor.visit(statement)
        self.relation_facts.extend(module_visitor.facts)
        visit_statements(tree.body, self.module_marker, "", True)
        return self.markers, self.edges


class AstNavigationProvider:
    name = PROVIDER_NAME

    def __init__(self, root: Path, data_dir: Optional[Path] = None):
        self.root = root.expanduser().resolve()
        self.workspace = initialize_store(self.root, data_dir)
        self.store = NavigationStore(self.workspace)
        self.last_index_stats: dict[str, Any] = {}

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _parse_file(self, path: Path) -> tuple[str, list[Marker], list[Edge], dict[str, Any]]:
        raw = path.read_bytes()
        digest = sha256(raw).hexdigest()
        text = raw.decode("utf-8")
        tree = ast.parse(text, filename=str(path))
        relative = self._relative(path)
        builder = _MarkerBuilder(self.workspace, relative, text, digest)
        markers, edges = builder.build(tree)
        imports = imported_names(tree, builder.module, path.name == "__init__.py")
        aliases, import_references = import_aliases(tree, builder.module, path.name == "__init__.py")
        metadata = {
            "module": builder.module,
            "imports": imports,
            "aliases": aliases,
            "relation_facts": [*builder.relation_facts, *import_references],
            "encoding": "utf-8",
            "indexer_version": INDEXER_VERSION,
        }
        return digest, markers, edges, metadata

    @staticmethod
    def _resolve_module(name: str, modules: dict[str, str]) -> Optional[str]:
        parts = name.split(".")
        while parts:
            candidate = ".".join(parts)
            if candidate in modules:
                return candidate
            parts.pop()
        return None

    def _rebuild_import_edges(self) -> list[Edge]:
        states = self.store.file_states(self.name)
        modules = {
            state["metadata"].get("module", ""): path
            for path, state in states.items()
            if state["metadata"].get("module")
        }
        edges: list[Edge] = []
        for path, state in states.items():
            source_module = state["metadata"].get("module")
            if not source_module:
                continue
            source_id = marker_id(self.workspace.repo_id, path, source_module, "module")
            for imported in state["metadata"].get("imports", []):
                target_module = self._resolve_module(imported, modules)
                if not target_module or target_module == source_module:
                    continue
                target_path = modules[target_module]
                target_id = marker_id(self.workspace.repo_id, target_path, target_module, "module")
                edges.append(
                    Edge(
                        repo_id=self.workspace.repo_id,
                        source_id=source_id,
                        target_id=target_id,
                        kind="imports",
                        evidence_hash=sha256(
                            f"{state['content_hash']}:{source_module}:{target_module}".encode("utf-8")
                        ).hexdigest(),
                        confidence=0.9,
                        provider=self.name,
                        metadata={"source_path": path, "imported": imported},
                    )
                )
        unique = {edge.id: edge for edge in edges}
        self.store.replace_relation_edges(self.name, "imports", unique.values())
        return list(unique.values())

    def _rebuild_semantic_edges(self) -> dict[str, Any]:
        states = self.store.file_states(self.name)
        markers = self.store.load_markers(self.name)
        by_path_symbol = {(marker.path, marker.symbol): marker for marker in markers}
        modules = {
            path: state["metadata"].get("module", "")
            for path, state in states.items()
        }
        qualified: dict[str, Marker] = {}
        short_names: dict[str, list[Marker]] = {}
        for marker in markers:
            module = modules.get(marker.path, "")
            if marker.kind == "module":
                qualified[marker.symbol] = marker
            elif marker.kind != "file" and module:
                qualified[f"{module}.{marker.symbol}"] = marker
            short_names.setdefault(marker.symbol.rsplit(".", 1)[-1], []).append(marker)

        def resolve(path: str, raw_name: str, aliases: dict[str, str]) -> tuple[Optional[Marker], float, str]:
            local = by_path_symbol.get((path, raw_name))
            if local:
                return local, 1.0, "same_file"
            parts = raw_name.split(".")
            alias_target = aliases.get(parts[0])
            candidate = ".".join([alias_target, *parts[1:]]) if alias_target else raw_name
            direct = qualified.get(candidate)
            if direct:
                return direct, 0.98 if alias_target else 0.95, "qualified"
            short = candidate.rsplit(".", 1)[-1]
            matches = short_names.get(short, [])
            if len(matches) == 1 and (alias_target or "." not in raw_name):
                return matches[0], 0.8 if alias_target else 0.72, "unique_short_name"
            return None, 0.0, "unresolved"

        resolved: dict[str, list[Edge]] = {kind: [] for kind in ("inherits", "calls", "references")}
        unresolved: Counter[str] = Counter()
        unresolved_relations: list[dict[str, Any]] = []
        for path, state in states.items():
            metadata = state["metadata"]
            aliases = metadata.get("aliases", {})
            for fact in metadata.get("relation_facts", []):
                kind = fact.get("kind")
                if kind not in resolved:
                    continue
                source = by_path_symbol.get((path, fact.get("source_symbol", "")))
                target, resolution_confidence, resolution = resolve(
                    path, fact.get("target_name", ""), aliases
                )
                if source is None or target is None or source.id == target.id:
                    unresolved[kind] += 1
                    if source is not None and fact.get("target_name"):
                        line = int(fact.get("line", 1))
                        evidence_hash = sha256(
                            f"{state['content_hash']}:{source.id}:{fact.get('target_name')}:{kind}:{line}".encode(
                                "utf-8"
                            )
                        ).hexdigest()
                        unresolved_relations.append(
                            {
                                "id": sha256(
                                    f"{self.workspace.repo_id}:{source.id}:{fact.get('target_name')}:{kind}".encode(
                                        "utf-8"
                                    )
                                ).hexdigest()[:24],
                                "path": path,
                                "source_id": source.id,
                                "source_symbol": source.symbol,
                                "target_name": fact.get("target_name"),
                                "kind": kind,
                                "line": line,
                                "evidence_hash": evidence_hash,
                                "confidence": min(0.35, float(fact.get("confidence", 0.5)) * 0.35),
                                "metadata": {
                                    "reference_kind": fact.get("reference_kind", ""),
                                    "resolution": "unresolved_external_or_ambiguous",
                                },
                            }
                        )
                    continue
                line = int(fact.get("line", 1))
                confidence = min(
                    1.0,
                    float(fact.get("confidence", 0.5)) * resolution_confidence,
                )
                edge = Edge(
                    repo_id=self.workspace.repo_id,
                    source_id=source.id,
                    target_id=target.id,
                    kind=kind,
                    evidence_hash=sha256(
                        f"{state['content_hash']}:{source.id}:{target.id}:{kind}:{line}".encode("utf-8")
                    ).hexdigest(),
                    confidence=confidence,
                    provider=self.name,
                    metadata={
                        "source_path": path,
                        "line": line,
                        "target_name": fact.get("target_name"),
                        "reference_kind": fact.get("reference_kind", ""),
                        "resolution": resolution,
                    },
                )
                resolved[kind].append(edge)
        counts: dict[str, int] = {}
        for kind, edges in resolved.items():
            unique = {edge.id: edge for edge in edges}
            counts[f"{kind}_edges"] = self.store.replace_relation_edges(
                self.name, kind, unique.values()
            )
        counts["unresolved_relation_facts"] = sum(unresolved.values())
        counts["unresolved_by_kind"] = dict(unresolved)
        counts["retained_unresolved_relations"] = self.store.replace_unresolved_relations(
            self.name, unresolved_relations
        )
        return counts

    def index(self, root: str = "", changed_paths: Iterable[str] = ()) -> ProviderResult:
        if root and Path(root).expanduser().resolve() != self.root:
            raise ValueError("provider root does not match index root")
        files = discover_python_files(self.root)
        current_paths = {self._relative(path): path for path in files}
        states = self.store.file_states(self.name)
        requested = {Path(path).as_posix() for path in changed_paths}
        deleted = sorted(set(states) - set(current_paths))
        if requested:
            deleted = [path for path in deleted if path in requested]
        removed_markers = self.store.delete_paths(deleted, self.name)
        changed = 0
        unchanged = 0
        failed = 0
        new_markers: list[Marker] = []
        new_edges: list[Edge] = []
        warnings: list[str] = []
        for relative, path in current_paths.items():
            if requested and relative not in requested:
                continue
            digest = sha256(path.read_bytes()).hexdigest()
            prior = states.get(relative, {})
            if (
                prior.get("content_hash") == digest
                and prior.get("metadata", {}).get("indexer_version") == INDEXER_VERSION
            ):
                unchanged += 1
                continue
            try:
                digest, markers, edges, metadata = self._parse_file(path)
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                failed += 1
                self.store.delete_paths([relative], self.name)
                warnings.append(f"{relative}: {exc.__class__.__name__}")
                continue
            self.store.replace_file(relative, digest, self.name, markers, edges, metadata)
            changed += 1
            new_markers.extend(markers)
            new_edges.extend(edges)
        import_edges = self._rebuild_import_edges()
        semantic_counts = self._rebuild_semantic_edges()
        counts = self.store.counts()
        self.last_index_stats = {
            "provider": self.name,
            "discovered_files": len(files),
            "changed_files": changed,
            "unchanged_files": unchanged,
            "deleted_files": len(deleted),
            "failed_files": failed,
            "removed_markers": removed_markers,
            "import_edges": len(import_edges),
            **semantic_counts,
            **counts,
        }
        return ProviderResult(
            provider=self.name,
            markers=tuple(new_markers),
            edges=tuple(new_edges),
            warnings=tuple(warnings),
            estimated_tokens=0,
        )

    def _score(self, marker: Marker, request: QueryRequest, degree: float) -> tuple[float, dict[str, float]]:
        task_tokens = tokenize(request.task)
        symbol_tokens = set().union(*(tokenize(value) for value in request.symbols)) if request.symbols else set()
        path_tokens = set().union(*(tokenize(value) for value in request.paths)) if request.paths else set()
        marker_symbol_tokens = tokenize(marker.symbol)
        marker_path_tokens = tokenize(marker.path)
        signature_tokens = tokenize(marker.signature)
        candidate_tokens = marker_symbol_tokens | marker_path_tokens | signature_tokens
        task_overlap = task_tokens & candidate_tokens
        task_overlap |= {
            candidate
            for candidate in candidate_tokens
            if len(candidate) >= 5
            and any(len(task_token) >= 5 and candidate[:5] == task_token[:5] for task_token in task_tokens)
        }
        exact_symbol = any(value.lower() == marker.symbol.lower() for value in request.symbols)
        partial_symbol = any(
            value.lower() in marker.symbol.lower() or marker.symbol.lower() in value.lower() for value in request.symbols
        )
        exact_path = any(value == marker.path for value in request.paths)
        components = {
            "base": round(marker.base_value, 4),
            "symbol": 8.0 if exact_symbol else (4.0 if partial_symbol else 1.5 * len(symbol_tokens & marker_symbol_tokens)),
            "path": 5.0 if exact_path else 1.0 * len(path_tokens & marker_path_tokens),
            # Rare task words carry more routing information than ubiquitous
            # codebase nouns such as tool/project/file. This compact IDF proxy
            # avoids a repo-specific corpus while preventing generic hubs from
            # beating an exact concept such as "optional".
            "task": round(
                sum(0.5 if token in GENERIC_CODE_TOKENS else 1.5 for token in task_overlap),
                4,
            ),
            "centrality": round(math.log1p(min(20.0, degree)), 4),
            "public": 0.5 if marker.metadata.get("public") else 0.0,
            "test_context": (
                0.5
                if "test" in task_tokens and (marker.path.startswith("tests/") or "/test" in marker.path)
                else (-3.0 if marker.path.startswith("tests/") or "/test" in marker.path else 0.0)
            ),
            "cost_penalty": -round(min(2.0, marker.expansion_tokens / 1000.0), 4),
        }
        return sum(components.values()), components

    def query(self, request: QueryRequest) -> ProviderResult:
        markers = self.store.load_markers(self.name)
        edges = self.store.load_edges(self.name)
        degrees = Counter()
        for edge in edges:
            weight = edge_degree_weight(edge)
            degrees[edge.source_id] += weight
            degrees[edge.target_id] += weight
        ranked: list[tuple[float, Marker]] = []
        for marker in markers:
            score, components = self._score(marker, request, degrees[marker.id])
            metadata = dict(marker.metadata)
            metadata["ranking"] = {
                "score": round(score, 4),
                "components": components,
                "reason": max(components, key=lambda key: components[key]),
            }
            ranked.append((score, replace(marker, metadata=metadata)))
        ranked.sort(key=lambda item: (-item[0], item[1].expansion_tokens, item[1].path, item[1].symbol))
        selected: list[Marker] = []
        considered = ranked[: request.limit]
        for _, marker in considered:
            trial = ProviderResult(provider=self.name, markers=tuple([*selected, marker]))
            if estimate_tokens(trial.to_dict()) <= request.budget_tokens:
                selected.append(marker)
        selected_ids = {marker.id for marker in selected}
        selected_edges: list[Edge] = []
        if request.include_edge_kinds:
            for edge in edges:
                if (
                    edge.kind in request.include_edge_kinds
                    and edge.source_id in selected_ids
                    and edge.target_id in selected_ids
                ):
                    trial = ProviderResult(
                        provider=self.name,
                        markers=tuple(selected),
                        edges=tuple([*selected_edges, edge]),
                    )
                    if estimate_tokens(trial.to_dict()) <= request.budget_tokens:
                        selected_edges.append(edge)
        omitted = max(0, len(ranked) - len(selected))
        provisional = ProviderResult(
            provider=self.name,
            markers=tuple(selected),
            edges=tuple(selected_edges),
            omitted_count=omitted,
        )
        total = estimate_tokens(provisional.to_dict())
        return replace(provisional, estimated_tokens=total)

    def expand(self, marker_ids: Iterable[str], budget_tokens: int) -> ProviderResult:
        wanted = set(marker_ids)
        markers = [marker for marker in self.store.load_markers(self.name) if marker.id in wanted]
        selected: list[Marker] = []
        for marker in markers:
            metadata = dict(marker.metadata)
            metadata["evidence_pointer"] = f"{marker.path}:{marker.start_line}"
            candidate = replace(marker, metadata=metadata)
            trial = ProviderResult(provider=self.name, markers=tuple([*selected, candidate]))
            if estimate_tokens(trial.to_dict()) <= budget_tokens:
                selected.append(candidate)
        result = ProviderResult(
            provider=self.name,
            markers=tuple(selected),
            omitted_count=max(0, len(wanted) - len(selected)),
        )
        return replace(result, estimated_tokens=estimate_tokens(result.to_dict()))

    def invalidate(self, paths: Iterable[str]) -> int:
        normalized = [Path(path).as_posix() for path in paths]
        removed = self.store.delete_paths(normalized, self.name)
        self._rebuild_import_edges()
        return removed
