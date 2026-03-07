@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0..\.."
set "PYINSTALLER_BUILD_ROOT=%PROJECT_ROOT%\dist-pyinstaller\dist\Bao"
set "NUITKA_BUILD_ROOT=%PROJECT_ROOT%\dist\build-win-x64\main.dist"
set "REQUIRE_PRIMARY=0"
if exist "%PYINSTALLER_BUILD_ROOT%\Bao.exe" (
    set "BUILD_ROOT=%PYINSTALLER_BUILD_ROOT%"
) else (
    if /I "%BAO_DESKTOP_REQUIRE_PRIMARY%"=="1" (
        echo [ERROR] PyInstaller primary output missing: %PYINSTALLER_BUILD_ROOT%\Bao.exe
        exit /b 1
    )
    set "BUILD_ROOT=%NUITKA_BUILD_ROOT%"
)

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--require-primary" (
    set "REQUIRE_PRIMARY=1"
    shift
    goto parse_args
)
if /I "%~1"=="--build-root" (
    if "%~2"=="" (
        echo [ERROR] Missing value for --build-root
        exit /b 1
    )
    set "BUILD_ROOT=%~2"
    shift
    shift
    goto parse_args
)
shift
goto parse_args

:args_done
pushd "%PROJECT_ROOT%"

where uv >nul 2>nul || (
    echo [ERROR] uv not installed. Install uv first: https://astral.sh/uv/
    popd
    exit /b 1
)

if "%REQUIRE_PRIMARY%"=="1" if not exist "%PYINSTALLER_BUILD_ROOT%\Bao.exe" (
    echo [ERROR] PyInstaller primary output missing: %PYINSTALLER_BUILD_ROOT%\Bao.exe
    popd
    exit /b 1
)

if not exist "%BUILD_ROOT%\Bao.exe" (
    echo [ERROR] Build output missing: %BUILD_ROOT%\Bao.exe
    popd
    exit /b 1
)

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
set "ISCC_EXE="
for /f "usebackq delims=" %%i in (`uv run python "app\scripts\resolve_inno_setup.py"`) do set "ISCC_EXE=%%i"
if errorlevel 1 (
    echo [ERROR] Inno Setup compiler resolution failed!
    popd
    exit /b 1
)
if not defined ISCC_EXE (
    echo [ERROR] Inno Setup compiler with required language files not found!
    popd
    exit /b 1
)

"%ISCC_EXE%" /DMyAppVersion=%VERSION% "/DBuildSource=%BUILD_ROOT%" app\scripts\bao_installer.iss
if errorlevel 1 (
    echo [ERROR] Installer build failed!
    popd
    exit /b 1
)

echo [OK] Installer output: dist\Bao-%VERSION%-windows-x64-setup.exe
popd
