"""Settings window — « Simple ».

Flat #1A1A1A card, one hairline border, 12 px radius. The window is frameless
with a translucent background only so the corners can be rounded; everything
painted inside is opaque. No blur, no shadow, no gradient.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import branding
from ..audio import SILENCE_PEAK, input_devices, resolve_device
from ..logging_setup import log
from . import icons, theme as T

LANGUAGES = [
    ("Français", "fr"),
    ("Anglais", "en"),
    ("Espagnol", "es"),
    ("Allemand", "de"),
    ("Italien", "it"),
    ("Détection automatique", "auto"),
]

KEY_NAMES = {
    "ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Maj",
    "cmd": "Win", "super": "Win", "space": "Espace", "tab": "Tab",
    "enter": "Entrée", "esc": "Échap", "escape": "Échap",
}


def pretty_hotkey(combo: str) -> list[str]:
    """`<ctrl>+<space>` becomes ['Ctrl', 'Espace'] for the key caps."""
    keys = []
    for part in combo.split("+"):
        token = part.strip().strip("<>").lower()
        if not token:
            continue
        keys.append(
            KEY_NAMES.get(
                token, token.upper() if len(token) == 1 else token.capitalize()
            )
        )
    return keys or ["—"]


def build_qss() -> str:
    return f"""
    * {{
        font-family: {T.css_font_stack()};
        color: {T.TEXT.name()};
        font-size: {T.FIELD_SIZE}px;
    }}
    QLabel#rowLabel {{
        color: {T.LABEL.name()};
        font-size: {T.LABEL_SIZE}px;
    }}
    QLabel#title {{
        color: {T.TEXT.name()};
        font-size: {T.TITLE_SIZE}px;
        font-weight: 600;
    }}
    QLabel#help, QLabel#result {{
        color: {T.HELP.name()};
        font-size: {T.HELP_SIZE}px;
    }}
    QLabel#cap {{
        color: {T.TEXT.name()};
        font-size: {T.KEY_SIZE}px;
        font-weight: 600;
        background: {T.SURFACE.name()};
        border: 1px solid {T.BORDER.name()};
        border-radius: {T.KEY_RADIUS}px;
        min-height: {T.KEY_H - 2}px;
        padding: 0 9px;
    }}
    QFrame#divider {{
        background: {T.SEPARATOR.name()};
        border: none;
        min-height: 1px;
        max-height: 1px;
    }}
    QLineEdit, QComboBox {{
        background: {T.SURFACE.name()};
        border: 1px solid {T.BORDER.name()};
        border-radius: {T.FIELD_RADIUS}px;
        color: {T.TEXT.name()};
        min-height: {T.FIELD_H - 2}px;
        max-height: {T.FIELD_H - 2}px;
        padding: 0 14px;
        selection-background-color: {T.BORDER.name()};
    }}
    QLineEdit:focus, QComboBox:focus, QComboBox:on {{
        border: 1px solid {T.TEXT.name()};
    }}
    QComboBox::drop-down {{ border: none; width: 0px; }}
    QComboBox::down-arrow {{ image: none; width: 0px; height: 0px; }}
    QComboBox QAbstractItemView {{
        background: {T.SURFACE.name()};
        border: 1px solid {T.BORDER.name()};
        color: {T.TEXT.name()};
        padding: 4px;
        outline: none;
        selection-background-color: {T.GHOST_HOVER.name()};
    }}
    QPushButton#secondary {{
        background: {T.SURFACE.name()};
        border: 1px solid {T.BORDER.name()};
        border-radius: {T.FIELD_RADIUS}px;
        color: {T.TEXT.name()};
        min-height: {T.FIELD_H - 2}px;
        padding: 0 24px;
        font-weight: 600;
    }}
    QPushButton#secondary:hover {{
        background: {T.SECONDARY_HOVER.name()};
        border-color: {T.SECONDARY_HOVER_BORDER.name()};
    }}
    QPushButton#secondary:disabled {{ color: {T.HELP.name()}; }}
    QPushButton#primary {{
        background: {T.INVERT_BG.name()};
        border: 1px solid {T.INVERT_BG.name()};
        border-radius: {T.FIELD_RADIUS}px;
        color: {T.INVERT_FG.name()};
        min-height: {T.FIELD_H - 2}px;
        padding: 0 26px;
        font-weight: 700;
    }}
    QPushButton#primary:hover {{
        background: {T.PRIMARY_HOVER.name()};
        border-color: {T.PRIMARY_HOVER.name()};
    }}
    QPushButton#ghost {{
        background: transparent;
        border: none;
        border-radius: 14px;
        min-width: 28px; max-width: 28px;
        min-height: 28px; max-height: 28px;
        padding: 0;
    }}
    QPushButton#ghost:hover {{ background: {T.GHOST_HOVER.name()}; }}
    QCheckBox {{
        color: {T.TEXT.name()};
        spacing: 11px;
    }}
    QCheckBox::indicator {{
        width: {T.CHECKBOX}px; height: {T.CHECKBOX}px;
        border-radius: {T.CHECKBOX_RADIUS}px;
        background: {T.SURFACE.name()};
        border: 1px solid {T.BORDER.name()};
    }}
    QCheckBox::indicator:checked {{
        background: {T.INVERT_BG.name()};
        border: 1px solid {T.INVERT_BG.name()};
    }}
    """


def mic_icon(size: int = 18, colour: QColor | None = None) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    icons.draw_mic(p, QRectF(0, 0, size, size), colour or T.TEXT, stroke=0.075)
    p.end()
    return QIcon(pix)


class FlatComboBox(QComboBox):
    """QSS has no usable arrow primitive, so the chevron is painted."""

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        icons.draw_chevron(
            p, QPointF(self.width() - 18, self.height() / 2), T.TEXT_MUTED
        )
        p.end()


class FlatCheckBox(QCheckBox):
    """Adds the tick the stylesheet cannot draw inside the indicator."""

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isChecked():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        top = (self.height() - T.CHECKBOX) / 2
        icons.draw_check(
            p, QRectF(0, top, T.CHECKBOX, T.CHECKBOX), T.INVERT_FG
        )
        p.end()


class LogoMark(QWidget):
    """The application icon itself, so the titlebar always matches the .ico."""

    SIZE = 20

    def __init__(self):
        super().__init__()
        self.setFixedSize(self.SIZE, self.SIZE)
        self._pixmap = branding.icon().pixmap(self.SIZE, self.SIZE)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._pixmap.isNull():
            icons.draw_wave(p, QRectF(0, 0, self.SIZE, self.SIZE), T.TEXT)
        else:
            p.drawPixmap(0, 0, self._pixmap)
        p.end()


class CloseButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.setObjectName("ghost")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        icons.draw_close(
            p, QRectF(0, 0, self.width(), self.height()), T.TEXT_MUTED, stroke=0.055
        )
        p.end()


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self._drag_from: QPoint | None = None

        self.setWindowTitle("YanzVoice — Réglages")
        self.setWindowIcon(branding.icon())
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(build_qss())
        self.setFixedWidth(T.WINDOW_W)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_titlebar())
        column.addWidget(self._build_body())

        QTimer.singleShot(0, self.key_edit.setFocus)

    # ---------- painting ----------

    def paintEvent(self, _event):
        """Flat card: one fill, one hairline border, one titlebar rule."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)

        path = QPainterPath()
        path.addRoundedRect(body, T.WINDOW_RADIUS, T.WINDOW_RADIUS)
        p.fillPath(path, T.BG)

        p.setPen(QPen(T.BORDER, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(body, T.WINDOW_RADIUS, T.WINDOW_RADIUS)

        p.setPen(QPen(T.SEPARATOR, 1.0))
        p.drawLine(
            QPointF(1, T.TITLEBAR_H - 0.5),
            QPointF(self.width() - 1, T.TITLEBAR_H - 0.5),
        )
        p.end()

    # ---------- construction ----------

    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(T.TITLEBAR_H)
        row = QHBoxLayout(bar)
        row.setContentsMargins(T.MARGIN_H - 14, 0, 12, 0)
        row.setSpacing(10)

        row.addWidget(LogoMark())
        title = QLabel("YanzVoice — Réglages")
        title.setObjectName("title")
        row.addWidget(title)
        row.addStretch(1)

        close = CloseButton()
        close.clicked.connect(self.reject)
        row.addWidget(close)
        return bar

    def _row(self, grid: QGridLayout, line: int, label: str, field: QWidget) -> None:
        tag = QLabel(label)
        tag.setObjectName("rowLabel")
        tag.setFixedWidth(T.LABEL_COL)
        grid.addWidget(tag, line, 0, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(field, line, 1)

    def _build_body(self) -> QWidget:
        body = QWidget()
        column = QVBoxLayout(body)
        column.setContentsMargins(T.MARGIN_H, T.MARGIN_V, T.MARGIN_H, T.MARGIN_V)
        column.setSpacing(T.ROW_GAP)

        grid = QGridLayout()
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(T.ROW_GAP)
        grid.setColumnStretch(1, 1)

        self.key_edit = QLineEdit(self.cfg.get("groq_api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("gsk_…")
        self._row(grid, 0, "Clé API Groq", self.key_edit)

        self.lang_box = FlatComboBox()
        for label, code in LANGUAGES:
            self.lang_box.addItem(label, code)
        index = self.lang_box.findData(self.cfg.get("language", "fr"))
        self.lang_box.setCurrentIndex(index if index >= 0 else 0)
        self._row(grid, 1, "Langue", self.lang_box)

        self.device_box = FlatComboBox()
        self.device_box.addItem("Périphérique système par défaut", "")
        for _i, name, channels, rate in input_devices():
            self.device_box.addItem(f"{name}  ({channels}ch, {int(rate)} Hz)", name)
        found = self.device_box.findData(self.cfg.get("input_device", ""))
        self.device_box.setCurrentIndex(found if found >= 0 else 0)
        self._row(grid, 2, "Micro", self.device_box)

        self.test_button = QPushButton("  Tester le micro (2 s)")
        self.test_button.setObjectName("secondary")
        self.test_button.setIcon(mic_icon(18))
        self.test_button.setIconSize(QSize(18, 18))
        self.test_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_button.clicked.connect(self._test_mic)
        self._row(grid, 3, "", self.test_button)

        column.addLayout(grid)

        self.test_result = QLabel("")
        self.test_result.setObjectName("result")
        self.test_result.setWordWrap(True)
        self.test_result.hide()
        column.addWidget(self.test_result)

        help_label = QLabel(
            "Clé gratuite sur <a style='color:{link}' "
            "href='https://console.groq.com/keys'>console.groq.com/keys</a>"
            " — aucune carte bancaire requise.".format(link=T.TEXT.name())
        )
        help_label.setObjectName("help")
        help_label.setOpenExternalLinks(True)
        help_label.setWordWrap(True)
        column.addWidget(help_label)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        column.addWidget(divider)

        self.paste_box = FlatCheckBox("Coller automatiquement dans l'application active")
        self.paste_box.setChecked(bool(self.cfg.get("auto_paste", True)))
        self.paste_box.setCursor(Qt.CursorShape.PointingHandCursor)
        column.addWidget(self.paste_box)

        column.addWidget(self._build_hotkey_row())
        column.addSpacing(4)
        column.addLayout(self._build_actions())
        return body

    def _build_hotkey_row(self) -> QWidget:
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(7)

        lead = QLabel("Raccourci global :")
        lead.setObjectName("help")
        line.addWidget(lead)

        for position, key in enumerate(
            pretty_hotkey(self.cfg.get("hotkey", "<ctrl>+<space>"))
        ):
            if position:
                plus = QLabel("+")
                plus.setObjectName("help")
                line.addWidget(plus)
            cap = QLabel(key)
            cap.setObjectName("cap")
            line.addWidget(cap)

        tail = QLabel("(modifiable dans config.json)")
        tail.setObjectName("help")
        line.addWidget(tail)
        line.addStretch(1)
        return row

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)

        cancel = QPushButton("Annuler")
        cancel.setObjectName("secondary")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)

        save = QPushButton("Enregistrer")
        save.setObjectName("primary")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setDefault(True)
        save.clicked.connect(self.accept)
        row.addWidget(save)
        return row

    # ---------- behaviour ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() < T.TITLEBAR_H:
                self._drag_from = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_from is not None:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, _event):
        self._drag_from = None

    def _test_mic(self) -> None:
        """Records a short take and reports the level in plain language."""
        name = self.device_box.currentData() or None
        index, resolved = resolve_device(name)
        if index is None:
            self._show_result("Aucun périphérique d'entrée disponible.")
            return
        self.test_button.setEnabled(False)
        self.test_button.setText("  Parle maintenant…")
        QTimer.singleShot(50, lambda: self._run_test(index, resolved))

    def _show_result(self, text: str) -> None:
        self.test_result.setText(text)
        self.test_result.show()

    def _run_test(self, index: int, resolved: str) -> None:
        import numpy as np
        import sounddevice as sd

        try:
            info = sd.query_devices(index)
            rate = float(info["default_samplerate"])
            channels = min(2, max(1, int(info["max_input_channels"])))
            data = sd.rec(
                int(2 * rate), samplerate=rate, channels=channels,
                dtype="float32", device=index,
            )
            sd.wait()
            mono = data.mean(axis=1) if channels > 1 else data[:, 0]
            peak = float(np.max(np.abs(mono)))
        except Exception as exc:
            log.error("mic test failed on %r: %s", resolved, exc)
            self._show_result(f"Échec sur « {resolved} » : {exc}")
        else:
            log.info("mic test %r peak=%.5f", resolved, peak)
            if peak < SILENCE_PEAK:
                self._show_result(
                    f"« {resolved} » : niveau {peak:.4f} — trop faible, la "
                    "transcription échouera. Essaie un autre périphérique."
                )
            else:
                self._show_result(f"« {resolved} » : niveau {peak:.3f} — bon.")
        finally:
            self.test_button.setEnabled(True)
            self.test_button.setText("  Tester le micro (2 s)")

    def values(self) -> dict:
        cfg = dict(self.cfg)
        cfg["groq_api_key"] = self.key_edit.text().strip()
        cfg["language"] = self.lang_box.currentData()
        cfg["auto_paste"] = self.paste_box.isChecked()
        cfg["input_device"] = self.device_box.currentData() or ""
        return cfg
