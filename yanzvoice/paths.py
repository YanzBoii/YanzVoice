"""Where things live, whether running from source or from a built .exe.

PyInstaller changes two assumptions the rest of the code would otherwise make:
`__file__` no longer sits next to the project's `assets/`, and the folder the
program runs from may be read-only (Program Files, a network share, a
read-only USB stick). Everything that needs those answers asks here.
"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running from a PyInstaller build rather than from source."""
    return getattr(sys, "frozen", False)


def resource_root() -> Path:
    """Folder holding the bundled read-only assets."""
    if is_frozen():
        # onefile unpacks to _MEIPASS; onedir keeps them beside the exe.
        bundled = getattr(sys, "_MEIPASS", None)
        return Path(bundled) if bundled else Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def assets() -> Path:
    return resource_root() / "assets"


def executable_dir() -> Path:
    """Folder the user actually launches, for shortcuts and error messages."""
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent
