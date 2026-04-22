# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for PDF Intelligence.
Build: pyinstaller pyinstaller.spec
Output: dist/PDFIntelligence.exe  (~25-30 MB with UPX)
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "src" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "data" / "synonyms.json"), "data"),
    ],
    hiddenimports=[
        "snowballstemmer",
        "nltk",
        "nltk.tokenize",
        "pdfplumber",
        "pypdf",
        "ebooklib",
        "bs4",
        "rapidfuzz",
        "reportlab",
        "PIL",
        "tkinter",
        "tkinter.ttk",
    ],
    excludes=[
        "numpy", "scipy", "sklearn", "torch", "tensorflow",
        "PyQt5", "PyQt6", "PySide2", "PySide6",
        "IPython", "jupyter", "matplotlib",
        "distutils", "setuptools", "pip",
        "test", "tests", "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PDFIntelligence",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # add: icon=str(ROOT / "assets" / "icon.ico")
)
