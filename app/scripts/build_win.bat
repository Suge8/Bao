@echo off
REM ──────────────────────────────────────────────────────────
REM Bao Desktop — Windows Nuitka Build Script
REM Usage: app\scripts\build_win.bat
REM ──────────────────────────────────────────────────────────
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0..\.."
pushd "%PROJECT_ROOT%"

REM ── Version ──
for /f "usebackq delims=" %%i in (`uv run python "app\scripts\read_version.py"`) do set "VERSION=%%i"

set "APP_NAME=Bao"
set "DIST_DIR=%PROJECT_ROOT%\dist"
set "BUILD_DIR=%DIST_DIR%\build-win-x64"

echo ========================================
echo   Bao Desktop — Windows Build
echo   Version: %VERSION%
echo ========================================
echo.

REM ── Pre-flight ──
echo ^> Checking dependencies...
where uv >nul 2>nul || (echo [ERROR] uv not installed. Install uv first: https://astral.sh/uv/ & exit /b 1)
uv run python -c "import nuitka" 2>nul || (echo [ERROR] Nuitka not installed. Run: uv sync --extra desktop-build & exit /b 1)
uv run python -c "import PySide6" 2>nul || (echo [ERROR] PySide6 not installed. Run: uv sync --extra desktop-build & exit /b 1)
REM Fix PySide6.__file__=None for Nuitka compatibility
for /f "tokens=*" %%v in ('uv run python -c "import PySide6; print(PySide6.__file__)"') do set "PF=%%v"
if "%PF%"=="None" (
    echo ^> Fixing PySide6 meta-package for Nuitka compatibility...
    for /f "tokens=*" %%q in ('uv run python -c "import PySide6.QtCore; print(PySide6.QtCore.qVersion^(^))"') do set "QTV=%%q"
    uv pip install PySide6==!QTV! --no-deps --quiet
)

REM ── Clean ──
echo ^> Cleaning previous build...
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

REM ── Build ──
echo ^> Building with Nuitka (this may take several minutes)...
echo.

REM ── Parallelism ──
set "JOBS=%NUITKA_JOBS%"
if "%JOBS%"=="" set "JOBS=%NUMBER_OF_PROCESSORS%"
if "%JOBS%"=="" set "JOBS=4"

uv run python -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --jobs=%JOBS% ^
    --windows-icon-from-ico="%PROJECT_ROOT%\assets\logo.ico" ^
    --windows-company-name="Bao" ^
    --windows-product-name="Bao" ^
    --windows-product-version="%VERSION%" ^
    --windows-file-description="Bao - Your Personal AI Assistant" ^
    --enable-plugin=pyside6 ^
    --include-qt-plugins=qml ^
    --noinclude-qt-plugins=tls ^
    --include-data-dir="%PROJECT_ROOT%\app\qml=qml" ^
    --include-data-dir="%PROJECT_ROOT%\app\resources=resources" ^
    --include-data-dir="%PROJECT_ROOT%\bao\skills=data\skills" ^
    --include-package=bao.templates.workspace ^
    --include-package=bao.templates.workspace.en ^
    --include-package=bao.templates.workspace.zh ^
    --include-package-data=bao.templates.workspace.en:*.md ^
    --include-package-data=bao.templates.workspace.zh:*.md ^
    --nofollow-import-to=tkinter ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=doctest ^
    --nofollow-import-to=idlelib ^
    --nofollow-import-to=lib2to3 ^
    --nofollow-import-to=ensurepip ^
    --nofollow-import-to=distutils ^
    --nofollow-import-to=turtledemo ^
    --nofollow-import-to=test ^
    --nofollow-import-to=lark_oapi.api.acs ^
    --nofollow-import-to=lark_oapi.api.admin ^
    --nofollow-import-to=lark_oapi.api.aily ^
    --nofollow-import-to=lark_oapi.api.apaas ^
    --nofollow-import-to=lark_oapi.api.application ^
    --nofollow-import-to=lark_oapi.api.approval ^
    --nofollow-import-to=lark_oapi.api.attendance ^
    --nofollow-import-to=lark_oapi.api.auth ^
    --nofollow-import-to=lark_oapi.api.authen ^
    --nofollow-import-to=lark_oapi.api.baike ^
    --nofollow-import-to=lark_oapi.api.base ^
    --nofollow-import-to=lark_oapi.api.bitable ^
    --nofollow-import-to=lark_oapi.api.block ^
    --nofollow-import-to=lark_oapi.api.board ^
    --nofollow-import-to=lark_oapi.api.calendar ^
    --nofollow-import-to=lark_oapi.api.cardkit ^
    --nofollow-import-to=lark_oapi.api.compensation ^
    --nofollow-import-to=lark_oapi.api.contact ^
    --nofollow-import-to=lark_oapi.api.corehr ^
    --nofollow-import-to=lark_oapi.api.directory ^
    --nofollow-import-to=lark_oapi.api.docs ^
    --nofollow-import-to=lark_oapi.api.document_ai ^
    --nofollow-import-to=lark_oapi.api.docx ^
    --nofollow-import-to=lark_oapi.api.drive ^
    --nofollow-import-to=lark_oapi.api.ehr ^
    --nofollow-import-to=lark_oapi.api.event ^
    --nofollow-import-to=lark_oapi.api.gray_test_open_sg ^
    --nofollow-import-to=lark_oapi.api.helpdesk ^
    --nofollow-import-to=lark_oapi.api.hire ^
    --nofollow-import-to=lark_oapi.api.human_authentication ^
    --nofollow-import-to=lark_oapi.api.lingo ^
    --nofollow-import-to=lark_oapi.api.mail ^
    --nofollow-import-to=lark_oapi.api.mdm ^
    --nofollow-import-to=lark_oapi.api.meeting_room ^
    --nofollow-import-to=lark_oapi.api.minutes ^
    --nofollow-import-to=lark_oapi.api.moments ^
    --nofollow-import-to=lark_oapi.api.okr ^
    --nofollow-import-to=lark_oapi.api.optical_char_recognition ^
    --nofollow-import-to=lark_oapi.api.passport ^
    --nofollow-import-to=lark_oapi.api.payroll ^
    --nofollow-import-to=lark_oapi.api.performance ^
    --nofollow-import-to=lark_oapi.api.personal_settings ^
    --nofollow-import-to=lark_oapi.api.report ^
    --nofollow-import-to=lark_oapi.api.search ^
    --nofollow-import-to=lark_oapi.api.security_and_compliance ^
    --nofollow-import-to=lark_oapi.api.sheets ^
    --nofollow-import-to=lark_oapi.api.speech_to_text ^
    --nofollow-import-to=lark_oapi.api.task ^
    --nofollow-import-to=lark_oapi.api.tenant ^
    --nofollow-import-to=lark_oapi.api.translation ^
    --nofollow-import-to=lark_oapi.api.vc ^
    --nofollow-import-to=lark_oapi.api.verification ^
    --nofollow-import-to=lark_oapi.api.wiki ^
    --nofollow-import-to=lark_oapi.api.workplace ^
    --output-dir="%BUILD_DIR%" ^
    --output-filename="%APP_NAME%.exe" ^
    --assume-yes-for-downloads ^
    "%PROJECT_ROOT%\app\main.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    popd
    exit /b 1
)

echo.
echo ========================================
echo   Build complete!
echo   Output: %BUILD_DIR%\main.dist\
echo ========================================
echo.
echo Next steps:
echo   - Test: %BUILD_DIR%\main.dist\%APP_NAME%.exe
echo   - Package: app\scripts\package_win_installer.bat

popd
