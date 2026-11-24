@echo off
chcp 936 >nul 2>&1
setlocal
cd /d "%~dp0"

echo ============================================================
echo    GitHub 发布包下载器
echo ============================================================
echo.
echo 用于下载私有仓库的 Release 附件。
echo 浏览器直接点链接会 404，因为未登录时 GitHub 对私有仓库一律返回 404。
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 没找到 Python。
    echo 如果你只是想在浏览器下载，直接登录 GitHub 后打开：
    echo   https://github.com/qiangshizhuang/emotion-cycle-system/releases
    echo.
    pause
    exit /b 1
)

python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo 首次运行需要装一个依赖 requests，正在安装...
    python -m pip install -q requests
)

python "下载GitHub发布包.py" %*
echo.
pause
