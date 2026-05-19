"""
Test: pyautogui visuaalinen GUI-testaus vs. atomacos accessibility.
Testaa kumpi löytää tkinter-settings-ikkunan painikkeet oikeasti.
"""
import subprocess, os, sys, time, tempfile, shutil
import unittest


class PyAutoGUITest(unittest.TestCase):
    """Test pyautogui kuvapohjainen GUI-testaus ilman accessibility API:a."""

    @classmethod
    def setUpClass(cls):
        cls._procs = []

    @classmethod
    def tearDownClass(cls):
        for p in cls._procs:
            try: p.kill(); p.wait(timeout=3)
            except: pass

    def _launch_settings(self) -> subprocess.Popen:
        tmpdir = tempfile.mkdtemp()
        env = os.environ.copy()
        env['CLAIRVOYANT_CONFIG_DIR'] = tmpdir
        env['PYTHONPATH'] = 'src:tests'
        proc = subprocess.Popen(
            [sys.executable, 'src/desktop/settings.py'],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self._procs.append(proc)
        time.sleep(2)  # Wait for window to appear
        return proc

    def test_pyautogui_finds_window_and_tabs(self):
        """pyautogui löytää ikkunan ja tabs-painikkeet."""
        self._launch_settings()
        import pyautogui
        pyautogui.FAILSAFE = False
        
        # Find settings window
        try:
            from pygetwindow import getWindowsWithTitle
            wins = getWindowsWithTitle('Clairvoyant')
            self.assertGreater(len(wins), 0, "No window found with pygetwindow")
            win = wins[0]
            print(f"Window found: '{win.title}' {win.size} at ({win.left},{win.top})")
            win.activate()
            time.sleep(0.5)

            # Take screenshot of the window area
            screenshot = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
            screenshot.save('/tmp/co_pyautogui_window.png')
            print(f"Screenshot saved: {screenshot.size}")

            # Check window has meaningful content
            w, h = screenshot.size
            self.assertGreater(w, 200, f"Window too narrow: {w}")
            self.assertGreater(h, 200, f"Window too short: {h}")

            # Pixel analysis: look for General tab region
            # Tab bar is on the left side, ~150-200px wide
            left_strip = screenshot.crop((0, 60, 180, h-60))
            left_strip.save('/tmp/co_pyautogui_left_strip.png')
            
            # Check left strip is not blank
            import numpy as np
            arr = np.array(left_strip)
            unique_colors = len(np.unique(arr.reshape(-1, arr.shape[2]), axis=0))
            self.assertGreater(unique_colors, 10, 
                f"Left strip (tab area) has only {unique_colors} unique colors — likely empty/blank")
            
            print(f"Left side (tab bar): {left_strip.size}, {unique_colors} unique colors")

            # Check scrollbar area on right
            right_strip = screenshot.crop((w-30, 60, w, h-60))
            right_strip.save('/tmp/co_pyautogui_right_strip.png')
            arr_r = np.array(right_strip)
            unique_right = len(np.unique(arr_r.reshape(-1, arr_r.shape[2]), axis=0))
            
            # General tab is at the top — look for text "General" in the left strip
            # pyautogui.locateOnScreen requires template images so instead check
            # that specific pixel regions differ (content exists)
            # Check the top-left where "General" would be
            top_left = screenshot.crop((0, 60, 180, 140))
            arr_tl = np.array(top_left)
            tl_std = float(np.std(arr_tl))
            self.assertGreater(tl_std, 5, 
                f"Top-left tab region has std {tl_std:.1f} — likely blank. Tab not rendering text.")

            print(f"Tab bar top-left std: {tl_std:.1f} (content present)")
            print(f"Scrollbar area right: {unique_right} colors (scrollbar {'present' if unique_right > 3 else 'absent'})")

        except Exception as e:
            # Save screenshot even on failure
            try:
                pyautogui.screenshot('/tmp/co_pyautogui_fail.png')
            except:
                pass
            raise

    def test_atomacos_no_tkinter_accessibility(self):
        """Todista että atomacos EI löydä tkinter-painikkeita."""
        proc = self._launch_settings()
        import atomacos
        app = atomacos.getAppRefByPid(proc.pid)
        win = app.windows()[0]
        
        # Try finding buttons
        buttons = win.findAllR(AXRole='AXButton')
        titles = [str(getattr(b, 'AXTitle', '')) for b in buttons]
        print(f"atomacos finds {len(buttons)} buttons with titles: {titles}")
        
        # None should have a real title (Tk 8.6 limitation)
        named_buttons = [t for t in titles if t and t != 'None']
        self.assertEqual(len(named_buttons), 0,
            f"atomacos unexpectedly found named buttons: {named_buttons}. "
            "If this test fails, Tk now has accessibility support!")
        
        # But system events can still find the window
        import subprocess as sp
        r = sp.run(['osascript', '-e', '''
            tell application "System Events"
                tell (first process whose name contains "Python")
                    set wins to every window
                    return count of wins
                end tell
            end tell
        '''], capture_output=True, text=True, timeout=5)
        print(f"System Events window count: {r.stdout.strip() or r.stderr.strip()}")

    def test_pyautogui_detects_content_change(self):
        """Testaa pyautogui osaa havaita tkinter-ikkunan sisällön muuttuvan."""
        proc = self._launch_settings()
        import pyautogui
        pyautogui.FAILSAFE = False
        from pygetwindow import getWindowsWithTitle
        import numpy as np
        from PIL import Image
        
        time.sleep(1)
        wins = getWindowsWithTitle('Clairvoyant')
        if not wins:
            self.skipTest("Window not found")
        win = wins[0]
        win.activate()
        time.sleep(0.5)
        
        # Take screenshot
        s1 = pyautogui.screenshot(region=(win.left, win.top, win.width, min(win.height, 600)))
        
        # Click on a tab in the left sidebar (approximate location)
        # Tab buttons are at x ~ 20-50, y ~ 180 (General is top)
        # Click at the left side at y=180 (below header) to activate Models tab
        import pyautogui as pg
        pg.click(win.left + 30, win.top + 220)  # Click on tab area
        time.sleep(0.5)
        
        # Take another screenshot
        s2 = pyautogui.screenshot(region=(win.left, win.top, win.width, min(win.height, 600)))
        
        # Compare: tabs area and content area should differ
        arr1 = np.array(s1)
        arr2 = np.array(s2)
        diff = np.abs(arr1.astype(float) - arr2.astype(float))
        mean_diff = float(np.mean(diff))
        print(f"Mean pixel diff between screenshots: {mean_diff:.1f}")
        
        # If content actually changed, we should see a difference
        # This proves pyautogui can detect GUI state changes
        self.assertGreater(mean_diff, 0.5, 
            f"Screenshots are nearly identical ({mean_diff:.1f}) — tab switch didn't change visible content")


if __name__ == '__main__':
    unittest.main(verbosity=2)
