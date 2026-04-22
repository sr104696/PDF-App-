# pyinstaller.spec
# Changes: Added nltk_data to datas (was missing in Lovable); kept UPX + strip;
# excludes heavy scientific stacks to stay under 30 MB compressed.
# Build: pyinstaller pyinstaller.spec
# Result: dist/PDFIntelligence.exe

block_cipher = None

EXCLUDES = [
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
    "sqlite3",
]

a = Analysis(
    ["src/main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("data/synonyms.json",  "data"),
        ("data/nltk_data",      "data/nltk_data"),  # bundled punkt data
        ("assets/icon.ico",     "assets"),
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # set True while debugging
    disable_windowed_traceback=False,
    icon="assets/icon.ico",
    onefile=True,
)
