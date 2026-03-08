@echo off
chcp 65001 >nul 2>&1
title AI Creative Studio

echo.
echo   AI Creative Studio
echo   ════════════════════════════════════
echo.

cd /d "%~dp0\.."
set PROJECT_DIR=%cd%

:: ── Check Python ──
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   [X] Python not found
    echo.
    echo   Please install Python 3.9+:
    echo     https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PYVER=%%i
echo   [OK] Python %PYVER%

:: ── Install dependencies ──
python -c "import streamlit" >nul 2>&1
if %errorlevel% neq 0 (
    echo   [..] First run - installing dependencies...
    echo.
    python -m pip install -r "%PROJECT_DIR%\requirements.txt" --quiet
    echo.
    echo   [OK] Dependencies installed
)

:: ── Skip Streamlit email prompt ──
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    echo [general] > "%USERPROFILE%\.streamlit\credentials.toml"
    echo email = "" >> "%USERPROFILE%\.streamlit\credentials.toml"
)

:: ── Start ──
echo.
echo   Starting...
echo   Browser will open at http://localhost:8501
echo   Close this window to stop the app
echo.

cd "%PROJECT_DIR%\studio"
python -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false

pause
