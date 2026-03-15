# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the GitHub EMU Migration desktop app.

Produces:
  macOS  → dist/EMU Migration.app
  Windows → dist/EMU Migration/EMU Migration.exe

Build:
  pyinstaller packaging/emu_migration.spec
"""

import platform
from pathlib import Path

block_cipher = None

_ROOT = Path(SPECPATH).resolve().parent          # project root
_SRC  = _ROOT / "src" / "emu_migration"
_UI   = _SRC / "ui"

# Collect the HTML/CSS/JS frontend assets
ui_datas = [(str(_UI), "emu_migration/ui")]

a = Analysis(
    [str(_SRC / "desktop.py")],
    pathex=[str(_ROOT / "src")],
    binaries=[],
    datas=ui_datas,
    hiddenimports=[
        "emu_migration",
        "emu_migration.desktop",
        "emu_migration.desktop_api",
        "emu_migration.assessment",
        "emu_migration.cli",
        "emu_migration.config",
        "emu_migration.demo",
        "emu_migration.emu_migration",
        "emu_migration.gei",
        "emu_migration.github_client",
        "emu_migration.models",
        "emu_migration.report",
        "emu_migration.sso_migration",
        "emu_migration._console",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "test",
        "matplotlib", "numpy", "pandas",
        "PIL", "scipy",
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
    [],
    exclude_binaries=True,
    name="EMU Migration",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=True,     # macOS argv emulation
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="EMU Migration",
)

# ── macOS .app bundle ─────────────────────────────────────────────
if platform.system() == "Darwin":
    app = BUNDLE(
        coll,
        name="EMU Migration.app",
        icon=None,                       # Add icon later: icon='assets/icon.icns'
        bundle_identifier="com.github.emu-migration",
        info_plist={
            "CFBundleName": "EMU Migration",
            "CFBundleDisplayName": "GitHub EMU Migration Tool",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,   # Respect macOS dark mode
        },
    )
