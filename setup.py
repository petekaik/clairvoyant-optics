"""setup.py — py2app configuration for minimal macOS .app bundle v4.0.2.

Usage: python setup.py py2app

Main app: src/macos/app.py (rumps menu bar app, LSUIElement=True = no Dock icon).
Settings window (src/macos/settings.py) runs as a separate process.
"""

import sys
from pathlib import Path
from setuptools import setup

version_file = Path(__file__).parent / "src" / "version.py"
if version_file.exists():
    with open(version_file) as f:
        exec(f.read())
else:
    VERSION = "4.0.2"

APP = ["src/macos/app.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "packages": [
        "rumps",
        "yaml",
        "tkinter",
    ],
    "includes": [
        "src.macos",
    ],
    "excludes": [],
    "plist": {
        "CFBundleName": "Clairvoyant-Optics",
        "CFBundleDisplayName": "Clairvoyant-Optics",
        "CFBundleIdentifier": "fi.kaikkonen.clairvoyant-optics",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": True,  # No Dock icon — menu bar only
        "NSHighResolutionCapable": True,
    },
}

icon_path = Path("assets/icon.icns")
if icon_path.exists() and icon_path.stat().st_size > 100:
    OPTIONS["iconfile"] = "assets/icon.icns"

setup(
    name="Clairvoyant-Optics",
    version=VERSION,
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
