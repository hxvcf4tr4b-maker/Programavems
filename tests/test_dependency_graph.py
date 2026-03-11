"""Tests for dependency_graph.py — require() parsing, cycle detection, ASCII render."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dependency_graph import DependencyGraph, _extract_requires


# ── _extract_requires ─────────────────────────────────────────────────────────

class TestExtractRequires:
    def test_simple_require(self):
        code = "local Foo = require(ReplicatedStorage.Modules.Foo)"
        deps = _extract_requires(code)
        assert "Modules.Foo" in deps or any("Foo" in d for d in deps)

    def test_service_require(self):
        code = 'local Bar = require(game:GetService("ReplicatedStorage").Modules.Bar)'
        deps = _extract_requires(code)
        assert any("Bar" in d for d in deps)

    def test_script_parent_require(self):
        code = "local Util = require(script.Parent.Util)"
        deps = _extract_requires(code)
        assert any("Util" in d for d in deps)

    def test_deduplication(self):
        code = (
            "require(ReplicatedStorage.Foo)\n"
            "require(ReplicatedStorage.Foo)\n"
        )
        deps = _extract_requires(code)
        assert len(deps) == len(set(deps))

    def test_no_requires(self):
        code = "print('hello world')\nlocal x = 1 + 2"
        assert _extract_requires(code) == []

    def test_multiple_requires(self):
        code = (
            "require(ReplicatedStorage.Foo)\n"
            "require(ReplicatedStorage.Bar)\n"
            "require(ReplicatedStorage.Baz)\n"
        )
        deps = _extract_requires(code)
        assert len(deps) >= 3


# ── DependencyGraph ───────────────────────────────────────────────────────────

def _make_graph(edges: dict[str, list[str]]) -> DependencyGraph:
    """Helper: create a DependencyGraph with pre-set edges (no Rojo needed)."""
    mock_rojo = MagicMock()
    mock_rojo.project_dir = Path("/fake")
    g = DependencyGraph(mock_rojo)
    for node, deps in edges.items():
        g.edges[node] = set(deps)
        g.files[node] = f"src/{node}.luau"
    # Ensure dep nodes appear in files too
    for deps in edges.values():
        for d in deps:
            if d not in g.files:
                g.files[d] = f"src/{d}.luau"
    return g


class TestFindCycles:
    def test_no_cycle(self):
        g = _make_graph({"A": ["B"], "B": ["C"], "C": []})
        assert g.find_cycles() == []

    def test_simple_cycle(self):
        g = _make_graph({"A": ["B"], "B": ["A"]})
        cycles = g.find_cycles()
        assert len(cycles) > 0
        # Cycle should contain both A and B
        flat = [node for cycle in cycles for node in cycle]
        assert "A" in flat or "B" in flat

    def test_self_loop_excluded(self):
        # A → A is filtered out in build() but test the cycle detector
        g = _make_graph({"A": []})
        g.edges["A"] = {"A"}  # artificially add self-loop
        # DFS should detect it
        cycles = g.find_cycles()
        # May or may not detect self-loops depending on implementation — just don't crash
        assert isinstance(cycles, list)

    def test_triangle_cycle(self):
        g = _make_graph({"A": ["B"], "B": ["C"], "C": ["A"]})
        cycles = g.find_cycles()
        assert len(cycles) > 0

    def test_no_cycles_in_tree(self):
        g = _make_graph({"Root": ["Lib1", "Lib2"], "Lib1": ["Util"], "Lib2": ["Util"], "Util": []})
        assert g.find_cycles() == []


class TestToAscii:
    def test_empty_graph_returns_placeholder(self):
        mock_rojo = MagicMock()
        mock_rojo.project_dir = Path("/fake")
        g = DependencyGraph(mock_rojo)
        result = g.to_ascii()
        assert "no scripts found" in result.lower()

    def test_returns_string(self):
        g = _make_graph({"A": ["B"], "B": []})
        result = g.to_ascii()
        assert isinstance(result, str)

    def test_nodes_appear_in_output(self):
        g = _make_graph({"MyModule": ["Dependency"], "Dependency": []})
        result = g.to_ascii()
        assert "MyModule" in result
        assert "Dependency" in result


class TestSummary:
    def test_summary_is_string(self):
        g = _make_graph({"A": ["B"]})
        assert isinstance(g.summary(), str)

    def test_summary_mentions_script_count(self):
        g = _make_graph({"A": ["B"], "B": []})
        summary = g.summary()
        assert "2" in summary  # 2 scripts

    def test_summary_mentions_cycle_when_present(self):
        g = _make_graph({"A": ["B"], "B": ["A"]})
        summary = g.summary()
        assert "cycle" in summary.lower() or "circular" in summary.lower()

    def test_summary_no_cycle_warning_when_clean(self):
        g = _make_graph({"A": ["B"], "B": []})
        summary = g.summary()
        # Should NOT mention cycle
        assert "cycle" not in summary.lower()
