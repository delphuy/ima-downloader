@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

REM ============================================================
REM  IMA 知识库下载器 - 启动脚本
REM  功能：检查 Python → 安装依赖 → 启动 GUI
REM ============================================================

echo ========================================
echo   IMA 知识库下载器 - 环境检查
echo ========================================

REM --- 1. 检查 Python ---
python --version >nul 2>&1
if errorlevel 1 (
    color 0c
    echo.
    echo [错误] 未找到 Python！
    echo.
    echo 请先安装 Python 3.8 或以上版本：
    echo   https://www.python.org/downloads/
    echo.
    echo 安装时请务必勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
echo [OK] Python 已安装

REM --- 2. 安装 / 更新依赖 ---
echo.
echo [1/2] 检查 Python 依赖...
python -c "import requests" 2>nul
if errorlevel 1 (
    echo       未找到 requests，正在安装...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        color 0c
        echo.
        echo [错误] 依赖安装失败，请检查网络或手动执行：
        echo   python -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)
echo [OK] 依赖已就绪（requests）

REM --- 3. 启动 GUI（最小化方式，避免 CMD 窗口） ---
echo.
echo [2/2] 启动 GUI...
echo.

REM 用 start /min 把 GUI 启动到最小化窗口，本 bat 随即退出
if "%1"=="" (
    start "" /min cmd /c "%~f0" _launched
    exit
)

REM 以下是 _launched 分支：真正启动 pythonw
:run
pythonw.exe gui.py
if errorlevel 1 (
    echo.
    echo [警告] pythonw 启动失败，尝试用 python（会显示控制台）...
    python gui.py
    pause
)
