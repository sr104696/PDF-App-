"""
setup.py — Package metadata for PDF Intelligence v2.
Allows installation via: pip install -e .
"""
from setuptools import setup, find_packages

setup(
    name="pdf_intelligence",
    version="2.0.0",
    description="Offline PDF & EPUB intelligent search with BM25 + FTS5 + Snowball",
    author="PDF Intelligence Contributors",
    license="MIT",
    python_requires=">=3.10",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "pdfplumber>=0.11",
        "pypdf>=5.0",
        "Pillow>=10",
        "snowballstemmer>=2.2",
        "nltk>=3.8",
        "rapidfuzz>=3.0",
        "ebooklib>=0.18",
        "beautifulsoup4>=4.12",
        "reportlab>=4.0",
        "pytesseract>=0.3",
    ],
    extras_require={
        "dev": ["pyinstaller>=6.0"],
    },
    entry_points={
        "console_scripts": [
            "pdf-intelligence=src.main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Text Processing :: Indexing",
        "Topic :: Desktop Environment",
    ],
)
