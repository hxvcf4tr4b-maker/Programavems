"""
watch_mode.py — Watch a Rojo src/ directory and auto-review changed scripts.

Uses the watchdog library. When a .lua / .luau file changes the tool:
  1. Lints it with selene (if available)
  2. Sends it to Claude for a quick code review
  3. Prints results in the terminal

Usage (called from main.py):
  watcher = FileWatcher(rojo_project, backend, console)
  watcher.start()   # non-blocking
  watcher.stop()
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

if TYPE_CHECKING:
    from ai_backend import AIBackend, TextDeltaEvent, StreamEndEvent
    from rojo_manager import RojoProject

# ─── Review prompt ────────────────────────────────────────────────────────────

_REVIEW_PROMPT = """\
Quickly review this Roblox Luau script for bugs, security issues, and
performance problems. Be concise — 3-5 bullet points max.
If the script looks fine, just say "Looks good".

```luau
{code}
```"""


# ─── Watcher ──────────────────────────────────────────────────────────────────


class FileWatcher:
    """Non-blocking file watcher for the Rojo src/ directory."""

    def __init__(
        self,
        rojo: "RojoProject",
        backend: "AIBackend",
        console: Console,
        debounce_seconds: float = 1.5,
    ) -> None:
        self.rojo = rojo
        self.backend = backend
        self.console = console
        self.debounce = debounce_seconds
        self._observer = None
        self._running = False
        self._pending: dict[str, float] = {}  # path → last-change timestamp
        self._lock = threading.Lock()
        self._debounce_thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the file observer. Returns False if watchdog is not installed."""
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            self.console.print("[warning]watchdog not installed — run: pip install watchdog[/warning]")
            return False

        src = self.rojo.project_dir / "src"
        if not src.exists():
            self.console.print(f"[warning]No src/ directory found at {src}[/warning]")
            return False

        handler = _LuauChangeHandler(self._on_file_changed)
        self._observer = Observer()
        self._observer.schedule(handler, str(src), recursive=True)
        self._observer.start()
        self._running = True

        self._debounce_thread = threading.Thread(target=self._debounce_loop, daemon=True)
        self._debounce_thread.start()

        self.console.print(
            Panel(
                f"[success]Watch mode active[/success]\n"
                f"Monitoring: [cyan]{src}[/cyan]\n"
                f"Changed scripts will be auto-reviewed.\n"
                f"Press [bold]Ctrl-C[/bold] or type [bold]/watch off[/bold] to stop.",
                border_style="green",
            )
        )
        return True

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None
        self._running = False
        self.console.print("[dim]Watch mode stopped.[/dim]")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_file_changed(self, path: str) -> None:
        with self._lock:
            self._pending[path] = time.monotonic()

    def _debounce_loop(self) -> None:
        """Fire reviews after the file has been stable for `debounce` seconds."""
        while self._running:
            time.sleep(0.3)
            now = time.monotonic()
            with self._lock:
                ready = [p for p, t in self._pending.items() if now - t >= self.debounce]
                for p in ready:
                    del self._pending[p]
            for p in ready:
                self._review_file(p)

    def _review_file(self, path: str) -> None:
        from selene_linter import format_issues, lint_file

        p = Path(path)
        if not p.exists():
            return

        try:
            code = p.read_text(encoding="utf-8")
        except OSError:
            return

        rel = p.relative_to(self.rojo.project_dir) if path.startswith(str(self.rojo.project_dir)) else p
        self.console.print(f"\n[tool]⚙ Watch:[/tool] [cyan]{rel}[/cyan] changed — reviewing…")

        # 1. Selene lint
        issues = lint_file(path)
        if issues:
            self.console.print(f"[warning]Selene found {len(issues)} issue(s):[/warning]")
            self.console.print(format_issues(issues))

        # 2. AI quick review (non-streaming to avoid cluttering the terminal mid-chat)
        prompt = _REVIEW_PROMPT.format(code=code[:6000])  # cap to avoid huge context
        try:
            review_text = ""
            for event in self.backend.stream(
                messages=[{"role": "user", "content": prompt}],
                system="You are a Roblox Luau expert. Be very concise.",
                tools=[],
            ):
                from ai_backend import TextDeltaEvent
                if isinstance(event, TextDeltaEvent):
                    review_text += event.text

            if review_text.strip():
                self.console.print(
                    Panel(
                        review_text.strip(),
                        title=f"[tool]AI Review — {p.name}[/tool]",
                        border_style="magenta",
                    )
                )
        except Exception as exc:
            self.console.print(f"[error]Review error:[/error] {exc}")


# ─── Watchdog event handler ───────────────────────────────────────────────────


class _LuauChangeHandler:
    def __init__(self, callback) -> None:
        self._cb = callback
        # Dynamically inherit from watchdog at import time
        try:
            from watchdog.events import FileSystemEventHandler

            class _Handler(FileSystemEventHandler):
                def on_modified(self_, event):
                    if not event.is_directory and self_._is_luau(event.src_path):
                        self._cb(event.src_path)

                def on_created(self_, event):
                    if not event.is_directory and self_._is_luau(event.src_path):
                        self._cb(event.src_path)

                @staticmethod
                def _is_luau(path: str) -> bool:
                    return path.endswith(".lua") or path.endswith(".luau")

            # Attach the callback reference to the inner class
            _Handler._cb = self._cb
            self._handler = _Handler()
        except ImportError:
            self._handler = None

    def __call__(self, *args, **kwargs):
        pass  # used as a passthrough; the actual handler is self._handler

    # Allow FileWatcher to pass self directly to observer.schedule
    def dispatch(self, event):
        if self._handler:
            self._handler.dispatch(event)

    # Patch: make this class usable as the event handler directly
    def __getattr__(self, name):
        if self._handler:
            return getattr(self._handler, name)
        raise AttributeError(name)
