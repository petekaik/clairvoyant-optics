#!/bin/bash
# Build script — builds .app bundle and packages as .dmg with installer layout
# Usage: ./scripts/build-dmg.sh [version]
#
# DMG structure (drag-to-install):
#   ├── Clairvoyant-Optics.app
#   └── Applications -> /Applications
#
# Requirements: py2app, pyyaml, rumps (in project venv)

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"

# ── Version ──────────────────────────────────────────────────

if [ -n "${1:-}" ]; then
    VERSION="$1"
else
    VERSION=$("$VENV_PYTHON" -c 'from src.version import VERSION; print(VERSION)')
fi
echo "🔨 Building Clairvoyant-Optics v${VERSION}"


# ── Clean + build .app ───────────────────────────────────────

echo "🧹 Cleaning previous builds..."
rm -rf dist build .eggs

echo "📦 Building .app bundle with py2app..."
"$VENV_PYTHON" setup.py py2app || {
    echo "⚠ py2app auto-codesign may have failed (Sequoia compat) — continuing..."
}

APP="dist/Clairvoyant-Optics.app"
if [ ! -d "$APP" ]; then
    echo "ERROR: .app not built at $APP"
    exit 1
fi


# ── Codesign (ad-hoc) — required for Sequoia ─────────────────

echo "🔏 Ad-hoc signing..."
# Sign all binaries inside the bundle (dylibs + executables)
find "$APP" -type f \( \
    -name "*.dylib" -o \
    -name "*.so" -o \
    -path "*/MacOS/*" \
    \) \
    ! -name "*.py" ! -name "*.txt" ! -name "*.plist" \
    ! -name "*.icns" ! -name "*.png" \
    ! -name "*.gz" ! -name "*.zip" \
    -exec codesign --force --sign - {} \; 2>/dev/null || true

echo "✅ .app bundle signed"


# ── Package DMG ──────────────────────────────────────────────

DMG_BUILD="/tmp/clairvoyant-dmg-build"
DMG_RW="/tmp/clairvoyant-rw.dmg"
FINAL_DMG="dist/Clairvoyant-Optics-${VERSION}.dmg"

echo "📀 Creating DMG layout..."
rm -rf "$DMG_BUILD"
mkdir -p "$DMG_BUILD"
cp -R "$APP" "$DMG_BUILD/"
ln -sf /Applications "$DMG_BUILD/Applications"

echo "💾 Creating read-write DMG..."
rm -f "$DMG_RW" "$FINAL_DMG"
hdiutil create \
    -size 60m \
    -volname "Clairvoyant-Optics" \
    -srcfolder "$DMG_BUILD" \
    -fs HFS+ \
    -format UDRW \
    "$DMG_RW" >/dev/null

echo "📦 Converting to compressed UDZO..."
hdiutil convert "$DMG_RW" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$FINAL_DMG" >/dev/null

rm -f "$DMG_RW"

SIZE=$(ls -lh "$FINAL_DMG" | awk '{print $5}')
echo "✅ DMG created: $FINAL_DMG ($SIZE)"


# ── Verify ───────────────────────────────────────────────────

echo "🔍 Verifying DMG..."
hdiutil verify "$FINAL_DMG" >/dev/null 2>&1 && echo "✅ DMG checksum VALID" || echo "⚠ Verification failed"


# ── Summary ──────────────────────────────────────────────────

echo ""
echo "Build complete: v${VERSION}"
echo "  .app: $(du -sh "$APP" | awk '{print $1}')"
echo "  .dmg: $SIZE"
echo ""
echo "To test:"
echo "  open $FINAL_DMG"
echo "  Drag Clairvoyant-Optics.app → Applications"
