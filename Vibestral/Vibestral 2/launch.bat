@echo off
setlocal
cd /d "%~dp0"

REM Auto-install dependencies if not present
python -c "import pdfplumber" 2>nul || (
    echo Installing dependencies...
    pip install -r pdf_intelligence\requirements.txt --quiet
)

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -OO -X utf8 -m pdf_intelligence.src.main %*
) else (
    python -OO -X utf8 -m pdf_intelligence.src.main %*
)
endlocal
