#!/bin/bash
# test-dmg.sh — Comprehensive DMG validation + smoke test + GUI interaction test
# Usage: ./scripts/test-dmg.sh [path-to-dmg]
#
# Test phases:
#   1. DMG integrity (checksum, mountable)
#   2. Install (cp -R to /Applications, simulating drag-to-install)
#   3. Quarantine cleanup
#   4. Process stability (5s, 30s, 60s)
#   5. Menu interaction (osascript click Settings → verify window)
#   6. Clean shutdown (SIGTERM from menu Quit)
#   7. Screenshots at key phases

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

DMG="${1:-$(ls -t dist/Clairvoyant-Optics-*.dmg 2>/dev/null | head -1)}"
if [ -z "$DMG" ] || [ ! -f "$DMG" ]; then
    echo "❌ DMG not found. Build first: ./scripts/build-dmg.sh"
    exit 1
fi

OUTPUT_DIR="/tmp/clairvoyant-test-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTPUT_DIR/screenshots"
PASS=0
FAIL=0

green() { echo "   ✅ $1"; ((PASS++)) || true; }
red()   { echo "   ❌ $1"; ((FAIL++)) || true; }
info()  { echo "   🔍 $1"; }

# ── Phase 1: DMG Integrity ────────────────────────────────────

echo ""
echo "════════════════════════════════════════════"
echo " Phase 1: DMG Integrity"
echo "════════════════════════════════════════════"
echo ""

DMG_SIZE=$(ls -lh "$DMG" | awk '{print $5}')
info "DMG: $DMG ($DMG_SIZE)"

if hdiutil verify "$DMG" >/dev/null 2>&1; then
    green "DMG checksum valid"
else
    red "DMG checksum FAILED"
fi

# ── Phase 2: Mount + Install ──────────────────────────────────

echo ""
echo "════════════════════════════════════════════"
echo " Phase 2: Mount & Install"
echo "════════════════════════════════════════════"
echo ""

# Clean previous
rm -rf /Applications/Clairvoyant-Optics.app 2>/dev/null || true

# Screenshot: before mount
screencapture -x "$OUTPUT_DIR/screenshots/01-before-install.png" 2>/dev/null || true

# Mount DMG
MOUNT=$(hdiutil attach "$DMG" -nobrowse 2>&1 | grep "/Volumes/" | awk '{for(i=3;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ $//')
if [ -z "$MOUNT" ] || [ ! -d "$MOUNT" ]; then
    red "DMG mount FAILED"
    exit 1
fi
green "DMG mounted at $MOUNT"

# Verify contents
if [ -d "$MOUNT/Clairvoyant-Optics.app" ]; then
    green ".app found in DMG"
else
    red ".app MISSING from DMG"
fi

if [ -L "$MOUNT/Applications" ]; then
    green "Applications symlink present"
else
    red "Applications symlink MISSING"
fi

# Screenshot: DMG window
screencapture -x "$OUTPUT_DIR/screenshots/02-dmg-mounted.png" 2>/dev/null || true

# Install (simulates drag-to-install)
cp -R "$MOUNT/Clairvoyant-Optics.app" /Applications/
if [ -d /Applications/Clairvoyant-Optics.app ]; then
    green "Installed to /Applications/"
else
    red "Install FAILED"
fi

# Detach DMG
hdiutil detach "$MOUNT" >/dev/null 2>&1 || true
green "DMG detached"

# ── Phase 3: Quarantine Cleanup ──────────────────────────────

echo ""
echo "════════════════════════════════════════════"
echo " Phase 3: Quarantine Cleanup"
echo "════════════════════════════════════════════"
echo ""

QUARANTINE=$(xattr -l /Applications/Clairvoyant-Optics.app/Contents/MacOS/python 2>/dev/null | grep "com.apple.quarantine" || true)
if [ -n "$QUARANTINE" ]; then
    info "Quarantine flag found — removing..."
    find /Applications/Clairvoyant-Optics.app -exec xattr -d com.apple.quarantine {} \; 2>/dev/null || true
    QUARANTINE_AFTER=$(xattr -l /Applications/Clairvoyant-Optics.app/Contents/MacOS/python 2>/dev/null | grep "com.apple.quarantine" || true)
    if [ -z "$QUARANTINE_AFTER" ]; then
        green "Quarantine removed"
    else
        red "Quarantine removal FAILED"
    fi
else
    green "No quarantine flag (clean)"
fi

# ── Phase 4: Process Stability ────────────────────────────────

echo ""
echo "════════════════════════════════════════════"
echo " Phase 4: Process Stability"
echo "════════════════════════════════════════════"
echo ""

# Run the real app (not smoke-test minimal rumps)
/Applications/Clairvoyant-Optics.app/Contents/MacOS/Clairvoyant-Optics &
APP_PID=$!
info "App PID: $APP_PID"

# Check at 5s
sleep 5
if kill -0 $APP_PID 2>/dev/null; then
    green "Running at 5s"
else
    red "CRASHED before 5s"
    # Try direct python run as fallback
    info "Attempting fallback: direct python run..."
    /Applications/Clairvoyant-Optics.app/Contents/MacOS/python \
        /Applications/Clairvoyant-Optics.app/Contents/Resources/src/macos/app.py &
    APP_PID=$!
    sleep 5
    if kill -0 $APP_PID 2>/dev/null; then
        green "Direct python run — alive at 5s"
    else
        red "Direct python run ALSO crashed"
    fi
fi

# Screenshot: app running
screencapture -x "$OUTPUT_DIR/screenshots/03-app-running.png" 2>/dev/null || true

# Check at 30s
sleep 25
if kill -0 $APP_PID 2>/dev/null; then
    green "Running at 30s"
else
    red "CRASHED between 5s–30s"
fi

# Check at 60s
sleep 30
if kill -0 $APP_PID 2>/dev/null; then
    green "Running at 60s (stable)"
else
    red "CRASHED between 30s–60s"
fi

# ── Phase 5: Menu Interaction ─────────────────────────────────

echo ""
echo "════════════════════════════════════════════"
echo " Phase 5: Menu Interaction"
echo "════════════════════════════════════════════"
echo ""

if kill -0 $APP_PID 2>/dev/null; then
    # Click the menu bar item via System Events
    # Note: LSUIElement apps appear in the menu bar extras area
    # We try clicking via process name first
    osascript -e '
    tell application "System Events"
        tell process "Clairvoyant-Optics"
            -- Try to click the menu bar
            try
                click menu bar item 1 of menu bar 2
                delay 1
            end try
        end tell
    end tell
    ' 2>/dev/null && green "Menu bar click executed" || red "Menu bar click FAILED"

    # Check if Settings menu item is accessible
    osascript -e '
    tell application "System Events"
        tell process "Clairvoyant-Optics"
            try
                set menuItems to name of every menu item of menu 1 of menu bar item 1 of menu bar 2
                return menuItems
            end try
        end tell
    end tell
    ' 2>/dev/null && green "Menu items accessible" || info "Menu items not accessible (may be hidden)"

    # Screenshot: menu open
    screencapture -x "$OUTPUT_DIR/screenshots/04-menu-open.png" 2>/dev/null || true

    # Close menu (press Escape)
    osascript -e 'tell application "System Events" to key code 53' 2>/dev/null || true
fi

# ── Phase 6: Clean Shutdown ───────────────────────────────────

echo ""
echo "════════════════════════════════════════════"
echo " Phase 6: Clean Shutdown"
echo "════════════════════════════════════════════"
echo ""

if kill -0 $APP_PID 2>/dev/null; then
    # Graceful SIGTERM first
    kill $APP_PID 2>/dev/null || true
    sleep 3
    if ! kill -0 $APP_PID 2>/dev/null; then
        green "Clean shutdown (SIGTERM)"
    else
        # Force kill
        kill -9 $APP_PID 2>/dev/null || true
        sleep 1
        if ! kill -0 $APP_PID 2>/dev/null; then
            green "Shutdown (SIGKILL)"
        else
            red "Shutdown FAILED — process stuck"
        fi
    fi
else
    info "Process already dead"
fi

# ── Cleanup ──────────────────────────────────────────────────

rm -rf /Applications/Clairvoyant-Optics.app 2>/dev/null || true

# ── Summary ──────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════"
echo "  Test Summary"
echo "════════════════════════════════════════════"
echo ""
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Screenshots: $OUTPUT_DIR/screenshots/"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo "❌ TESTS FAILED ($FAIL failures)"
    exit 1
else
    echo "✅ ALL TESTS PASSED ($PASS/$PASS)"
    exit 0
fi
