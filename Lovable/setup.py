"""Optional pip-installable setup. The app does not need to be installed —
the launch.bat / launch.sh scripts run it directly."""
from setuptools import find_packages, setup

setup(
    name="pdf-intelligence",
    version="1.0.0",
    description="Offline PDF & EPUB intelligent search (BM25, FTS5, no cloud).",
    author="PDF Intelligence",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pdfplumber==0.11.4",
        "pypdf==5.1.0",
        "snowballstemmer==2.2.0",
        "rapidfuzz==3.10.1",
        "nltk==3.9.1",
        "ebooklib==0.18",
        "beautifulsoup4==4.12.3",
        "reportlab==4.2.5",
        "pytesseract==0.3.13",
        "Pillow>=10.0.0",
    ],
    extras_require={
        "fast": ["lxml==5.3.0"],
        "build": ["pyinstaller==6.11.1"],
    },
    entry_points={"console_scripts": ["pdf-intel=src.main:main"]},
)
