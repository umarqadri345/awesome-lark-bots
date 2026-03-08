@echo off
chcp 65001 >nul 2>&1
title AI Creative Studio

echo.
echo   ⚡ AI 创意工作站 / AI Creative Studio
echo   ════════════════════════════════════
echo.

cd /d "%~dp0\.."
set PROJECT_DIR=%cd%

:: ── 检查 Python ──
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   ❌ 未找到 Python
    echo.
    echo   请先安装 Python 3.9+：
    echo     https://www.python.org/downloads/
    echo   安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PYVER=%%i
echo   ✓ Python %PYVER%

:: ── 安装依赖 ──
python -c "import streamlit" >nul 2>&1
if %errorlevel% neq 0 (
    echo   ⏳ 首次运行，正在安装依赖...
    echo.
    python -m pip install -r "%PROJECT_DIR%\requirements.txt" --quiet
    echo.
    echo   ✓ 依赖安装完成
)

:: ── 跳过 Streamlit 邮箱提示 ──
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    echo [general] > "%USERPROFILE%\.streamlit\credentials.toml"
    echo email = "" >> "%USERPROFILE%\.streamlit\credentials.toml"
)

:: ── 启动 ──
echo.
echo   🚀 正在启动...
echo   浏览器将自动打开 http://localhost:8501
echo   关闭此窗口即可停止应用
echo.

cd "%PROJECT_DIR%\studio"
python -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false

pause
