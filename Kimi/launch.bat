@echo off
cd /d "%~dp0"
python -OO -B main.py
if errorlevel 1 pause
