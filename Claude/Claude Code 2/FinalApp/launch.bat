@echo off
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
pip install -q -r requirements.txt --break-system-packages 2>nul || pip install -q -r requirements.txt
python -m src.main %*
if errorlevel 1 pause
