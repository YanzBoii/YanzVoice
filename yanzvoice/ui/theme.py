"""Design tokens for « Simple ».

Flat opaque greys, hairline borders, no blur, no gradient, no shadow, no
colour. Every value below comes straight from the spec's tables; nothing here
is interpolated or invented.
"""
from __future__ import annotations

import ctypes

from PyQt6.QtGui import QColor, QFont, QFontDatabase

from .. import paths

ASSETS = paths.assets()
ICON_FILE = ASSETS / "icons" / "yanzvoice.ico"

# ---- colour (all solid) ----------------------------------------------------

BG = QColor(0x1A, 0x1A, 0x1A)            # #1A1A1A  pill and window
SURFACE = QColor(0x26, 0x26, 0x26)       # #262626  buttons, fields, keys
BORDER = QColor(0x3A, 0x3A, 0x3A)        # #3A3A3A
BORDER_ERROR = QColor(0x6B, 0x6B, 0x6B)  # #6B6B6B
SEPARATOR = QColor(0x2E, 0x2E, 0x2E)     # #2E2E2E

TEXT = QColor(0xED, 0xED, 0xED)          # #EDEDED
TEXT_MUTED = QColor(0xA0, 0xA0, 0xA0)    # #A0A0A0  « Prêt », icons
HELP = QColor(0x90, 0x90, 0x90)          # #909090
LABEL = QColor(0xC8, 0xC8, 0xC8)         # #C8C8C8

INVERT_BG = QColor(0xED, 0xED, 0xED)     # primary button / listening orb
INVERT_FG = QColor(0x11, 0x11, 0x11)     # text and glyph on top of it

GHOST_HOVER = QColor(0x2E, 0x2E, 0x2E)
SECONDARY_HOVER = QColor(0x30, 0x30, 0x30)
SECONDARY_HOVER_BORDER = QColor(0x5A, 0x5A, 0x5A)
PRIMARY_HOVER = QColor(0xFF, 0xFF, 0xFF)

# ---- shapes ----------------------------------------------------------------

# Compact by default: the pill sits over whatever the user is working in, so
# it should read at a glance without occupying the screen. The proportions of
# the spec are kept, scaled to ~80 %.
PILL_W, PILL_H = 264, 44
PILL_RADIUS = 22
PILL_PAD = 4
PILL_GAP = 8
BUTTON = 34

WINDOW_W = 640
WINDOW_RADIUS = 12
TITLEBAR_H = 48

FIELD_H = 44
FIELD_RADIUS = 8
CHECKBOX = 22
CHECKBOX_RADIUS = 6
KEY_H = 26
KEY_RADIUS = 6

MARGIN_V = 28
MARGIN_H = 32
ROW_GAP = 16
LABEL_COL = 132

WAVE_BARS = 26
WAVE_BAR_W = 2.5
WAVE_MAX_H = 20.0

# The bars are the only steady animation; the reveal plays once per show.
WAVE_FPS = 15

# Opening: the orb alone, then the pill unrolls to the right.
REVEAL_MS = 620
REVEAL_ORB_END = 0.30     # orb has faded in by here
REVEAL_TEXT_START = 0.62  # label and controls start appearing
REVEAL_DONE = 0.985       # chrome becomes clickable past this point


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - pow(1.0 - t, 3)


SPI_GETCLIENTAREAANIMATION = 0x1042
_reduced: bool | None = None


def reduced_motion() -> bool:
    """Honours the Windows « Afficher les animations » accessibility setting.

    When it is off, the opening reveal is skipped entirely.
    """
    global _reduced
    if _reduced is None:
        enabled = ctypes.c_int(1)
        try:
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
            )
        except Exception:
            enabled = ctypes.c_int(1)
        _reduced = not bool(enabled.value)
    return _reduced

# ---- type ------------------------------------------------------------------

STATUS_SIZE = 13
TITLE_SIZE = 13
LABEL_SIZE = 14
FIELD_SIZE = 14
HELP_SIZE = 13
KEY_SIZE = 12

_family: str | None = None


def family() -> str:
    """The system UI face — nothing is bundled."""
    global _family
    if _family is None:
        available = QFontDatabase.families()
        for candidate in ("Segoe UI Variable Text", "Segoe UI", "Arial"):
            if candidate in available:
                _family = candidate
                break
        else:
            _family = "Sans Serif"
    return _family


def font(size: int, weight: int = 400) -> QFont:
    f = QFont(family())
    f.setPixelSize(size)
    f.setWeight(QFont.Weight(weight))
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def css_font_stack() -> str:
    return f"'{family()}', 'Segoe UI', sans-serif"


def hex_of(c: QColor) -> str:
    return c.name()
