# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — 在 Windows 上执行: pyinstaller worklog.spec
# 产物: dist/Worklog/Worklog.exe（双击运行；请整夹分发 dist/Worklog）

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None
root = Path(SPECPATH)

datas = [
    (str(root / "app.py"), "."),
    (str(root / "db.py"), "."),
    (str(root / "paths.py"), "."),
    (str(root / "templates.py"), "."),
    (str(root / "ical_client.py"), "."),
    (str(root / "ui_helpers.py"), "."),
    (str(root / "scripts"), "scripts"),
    (str(root / ".streamlit" / "config.toml"), ".streamlit"),
    (str(root / "data" / ".gitkeep"), "data"),
    (str(root / "reports" / ".gitkeep"), "reports"),
]

binaries = []
hiddenimports = [
    "streamlit",
    "streamlit.web",
    "streamlit.web.cli",
    "streamlit.web.bootstrap",
    "streamlit.runtime",
    "streamlit.runtime.scriptrunner",
    "streamlit.runtime.scriptrunner.magic_funcs",
    "pandas",
    "openpyxl",
    "pyarrow",
    "google.protobuf",
    "watchdog",
    "tornado",
    "click",
    "toml",
    "blinker",
    "cachetools",
    "packaging",
    "PIL",
]

for pkg in ("streamlit", "altair", "jsonschema"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:
        print("collect_all skip", pkg, exc)

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="Worklog",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    upx=True,
    upx_exclude=[],
    name="Worklog",
)
