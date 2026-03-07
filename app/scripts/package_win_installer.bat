@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0..\.."
pushd "%PROJECT_ROOT%"

for /f "usebackq delims=" %%i in (`uv run python "app\scripts\read_version.py"`) do set "VERSION=%%i"

echo ========================================
echo   Bao Desktop ^- Windows Installer
echo   Version: %VERSION%
echo ========================================
echo.

echo ^> Generating installer assets...
uv run --with pillow python "app\scripts\generate_installer_assets.py"
if errorlevel 1 (
    echo [ERROR] Installer asset generation failed!
    popd
    exit /b 1
)

echo ^> Resolving Inno Setup compiler...
for /f "usebackq delims=" %%i in (`uv run python "app\scripts\resolve_inno_setup.py"`) do set "ISCC_EXE=%%i"
if not defined ISCC_EXE (
    echo [ERROR] Inno Setup compiler with required language files not found!
    popd
    exit /b 1
)

"%ISCC_EXE%" /DMyAppVersion=%VERSION% app\scripts\bao_installer.iss
if errorlevel 1 (
    echo [ERROR] Installer build failed!
    popd
    exit /b 1
)

echo [OK] Installer output: dist\Bao-%VERSION%-windows-x64-setup.exe
popd
