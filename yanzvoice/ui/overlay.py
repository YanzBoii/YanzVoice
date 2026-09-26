"""The floating pill — « Simple ».

320 x 56, flat #1A1A1A, one hairline border, no blur and no gradient. The
window keeps a translucent background only so the 28 px radius has somewhere
to show; everything inside it is opaque.

The listening bars are the only thing that moves.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from . import icons, theme as T
from .effects import make_non_activating

IDLE, RECORDING, WORKING, DONE, ERROR = "idle", "recording", "working", "done", "error"

LABELS = {
    IDLE: "Prêt",
    WORKING: "Transcription…",
    DONE: "Collé",
    ERROR: "Échec de la transcription",
}


class Overlay(QWidget):
    mic_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    close_clicked = pyqtSignal()
    moved = pyqtSignal(int, int)

    def __init__(self, recorder):
        super().__init__(None)
        self._recorder = recorder
        self.state = IDLE
        self.message = LABELS[IDLE]

        self._hover: str | None = None
        self._drag_from: QPoint | None = None
        self._dragged = False
        self._reveal = 1.0
        self._reveal_start = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(T.PILL_W, T.PILL_H)
        self.setMouseTracking(True)

        # Drives the opening reveal, then the bars while recording. Idle, it
        # is stopped: nothing on a resting pill needs repainting.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ---------- geometry ----------

    def _orb_rect(self) -> QRectF:
        # Centred inside the left cap, so the circle sits true in the radius.
        offset = (T.PILL_H - T.BUTTON) / 2
        return QRectF(offset, offset, T.BUTTON, T.BUTTON)

    def _close_rect(self) -> QRectF:
        offset = (T.PILL_H - T.BUTTON) / 2
        return QRectF(
            T.PILL_W - offset - T.BUTTON, offset, T.BUTTON, T.BUTTON
        )

    def _dots_rect(self) -> QRectF:
        return self._close_rect().translated(-T.BUTTON, 0)

    def _revealed_width(self) -> float:
        """Width of the pill body right now: a circle first, then the full bar."""
        eased = T.ease_out_cubic(
            (self._reveal - T.REVEAL_ORB_END) / (1.0 - T.REVEAL_ORB_END)
        ) if self._reveal > T.REVEAL_ORB_END else 0.0
        return T.PILL_H + (T.PILL_W - T.PILL_H) * eased

    def _content_opacity(self) -> float:
        if self._reveal >= 1.0:
            return 1.0
        if self._reveal <= T.REVEAL_TEXT_START:
            return 0.0
        return (self._reveal - T.REVEAL_TEXT_START) / (1.0 - T.REVEAL_TEXT_START)

    def _shows_chrome(self) -> bool:
        """Only the resting state carries « … » and « × », per the spec.

        Hidden while the pill is still unrolling, so a click never lands on a
        control that has not reached its final place.
        """
        return self.state == IDLE and self._reveal >= T.REVEAL_DONE

    def _content_rect(self) -> QRectF:
        left = self._orb_rect().right() + T.PILL_GAP
        right = (
            self._dots_rect().left() - T.PILL_GAP
            if self._shows_chrome()
            else T.PILL_W - (T.PILL_H - T.BUTTON) / 2 - T.PILL_GAP
        )
        return QRectF(left, 0, max(10.0, right - left), T.PILL_H)

    # ---------- lifecycle ----------

    def showEvent(self, event):
        super().showEvent(event)
        make_non_activating(int(self.winId()))
        self.start_reveal()

    def start_reveal(self) -> None:
        """Plays the opening once: orb first, then the bar unrolls."""
        if T.reduced_motion():
            self._reveal = 1.0
            return
        self._reveal = 0.0
        self._reveal_start = time.monotonic()
        self._timer.start(16)

    def place_bottom_center(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.center().x() - T.PILL_W // 2, area.bottom() - T.PILL_H - 56)

    def move_onto_screen(self, x: int, y: int) -> bool:
        """Moves to (x, y), clamped so the pill stays reachable.

        Returns False when no screen covers that point — a monitor was
        unplugged since the position was saved — so the caller can recentre.
        """
        screens = QApplication.screens()
        if not screens:
            return False
        centre = QPoint(x + T.PILL_W // 2, y + T.PILL_H // 2)
        target = next(
            (s for s in screens if s.availableGeometry().contains(centre)), None
        )
        if target is None:
            return False
        area = target.availableGeometry()
        x = max(area.left() - T.PILL_W // 3, min(x, area.right() - T.PILL_W * 2 // 3))
        y = max(area.top(), min(y, area.bottom() - T.PILL_H))
        self.move(x, y)
        return True

    def set_state(self, state: str, message: str = "") -> None:
        self.state = state
        self.message = message or LABELS.get(state, self.message)
        self._sync_timer()
        self.update()

    def _sync_timer(self) -> None:
        """Runs at 60 fps while revealing, at the bar rate while recording."""
        if self._reveal < 1.0:
            self._timer.start(16)
        elif self.state == RECORDING:
            self._timer.start(1000 // T.WAVE_FPS)
        else:
            self._timer.stop()

    def _tick(self) -> None:
        if self._reveal < 1.0:
            elapsed = (time.monotonic() - self._reveal_start) * 1000
            self._reveal = min(1.0, elapsed / T.REVEAL_MS)
            if self._reveal >= 1.0:
                self._sync_timer()
        self.update()

    # ---------- painting ----------

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # During the opening the body is narrower than the window; the rest
        # of the surface stays transparent.
        width = self._revealed_width()
        body = QRectF(0.5, 0.5, width - 1, T.PILL_H - 1)

        if self._reveal <= T.REVEAL_ORB_END:
            # Only the orb exists yet, fading up in place.
            p.setOpacity(
                min(1.0, self._reveal / T.REVEAL_ORB_END) if T.REVEAL_ORB_END else 1.0
            )

        path = QPainterPath()
        path.addRoundedRect(body, T.PILL_RADIUS, T.PILL_RADIUS)
        p.fillPath(path, T.BG)

        border = T.BORDER_ERROR if self.state == ERROR else T.BORDER
        p.setPen(QPen(border, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(body, T.PILL_RADIUS, T.PILL_RADIUS)

        self._paint_orb(p)

        opacity = self._content_opacity()
        if opacity > 0.01:
            p.save()
            # Clip to the body so nothing spills past the unrolling edge.
            p.setClipPath(path)
            p.setOpacity(opacity)
            self._paint_content(p)
            p.restore()

        if self._shows_chrome():
            self._paint_ghost(p, self._dots_rect(), "dots", icons.draw_dots)
            self._paint_ghost(p, self._close_rect(), "close", icons.draw_close)
        p.end()

    def _paint_orb(self, p: QPainter) -> None:
        rect = self._orb_rect()
        recording = self.state == RECORDING

        p.setPen(Qt.PenStyle.NoPen)
        if recording:
            # Listening reads as an inverted orb, not as a colour.
            p.setBrush(T.INVERT_BG)
            p.drawEllipse(rect)
            icons.draw_stop(p, rect, T.INVERT_FG, side=14.0, radius=3.0)
            return

        p.setBrush(T.SURFACE)
        p.drawEllipse(rect)
        p.setPen(QPen(T.BORDER, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))

        if self.state == WORKING:
            icons.draw_dots(p, rect, T.TEXT)
        elif self.state == DONE:
            icons.draw_check(p, rect, T.TEXT)
        elif self.state == ERROR:
            icons.draw_alert(p, rect, T.TEXT)
        else:
            icons.draw_mic(p, rect, T.TEXT)

    def _paint_ghost(self, p: QPainter, rect: QRectF, key: str, draw) -> None:
        if self._hover == key:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(T.GHOST_HOVER)
            p.drawEllipse(rect)
        draw(p, rect, T.TEXT_MUTED)

    def _paint_content(self, p: QPainter) -> None:
        rect = self._content_rect()
        if self.state == RECORDING:
            self._paint_bars(p, rect)
            return

        weight = 600 if self.state == DONE else 500
        p.setFont(T.font(T.STATUS_SIZE, weight))
        p.setPen(T.TEXT_MUTED if self.state == IDLE else T.TEXT)

        text = p.fontMetrics().elidedText(
            self.message, Qt.TextElideMode.ElideRight, int(rect.width())
        )
        flags = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        p.drawText(rect, int(flags), text)

    def _paint_bars(self, p: QPainter, rect: QRectF) -> None:
        levels = self._recorder.levels
        count = min(T.WAVE_BARS, len(levels))
        gap = (rect.width() - count * T.WAVE_BAR_W) / max(1, count - 1)
        span = count * T.WAVE_BAR_W + (count - 1) * gap
        start_x = rect.left() + (rect.width() - span) / 2
        mid = rect.center().y()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.TEXT)
        for i in range(count):
            level = float(levels[len(levels) - count + i])
            height = max(3.0, min(1.0, level) * T.WAVE_MAX_H)
            x = start_x + i * (T.WAVE_BAR_W + gap)
            path = QPainterPath()
            path.addRoundedRect(
                QRectF(x, mid - height / 2, T.WAVE_BAR_W, height), 1.5, 1.5
            )
            p.fillPath(path, T.TEXT)

    # ---------- interaction ----------

    def _hit(self, pos: QPointF) -> str | None:
        if self._orb_rect().contains(pos):
            return "orb"
        if self._shows_chrome():
            if self._dots_rect().contains(pos):
                return "dots"
            if self._close_rect().contains(pos):
                return "close"
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hit = self._hit(event.position())
        if hit == "orb":
            self.mic_clicked.emit()
        elif hit == "dots":
            self.settings_clicked.emit()
        elif hit == "close":
            self.close_clicked.emit()
        else:
            self._drag_from = event.globalPosition().toPoint() - self.pos()
            self._dragged = False

    def mouseMoveEvent(self, event):
        hit = self._hit(event.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if hit
                else Qt.CursorShape.ArrowCursor
            )
            self.update()
        if self._drag_from is not None:
            self._dragged = True
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, _event):
        was_dragging, self._drag_from = self._drag_from is not None, None
        if was_dragging and self._dragged:
            self.move_onto_screen(self.pos().x(), self.pos().y())
            self.moved.emit(self.pos().x(), self.pos().y())
        self._dragged = False

    def leaveEvent(self, event):
        if self._hover is not None:
            self._hover = None
            self.update()
        self.unsetCursor()
        super().leaveEvent(event)
