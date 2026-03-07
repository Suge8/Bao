#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Bao Desktop — macOS DMG Installer Creator
# Usage: bash app/scripts/create_dmg.sh [--arch arm64|x86_64] [--app-path /path/to/Bao.app]
# Requires: brew install create-dmg
# ──────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# ── Parse args ──
ARCH="$(uname -m)"
APP_PATH=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch) ARCH="$2"; shift 2 ;;
        --app-path) APP_PATH="$2"; shift 2 ;;
        *) shift ;;
    esac
done

case "$ARCH" in
    arm64|aarch64) ARCH="arm64" ;;
    x86_64|amd64)  ARCH="x86_64" ;;
esac

APP_NAME="Bao"
if [[ -z "$APP_PATH" ]]; then
    PYINSTALLER_APP_PATH="$PROJECT_ROOT/dist-pyinstaller/dist/$APP_NAME.app"
    NUITKA_APP_PATH="$PROJECT_ROOT/dist/$APP_NAME.app"
    if [[ -d "$PYINSTALLER_APP_PATH" ]]; then
        APP_PATH="$PYINSTALLER_APP_PATH"
    else
        APP_PATH="$NUITKA_APP_PATH"
    fi
fi
DMG_TEMP="$PROJECT_ROOT/dist/dmg-staging"

# ── Pre-flight ──
command -v create-dmg >/dev/null 2>&1 || {
    echo "❌ create-dmg not found. Run: brew install create-dmg"
    exit 1
}

if [[ ! -d "$APP_PATH" ]]; then
    echo "❌ $APP_PATH not found. Run the mac build first."
    exit 1
fi

INFO_PLIST="$APP_PATH/Contents/Info.plist"
if [[ ! -f "$INFO_PLIST" ]]; then
    echo "❌ $INFO_PLIST not found. Rebuild the app first."
    exit 1
fi

VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$INFO_PLIST")
DMG_NAME="$APP_NAME-$VERSION-macos-$ARCH"
DMG_PATH="$PROJECT_ROOT/dist/$DMG_NAME.dmg"

echo "╔══════════════════════════════════════════╗"
echo "║  Bao Desktop — DMG Creator              ║"
echo "║  Version: $VERSION ($ARCH)"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Clean ──
rm -rf "$DMG_TEMP" "$DMG_PATH"
mkdir -p "$DMG_TEMP"
cp -R "$APP_PATH" "$DMG_TEMP/"

# ── Create DMG ──
echo "▸ Creating DMG installer..."
echo ""

create-dmg \
    --volname "$APP_NAME" \
    --volicon "$PROJECT_ROOT/assets/logo.icns" \
    --background "$PROJECT_ROOT/app/resources/dmg-background.png" \
    --window-pos 200 120 \
    --window-size 660 400 \
    --icon-size 120 \
    --icon "$APP_NAME.app" 160 205 \
    --app-drop-link 500 205 \
    --hide-extension "$APP_NAME.app" \
    --no-internet-enable \
    "$DMG_PATH" \
    "$DMG_TEMP/"

# ── Clean staging ──
rm -rf "$DMG_TEMP"

# ── Report ──
DMG_SIZE=$(du -sh "$DMG_PATH" | cut -f1)
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ DMG created!                         ║"
echo "║  Output: $DMG_PATH"
echo "║  Size:   $DMG_SIZE"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "To sign & notarize:"
echo "  codesign --deep --force --sign \"Developer ID\" \"$APP_PATH\""
echo "  xcrun notarytool submit \"$DMG_PATH\" --apple-id ID --team-id TEAM --password PWD"
