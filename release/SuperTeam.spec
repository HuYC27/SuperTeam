# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(project / 'desktop.py')],
    pathex=[str(project)],
    binaries=[],
    datas=[],
    hiddenimports=[
        'server','connections','native_instance','app_settings','native_services',
        'memory_agent','file_library','desktop_control','windows_desktop','desktop_mcp',
        'chat_archive','xlrd','skill_library','quotas','webview.platforms.edgechromium',
        'pillow_heif','pillow_avif','api_connector'
    ],
    hookspath=[str(project / 'release' / 'pyinstaller-hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pandas','scipy','matplotlib','torch','PyQt5','PyQt6','PySide2','PySide6','IPython','notebook','tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SuperTeam',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(project / 'ui' / 'assets' / 'superteam-v1.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SuperTeam',
)

