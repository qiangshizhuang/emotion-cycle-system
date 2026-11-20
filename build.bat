@echo off
chcp 936 >nul 2>&1
setlocal
cd /d "%~dp0"

echo ============================================================
echo     A gu Emotion Cycle System - Build EXE
echo ============================================================
echo    A股情绪周期系统 · 一键打包
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python。
    echo.
    echo 请先安装 Python 3.11： https://www.python.org/downloads/
    echo 安装时务必勾选 "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

python -c "import sys;print('  Python:',sys.version.split()[0],' 64bit' if sys.maxsize>2**32 else ' 32bit')"
echo.

echo [1/4] 安装依赖库（首次约 2-4 分钟）...
python -m pip install --upgrade pip -q
python -m pip install -q pyinstaller pandas numpy pyarrow akshare
if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败。若网络较慢，可改用国内镜像重试：
    echo   python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller pandas numpy pyarrow akshare
    echo.
    pause
    exit /b 1
)

echo [2/4] 清理旧文件...
if exist build rmdir /s /q build 2>nul
if exist dist rmdir /s /q dist 2>nul

echo [3/4] 开始打包（约 3-8 分钟，请勿关闭窗口）...
python -m PyInstaller build.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请把上面的红色错误信息截图反馈。
    echo.
    pause
    exit /b 1
)

echo [4/4] 复制可编辑配置文件...
copy /y config.py "dist\情绪周期系统\config.py" >nul

echo.
echo ============================================================
echo     打包完成！
echo.
echo     产物： dist\情绪周期系统\情绪周期系统.exe
echo     双击即可运行。
echo     首次运行会自动下载全市场数据，约 5-8 分钟。
echo ============================================================
echo.
pause
