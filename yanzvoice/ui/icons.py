"""Vector icons drawn with QPainter so they stay crisp at any DPI.

Each icon is drawn inside a square box and scales from its width, so one
routine serves both an 18 px titlebar mark and a 44 px pill orb.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def draw_mic(p: QPainter, rect: QRectF, color: QColor, stroke: float = 0.045) -> None:
    """Dictaphone capsule over its stand."""
    w = rect.width()
    p.setPen(_pen(color, max(1.2, w * stroke)))
    p.setBrush(Qt.BrushStyle.NoBrush)

    capsule = QRectF(
        rect.left() + w * 0.405, rect.top() + w * 0.245, w * 0.19, w * 0.29
    )
    path = QPainterPath()
    path.addRoundedRect(capsule, capsule.width() / 2, capsule.width() / 2)
    p.fillPath(path, color)

    arc = QRectF(rect.left() + w * 0.315, rect.top() + w * 0.365, w * 0.37, w * 0.30)
    p.drawArc(arc, 180 * 16, 180 * 16)

    cx = rect.center().x()
    p.drawLine(QPointF(cx, rect.top() + w * 0.665), QPointF(cx, rect.top() + w * 0.755))


def draw_stop(
    p: QPainter, rect: QRectF, color: QColor, side: float = 14.0, radius: float = 3.0
) -> None:
    """A rounded square, sized in absolute pixels per the spec."""
    c = rect.center()
    square = QRectF(c.x() - side / 2, c.y() - side / 2, side, side)
    path = QPainterPath()
    path.addRoundedRect(square, radius, radius)
    p.fillPath(path, color)


def draw_dots(p: QPainter, rect: QRectF, color: QColor) -> None:
    """Three dots: the settings affordance, and the transcription orb."""
    w = rect.width()
    r = w * 0.052
    c = rect.center()
    gap = w * 0.16
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    for dx in (-gap, 0.0, gap):
        p.drawEllipse(QPointF(c.x() + dx, c.y()), r, r)


def draw_close(p: QPainter, rect: QRectF, color: QColor, stroke: float = 0.038) -> None:
    w = rect.width()
    p.setPen(_pen(color, max(1.1, w * stroke)))
    m = w * 0.385
    r = rect.adjusted(m, m, -m, -m)
    p.drawLine(r.topLeft(), r.bottomRight())
    p.drawLine(r.topRight(), r.bottomLeft())


def draw_check(p: QPainter, rect: QRectF, color: QColor) -> None:
    w = rect.width()
    path = QPainterPath(QPointF(rect.left() + w * 0.345, rect.top() + w * 0.510))
    path.lineTo(rect.left() + w * 0.450, rect.top() + w * 0.615)
    path.lineTo(rect.left() + w * 0.655, rect.top() + w * 0.395)

    p.setPen(_pen(color, max(1.4, w * 0.048)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def draw_alert(p: QPainter, rect: QRectF, color: QColor) -> None:
    """Exclamation mark for the error state."""
    w = rect.width()
    c = rect.center()
    p.setPen(_pen(color, max(1.4, w * 0.050)))
    p.drawLine(
        QPointF(c.x(), rect.top() + w * 0.330), QPointF(c.x(), rect.top() + w * 0.545)
    )
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    r = max(1.0, w * 0.030)
    p.drawEllipse(QPointF(c.x(), rect.top() + w * 0.650), r, r)


def draw_chevron(p: QPainter, centre: QPointF, color: QColor, size: float = 4.5) -> None:
    """The dropdown marker QSS cannot draw properly on its own."""
    p.setPen(_pen(color, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(
        QPointF(centre.x() - size, centre.y() - size * 0.45),
        QPointF(centre.x(), centre.y() + size * 0.55),
    )
    p.drawLine(
        QPointF(centre.x(), centre.y() + size * 0.55),
        QPointF(centre.x() + size, centre.y() - size * 0.45),
    )


def draw_wave(p: QPainter, rect: QRectF, color: QColor) -> None:
    """The YanzVoice mark: five rounded bars, tallest in the middle.

    Proportions taken from the logo's 256 px artboard, where the bars are
    16 wide on a 28 pitch with heights 36 / 66 / 96 / 66 / 36.
    """
    w = rect.width()
    bar = w * 0.0925          # 16 / 173, the mark's own bounding width
    pitch = w * 0.1620
    heights = (0.28, 0.52, 0.75, 0.52, 0.28)
    total = bar + pitch * 4
    left = rect.left() + (w - total) / 2
    mid = rect.center().y()

    p.setPen(Qt.PenStyle.NoPen)
    for index, factor in enumerate(heights):
        height = rect.height() * factor
        x = left + index * pitch
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(x, mid - height / 2, bar, height), bar / 2, bar / 2
        )
        p.fillPath(path, color)
