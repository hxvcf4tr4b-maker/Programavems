# -*- mode: python ; coding: utf-8 -*-
# Reproducible PyInstaller spec — run:  pyinstaller roblox_devtool.spec

import os, sys

block_cipher = None

_extra_datas = [
    (src, ".") for src in [
        "ai_backend.py", "rojo_manager.py", "selene_linter.py",
        "watch_mode.py", "dependency_graph.py", "git_manager.py",
        "open_cloud.py", "templates.py", "server_mode.py", "http_server.py",
    ] if os.path.exists(src)
]

a = Analysis(
    ["main.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=_extra_datas,
    hiddenimports=[
        "anthropic", "anthropic._streaming", "anthropic.types",
        "openai", "openai._streaming",
        "google.generativeai",
        "watchdog", "watchdog.observers", "watchdog.observers.polling",
        "watchdog.events",
        "httpx", "httpcore", "anyio", "sniffio", "certifi",
        "rich", "rich.console", "rich.panel", "rich.markdown",
        "rich.syntax", "rich.table", "rich.prompt", "rich.theme",
        "prompt_toolkit",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "cv2"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="roblox-dev-tool",
    debug=False,
    strip=False,
    upx=True,
    console=True,
    runtime_tmpdir=None,
)
