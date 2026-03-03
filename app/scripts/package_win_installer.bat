@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0..\.."
pushd "%PROJECT_ROOT%"

for /f "tokens=*" %%i in ('python -c "import re; f=open('pyproject.toml'); m=re.search(r'version\s*=\s*\"([^\"]+)\"',f.read()); print(m.group(1) if m else '0.0.0')"') do set "VERSION=%%i"

echo ========================================
echo   Bao Desktop ^- Windows Installer
echo   Version: %VERSION%
echo ========================================
echo.

iscc /DMyAppVersion=%VERSION% app\scripts\bao_installer.iss
if errorlevel 1 (
    echo [ERROR] Installer build failed!
    popd
    exit /b 1
)

echo [OK] Installer output: dist\Bao-%VERSION%-windows-x64-setup.exe
popd
