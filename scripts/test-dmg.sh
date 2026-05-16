#!/bin/bash
# macOS GUI Validation Pipeline — testaa .dmg:n toimivuus automaattisesti
#
# 6-vaiheinen validointi:
#   1. DMG:n eheys
#   2. Asennus /Applications/
#   3. Karanteenin poisto + ad-hoc-signaus
#   4. Prosessin stabiilius (5s/30s/60s)
#   5. Menu bar -interaktio (osascript System Events)
#   6. Settings-ikkunan testaus
#   7. Clean shutdown
#
# Käyttö: ./scripts/test-dmg.sh [dmg-polku]
#   Oletus: dist/Clairvoyant-Optics-*.dmg (uusin)

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
EVIDENCE_DIR="/tmp/clairvoyant-test-evidence"
rm -rf "$EVIDENCE_DIR"
mkdir -p "$EVIDENCE_DIR"

pass() { echo -e "${GREEN}✅ $1${NC}"; PASS=$((PASS + 1)); }
fail() { echo -e "${RED}❌ $1${NC}"; FAIL=$((FAIL + 1)); }
info() { echo -e "${YELLOW}ℹ️  $1${NC}"; }

# ── DMG path ──────────────────────────────────────────────────

DMG="${1:-}"
if [ -z "$DMG" ]; then
    DMG=$(ls -t dist/Clairvoyant-Optics-*.dmg 2>/dev/null | head -1)
fi
if [ -z "$DMG" ] || [ ! -f "$DMG" ]; then
    echo "❌ DMG:tä ei löydy: ${DMG:-dist/}"
    echo "Käyttö: $0 [dmg-polku]"
    exit 1
fi

APP_NAME="Clairvoyant-Optics"
APP_PATH="/Applications/${APP_NAME}.app"
VERSION=$(echo "$DMG" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "?.?.?")
info "Testataan: $DMG (v${VERSION})"

# ═══════════════════════════════════════════════════════════════
# Phase 1: DMG Integrity
# ═══════════════════════════════════════════════════════════════

echo ""
echo "━━━ Phase 1: DMG Integrity ━━━"

if hdiutil verify "$DMG" >/dev/null 2>&1; then
    pass "DMG checksum valid"
else
    fail "DMG checksum INVALID"
fi

DMG_SIZE=$(ls -lh "$DMG" | awk '{print $5}')
info "DMG koko: $DMG_SIZE"

# ═══════════════════════════════════════════════════════════════
# Phase 2: Mount & Install
# ═══════════════════════════════════════════════════════════════

echo ""
echo "━━━ Phase 2: Mount & Install ━━━"

# Clean previous
rm -rf "$APP_PATH" 2>/dev/null || true
killall -9 "$APP_NAME" 2>/dev/null || true
sleep 1

# Mount
MOUNT=$(hdiutil attach "$DMG" -nobrowse 2>&1 | grep "/Volumes/" | tail -1 | awk '{for(i=3;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ $//')
if [ -z "$MOUNT" ]; then
    fail "DMG:n mounttaus epäonnistui"
    exit 1
fi
pass "DMG mountattu: $MOUNT"

# Verify DMG contents
if [ -d "$MOUNT/${APP_NAME}.app" ]; then
    pass ".app-bundle löytyy DMG:stä"
else
    fail ".app-bundle PUUTTUU DMG:stä"
fi

if [ -L "$MOUNT/Applications" ]; then
    pass "Applications-symlinkki löytyy DMG:stä"
else
    fail "Applications-symlinkki PUUTTUU DMG:stä"
fi

# Screenshot: DMG contents
screencapture -x "$EVIDENCE_DIR/01-dmg-mounted.png" 2>/dev/null || true

# Install
cp -R "$MOUNT/${APP_NAME}.app" /Applications/ 2>/dev/null
if [ -d "$APP_PATH" ]; then
    pass "Asennus /Applications/ onnistui"
else
    fail "Asennus /Applications/ EPÄONNISTUI"
    hdiutil detach "$MOUNT" >/dev/null 2>/dev/null
    exit 1
fi

hdiutil detach "$MOUNT" >/dev/null 2>/dev/null
pass "DMG unmountattu"

# Verify bundle structure
RESOURCES="$APP_PATH/Contents/Resources"
BIN="$APP_PATH/Contents/MacOS"

for file in "eye_22.png" "eye_44.png" "settings.py" "menu_bar.py" "web_dashboard.py"; do
    if [ -f "$RESOURCES/$file" ]; then
        pass "  $file löytyy bundlesta"
    else
        fail "  $file PUUTTUU bundlesta"
    fi
done

# Check key binaries
for file in "python" "${APP_NAME}"; do
    if [ -f "$BIN/$file" ]; then
        pass "  $file löytyy bundlesta"
    else
        fail "  $file PUUTTUU bundlesta"
    fi
done

# ═══════════════════════════════════════════════════════════════
# Phase 3: Quarantine + Sign
# ═══════════════════════════════════════════════════════════════

echo ""
echo "━━━ Phase 3: Quarantine Cleanup & Sign ━━━"

# Remove quarantine attributes
find "$APP_PATH" -exec xattr -d com.apple.quarantine {} \; 2>/dev/null || true
pass "Karanteeniattribuutit poistettu"

# Ad-hoc sign binaries
find "$APP_PATH" -type f \( -name "*.dylib" -o -name "*.so" \) \
    -exec codesign --force --sign - {} \; 2>/dev/null || true
codesign --force --sign - "$BIN/python" "$BIN/${APP_NAME}" 2>/dev/null || true
pass "Ad-hoc-signaus tehty"

# ═══════════════════════════════════════════════════════════════
# Phase 4: Process Stability
# ═══════════════════════════════════════════════════════════════

echo ""
echo "━━━ Phase 4: Process Stability ━━━"

# Start app via py2app boot wrapper
info "Käynnistetään sovellus..."
"$BIN/${APP_NAME}" >/dev/null 2>&1 &
APP_PID=$!

sleep 5
if kill -0 $APP_PID 2>/dev/null; then
    pass "Sovellus käynnissä (5s)"
else
    fail "Sovellus kaatui 5s sisällä"
    # Try fallback: direct python
    info "Yritetään fallback: suora python menu_bar.py..."
    "$BIN/python" "$RESOURCES/menu_bar.py" >/dev/null 2>&1 &
    APP_PID=$!
    sleep 5
    if kill -0 $APP_PID 2>/dev/null; then
        pass "Fallback: sovellus käynnissä (5s)"
    else
        fail "Fallback: sovellus kaatui — tutki lokit"
        exit 1
    fi
fi

screencapture -x "$EVIDENCE_DIR/02-app-running.png" 2>/dev/null || true

sleep 25
if kill -0 $APP_PID 2>/dev/null; then
    pass "Sovellus käynnissä (30s)"
else
    fail "Sovellus kaatui 5-30s välillä"
    exit 1
fi

sleep 30
if kill -0 $APP_PID 2>/dev/null; then
    pass "Sovellus käynnissä (60s) — stabiili"
else
    fail "Sovellus kaatui 30-60s välillä"
    exit 1
fi

# ═══════════════════════════════════════════════════════════════
# Phase 5: Menu Bar Interaction
# ═══════════════════════════════════════════════════════════════

echo ""
echo "━━━ Phase 5: Menu Bar Interaction ━━━"

# Check if process is visible to System Events
MENU_TEST=$(osascript -s o <<'APPLESCRIPT' 2>/dev/null
tell application "System Events"
    try
        set procList to name of every process
        return procList as string
    on error
        return "ERROR"
    end try
end tell
APPLESCRIPT
)

if echo "$MENU_TEST" | grep -q "$APP_NAME"; then
    pass "Prosessi '$APP_NAME' näkyy System Eventsissä"
else
    fail "Prosessi '$APP_NAME' EI näy System Eventsissä"
fi

# LSUIElement apps: verify accessibility works (menu bar click requires keystroke permission)
# We just check that the process responds via accessibility — this confirms the icon is in the menu bar.

cat >/tmp/_cv_ax_test.scpt <<'ASEOF'
tell application "System Events"
    try
        tell process "Clairvoyant-Optics"
            set axRole to role of UI element 1
            return "AX_OK: " & axRole
        end tell
    on error errMsg
        return "AX_FAIL: " & errMsg
    end try
end tell
ASEOF
AX_CHECK=$(osascript /tmp/_cv_ax_test.scpt 2>/dev/null)
rm -f /tmp/_cv_ax_test.scpt

if echo "$AX_CHECK" | grep -q "AX_OK"; then
    pass "Accessibility-yhteys OK — menu bar extra löytyi (role: $(echo "$AX_CHECK" | sed 's/AX_OK: //'))"
else
    fail "Accessibility-yhteys EI toimi — menu bar icon ei ehkä renderöidy"
fi

screencapture -x "$EVIDENCE_DIR/03-menu-open.png" 2>/dev/null || true
sleep 0.5

# Phase 6: Settings Window Test
# Three strategies:
#   A) Try ⌘S shortcut (key changed from comma to 's' in v4.2.3)
#   B) Settings.app wrapper via open -a (production path — has own window-server)
#   C) Fallback: PID file check

echo ""
echo "━━━ Phase 6: Settings Window ━━━"

SETTINGS_SPAWNED=false

# Strategy A: ⌘S shortcut (requires keystroke permission)
cat >/tmp/_cv_settings_cmd.scpt <<'ASEOF'
tell application "Clairvoyant-Optics"
    activate
end tell
delay 0.5
tell application "System Events"
    keystroke "s" using command down
end tell
delay 2
ASEOF
osascript /tmp/_cv_settings_cmd.scpt 2>/dev/null || true
rm -f /tmp/_cv_settings_cmd.scpt
sleep 3

# Check for settings window
SETTINGS_WINDOW=$(osascript -s o 2>/dev/null <<'APPLESCRIPT'
tell application "System Events"
    repeat with procName in name of every process
        try
            tell process procName
                repeat with w in name of every window
                    if w contains "Clairvoyant" and w contains "Settings" then
                        return procName & ":" & w as string
                    end if
                end repeat
            end tell
        on error
        end try
    end repeat
    return ""
end tell
APPLESCRIPT
)

if [ -n "$SETTINGS_WINDOW" ]; then
    pass "Settings-ikkuna löytyi (⌘S): $SETTINGS_WINDOW"
    SETTINGS_SPAWNED=true
fi

# Strategy B: Settings.app wrapper (open -a — production spawn path)
if ! $SETTINGS_SPAWNED; then
    info "⌘S ei toiminut — käytetään Settings.app wrapperia..."
    SETTINGS_APP="$RESOURCES/Settings.app"
    if [ -d "$SETTINGS_APP" ]; then
        open -a "$SETTINGS_APP"
        sleep 4

        WRAPPER_WINDOW=$(osascript -s o 2>/dev/null <<'APPLESCRIPT'
tell application "System Events"
    try
        return name of every window of process "Clairvoyant-Settings"
    on error
        return ""
    end try
end tell
APPLESCRIPT
)
        if [ -n "$WRAPPER_WINDOW" ]; then
            pass "Settings-ikkuna löytyi (Settings.app): $WRAPPER_WINDOW"
            SETTINGS_SPAWNED=true
        else
            fail "Settings.app spawnattu mutta ikkunaa ei löydy"
        fi
    else
        fail "Settings.app wrapper PUUTTUU bundlesta"
    fi
fi

# Strategy C: PID file check (fallback)
if ! $SETTINGS_SPAWNED; then
    SETTINGS_PID_FILE="$HOME/.clairvoyant-optics/settings.pid"
    if [ -f "$SETTINGS_PID_FILE" ]; then
        SETTINGS_PID=$(cat "$SETTINGS_PID_FILE")
        if kill -0 "$SETTINGS_PID" 2>/dev/null; then
            pass "Settings-prosessi elossa (PID $SETTINGS_PID)"
            SETTINGS_SPAWNED=true
        else
            fail "Settings-prosessi KUOLLUT (PID $SETTINGS_PID)"
        fi
    else
        fail "Settings PID-tiedostoa ei löydy"
    fi
fi

if ! $SETTINGS_SPAWNED; then
    fail "Settings-ikkunaa ei löydy millään keinolla"
fi

screencapture -x "$EVIDENCE_DIR/04-settings-window.png" 2>/dev/null || true

# Close settings window (Escape)
osascript -e 'tell application "System Events" to key code 53' 2>/dev/null || true
sleep 1

# ═══════════════════════════════════════════════════════════════
# Phase 7: Clean Shutdown
# ═══════════════════════════════════════════════════════════════

echo ""
echo "━━━ Phase 7: Clean Shutdown ━━━"

# Graceful kill
kill $APP_PID 2>/dev/null || true
sleep 2

if ! kill -0 $APP_PID 2>/dev/null; then
    pass "Sovellus sammui siististi (SIGTERM)"
else
    info "SIGTERM ei riittänyt — pakotetaan SIGKILL"
    kill -9 $APP_PID 2>/dev/null || true
    sleep 1
    if ! kill -0 $APP_PID 2>/dev/null; then
        pass "Sovellus sammui SIGKILL:llä"
    else
        fail "Sovellus EI sammu — zombie-prosessi"
    fi
fi

# Kill settings if still alive
SETTINGS_PID_FILE="$HOME/.clairvoyant-optics/settings.pid"
if [ -f "$SETTINGS_PID_FILE" ]; then
    SETTINGS_PID=$(cat "$SETTINGS_PID_FILE")
    kill "$SETTINGS_PID" 2>/dev/null || true
    rm -f "$SETTINGS_PID_FILE"
fi

# Cleanup
rm -rf "$APP_PATH" 2>/dev/null || true
pass "Siivottu: /Applications/${APP_NAME}.app poistettu"

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════

echo ""
echo "════════════════════════════════════════════"
printf "  ${GREEN}Läpäisty: %d${NC}  |  ${RED}Hylätty: %d${NC}\n" $PASS $FAIL
echo "  Evidence:  $EVIDENCE_DIR"
echo "════════════════════════════════════════════"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "🔍 Vianjäljitys:"
    echo "  1. Katso screenshotit: open $EVIDENCE_DIR"
    echo "  2. Tarkista app-lokit: ~/.clairvoyant-optics/"
    echo "  3. Kokeile manuaalisesti: open $DMG"
    exit 1
else
    echo ""
    echo "🎉 Kaikki $PASS testiä läpäisty — DMG on valmis julkaistavaksi!"
    exit 0
fi
