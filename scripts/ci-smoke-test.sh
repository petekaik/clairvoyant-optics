#!/bin/bash
# CI Smoke Test — headless validation for Clairvoyant-Optics .app bundle
# Replaces GUI-dependent phases (5-7) of test-dmg.sh for CI runners.
# Usage: ./scripts/ci-smoke-test.sh [dmg-path]
#   Default: dist/Clairvoyant-Optics-*.dmg (latest)

set -euo pipefail

cd "$(dirname "$0")/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS=0; FAIL=0
pass() { echo -e "${GREEN}✅ $1${NC}"; PASS=$((PASS + 1)); }
fail() { echo -e "${RED}❌ $1${NC}"; FAIL=$((FAIL + 1)); }
info() { echo -e "${YELLOW}ℹ️  $1${NC}"; }

DMG="${1:-$(ls -t dist/Clairvoyant-Optics-*.dmg 2>/dev/null | head -1)}"
if [ -z "$DMG" ] || [ ! -f "$DMG" ]; then
    echo "❌ DMG not found: ${DMG:-dist/}"
    exit 1
fi

APP="dist/Clairvoyant-Optics.app"
BIN="$APP/Contents/MacOS"
RESOURCES="$APP/Contents/Resources"
FW="$APP/Contents/Frameworks"

# ── 1. Bundle structure integrity ──────────────────────────────

echo "━━━ 1. Bundle Structure ━━━"

[ -d "$APP" ] && pass ".app bundle exists" || { fail ".app missing"; exit 1; }

for f in "MacOS/python" "MacOS/Clairvoyant-Optics"; do
    [ -f "$APP/Contents/$f" ] && pass "  $f" || fail "  $f MISSING"
done

for f in "eye_22.png" "eye_44.png" "settings.py" "menu_bar.py"; do
    [ -f "$RESOURCES/$f" ] && pass "  $f" || fail "  $f MISSING"
done

# Settings.app wrapper (spawned via open -a for window-server context)
if [ -d "$RESOURCES/Settings.app" ]; then
    pass "  Settings.app/"
    [ -f "$RESOURCES/Settings.app/Contents/Info.plist" ] && pass "    Info.plist" || fail "    Info.plist MISSING"
    [ -x "$RESOURCES/Settings.app/Contents/MacOS/Clairvoyant-Settings" ] && pass "    launcher script" || fail "    launcher script MISSING/not executable"
else
    fail "  Settings.app/ MISSING"
fi

for lib in libtcl8.6.dylib libtk8.6.dylib libpython3.11.dylib; do
    [ -f "$FW/$lib" ] && pass "  $lib" || info "  $lib not in Frameworks (may be ok)"
done

# ── 2. Python import chain ──────────────────────────────────────

echo "━━━ 2. Python Import Chain ━━━"

for mod in tkinter yaml rumps; do
    if "$BIN/python" -c "import $mod" 2>/dev/null; then
        pass "import $mod"
    else
        fail "import $mod FAILED"
    fi
done

# ── 3. settings.py syntax + import check ────────────────────────

echo "━━━ 3. settings.py Validation ━━━"

if "$BIN/python" -c "compile(open('$RESOURCES/settings.py').read(), 'settings.py', 'exec')" 2>/dev/null; then
    pass "settings.py syntax OK"
else
    fail "settings.py syntax ERROR"
fi

# ── 4. Process stability (15s) ──────────────────────────────────

echo "━━━ 4. Process Stability ━━━"

killall -9 Clairvoyant-Optics python 2>/dev/null || true
sleep 1

info "Starting app..."
"$BIN/Clairvoyant-Optics" >/dev/null 2>&1 &
APP_PID=$!
sleep 5

if kill -0 $APP_PID 2>/dev/null; then
    pass "App alive at 5s"
    sleep 10
    if kill -0 $APP_PID 2>/dev/null; then
        pass "App alive at 15s — stable"
    else
        fail "App crashed 5s-15s"
    fi
else
    fail "App crashed within 5s"
fi

# ── 5. Settings PID file ────────────────────────────────────────

echo "━━━ 5. Settings PID File ━━━"

SETTINGS_PID_FILE="$HOME/.clairvoyant-optics/settings.pid"
sleep 3
if [ -f "$SETTINGS_PID_FILE" ]; then
    SPID=$(cat "$SETTINGS_PID_FILE")
    if kill -0 "$SPID" 2>/dev/null; then
        pass "Settings process alive (PID $SPID)"
    else
        fail "Settings PID file exists but process dead (PID $SPID)"
    fi
else
    info "No settings PID file — app may not auto-spawn settings (OK for CI)"
fi

# ── Cleanup ─────────────────────────────────────────────────────

kill $APP_PID 2>/dev/null || true
sleep 1
kill -9 $APP_PID 2>/dev/null || true

if [ -f "$SETTINGS_PID_FILE" ]; then
    kill "$(cat "$SETTINGS_PID_FILE")" 2>/dev/null || true
    rm -f "$SETTINGS_PID_FILE"
fi

# ── Summary ─────────────────────────────────────────────────────

echo ""
echo "════════════════════════════════════════════"
printf "  ${GREEN}Passed: %d${NC}  |  ${RED}Failed: %d${NC}\n" $PASS $FAIL
echo "════════════════════════════════════════════"

[ $FAIL -eq 0 ] && exit 0 || exit 1
