#!/bin/bash
# Build script — builds .app bundle and packages as .dmg
# Usage: ./scripts/build-dmg.sh [version]
# Requirements: py2app, create-dmg (brew install create-dmg)

set -euo pipefail

VERSION="${1:-$(python3 -c 'from src.version import VERSION; print(VERSION)')}"
echo "🔨 Building Clairvoyant-Optics v${VERSION}"

cd "$(dirname "$0")/.."

# Clean previous builds
rm -rf dist build

# Install deps
pip install py2app 2>/dev/null || true

# Build .app bundle
python3 setup.py py2app

APP="dist/Clairvoyant-Optics.app"
if [ ! -d "$APP" ]; then
    echo "ERROR: .app not built"
    exit 1
fi

echo "✅ .app bundle built: $APP"

# Create icon if missing
if [ ! -f assets/icon.icns ]; then
    mkdir -p assets
    # Generate a minimal 1x1 icon placeholder — replace with real icon
    echo "⚠ No icon found — generating placeholder"
    python3 -c "
import struct, pathlib
# Minimal .icns with 1 icon type
icns = b'icns' + struct.pack('>I', 0)  # Will fix size later
pathlib.Path('assets/icon.icns').write_bytes(icns)
echo 'Placeholder icon created: assets/icon.icns'
" || touch assets/icon.icns
fi

# Package as .dmg
DMG="dist/Clairvoyant-Optics-${VERSION}.dmg"

if command -v create-dmg &>/dev/null; then
    create-dmg \
        --volname "Clairvoyant-Optics" \
        --volicon "assets/icon.icns" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "Clairvoyant-Optics.app" 150 190 \
        --hide-extension "Clairvoyant-Optics.app" \
        --app-drop-link 450 190 \
        "$DMG" \
        "$APP"
    echo "✅ DMG created: $DMG"
elif command -v hdiutil &>/dev/null; then
    echo "⚠ create-dmg not found, using basic hdiutil..."
    hdiutil create -volname "Clairvoyant-Optics" -srcfolder "dist" -ov -format UDZO "$DMG"
    echo "✅ DMG created (basic): $DMG"
else
    echo "⚠ Neither create-dmg nor hdiutil found — no DMG created"
    echo "Install create-dmg: brew install create-dmg"
fi

# Show result
echo ""
echo "Build complete:"
ls -lh dist/

# Optional: codesign (requires Apple Developer cert)
# codesign --deep --force --verify --verbose --sign "Developer ID Application" "$APP"
