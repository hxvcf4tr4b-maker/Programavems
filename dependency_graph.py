"""
dependency_graph.py — Parse require() calls in a Rojo project and render a graph.

Detects:
  require(ReplicatedStorage.Modules.Foo)
  require(script.Parent.Bar)
  require(game:GetService("ReplicatedStorage").Modules.Baz)
  local X = require(...)

Outputs an ASCII dependency tree and highlights circular dependencies.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rojo_manager import RojoProject

# ─── Require patterns ─────────────────────────────────────────────────────────

_REQUIRE_PATTERNS = [
    # require(ReplicatedStorage.Modules.Foo)
    re.compile(r"require\(([A-Za-z][A-Za-z0-9_.]+)\)"),
    # require(game:GetService("ReplicatedStorage").Modules.Foo)
    re.compile(r'require\(game:GetService\(["\']([^"\']+)["\']\)\.([A-Za-z0-9_.]+)\)'),
    # require(script.Parent.Something)
    re.compile(r"require\(script\.([A-Za-z0-9_.]+)\)"),
]


def _extract_requires(code: str) -> list[str]:
    deps: list[str] = []
    for pat in _REQUIRE_PATTERNS:
        for m in pat.finditer(code):
            # Last group contains the path
            dep = m.group(len(m.groups()))
            deps.append(dep.strip())
    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for d in deps:
        if d not in seen:
            seen.add(d)
            result.append(d)
    return result


# ─── Graph builder ────────────────────────────────────────────────────────────


class DependencyGraph:
    """Builds and renders a require() dependency graph for a Rojo project."""

    def __init__(self, rojo: "RojoProject") -> None:
        self.rojo = rojo
        # module_name → set of dependency names
        self.edges: dict[str, set[str]] = defaultdict(set)
        # module_name → file path
        self.files: dict[str, str] = {}

    def build(self) -> None:
        """Walk src/ and parse every .luau file."""
        src = self.rojo.project_dir / "src"
        if not src.exists():
            return

        for p in src.rglob("*"):
            if p.suffix not in (".lua", ".luau"):
                continue
            # Use stem (without extensions like .server) as the module name
            name = p.stem.split(".")[0]
            self.files[name] = str(p.relative_to(self.rojo.project_dir))
            try:
                code = p.read_text(encoding="utf-8")
            except OSError:
                continue
            for dep in _extract_requires(code):
                # Take the last component of a dotted path as the module name
                dep_name = dep.split(".")[-1]
                if dep_name and dep_name != name:
                    self.edges[name].add(dep_name)

    def find_cycles(self) -> list[list[str]]:
        """Return all cycles detected using DFS."""
        visited: set[str] = set()
        stack: set[str] = set()
        cycles: list[list[str]] = []

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            stack.add(node)
            for neighbour in self.edges.get(node, set()):
                if neighbour not in visited:
                    dfs(neighbour, path + [neighbour])
                elif neighbour in stack:
                    # Found a cycle
                    cycle_start = path.index(neighbour) if neighbour in path else 0
                    cycles.append(path[cycle_start:] + [neighbour])
            stack.discard(node)

        for node in list(self.edges.keys()):
            if node not in visited:
                dfs(node, [node])
        return cycles

    def to_ascii(self, max_depth: int = 4) -> str:
        """Render the graph as an indented ASCII tree."""
        if not self.edges and not self.files:
            return "(no scripts found)"

        lines: list[str] = []
        all_nodes = set(self.edges.keys()) | set(self.files.keys())
        # Roots = nodes that nothing depends on
        dependents: set[str] = set()
        for deps in self.edges.values():
            dependents |= deps
        roots = [n for n in sorted(all_nodes) if n not in dependents]
        if not roots:
            roots = sorted(all_nodes)[:1]  # pick one if everything is circular

        visited: set[str] = set()

        def render(node: str, prefix: str, depth: int) -> None:
            if depth > max_depth:
                lines.append(f"{prefix}  … (truncated)")
                return
            is_new = node not in visited
            visited.add(node)
            path = self.files.get(node, "")
            marker = "" if is_new else " [↑ cycle]"
            lines.append(f"{prefix}📦 {node}  [dim]{path}[/dim]{marker}")
            if is_new:
                children = sorted(self.edges.get(node, set()))
                for i, child in enumerate(children):
                    is_last = i == len(children) - 1
                    branch = "└─ " if is_last else "├─ "
                    new_prefix = prefix + ("   " if is_last else "│  ")
                    render(child, prefix + branch, depth + 1)

        for root in roots:
            render(root, "", 0)
            lines.append("")

        # Orphan modules (no edges at all)
        orphans = sorted(n for n in self.files if n not in all_nodes or (n not in self.edges and n not in dependents))
        if orphans:
            lines.append("[dim]Standalone modules (no require connections):[/dim]")
            for o in orphans:
                lines.append(f"  📦 {o}  [dim]{self.files.get(o, '')}[/dim]")

        return "\n".join(lines)

    def summary(self) -> str:
        """One-line summary."""
        total = len(self.files)
        edges = sum(len(v) for v in self.edges.values())
        cycles = self.find_cycles()
        cycle_str = f"  ⚠ {len(cycles)} circular dependency!" if cycles else ""
        return f"{total} scripts, {edges} require() connections{cycle_str}"
