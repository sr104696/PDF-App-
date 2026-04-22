@echo off
REM Optimized launch: -O strips asserts, -B prevents .pyc writes, faster cold start.
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -OO -B -m src.main %*
) else (
    python -OO -B -m src.main %*
)
endlocal
