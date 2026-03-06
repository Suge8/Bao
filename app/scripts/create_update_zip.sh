#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

ARCH="$(uname -m)"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch) ARCH="$2"; shift 2 ;;
        *) shift ;;
    esac
done

case "$ARCH" in
    arm64|aarch64) ARCH="arm64" ;;
    x86_64|amd64) ARCH="x86_64" ;;
esac

APP_NAME="Bao"
APP_PATH="$PROJECT_ROOT/dist/$APP_NAME.app"

if [[ ! -d "$APP_PATH" ]]; then
    echo "❌ $APP_PATH not found. Run build_mac.sh first."
    exit 1
fi

INFO_PLIST="$APP_PATH/Contents/Info.plist"
if [[ ! -f "$INFO_PLIST" ]]; then
    echo "❌ $INFO_PLIST not found. Rebuild the app with build_mac.sh first."
    exit 1
fi

VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$INFO_PLIST")
ZIP_PATH="$PROJECT_ROOT/dist/$APP_NAME-$VERSION-macos-$ARCH-update.zip"

rm -f "$ZIP_PATH"
/usr/bin/ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

ZIP_SIZE=$(du -sh "$ZIP_PATH" | cut -f1)
echo "✅ Update zip created: $ZIP_PATH ($ZIP_SIZE)"
