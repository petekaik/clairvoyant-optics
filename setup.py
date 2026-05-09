"""setup.py — py2app-konfiguraatio macOS .app-bundlelle.

Käyttö: python setup.py py2app
"""

import sys
from pathlib import Path
from setuptools import setup

# Versio version.py:stä tai oletus
version_file = Path(__file__).parent / "src" / "version.py"
if version_file.exists():
    with open(version_file) as f:
        exec(f.read())
else:
    VERSION = "2.1.0"

APP = ["src/macos/menubar_app.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "packages": [
        "rumps", "cv2", "numpy", "requests",
        "insightface", "onnxruntime", "ultralytics",
        "fastapi", "uvicorn", "macos_notifications",
        "osxphotos",
    ],
    "includes": [
        "src", "src.cli", "src.main", "src.config",
        "src.recognition", "src.detection", "src.streams",
        "src.integration", "src.utils", "src.macos",
    ],
    "excludes": [
        "tkinter", "PyQt5", "PySide2", "wx",
        "matplotlib", "scipy", "pandas",
    ],
    "plist": {
        "CFBundleName": "Clairvoyant-Optics",
        "CFBundleDisplayName": "Clairvoyant-Optics",
        "CFBundleIdentifier": "fi.kaikkonen.clairvoyant-optics",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": True,  # Menubar-only, ei Dock-kuvaketta
        "NSHighResolutionCapable": True,
    },
}

# Iconfile vain jos tiedosto on olemassa
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
