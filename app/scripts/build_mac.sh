#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Bao Desktop — macOS Nuitka Build Script
# Usage: bash app/scripts/build_mac.sh [--arch arm64|x86_64]
# ──────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

command -v uv >/dev/null 2>&1 || { echo "❌ uv not found"; exit 1; }

# ── Parse args ──
ARCH="${1:---arch}"
if [[ "$ARCH" == "--arch" ]]; then
    ARCH="${2:-$(uname -m)}"
fi

# Normalize arch name
case "$ARCH" in
    arm64|aarch64) ARCH="arm64" ;;
    x86_64|amd64)  ARCH="x86_64" ;;
    *)
        echo "❌ Unsupported architecture: $ARCH"
        echo "   Usage: $0 --arch arm64|x86_64"
        exit 1
        ;;
esac

# ── Version ──
VERSION=$(uv run python app/scripts/read_version.py)

APP_NAME="Bao"
DIST_DIR="$PROJECT_ROOT/dist"
BUILD_DIR="$DIST_DIR/build-mac-$ARCH"
OUTPUT_APP="$DIST_DIR/$APP_NAME.app"

echo "╔══════════════════════════════════════════╗"
echo "║  Bao Desktop — macOS Build              ║"
echo "║  Version: $VERSION"
echo "║  Arch:    $ARCH"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Pre-flight checks ──
echo "▸ Checking dependencies..."
uv run python -c "import nuitka" 2>/dev/null || { echo "❌ Nuitka not installed. Run: uv pip install nuitka ordered-set zstandard"; exit 1; }
uv run python -c "import PySide6" 2>/dev/null || { echo "❌ PySide6 not installed. Run: uv sync --extra desktop"; exit 1; }

# Nuitka's pyside6 plugin requires PySide6.__file__ to be set.
# PySide6-Essentials alone leaves __file__=None (no __init__.py).
# Fix: install the PySide6 meta-package without pulling in Addons.
PYSIDE6_FILE=$(uv run python -c "import PySide6; print(PySide6.__file__)" 2>/dev/null)
if [[ "$PYSIDE6_FILE" == "None" || -z "$PYSIDE6_FILE" ]]; then
    echo "▸ Fixing PySide6 meta-package for Nuitka compatibility..."
    uv pip install PySide6==$(uv run python -c "import PySide6.QtCore; print(PySide6.QtCore.qVersion())") --no-deps --quiet
fi

# Remove broken QML plugins that reference frameworks only in PySide6-Addons.
# PySide6-Essentials ships these plugins but lacks the required .framework files,
# causing Nuitka FATAL errors during DLL path resolution.
PYSIDE6_DIR=$(uv run python -c "import PySide6, os; print(os.path.dirname(PySide6.__file__))" 2>/dev/null)
if [[ -d "$PYSIDE6_DIR/Qt/qml" ]]; then
    BROKEN_PLUGINS=(
        "QtQml/StateMachine"
        "QtQml/XmlListModel"
        "QtQml/WorkerScript"
        "QtQuick/Pdf"
        "QtQuick/Scene2D"
        "QtQuick/Scene3D"
        "QtQuick/Shapes/DesignHelpers"
        "QtQuick/VirtualKeyboard"
    )
    for plugin in "${BROKEN_PLUGINS[@]}"; do
        target="$PYSIDE6_DIR/Qt/qml/$plugin"
        if [[ -d "$target" ]]; then
            echo "\u25b8 Removing broken QML plugin: $plugin"
            rm -rf "$target"
        fi
    done
fi

# ── Clean previous build ──
echo "▸ Cleaning previous build..."
rm -rf "$BUILD_DIR" "$OUTPUT_APP"
mkdir -p "$DIST_DIR"

JOBS="${NUITKA_JOBS:-}"
if [[ -z "$JOBS" ]]; then
    if command -v sysctl >/dev/null 2>&1; then
        JOBS="$(sysctl -n hw.ncpu 2>/dev/null || true)"
    fi
    if [[ -z "$JOBS" ]] && command -v getconf >/dev/null 2>&1; then
        JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
    fi
fi
if [[ -z "$JOBS" || ! "$JOBS" =~ ^[0-9]+$ || "$JOBS" -lt 1 ]]; then
    JOBS=4
fi

# ── Build with Nuitka ──
echo "▸ Building with Nuitka (this may take several minutes)..."
echo ""

uv run python -m nuitka \
    --standalone \
    --jobs="$JOBS" \
    --macos-create-app-bundle \
    --macos-app-icon="$PROJECT_ROOT/assets/logo.icns" \
    --macos-app-name="$APP_NAME" \
    --macos-app-version="$VERSION" \
    --enable-plugin=pyside6 \
    --include-qt-plugins=qml \
    --noinclude-dlls='*QtTest*' \
    --include-data-dir="$PROJECT_ROOT/app/qml=qml" \
    --include-data-dir="$PROJECT_ROOT/app/resources=resources" \
    --include-data-dir="$PROJECT_ROOT/bao/skills=data/skills" \
    --include-data-dir="$PROJECT_ROOT/bao/templates/workspace=bao/templates/workspace" \
    --nofollow-import-to=tkinter \
    --nofollow-import-to=unittest \
    --nofollow-import-to=doctest \
    --nofollow-import-to=idlelib \
    --nofollow-import-to=lib2to3 \
    --nofollow-import-to=ensurepip \
    --nofollow-import-to=distutils \
    --nofollow-import-to=turtledemo \
    --nofollow-import-to=test \
    --nofollow-import-to=pytest \
    --nofollow-import-to=_pytest \
    \
    `# ── lark_oapi (飞书 SDK) 裁剪：只保留 im 模块，排除其余 54 个 API 模块 ──` \
    --nofollow-import-to=lark_oapi.api.acs \
    --nofollow-import-to=lark_oapi.api.admin \
    --nofollow-import-to=lark_oapi.api.aily \
    --nofollow-import-to=lark_oapi.api.apaas \
    --nofollow-import-to=lark_oapi.api.application \
    --nofollow-import-to=lark_oapi.api.approval \
    --nofollow-import-to=lark_oapi.api.attendance \
    --nofollow-import-to=lark_oapi.api.auth \
    --nofollow-import-to=lark_oapi.api.authen \
    --nofollow-import-to=lark_oapi.api.baike \
    --nofollow-import-to=lark_oapi.api.base \
    --nofollow-import-to=lark_oapi.api.bitable \
    --nofollow-import-to=lark_oapi.api.block \
    --nofollow-import-to=lark_oapi.api.board \
    --nofollow-import-to=lark_oapi.api.calendar \
    --nofollow-import-to=lark_oapi.api.cardkit \
    --nofollow-import-to=lark_oapi.api.compensation \
    --nofollow-import-to=lark_oapi.api.contact \
    --nofollow-import-to=lark_oapi.api.corehr \
    --nofollow-import-to=lark_oapi.api.directory \
    --nofollow-import-to=lark_oapi.api.docs \
    --nofollow-import-to=lark_oapi.api.document_ai \
    --nofollow-import-to=lark_oapi.api.docx \
    --nofollow-import-to=lark_oapi.api.drive \
    --nofollow-import-to=lark_oapi.api.ehr \
    --nofollow-import-to=lark_oapi.api.event \
    --nofollow-import-to=lark_oapi.api.gray_test_open_sg \
    --nofollow-import-to=lark_oapi.api.helpdesk \
    --nofollow-import-to=lark_oapi.api.hire \
    --nofollow-import-to=lark_oapi.api.human_authentication \
    --nofollow-import-to=lark_oapi.api.lingo \
    --nofollow-import-to=lark_oapi.api.mail \
    --nofollow-import-to=lark_oapi.api.mdm \
    --nofollow-import-to=lark_oapi.api.meeting_room \
    --nofollow-import-to=lark_oapi.api.minutes \
    --nofollow-import-to=lark_oapi.api.moments \
    --nofollow-import-to=lark_oapi.api.okr \
    --nofollow-import-to=lark_oapi.api.optical_char_recognition \
    --nofollow-import-to=lark_oapi.api.passport \
    --nofollow-import-to=lark_oapi.api.payroll \
    --nofollow-import-to=lark_oapi.api.performance \
    --nofollow-import-to=lark_oapi.api.personal_settings \
    --nofollow-import-to=lark_oapi.api.report \
    --nofollow-import-to=lark_oapi.api.search \
    --nofollow-import-to=lark_oapi.api.security_and_compliance \
    --nofollow-import-to=lark_oapi.api.sheets \
    --nofollow-import-to=lark_oapi.api.speech_to_text \
    --nofollow-import-to=lark_oapi.api.task \
    --nofollow-import-to=lark_oapi.api.tenant \
    --nofollow-import-to=lark_oapi.api.translation \
    --nofollow-import-to=lark_oapi.api.vc \
    --nofollow-import-to=lark_oapi.api.verification \
    --nofollow-import-to=lark_oapi.api.wiki \
    --nofollow-import-to=lark_oapi.api.workplace \
    --output-dir="$BUILD_DIR" \
    --output-filename="$APP_NAME" \
    --assume-yes-for-downloads \
    "$PROJECT_ROOT/app/main.py"

# ── Locate the .app bundle ──
BUILT_APP=$(find "$BUILD_DIR" -name "*.app" -maxdepth 2 | head -1)
if [[ -z "$BUILT_APP" ]]; then
    echo "❌ Build failed: .app bundle not found in $BUILD_DIR"
    exit 1
fi

# ── Move to dist/ ──
mv "$BUILT_APP" "$OUTPUT_APP"

# ── Report ──
APP_SIZE=$(du -sh "$OUTPUT_APP" | cut -f1)
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ Build complete!                      ║"
echo "║  Output: $OUTPUT_APP"
echo "║  Size:   $APP_SIZE"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  • Test:    open \"$OUTPUT_APP\""
echo "  • Package: bash app/scripts/create_dmg.sh --arch $ARCH"
