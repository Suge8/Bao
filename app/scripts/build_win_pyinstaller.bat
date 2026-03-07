@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0..\.."
pushd "%PROJECT_ROOT%"

for /f "usebackq delims=" %%i in (`uv run python "app\scripts\read_version.py"`) do set "VERSION=%%i"

set "APP_NAME=Bao"
set "BUILD_ROOT=%PROJECT_ROOT%\dist-pyinstaller"
set "DIST_DIR=%BUILD_ROOT%\dist"
set "WORK_DIR=%BUILD_ROOT%\build-win-x64"
set "SPEC_DIR=%BUILD_ROOT%\spec-win-x64"

echo ========================================
echo   Bao Desktop ^- Windows PyInstaller Build
echo   Version: %VERSION%
echo ========================================
echo.

where uv >nul 2>nul || (echo [ERROR] uv not installed. Install uv first: https://astral.sh/uv/ & exit /b 1)
uv run python -c "import PyInstaller" 2>nul || (echo [ERROR] PyInstaller not installed. Run: uv sync --extra desktop-build-pyinstaller & exit /b 1)
uv run python -c "import PySide6" 2>nul || (echo [ERROR] PySide6 not installed. Run: uv sync --extra desktop-build-pyinstaller & exit /b 1)

if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"
if exist "%SPEC_DIR%" rmdir /s /q "%SPEC_DIR%"
if exist "%DIST_DIR%\%APP_NAME%" rmdir /s /q "%DIST_DIR%\%APP_NAME%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%"
if not exist "%SPEC_DIR%" mkdir "%SPEC_DIR%"

uv run pyinstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --name "%APP_NAME%" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%WORK_DIR%" ^
    --specpath "%SPEC_DIR%" ^
    --icon "%PROJECT_ROOT%\app\resources\logo.ico" ^
    --add-data "%PROJECT_ROOT%\app\qml;app\qml" ^
    --add-data "%PROJECT_ROOT%\app\resources;app\resources" ^
    --add-data "%PROJECT_ROOT%\assets;assets" ^
    --add-data "%PROJECT_ROOT%\bao\skills;bao\skills" ^
    --add-data "%PROJECT_ROOT%\bao\templates\workspace;bao\templates\workspace" ^
    --collect-all lancedb ^
    --collect-all pyarrow ^
    --collect-submodules bao.channels ^
    --collect-submodules bao.providers ^
    --collect-submodules bao.skills ^
    --collect-submodules bao.agent.tools ^
    --exclude-module tkinter ^
    --exclude-module unittest ^
    --exclude-module doctest ^
    --exclude-module idlelib ^
    --exclude-module lib2to3 ^
    --exclude-module ensurepip ^
    --exclude-module distutils ^
    --exclude-module turtledemo ^
    --exclude-module test ^
    --exclude-module pytest ^
    --exclude-module _pytest ^
    "%PROJECT_ROOT%\app\main.py"

if errorlevel 1 (
    echo [ERROR] Build failed!
    popd
    exit /b 1
)

if not exist "%DIST_DIR%\%APP_NAME%\%APP_NAME%.exe" (
    echo [ERROR] Build output missing: %DIST_DIR%\%APP_NAME%\%APP_NAME%.exe
    popd
    exit /b 1
)

echo.
echo ========================================
echo   Build complete!
echo   Output: %DIST_DIR%\%APP_NAME%\
echo ========================================
echo.
echo Next steps:
echo   - Test: %DIST_DIR%\%APP_NAME%\%APP_NAME%.exe
echo   - Package: app\scripts\package_win_installer.bat --build-root %DIST_DIR%\%APP_NAME%

popd
