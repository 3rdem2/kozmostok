# -*- mode: python ; coding: utf-8 -*-
"""KozmoStok PyInstaller tanimi (Windows onedir / macOS .app).

Derleme:
  Windows : python -m PyInstaller --noconfirm --clean KozmoStok.spec
  macOS   : python -m PyInstaller --noconfirm --clean KozmoStok.spec
"""

import os
import sys

KOK = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(KOK, "assets"), "assets"),
    (os.path.join(KOK, "surum.json"), "."),
    (os.path.join(KOK, "config.ini"), "."),
]

gizli = [
    "psycopg2",
    "psycopg2.extras",
    "psycopg2.extensions",
    "barcode",
    "barcode.writer",
    "openpyxl",
    "openpyxl.styles",
    "PIL.Image",
    "PIL.PngImagePlugin",
]

haric = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "IPython",
    "pytest",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineQuick",
    "PyQt6.QtQuick",
    "PyQt6.QtQuick3D",
    "PyQt6.QtQml",
    "PyQt6.Qt3DCore",
    "PyQt6.Qt3DRender",
    "PyQt6.QtMultimedia",
    "PyQt6.QtMultimediaWidgets",
    "PyQt6.QtBluetooth",
    "PyQt6.QtNfc",
    "PyQt6.QtPositioning",
    "PyQt6.QtSerialPort",
    "PyQt6.QtSql",
    "PyQt6.QtTest",
    "PyQt6.QtDesigner",
    "PyQt6.QtHelp",
    "PyQt6.QtCharts",
    "PyQt6.QtDataVisualization",
    "PyQt6.QtNetworkAuth",
    "PyQt6.QtRemoteObjects",
    "PyQt6.QtScxml",
    "PyQt6.QtStateMachine",
    "PyQt6.QtWebSockets",
    "PyQt6.QtWebChannel",
    "PyQt6.QtSensors",
    "PyQt6.QtSpatialAudio",
    "PyQt6.QtTextToSpeech",
]

a = Analysis(
    ["main.py"],
    pathex=[KOK],
    binaries=[],
    datas=datas,
    hiddenimports=gizli,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=haric,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KozmoStok",
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
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KozmoStok",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="KozmoStok.app",
        icon=None,
        bundle_identifier="com.kozmosize.kozmostok",
        info_plist={
            "CFBundleName": "KozmoStok",
            "CFBundleDisplayName": "KozmoStok",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
