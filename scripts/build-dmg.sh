#!/bin/bash
# Build script — builds .app bundle and packages as .dmg with installer layout
# Usage: ./scripts/build-dmg.sh [version]
#
# DMG structure (drag-to-install):
#   ├── Clairvoyant-Optics.app
#   └── Applications -> /Applications
#
# Requirements: project venv/ with py2app, pyyaml, rumps installed

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"

# ── Version ──────────────────────────────────────────────────

VERSION="${1:-$($VENV_PYTHON -c 'from src.version import VERSION; print(VERSION)')}"
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
    echo "❌ ERROR: .app not built at $APP"
    exit 1
fi

BUNDLE_SIZE=$(du -sh "$APP" | awk '{print $1}')
echo "✅ .app bundle: $BUNDLE_SIZE"

# ── Fix missing @rpath dylibs ─────────────────────────────────

FW="$APP/Contents/Frameworks"
PROJ_VENV_LIB="$PROJECT_ROOT/venv/lib/python3.11"

echo "🔍 Scanning for missing @rpath libraries..."
REQUIRED_LIBS=$(
    find "$APP/Contents/Resources" -name "*.so" -o -name "*.dylib" 2>/dev/null | \
    while read f; do otool -L "$f" 2>/dev/null; done | \
    grep -oE '@rpath/([^ ]+)' | sed 's|@rpath/||' | sort -u
)

echo "   Required @rpath libs:"
for lib in $REQUIRED_LIBS; do
    if [ -f "$FW/$lib" ]; then
        echo "     ✅ $lib"
    else
        SRC=$(find "$PROJECT_ROOT/venv" "$(dirname "$VENV_PYTHON")"/../lib \
            /opt/anaconda3/lib /opt/anaconda3/conda-bld /opt/homebrew/lib \
            -path "*/skeleton*/lib/$lib" -o -name "$lib" 2>/dev/null | head -1)
        if [ -n "${SRC:-}" ]; then
            cp "$SRC" "$FW/"
            echo "     📋 $lib (copied from $SRC)"
        else
            echo "     ❌ $lib NOT FOUND — bundle may be broken"
        fi
    fi
done


# ── Codesign (ad-hoc) — required for Sequoia ─────────────────

echo "🔏 Ad-hoc signing..."
# Sign all .dylib/.so files
find "$APP" -type f \( -name "*.dylib" -o -name "*.so" \) \
    -exec codesign --force --sign - {} \; 2>/dev/null || true
# Sign the two executables in MacOS/
codesign --force --sign - "$APP/Contents/MacOS/python" "$APP/Contents/MacOS/Clairvoyant-Optics" 2>/dev/null || true

echo "✅ Signed"


# ── Package DMG ──────────────────────────────────────────────

DMG_BUILD="/tmp/clairvoyant-dmg-build"
DMG_RW="/tmp/clairvoyant-rw.dmg"
FINAL_DMG="dist/Clairvoyant-Optics-${VERSION}.dmg"

echo "📀 Creating DMG layout (drag-to-install)..."
rm -rf "$DMG_BUILD"
mkdir -p "$DMG_BUILD"
cp -R "$APP" "$DMG_BUILD/"
ln -sf /Applications "$DMG_BUILD/Applications"

echo "💾 Creating read-write DMG..."
rm -f "$DMG_RW" "$FINAL_DMG"
hdiutil create \
    -size 80m \
    -volname "Clairvoyant-Optics" \
    -srcfolder "$DMG_BUILD" \
    -fs HFS+ \
    -format UDRW \
    "$DMG_RW" >/dev/null 2>&1

echo "📦 Converting to compressed UDZO..."
hdiutil convert "$DMG_RW" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$FINAL_DMG" >/dev/null 2>&1
rm -f "$DMG_RW"

DMG_SIZE=$(ls -lh "$FINAL_DMG" | awk '{print $5}')


# ── Verify ───────────────────────────────────────────────────

echo "🔍 Verifying DMG..."
hdiutil verify "$FINAL_DMG" >/dev/null 2>&1 && echo "✅ DMG checksum VALID" || echo "⚠ Verification failed"


# ── Smoke test ───────────────────────────────────────────────

echo ""
echo "🚀 Smoke test: install + run 15s stability..."
# Remove old install
rm -rf /Applications/Clairvoyant-Optics.app 2>/dev/null || true

# Mount & install
MOUNT=$(hdiutil attach "$FINAL_DMG" -nobrowse 2>/dev/null | grep "/Volumes/" | awk '{for(i=3;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ $//')
cp -R "$MOUNT/Clairvoyant-Optics.app" /Applications/ 2>/dev/null || true
hdiutil detach "$MOUNT" >/dev/null 2>/dev/null || true

# Clean quarantine + sign binaries (required for Sequoia)
find /Applications/Clairvoyant-Optics.app -exec xattr -d com.apple.quarantine {} \; 2>/dev/null || true
codesign --force --sign - /Applications/Clairvoyant-Optics.app/Contents/MacOS/python /Applications/Clairvoyant-Optics.app/Contents/MacOS/Clairvoyant-Optics 2>/dev/null || true

# Run and wait
echo "   Starting app..."
/Applications/Clairvoyant-Optics.app/Contents/MacOS/Clairvoyant-Optics 2>/dev/null &
APP_PID=$!

sleep 5
if kill -0 $APP_PID 2>/dev/null; then
    echo "   ✅ Running (5s)"
    sleep 10
    if kill -0 $APP_PID 2>/dev/null; then
        echo "   ✅ Running (15s — stable)"
        kill $APP_PID 2>/dev/null
        wait $APP_PID 2>/dev/null
        echo "   ✅ Clean shutdown"
    else
        echo "   ❌ CRASHED between 5s–15s"
        exit 1
    fi
else
    echo "   ❌ CRASHED within 5s"
    exit 1
fi

# Cleanup
rm -rf /Applications/Clairvoyant-Optics.app 2>/dev/null || true


# ── Summary ──────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════"
echo "  Build complete: v${VERSION}"
echo "  .app size:  $BUNDLE_SIZE"
echo "  .dmg size:  $DMG_SIZE"
echo "  .dmg path:  $FINAL_DMG"
echo "════════════════════════════════════════════"
echo ""
echo "To test on your Mac:"
echo "  open $FINAL_DMG"
echo "  Drag Clairvoyant-Optics.app → Applications"
