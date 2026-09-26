"""Clipboard hand-off and automatic paste into the previously focused window."""
from __future__ import annotations

import ctypes
import time

import pyperclip
from pynput.keyboard import Controller, Key

_user32 = ctypes.windll.user32
_keyboard = Controller()


def foreground_window() -> int:
    """Handle of the window the user was typing in, captured before we show up."""
    return int(_user32.GetForegroundWindow())


def _focus(hwnd: int) -> None:
    if not hwnd or not _user32.IsWindow(hwnd):
        return
    if _user32.GetForegroundWindow() == hwnd:
        return
    # Attaching to the foreground thread lifts the OS restriction on
    # SetForegroundWindow coming from a background process.
    target_thread = _user32.GetWindowThreadProcessId(hwnd, None)
    our_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    attached = bool(_user32.AttachThreadInput(our_thread, target_thread, True))
    try:
        _user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            _user32.AttachThreadInput(our_thread, target_thread, False)


def copy(text: str) -> None:
    pyperclip.copy(text)


def paste_into(hwnd: int, text: str) -> None:
    """Puts text on the clipboard and sends Ctrl+V to the target window."""
    copy(text)
    _focus(hwnd)
    time.sleep(0.06)
    with _keyboard.pressed(Key.ctrl):
        _keyboard.press("v")
        _keyboard.release("v")
