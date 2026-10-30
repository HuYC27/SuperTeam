# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(project / 'desktop_mcp.py')],
    pathex=[str(project)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy','pandas','scipy','matplotlib','torch','PyQt5','PyQt6','PySide2','PySide6','IPython','notebook','tkinter','webview'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SuperTeamComputer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SuperTeamComputer',
)
