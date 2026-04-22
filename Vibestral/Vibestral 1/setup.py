from setuptools import setup, find_packages

setup(
    name="pdf_intelligence",
    version="1.0.0",
    description="Offline PDF and EPUB indexing and search application",
    author="PDF Intelligence Team",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "pdfplumber==0.11.0",
        "pdfminer.six==20231228",
        "Pillow==10.3.0",
        "snowballstemmer==2.2.0",
        "EbookLib==0.18",
        "beautifulsoup4==4.12.3"
    ],
    entry_points={
        "console_scripts": [
            "pdf_intelligence=src.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Utilities",
    ],
)
