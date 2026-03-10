"""
git_manager.py — Git auto-commit integration.

Stages and commits saved scripts with an AI-generated commit message.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_backend import AIBackend


class GitManager:
    def __init__(self, project_dir: str | Path) -> None:
        self.project_dir = Path(project_dir).resolve()

    def is_git_repo(self) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def stage_files(self, paths: list[str | Path]) -> None:
        for p in paths:
            subprocess.run(
                ["git", "add", str(p)],
                cwd=str(self.project_dir),
                capture_output=True,
            )

    def commit(self, message: str) -> bool:
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def generate_message(
        self,
        backend: "AIBackend",
        files: list[str],
        context: str = "",
    ) -> str:
        """Ask the AI to write a conventional commit message for the given files."""
        file_list = "\n".join(f"  - {f}" for f in files)
        prompt = (
            f"Write a short, conventional-commit-style git commit message "
            f"(max 72 chars, imperative mood) for these Luau script files:\n"
            f"{file_list}\n"
        )
        if context:
            prompt += f"\nContext: {context}\n"
        prompt += "\nReply with ONLY the commit message string, nothing else."

        message = ""
        for event in backend.stream(
            messages=[{"role": "user", "content": prompt}],
            system="You write concise git commit messages.",
            tools=[],
        ):
            from ai_backend import TextDeltaEvent
            if isinstance(event, TextDeltaEvent):
                message += event.text
        return message.strip().strip('"').strip("'")

    def auto_commit(
        self,
        backend: "AIBackend",
        paths: list[str | Path],
        context: str = "",
    ) -> tuple[bool, str]:
        """Stage paths, generate a commit message with AI, and commit. Returns (success, message)."""
        if not self.is_git_repo():
            return False, "Not a git repository"

        str_paths = [str(p) for p in paths]
        self.stage_files(str_paths)

        msg = self.generate_message(backend, str_paths, context)
        if not msg:
            msg = "chore: update Luau scripts"

        success = self.commit(msg)
        return success, msg
