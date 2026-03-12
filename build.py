#!/usr/bin/env python3
"""
build.py — Build roblox-dev-tool into a standalone executable.

Usage:
  python build.py              # single-file build for current platform
  python build.py --onedir     # folder output (faster startup)
  python build.py --no-clean   # skip clearing dist/ and build/

Output:
  dist/roblox-dev-tool         (Linux / macOS)
  dist/roblox-dev-tool.exe     (Windows — must be built on Windows)

Cross-compilation notes:
  Windows .exe → build on Windows or use a Windows CI runner
  macOS  .app  → build on macOS
  Linux binary → build on Linux (this machine)
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys


def build_web_ui() -> bool:
    """Build the Next.js web UI into web/out/ — returns True on success."""
    web_dir = os.path.join(os.path.dirname(__file__), "web")
    if not os.path.exists(web_dir):
        print("  web/ directory not found — skipping web UI build")
        return False

    node = shutil.which("node")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not node or not npm:
        print("  Node.js / npm not found — skipping web UI build")
        print("  Install from https://nodejs.org to include the web UI")
        return False

    print(f"  Node: {node}")
    print(f"  npm:  {npm}")

    print("  Installing web dependencies…")
    subprocess.check_call([npm, "install", "--legacy-peer-deps"], cwd=web_dir)

    print("  Building Next.js app…")
    subprocess.check_call([npm, "run", "build"], cwd=web_dir)

    out_dir = os.path.join(web_dir, "out")
    if os.path.exists(out_dir):
        print(f"  Web UI built → {out_dir}")
        return True
    return False


def check_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found — installing…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build(onefile: bool = True, clean: bool = True, skip_web: bool = False) -> None:
    check_pyinstaller()

    # Build the web UI first so PyInstaller can bundle it
    if not skip_web:
        print("\n── Building web UI ───────────────────────────────────────────────────────")
        build_web_ui()
        print()

    if clean:
        for d in ("build", "dist"):
            if os.path.exists(d):
                shutil.rmtree(d)
                print(f"Removed {d}/")

    system = platform.system()
    print(f"Platform: {system} / {platform.machine()}")

    # All Python source files to bundle alongside main.py
    extra_sources = [
        "ai_backend.py",
        "rojo_manager.py",
        "selene_linter.py",
        "watch_mode.py",
        "dependency_graph.py",
        "git_manager.py",
        "open_cloud.py",
        "templates.py",
        "server_mode.py",
        "http_server.py",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "roblox-dev-tool",
        "--noconfirm",
        "--clean",
        "--console",
    ]

    sep = os.pathsep
    for src in extra_sources:
        if os.path.exists(src):
            cmd += ["--add-data", f"{src}{sep}."]

    # Bundle web UI if built
    web_out = os.path.join("web", "out")
    if os.path.exists(web_out):
        cmd += ["--add-data", f"{web_out}{sep}web/out"]
        print(f"  Bundling web UI from {web_out}")
    else:
        print("  No web/out found — web UI will not be bundled")

    cmd += [
        "--hidden-import", "anthropic",
        "--hidden-import", "anthropic._streaming",
        "--hidden-import", "openai",
        "--hidden-import", "google.generativeai",
        "--hidden-import", "watchdog",
        "--hidden-import", "watchdog.observers",
        "--hidden-import", "watchdog.events",
        "--hidden-import", "httpx",
        "--hidden-import", "gitpython",
        "--collect-all", "anthropic",
        "--collect-all", "rich",
        "--collect-all", "prompt_toolkit",
        "--collect-all", "watchdog",
    ]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if system == "Windows" and os.path.exists("icon.ico"):
        cmd += ["--icon", "icon.ico"]

    cmd += ["--add-data", f"web_server.py{sep}."]
    cmd.append("main.py")

    print("Running:", " ".join(cmd[:6]) + " …")
    subprocess.check_call(cmd)

    ext = ".exe" if system == "Windows" else ""
    out = os.path.join("dist", f"roblox-dev-tool{ext}" if onefile else "roblox-dev-tool")

    if os.path.exists(out):
        size = os.path.getsize(out) if os.path.isfile(out) else 0
        print(f"\n✔  Build complete!")
        print(f"   Output: {out}  ({size / 1_048_576:.1f} MB)" if size else f"   Output: {out}/")
        print()
        print("Usage:")
        if system == "Windows":
            print(f"   set ANTHROPIC_API_KEY=sk-...  && {out}")
            print(f"   {out} --model openai:gpt-4o")
            print(f"   {out} --new-project MyGame")
        else:
            print(f"   export ANTHROPIC_API_KEY=sk-...")
            print(f"   ./{out}")
            print(f"   ./{out} --model openai:gpt-4o")
            print(f"   ./{out} --new-project MyGame")
    else:
        print("Build may have failed — check PyInstaller output above.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build roblox-dev-tool executable")
    parser.add_argument("--onedir", action="store_true", help="Folder build instead of single file")
    parser.add_argument("--no-clean", action="store_true", help="Skip cleaning dist/ and build/")
    parser.add_argument("--no-web", action="store_true", help="Skip building the web UI")
    args = parser.parse_args()
    build(onefile=not args.onedir, clean=not args.no_clean, skip_web=args.no_web)
