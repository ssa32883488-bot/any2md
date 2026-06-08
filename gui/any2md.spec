# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for any2md setup wizard."""

import os
import shutil
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)
ENGINE_SRC = ROOT.parent / "engine"

# Stage engine next to spec before analysis (build.ps1 also copies to _bundle/engine)
bundle_engine = ROOT / "_bundle" / "engine"
if ENGINE_SRC.is_dir() and not bundle_engine.is_dir():
    shutil.copytree(ENGINE_SRC, bundle_engine)

engine_data = str(bundle_engine) if bundle_engine.is_dir() else str(ENGINE_SRC)

a = Analysis(
    [str(ROOT / "app" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(engine_data, "engine")],
    hiddenimports=[
        "app.ui.wizard",
        "app.ui.main_window",
        "app.ui.chunk_dialog",
        "app.gpu_probe",
        "app.download_worker",
        "app.model_downloader",
        "app.parse_worker",
        "app.batch_worker",
        "app.chunk_worker",
        "app.chunk_download_worker",
        "app.chunk_catalog",
        "app.progress_estimator",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="any2md",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=os.environ.get("ANY2MD_COLLECT_NAME", "any2md"),
)
