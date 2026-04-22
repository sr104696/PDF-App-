# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for PDF Intelligence v2
# Build:  pyinstaller pyinstaller.spec
# Output: dist/PDFIntelligence.exe  (~25-30 MB with UPX)
#
# Prerequisites:
#   pip install pyinstaller
#   Install UPX and put it on PATH for maximum compression
#
# Notes:
#   Tesseract is NOT bundled (adds ~40 MB). Users install it separately.
#   NLTK punkt data bundled only if you've run:
#     python -c "import nltk; nltk.download('punkt', download_dir='data/nltk_data')"
#   Otherwise the regex sentence-splitter fallback is used automatically.

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Collect snowballstemmer language data files
datas = [
    ("data", "data"),          # synonyms.json + any pre-downloaded NLTK data
    ("assets", "assets"),      # icon.png
]

# Include any nltk data that was pre-downloaded
_nltk_data = os.path.join("data", "nltk_data")
if os.path.isdir(_nltk_data):
    datas.append((_nltk_data, "data/nltk_data"))

a = Analysis(
    ["src/main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "sqlite3",
        "snowballstemmer",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "pdfplumber",
        "pdfminer",
        "pdfminer.high_level",
        "pdfminer.layout",
        "ebooklib",
        "bs4",
        "bs4.builder._htmlparser",
        "reportlab",
        "reportlab.pdfgen",
        "rapidfuzz",
        "nltk",
        "nltk.tokenize",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Heavy scientific stack — not needed
        "numpy", "scipy", "sklearn", "matplotlib", "pandas",
        # GUI toolkits we don't use
        "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
        # AI / ML — explicitly forbidden by spec
        "torch", "tensorflow", "transformers", "sentence_transformers",
        # Jupyter / IPython
        "IPython", "jupyter", "notebook",
        # Other bloat
        "distutils", "setuptools", "pip", "pkg_resources",
        "email", "html", "http", "urllib", "xmlrpc",
        "multiprocessing",   # not used; single-thread model
        "curses", "readline",
        "test", "unittest",  # don't ship test modules
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
    name="PDFIntelligence",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,          # strip debug symbols (Linux/macOS)
    upx=True,            # UPX compression (install UPX separately)
    upx_exclude=[
        "vcruntime140.dll",
        "python3*.dll",
    ],
    runtime_tmpdir=None,
    console=False,       # no console window on Windows
    icon="assets/icon.ico" if os.path.exists("assets/icon.ico") else None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
