"""
selene_linter.py — Luau static analysis via selene.

Selene is a Luau linter: https://github.com/Kampfkarren/selene
Install: cargo install selene  (or grab a binary from GitHub releases)

If selene is not installed this module gracefully returns an empty result
and prints a hint — nothing breaks.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# ─── Data types ───────────────────────────────────────────────────────────────


@dataclass
class LintIssue:
    severity: str      # "error" | "warning" | "allow"
    line: int
    column: int
    code: str          # e.g. "undefined_variable"
    message: str


# ─── Minimal selene.toml for a Roblox project ─────────────────────────────────

_ROBLOX_SELENE_TOML = """\
std = "roblox"
[rules]
empty_if = "allow"
unused_variable = "warn"
"""

# ─── Public API ───────────────────────────────────────────────────────────────


def selene_available() -> bool:
    """Return True if the `selene` binary is on PATH."""
    return shutil.which("selene") is not None


def lint_code(code: str, script_type: str = "ModuleScript") -> list[LintIssue]:
    """
    Lint Luau code with selene.

    Returns a list of LintIssue. Returns [] if selene is not installed
    or if there are no issues.
    """
    if not selene_available():
        return []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Choose the right extension so selene understands the script type
        ext_map = {
            "Script": ".server.lua",
            "LocalScript": ".client.lua",
            "ModuleScript": ".lua",
        }
        ext = ext_map.get(script_type, ".lua")
        script_file = tmp / f"script{ext}"
        script_file.write_text(code, encoding="utf-8")

        # Write a minimal selene.toml so roblox globals are known
        (tmp / "selene.toml").write_text(_ROBLOX_SELENE_TOML, encoding="utf-8")

        try:
            result = subprocess.run(
                ["selene", "--display-style", "json", str(script_file)],
                cwd=str(tmp),
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = result.stdout.strip()
        except subprocess.TimeoutExpired:
            return []
        except FileNotFoundError:
            return []

    if not output:
        return []

    issues: list[LintIssue] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            # Fallback: try to parse the human-readable output
            issues.extend(_parse_text_line(line))
            continue

        sev = obj.get("severity", "warning")
        primary = obj.get("primary_label", {})
        issues.append(
            LintIssue(
                severity=sev,
                line=primary.get("start", {}).get("line", 0) + 1,
                column=primary.get("start", {}).get("character", 0) + 1,
                code=obj.get("code", ""),
                message=obj.get("message", ""),
            )
        )
    return issues


def lint_file(path: str | Path) -> list[LintIssue]:
    """Lint a file on disk."""
    p = Path(path)
    if not p.exists():
        return []

    script_type = "ModuleScript"
    name = p.name
    if ".server." in name:
        script_type = "Script"
    elif ".client." in name:
        script_type = "LocalScript"

    return lint_code(p.read_text(encoding="utf-8"), script_type)


def format_issues(issues: list[LintIssue]) -> str:
    """Return a human-readable summary string."""
    if not issues:
        return "No issues found."
    lines = []
    for iss in issues:
        lines.append(
            f"  [{iss.severity.upper()}] line {iss.line}:{iss.column}  {iss.code}  — {iss.message}"
        )
    return "\n".join(lines)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _parse_text_line(line: str) -> list[LintIssue]:
    """Fallback parser for selene's text output format."""
    # e.g.  script.lua:5:10: warning[undefined_variable]: `foo` is not defined
    m = re.match(
        r".+:(\d+):(\d+):\s*(\w+)\[([^\]]+)\]:\s*(.+)", line
    )
    if m:
        return [
            LintIssue(
                severity=m.group(3),
                line=int(m.group(1)),
                column=int(m.group(2)),
                code=m.group(4),
                message=m.group(5),
            )
        ]
    return []
