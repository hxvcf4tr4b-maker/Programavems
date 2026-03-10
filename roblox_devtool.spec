# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for roblox-dev-tool.
# Run directly with:  pyinstaller roblox_devtool.spec

import sys
import os

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=[
        # Bundle rojo_manager alongside main
        ("rojo_manager.py", "."),
    ],
    hiddenimports=[
        "anthropic",
        "anthropic._streaming",
        "anthropic.types",
        "anthropic._client",
        "anthropic._models",
        "anthropic._response",
        "anthropic._base_client",
        "rich",
        "rich.console",
        "rich.panel",
        "rich.markdown",
        "rich.syntax",
        "rich.table",
        "rich.prompt",
        "rich.theme",
        "rich.columns",
        "prompt_toolkit",
        "httpx",
        "httpcore",
        "anyio",
        "sniffio",
        "certifi",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,         # Must be True — this is a terminal app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",    # Uncomment and add an .ico file for Windows
)
