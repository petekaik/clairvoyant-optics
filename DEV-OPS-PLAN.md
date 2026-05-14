# Clairvoyant-Optics DevOps Plan — CLI Executable
> **For Hermes CLI session:** Autonomous end-to-end execution. No user interaction.
> **Goal:** Build, test, and validate a working macOS .app bundle where menu bar shows icon AND Settings window opens visually.
> **Architecture:** py2app → build-dmg.sh → test-dmg.sh → fix loop → commit → CI parity
> **Delegation:** OpenClaw/Nex for parallel analysis tasks. Hermes is the builder.

**Last known state (2026-05-14):** DMG installs but app doesn't work. Two symptoms:
1. Menu bar shows "Clairvoyant-Optics" **text** instead of eye icon → `eye_22.png` missing from `Contents/Resources/`
2. "Settings…" menu item does nothing → `settings.py` missing/not spawning in bundle, OR settings process spawns but tkinter window never renders

---

## Phase 0: Reconnaissance (5 min)

### Task 0.1 — Verify current build
```bash
cd ~/projects/Clairvoyant-Optics
ls -la dist/Clairvoyant-Optics-*.dmg 2>/dev/null
ls -la dist/Clairvoyant-Optics.app/Contents/Resources/ 2>/dev/null
```

### Task 0.2 — Check what the 2026-05-14 session discovered
Run a fresh build and capture the exact failure:
```bash
./scripts/build-dmg.sh
./scripts/test-dmg.sh 2>&1 | tee /tmp/clairvoyant-test-output.log
```

### Task 0.3 — Isolate root cause
If test-dmg.sh fails at Phase 2 (bundle structure), the build script's `cp -f` is failing silently. Check:
```bash
APP="dist/Clairvoyant-Optics.app"
echo "=== Resources ==="
ls -la "$APP/Contents/Resources/" | grep -E "eye_|settings"
echo "=== MacOS ==="
ls -la "$APP/Contents/MacOS/"
```

---

## Phase 1: Fix the Build (immediate)

The current `build-dmg.sh` already has the copy commands at lines 45-47 and the @rpath fix at lines 55-77. **If these are failing**, here's why and how to fix:

### Task 1.1 — Run build step-by-step
Don't trust the automated script. Run phases manually:

```bash
cd ~/projects/Clairvoyant-Optics
source venv/bin/activate

# Clean
rm -rf dist build

# Build app bundle
python setup.py py2app || echo "py2app codesign step may have failed — expected on Sequoia, continuing"

# Verify .app exists
ls -la dist/Clairvoyant-Optics.app/Contents/MacOS/python

# Copy assets (MANUAL — verify each copy)
APP="dist/Clairvoyant-Optics.app"
RESOURCES="$APP/Contents/Resources"
cp -fv assets/eye_22.png "$RESOURCES/"
cp -fv assets/eye_44.png "$RESOURCES/"  
cp -fv src/macos/settings.py "$RESOURCES/"
# VERIFY:
ls -la "$RESOURCES/eye_22.png"
ls -la "$RESOURCES/eye_44.png"
ls -la "$RESOURCES/settings.py"
```

### Task 1.2 — Fix @rpath libraries
```bash
FW="$APP/Contents/Frameworks"

# Scan for missing @rpath dylibs
REQUIRED_LIBS=$(find "$APP/Contents/Resources" -name "*.so" -o -name "*.dylib" 2>/dev/null | \
  while read f; do otool -L "$f" 2>/dev/null; done | \
  grep -oE '@rpath/([^ ]+)' | sed 's|@rpath/||' | sort -u)

echo "Required @rpath libs:"
for lib in $REQUIRED_LIBS; do
    if [ -f "$FW/$lib" ]; then
        echo "  ✅ $lib"
    else
        # Search: project venv first, then conda, then homebrew
        SRC=$(find venv /opt/anaconda3/lib /opt/anaconda3/conda-bld /opt/homebrew/lib \
            -path "*/skeleton*/lib/$lib" -o -name "$lib" 2>/dev/null | head -1)
        if [ -n "${SRC:-}" ]; then
            cp "$SRC" "$FW/"
            echo "  📋 $lib (from $SRC)"
        else
            echo "  ❌ $lib NOT FOUND"
        fi
    fi
done
```

### Task 1.3 — Code sign for Sequoia (CRITICAL)
Sequoia requires ad-hoc signing of individual binaries, not the whole .app:
```bash
# Sign dylib + .so files individually
find "$APP" -type f \( -name "*.dylib" -o -name "*.so" \) \
    -exec codesign --force --sign - {} \; 2>/dev/null || true

# Sign the two executables
codesign --force --sign - "$APP/Contents/MacOS/python" 2>/dev/null || true
codesign --force --sign - "$APP/Contents/MacOS/Clairvoyant-Optics" 2>/dev/null || true

echo "✅ Signed"
```

### Task 1.4 — Smoke test (bare metal)
```bash
# Clean quarantine + install
rm -rf /Applications/Clairvoyant-Optics.app 2>/dev/null || true
cp -R "$APP" /Applications/

# Remove quarantine
find /Applications/Clairvoyant-Optics.app -exec xattr -d com.apple.quarantine {} \; 2>/dev/null || true

# Run
/Applications/Clairvoyant-Optics.app/Contents/MacOS/Clairvoyant-Optics &
APP_PID=$!

echo "PID: $APP_PID — waiting 5s..."
sleep 5
kill -0 $APP_PID 2>/dev/null && echo "✅ Alive at 5s" || echo "❌ CRASHED"

# Check if settings.py was spawned
sleep 3
ls -la ~/.clairvoyant-optics/settings.pid 2>/dev/null && echo "Settings PID file exists" || echo "❌ No settings PID"
```

---

## Phase 2: GUI Validation (requires GUI session on this Mac)

Since you're on the real Mac with a GUI session, we can do what Discord sessions can't:

### Task 2.1 — Full test-dmg.sh
```bash
cd ~/projects/Clairvoyant-Optics
./scripts/test-dmg.sh dist/Clairvoyant-Optics-*.dmg
```

This runs all 7 phases including:
- Phase 5: Menu bar interaction (System Events osascript)
- Phase 6: Settings window spawn + window detection
- Phase 7: Clean shutdown

Screenshots saved to `/tmp/clairvoyant-test-evidence/`.

### Task 2.2 — If Settings window doesn't appear: debug settings.py standalone
```bash
# Spawn settings directly from the bundle (without rumps)
cd ~/projects/Clairvoyant-Optics
cp -R dist/Clairvoyant-Optics.app /Applications/ 2>/dev/null || true
find /Applications/Clairvoyant-Optics.app -exec xattr -d com.apple.quarantine {} \; 2>/dev/null || true

# Run settings.py directly
/Applications/Clairvoyant-Optics.app/Contents/MacOS/python \
    /Applications/Clairvoyant-Optics.app/Contents/Resources/settings.py &
SETTINGS_PID=$!
sleep 3

# Check: is the window visible?
osascript -e 'tell application "System Events" to set allWindows to name of every window of every process' 2>/dev/null | grep -i "clairvoyant\|settings"
kill $SETTINGS_PID 2>/dev/null
```

**If this works but rumps→spawn doesn't:** The issue is in `spawn_settings()` — the subprocess path resolution or the bundled python isn't being found.

**If this also fails:** There's a tkinter/Cocoa initialization problem in the bundled environment.

### Task 2.3 — Debug spawn_settings() in bundle context
The `spawn_settings()` function in app.py (line 135) does:
```python
python = str(BUNDLED_PYTHON) if IS_BUNDLED else sys.executable
# BUNDLED_PYTHON = BUNDLE_CONTENTS / "MacOS" / "python"
```

Verify the bundled python works:
```bash
/Applications/Clairvoyant-Optics.app/Contents/MacOS/python --version
/Applications/Clairvoyant-Optics.app/Contents/MacOS/python -c "import tkinter; print('tkinter OK')"
/Applications/Clairvoyant-Optics.app/Contents/MacOS/python -c "import yaml; print('yaml OK')"
/Applications/Clairvoyant-Optics.app/Contents/MacOS/python -c "import rumps; print('rumps OK')"
```

### Task 2.4 — If rumps crashes: test app.py directly
```bash
# Run app.py with bundled python (bypasses py2app boot wrapper)
/Applications/Clairvoyant-Optics.app/Contents/MacOS/python \
    /Applications/Clairvoyant-Optics.app/Contents/Resources/app.py &
APP_PID=$!
sleep 5
kill -0 $APP_PID && echo "Direct app.py: OK" || echo "Direct app.py: CRASHED"
```

---

## Phase 3: The Fix

Based on what Phase 2 reveals, apply ONE of these fixes:

### Fix A: Missing assets in Resources (most likely)
If `eye_22.png` or `settings.py` aren't in Resources after build:
→ The `cp -f` in build-dmg.sh is silently failing. Add explicit error checking:
```bash
cp -f "assets/eye_22.png" "$RESOURCES/" || { echo "FATAL: cannot copy eye_22.png"; exit 1; }
cp -f "assets/eye_44.png" "$RESOURCES/" || { echo "FATAL: cannot copy eye_44.png"; exit 1; }
cp -f "src/macos/settings.py" "$RESOURCES/" || { echo "FATAL: cannot copy settings.py"; exit 1; }
```

### Fix B: settings.py crashes on import (tkinter/Cocoa)
If `python -c "import tkinter"` fails from the bundle:
→ Missing @rpath library (libtcl, libtk). The @rpath scan in build-dmg.sh should catch this, but verify:
```bash
find /Applications/Clairvoyant-Optics.app/Contents/Resources -name "_tkinter*" | \
    xargs otool -L 2>/dev/null | grep @rpath
```
Each `@rpath/libxxx.dylib` reference must have the library in `Contents/Frameworks/`.

### Fix C: rumps can't fork tkinter (process model)
The skill is explicit: rumps + tkinter same process → SIGBUS. But our architecture already runs them separate. If `spawn_settings()` returns True but settings never shows:
→ Maybe `DEVNULL` is swallowing errors. Change to capture stderr:
```python
# In app.py, spawn_settings():
kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}  # DEBUG
```
Then read proc.stderr after 3 seconds.

### Fix D: settings.py uses IS_BUNDLED detection but tkinter fails
Check if settings.py has bundle-aware path logic (it reads CONFIG_DIR from `Path.home()/.clairvoyant-optics/` which is fine in both modes). But if it tries to import project-local modules, those won't exist in the bundle. The v4.2.0 settings.py should be self-contained (no src.* imports).

---

## Phase 4: Delegation Strategy (Nex/OpenClaw)

**WHEN to delegate:** Tasks that are reasoning-heavy but don't need GUI access.

### Delegate Task A: Codebase analysis (parallel with build)
```bash
# Send to Nex while you build:
openclaw agent --local -m '
Analyze ~/projects/Clairvoyant-Optics/src/macos/settings.py (717 lines).
Find ALL potential failure points that could prevent the tkinter window from rendering:
1. Import errors (modules that might not exist in bundle)
2. File path assumptions (anything besides CONFIG_DIR that uses relative paths)
3. Missing signal handlers (SIGUSR1/SIGTERM setup)
4. Tkinter initialization that could fail silently
5. Dark mode detection that might hang
6. Any infinite loops or blocking calls in __init__
Report each finding with line number and fix.
' --agent researcher --timeout 300
```

### Delegate Task B: GitHub Actions migration plan
```bash
openclaw agent --local -m '
Compare these two files:
- ~/projects/Clairvoyant-Optics/.github/workflows/build.yml (uses PyInstaller, incomplete)
- ~/projects/Clairvoyant-Optics/scripts/build-dmg.sh (uses py2app, production)

The local build-dmg.sh works on real Macs. I need to migrate it to GitHub Actions (macos-latest runner).
Requirements:
1. Must use py2app (NOT PyInstaller) — current build.yml uses wrong tool
2. Must handle Sequoia codesign (individual binary signing, not whole .app)
3. Must fix @rpath dylibs
4. Must copy eye_22.png, eye_44.png, settings.py to Resources/
5. Must produce DMG artifact
6. Must run test-dmg.sh as far as possible in CI (phases 1-4 can run headless, 5-7 need GUI)
7. Create release on v* tags
Write the complete workflow YAML.
' --agent coder --timeout 300
```

### Delegate Task C: Cross-platform CI smoke test
```bash
openclaw agent --local -m '
In ~/projects/Clairvoyant-Optics, design a CI-compatible smoke test that replaces the GUI phases of test-dmg.sh.
The CI runner has NO GUI session — no osascript, no screencapture, no System Events.

What CAN be tested:
1. Bundle structure integrity (all files present)
2. Python import chain (import rumps, yaml, tkinter from bundled python)
3. settings.py syntax + import check (python -c "compile(open(...))")
4. Process stability (start app, wait 15s, verify alive via kill -0)
5. Settings PID file creation (check if spawn_settings writes ~/.clairvoyant-optics/settings.pid)
6. DMG checksum + mountability

Write a ~50-line script that implements all 6 checks. Save as scripts/ci-smoke-test.sh.
' --agent coder --timeout 300
```

### HOW to receive delegated results
Nex sends results back to `#agent-chat` on Discord. You can:
1. Watch `#agent-chat` for results
2. Or read from log files if using local CLI:
```bash
openclaw agent --local -m '...' --agent researcher --timeout 300 2>&1 | tee /tmp/nex-result-$(date +%s).txt
```

---

## Phase 5: CI/CD Parity (GitHub Actions)

### Goal
When a tag is pushed, GitHub Actions builds the DMG and creates a release. The DMG is tested as far as possible in CI (phases 1-4), and the rest (GUI validation) runs locally via test-dmg.sh.

### Task 5.1 — Replace build.yml
The current `.github/workflows/build.yml` uses PyInstaller and has multiple issues:
- Uses `--deep` flag (deprecated on Sequoia)
- References `menubar_app.py` (old filename, now `app.py`)
- No @rpath handling
- No asset copying
- No DMG validation

Replace it with a py2app-based workflow. Delegate this to Nex (Delegate Task B above) and then review + merge.

### Task 5.2 — Add ci-smoke-test.sh to workflow
After building, run `scripts/ci-smoke-test.sh` (created by Delegate Task C) to validate the bundle before packaging DMG.

### Task 5.3 — Test the workflow locally
```bash
# Simulate CI environment
cd ~/projects/Clairvoyant-Optics
# Install act for local workflow testing: brew install act
act push --job build 2>&1 | tee /tmp/act-output.log
```

---

## Phase 6: Commit & Version Bump

Once everything passes:
```bash
cd ~/projects/Clairvoyant-Optics

# Update version (bump patch: 4.2.1 → 4.2.2)
# Edit src/version.py, then:

git add -A
git commit -m "fix: DMG build fixes + CI parity (v4.2.2)

- Fix asset copying validation (exit on failure)
- Fix @rpath library discovery in conda envs
- Add ci-smoke-test.sh for headless CI validation
- Migrate CI to py2app (from broken PyInstaller config)
- Add delegation playbook to DEV-OPS-PLAN.md"

git tag -a v4.2.2 -m "v4.2.2: Fixed DMG + CI parity"
git push origin master --tags
```

---

## Phase 7: Validation Checklist

Before declaring victory:

- [ ] `./scripts/build-dmg.sh` completes without errors
- [ ] `./scripts/test-dmg.sh` passes all 7 phases
- [ ] Menu bar shows **eye icon** (not text "Clairvoyant-Optics")
- [ ] Clicking menu bar icon shows menu with "Settings…" and "Quit"
- [ ] Clicking "Settings…" opens tkinter settings window
- [ ] Settings window opens when pressing ⌘, shortcut
- [ ] Settings window follows macOS HIG (toolbar sidebar, SF fonts, dark mode)
- [ ] Changing a setting in settings window persists to `~/.clairvoyant-optics/config.yaml`
- [ ] Launch at login creates valid LaunchAgent plist
- [ ] Quit cleans up all processes (no zombies)
- [ ] `./scripts/ci-smoke-test.sh` passes (headless checks)
- [ ] GitHub Actions workflow builds successfully
- [ ] DMG from CI is identical to local build (same checksum)

---

## Troubleshooting Quick Reference

| Symptom | Root Cause | Check |
|---------|-----------|-------|
| Menu bar shows app name text | `eye_22.png` missing from Resources | `ls Contents/Resources/eye_22.png` |
| Settings does nothing | `settings.py` missing from Resources | `ls Contents/Resources/settings.py` |
| App crashes instantly | @rpath lib missing, not signed | `otool -L` on .so files |
| Settings spawns but no window | tkinter init crashed silently | Run settings.py standalone, capture stderr |
| DMG verification fails | Build was interrupted | Rebuild from clean |
| CI build fails | Wrong Python version, missing deps | Check workflow runs-on and setup-python |

---

**Start here:** Run Phase 0 reconnaissance, then Phase 1 fix, then Phase 2 validate. Delegate Phase 4 tasks to Nex in parallel.
