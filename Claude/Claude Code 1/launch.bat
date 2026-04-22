@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  PDF Intelligence v2 — Windows launch script
REM  Uses -OO (strip docstrings + asserts) and -B (no .pyc files) for speed.
REM ─────────────────────────────────────────────────────────────────────────
setlocal
set PYTHONPATH=%~dp0
python -OO -B -m src.main %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Python exited with code %ERRORLEVEL%.
    echo Make sure you have Python 3.10+ and have run:
    echo   pip install -r requirements.txt
    pause
)
endlocal
