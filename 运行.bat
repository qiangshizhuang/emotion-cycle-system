@echo off
chcp 936 >nul 2>&1
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
    echo 未找到 Python，请先安装 Python 3.11 并勾选 Add to PATH
    pause
    exit /b 1
)
python app.py
pause
