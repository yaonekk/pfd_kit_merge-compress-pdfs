@echo off
title PDF Kit - Merge
cd /d "%~dp0"
python merge_pdfs.py %*
if errorlevel 1 (
    echo.
    echo If Python was not found, install it from https://www.python.org/downloads/
    echo then run:  python -m pip install -r requirements.txt
    pause
    exit /b 1
)
echo.
pause
