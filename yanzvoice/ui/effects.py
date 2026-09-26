"""Windows compositor glass, and a window that never steals focus.

Two routes to a real backdrop blur, newest first:

  * Windows 11 22621+ exposes it officially through DWMWA_SYSTEMBACKDROP_TYPE.
    Value 3 is Acrylic (transient window), which is the glass we want.
  * Earlier builds only have the undocumented accent policy. It works, but it
    is not contractual, so it is the fallback and never the first choice.

`enable_glass` reports which one it got, so painting can thicken the fill when
neither is available and the text would otherwise sit on bare desktop.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33

DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
DWMSBT_MAINWINDOW = 2       # Mica
DWMWCP_ROUND = 2

ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
ACCENT_ENABLE_BLURBEHIND = 3
WCA_ACCENT_POLICY = 19

_user32 = ctypes.windll.user32
try:
    _dwmapi = ctypes.windll.dwmapi
except OSError:  # pragma: no cover - non-Windows
    _dwmapi = None


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class WINCOMPATTRDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(ACCENT_POLICY)),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _build() -> int:
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def supports_system_backdrop() -> bool:
    return _dwmapi is not None and _build() >= 22621


def _set_dwm_int(hwnd: int, attribute: int, value: int) -> bool:
    if _dwmapi is None:
        return False
    val = ctypes.c_int(value)
    result = _dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd), ctypes.c_uint(attribute),
        ctypes.byref(val), ctypes.sizeof(val),
    )
    return result == 0


def _accent_blur(hwnd: int, tint_abgr: int) -> bool:
    try:
        set_attr = _user32.SetWindowCompositionAttribute
    except AttributeError:
        return False
    set_attr.argtypes = [wintypes.HWND, ctypes.POINTER(WINCOMPATTRDATA)]
    set_attr.restype = ctypes.c_int

    for state in (ACCENT_ENABLE_ACRYLICBLURBEHIND, ACCENT_ENABLE_BLURBEHIND):
        accent = ACCENT_POLICY(state, 2, tint_abgr, 0)
        data = WINCOMPATTRDATA(
            WCA_ACCENT_POLICY, ctypes.pointer(accent), ctypes.sizeof(accent)
        )
        if set_attr(wintypes.HWND(hwnd), ctypes.byref(data)):
            return True
    return False


def enable_glass(hwnd: int, tint_abgr: int = 0x1E141826) -> bool:
    """Applies a real backdrop blur. Returns False if none was available."""
    if _dwmapi is not None:
        _set_dwm_int(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1)

    if supports_system_backdrop():
        if _set_dwm_int(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW):
            return True
    return _accent_blur(hwnd, tint_abgr)


def round_corners(hwnd: int) -> None:
    """Lets DWM clip the window itself, so the blur follows the radius."""
    _set_dwm_int(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)


def make_non_activating(hwnd: int) -> None:
    """Keeps the overlay from ever taking focus from the active app."""
    get_long = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    set_long = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    style = get_long(wintypes.HWND(hwnd), GWL_EXSTYLE)
    set_long(
        wintypes.HWND(hwnd), GWL_EXSTYLE,
        style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
    )
