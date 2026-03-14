#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

command -v uv >/dev/null 2>&1 || { echo "❌ uv not found"; exit 1; }

ARCH="${1:---arch}"
if [[ "$ARCH" == "--arch" ]]; then
    ARCH="${2:-$(uname -m)}"
fi

case "$ARCH" in
    arm64|aarch64) ARCH="arm64" ;;
    x86_64|amd64) ARCH="x86_64" ;;
    *)
        echo "❌ Unsupported architecture: $ARCH"
        echo "   Usage: $0 --arch arm64|x86_64"
        exit 1
        ;;
esac

VERSION=$(uv run python app/scripts/read_version.py)
BUNDLE_IDENTIFIER="io.github.suge8.bao"
APPLE_EVENTS_USAGE_DESCRIPTION="Bao needs Automation permission to send messages and media through Messages.app."
CODESIGN_IDENTITY="${BAO_MAC_CODESIGN_IDENTITY:--}"

plist_set_or_add() {
    local plist_path="$1"
    local key="$2"
    local value="$3"

    /usr/libexec/PlistBuddy -c "Set :$key \"$value\"" "$plist_path" >/dev/null 2>&1 || \
        /usr/libexec/PlistBuddy -c "Add :$key string \"$value\"" "$plist_path"
}

plist_require_key() {
    local plist_path="$1"
    local key="$2"

    /usr/libexec/PlistBuddy -c "Print :$key" "$plist_path" >/dev/null 2>&1 || {
        echo "❌ Missing required Info.plist key: $key"
        exit 1
    }
}

resign_app_bundle() {
    local app_path="$1"

    echo "▸ Re-signing app bundle after Info.plist updates..."
    if [[ "$CODESIGN_IDENTITY" == "-" ]]; then
        /usr/bin/codesign --force --deep --sign "$CODESIGN_IDENTITY" "$app_path"
        return
    fi

    /usr/bin/codesign --force --deep --options runtime --timestamp --sign "$CODESIGN_IDENTITY" "$app_path"
}

APP_NAME="Bao"
BUILD_ROOT="$PROJECT_ROOT/dist-pyinstaller"
DIST_DIR="$BUILD_ROOT/dist"
WORK_DIR="$BUILD_ROOT/build-mac-$ARCH"
SPEC_DIR="$BUILD_ROOT/spec-mac-$ARCH"
OUTPUT_APP="$DIST_DIR/$APP_NAME.app"

echo "╔══════════════════════════════════════════╗"
echo "║  Bao Desktop — macOS PyInstaller Build  ║"
echo "║  Version: $VERSION"
echo "║  Arch:    $ARCH"
echo "╚══════════════════════════════════════════╝"
echo ""

echo "▸ Checking dependencies..."
uv run python -c "import PyInstaller" 2>/dev/null || {
    echo "❌ PyInstaller not installed. Run: uv sync --extra desktop-build-pyinstaller"
    exit 1
}
uv run python -c "import PySide6" 2>/dev/null || {
    echo "❌ PySide6 not installed. Run: uv sync --extra desktop-build-pyinstaller"
    exit 1
}

if [[ -n "${BAO_BROWSER_RUNTIME_SOURCE_DIR:-}" ]]; then
    echo "▸ Syncing managed browser runtime from $BAO_BROWSER_RUNTIME_SOURCE_DIR ..."
    uv run python app/scripts/sync_browser_runtime.py --source "$BAO_BROWSER_RUNTIME_SOURCE_DIR"
fi

echo "▸ Verifying managed browser runtime ..."
uv run python app/scripts/verify_browser_runtime.py --require-ready

echo "▸ Cleaning previous PyInstaller build..."
rm -rf "$WORK_DIR" "$SPEC_DIR" "$OUTPUT_APP"
mkdir -p "$DIST_DIR" "$WORK_DIR" "$SPEC_DIR"

START_TS=$(python3 -c 'import time; print(int(time.time()))')

echo "▸ Building with PyInstaller onedir..."
echo ""

uv run pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --distpath "$DIST_DIR" \
    --workpath "$WORK_DIR" \
    --specpath "$SPEC_DIR" \
    --target-architecture "$ARCH" \
    --osx-bundle-identifier "$BUNDLE_IDENTIFIER" \
    --icon "$PROJECT_ROOT/assets/logo.icns" \
    --add-data "$PROJECT_ROOT/app/qml:app/qml" \
    --add-data "$PROJECT_ROOT/app/resources:app/resources" \
    --add-data "$PROJECT_ROOT/assets:assets" \
    --add-data "$PROJECT_ROOT/bao/skills:bao/skills" \
    --add-data "$PROJECT_ROOT/bao/templates/workspace:bao/templates/workspace" \
    --collect-all lancedb \
    --collect-all pyarrow \
    --collect-submodules bao.channels \
    --collect-submodules bao.providers \
    --collect-submodules bao.skills \
    --collect-submodules bao.agent.tools \
    --exclude-module tkinter \
    --exclude-module unittest \
    --exclude-module doctest \
    --exclude-module idlelib \
    --exclude-module lib2to3 \
    --exclude-module ensurepip \
    --exclude-module distutils \
    --exclude-module turtledemo \
    --exclude-module test \
    --exclude-module pytest \
    --exclude-module _pytest \
    "$PROJECT_ROOT/app/main.py"

if [[ ! -d "$OUTPUT_APP" ]]; then
    echo "❌ Build failed: $OUTPUT_APP not found"
    exit 1
fi

INFO_PLIST="$OUTPUT_APP/Contents/Info.plist"
if [[ -f "$INFO_PLIST" ]]; then
    plist_set_or_add "$INFO_PLIST" "CFBundleShortVersionString" "$VERSION"
    plist_set_or_add "$INFO_PLIST" "CFBundleVersion" "$VERSION"
    plist_set_or_add "$INFO_PLIST" "CFBundleIdentifier" "$BUNDLE_IDENTIFIER"
    plist_set_or_add "$INFO_PLIST" "NSAppleEventsUsageDescription" "$APPLE_EVENTS_USAGE_DESCRIPTION"
    plist_require_key "$INFO_PLIST" "CFBundleIdentifier"
    plist_require_key "$INFO_PLIST" "NSAppleEventsUsageDescription"
    resign_app_bundle "$OUTPUT_APP"
else
    echo "❌ Build failed: $INFO_PLIST not found"
    exit 1
fi

END_TS=$(python3 -c 'import time; print(int(time.time()))')
DURATION_SEC=$((END_TS - START_TS))
APP_SIZE=$(du -sh "$OUTPUT_APP" | cut -f1)

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ PyInstaller build complete!         ║"
echo "║  Output: $OUTPUT_APP"
echo "║  Size:   $APP_SIZE"
echo "║  Time:   ${DURATION_SEC}s"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  • Smoke: QT_QPA_PLATFORM=offscreen \"$OUTPUT_APP/Contents/MacOS/$APP_NAME\" --smoke"
echo "  • Open:  open \"$OUTPUT_APP\""
