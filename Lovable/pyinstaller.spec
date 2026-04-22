# PyInstaller spec — single-file Windows build, optimized for size.
# Build:  pyinstaller pyinstaller.spec
# Result: dist/PDFIntelligence.exe  (target < 30 MB compressed)

# pylint: disable=undefined-variable
block_cipher = None

EXCLUDES = [
    # Heavy stuff we never use
    "numpy", "scipy", "pandas", "matplotlib", "sklearn",
    "torch", "tensorflow", "transformers",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    "IPython", "notebook", "jupyter",
    "tkinter.test", "test", "unittest", "pydoc_data",
    "setuptools", "pip", "wheel", "distutils",
]

HIDDENIMPORTS = [
    "snowballstemmer.basestemmer",
    "snowballstemmer.among",
    "ebooklib.epub",
    "bs4",
    "pdfplumber",
    "pypdf",
    "reportlab.pdfbase._fontdata",
]

a = Analysis(
    ["src/main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("data/synonyms.json", "data"),
        ("assets/icon.ico", "assets"),
    ],
    hiddenimports=HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    name="PDFIntelligence",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,                # requires UPX on PATH (or use --upx-dir)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # set True while debugging
    disable_windowed_traceback=False,
    icon="assets/icon.ico",
    onefile=True,
)
