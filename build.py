#!/usr/bin/env python3
"""
build.py — Build roblox-dev-tool into a standalone executable.

Usage:
  python build.py              # builds for current platform
  python build.py --onefile    # single-file binary (default)
  python build.py --onedir     # folder output instead

Output:
  dist/roblox-dev-tool         (Linux/macOS)
  dist/roblox-dev-tool.exe     (Windows)
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys


def check_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build(onefile: bool = True, clean: bool = True) -> None:
    check_pyinstaller()

    # Clean previous build artefacts
    if clean:
        for d in ("build", "dist"):
            if os.path.exists(d):
                shutil.rmtree(d)
                print(f"Removed old {d}/")

    exe_name = "roblox-dev-tool"
    system = platform.system()
    print(f"Building for: {system} ({platform.machine()})")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name", exe_name,
        "--noconfirm",
        "--clean",
        # Include the rojo_manager module explicitly
        "--add-data", f"rojo_manager.py{os.pathsep}.",
        # Ensure all SDK sub-packages are bundled
        "--hidden-import", "anthropic",
        "--hidden-import", "anthropic._streaming",
        "--hidden-import", "anthropic.types",
        "--collect-all", "anthropic",
        "--collect-all", "rich",
        "--collect-all", "prompt_toolkit",
        # Keep console window (required for interactive CLI)
        "--console",
    ]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # Windows-specific: add an icon if one exists
    if system == "Windows" and os.path.exists("icon.ico"):
        cmd += ["--icon", "icon.ico"]

    cmd.append("main.py")

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)

    # Print result
    ext = ".exe" if system == "Windows" else ""
    if onefile:
        out = os.path.join("dist", f"{exe_name}{ext}")
    else:
        out = os.path.join("dist", exe_name)

    if os.path.exists(out):
        size = os.path.getsize(out) if os.path.isfile(out) else 0
        size_mb = size / 1_048_576
        print()
        print(f"✔  Build complete!")
        print(f"   Output : {out}")
        if size_mb:
            print(f"   Size   : {size_mb:.1f} MB")
        print()
        if system == "Windows":
            print(f"   Run with: {out}")
        else:
            print(f"   Run with: ./{out}")
        print()
        print("Note: set ANTHROPIC_API_KEY before running:")
        if system == "Windows":
            print(f"   set ANTHROPIC_API_KEY=your-key && {out}")
        else:
            print(f"   export ANTHROPIC_API_KEY=your-key && ./{out}")
    else:
        print("Build may have failed — check PyInstaller output above.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build roblox-dev-tool executable")
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build as a folder instead of a single file",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip cleaning dist/ and build/ before building",
    )
    args = parser.parse_args()
    build(onefile=not args.onedir, clean=not args.no_clean)
