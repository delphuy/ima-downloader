@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

REM ============================================================
REM   IMA Knowledge Base Downloader v1.0.1 - Launcher
REM ============================================================

REM --- 1. Check Python ---
python --version >nul 2>&1
if errorlevel 1 (
    color 0c
    echo.
    echo [ERROR] Python not found.
    echo   https://www.python.org/downloads/
    echo   Make sure to check Add Python to PATH during install.
    echo.
    pause
    exit /b 1
)
echo [OK] Python installed

REM --- 2. Check / install dependencies ---
echo.
echo [1/2] Checking dependencies...
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo     Installing requests...
    python -m pip install -r requirements.txt >nul 2>&1
    if errorlevel 1 (
        color 0c
        echo.
        echo [ERROR] pip install failed. Run manually:
        echo   python -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)
echo [OK] Dependencies ready

REM --- 3. Launch GUI (hidden /min, then exit so CMD window vanishes) ---
echo.
echo [2/2] Launching GUI...
if "%~1" == "" (
    start "" /min cmd /d /c "pushd \"%~dp0\" && \"%~f0\" _launched && exit"
    exit
)
pythonw.exe gui.py
if errorlevel 1 (
    echo.
    echo [WARNING] pythonw failed, trying python...
    python gui.py
    pause
)