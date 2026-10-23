"""Range-aware circular process gauge drawn natively with Qt."""
from __future__ import annotations

from dataclasses import dataclass
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from prevex_hmi.gui.presentation import format_reading, measurement, severity


@dataclass(frozen=True)
class GaugeState:
    value: float | None = None
    maximum: float | None = None
    unit: str = ""
    reading: str = "--"
    status: str = "Waiting for first update"
    color: str = "#8290a5"
    bands: tuple[tuple[float, float, str], ...] = ()
    thresholds: str = "Alarm bands awaiting setpoints"

    @property
    def fraction(self) -> float | None:
        if self.value is None or self.maximum is None:
            return None
        return min(1.0, max(0.0, self.value / self.maximum))

    @property
    def range_note(self) -> str:
        if self.maximum is None:
            return "Range unavailable"
        if self.value is not None and self.value < 0:
            return "BELOW RANGE"
        if self.value is not None and self.value > self.maximum:
            return "ABOVE RANGE"
        return f"Range 0 - {self.maximum:g} {self.unit}"


def gauge_state(snapshot: dict | None) -> GaugeState:
    if snapshot is None:
        return GaugeState()
    value, unit = measurement(snapshot)
    color, status = severity(snapshot)
    if value is None:
        color = "#8290a5"
    # FULLSCLE is the engineering full-scale value, not reading-format raw data.
    # Never substitute the signed raw-word maximum for analyzer range.
    raw_maximum = snapshot["raw"].get(3)
    maximum = float(raw_maximum) if type(raw_maximum) is int and raw_maximum > 0 else None
    bands = ()
    thresholds = "Alarm bands awaiting setpoints"
    if snapshot["quality"] == "GOOD" and maximum is not None:
        low, _ = measurement(snapshot, 5)
        high, _ = measurement(snapshot, 6)
        if low is not None and high is not None and 0 <= low < high <= maximum:
            low, high = float(low), float(high)
            if snapshot["config"]["family"] == "BTU":
                bands = ((0, low, "#efb753"), (low, high, "#39c6a4"), (high, maximum, "#f27778"))
                thresholds = f"Low alarm {low:g}  |  High alarm {high:g} {unit}"
            else:
                bands = ((0, low, "#39c6a4"), (low, high, "#efb753"), (high, maximum, "#f27778"))
                thresholds = f"Warning {low:g}  |  Danger {high:g} {unit}"
        elif low is not None and high is not None:
            thresholds = "Alarm thresholds outside displayed range / unverified"
    if snapshot["quality"] != "GOOD":
        thresholds = "No current reading - indicator hidden"
    return GaugeState(
        value=None if value is None else float(value), maximum=maximum,
        unit=unit if value is not None else "", reading=format_reading(snapshot),
        status=status if value is not None or snapshot["quality"] != "GOOD" else "Reading unavailable",
        color=color, bands=bands, thresholds=thresholds,
    )


class CircularGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = GaugeState()
        self.dark = True
        self.setMinimumSize(350, 330)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("Selected analyzer reading and measurement range")

    def set_snapshot(self, snapshot: dict | None) -> None:
        self.state = gauge_state(snapshot)
        self.setAccessibleDescription(f"{self.state.reading} {self.state.unit}; {self.state.status}; {self.state.range_note}; {self.state.thresholds}")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = min(self.width() / 460, self.height() / 430)
        painter.translate((self.width() - 460 * scale) / 2, (self.height() - 430 * scale) / 2)
        painter.scale(scale, scale)
        painter.translate(0,20)
        text = "#e7edf7" if self.dark else "#172335"
        muted = "#adbbcf" if self.dark else "#425570"
        track = "#2c3b50" if self.dark else "#d5deea"
        arc = QRectF(82, 42, 296, 296)

        def draw_arc(start: float, end: float, color: str, width=18):
            painter.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.FlatCap))
            painter.drawArc(arc, round((225 - start * 270) * 16), round(-(end - start) * 270 * 16))

        draw_arc(0, 1, track)
        if self.state.maximum:
            for low, high, color in self.state.bands:
                draw_arc(low / self.state.maximum, high / self.state.maximum, color)
            for index in range(11):
                angle = math.radians(225 - index * 27)
                outer = QPointF(230 + 171 * math.cos(angle), 190 - 171 * math.sin(angle))
                inner = QPointF(230 + 162 * math.cos(angle), 190 - 162 * math.sin(angle))
                painter.setPen(QPen(QColor(muted), 1.5))
                painter.drawLine(inner, outer)
            for fraction in (0, 0.25, 0.5, 0.75, 1):
                angle = math.radians(225 - fraction * 270)
                x, y = 230 + 193 * math.cos(angle), 190 - 193 * math.sin(angle)
                painter.setFont(QFont(self.font().family(), 10))
                painter.setPen(QColor(muted))
                painter.drawText(QRectF(x - 32, y - 12, 64, 24), Qt.AlignCenter, f"{fraction * self.state.maximum:g}")
        fraction = self.state.fraction
        if fraction is not None:
            # The indicator clamps to the arc; the numeric reading remains exact.
            angle = math.radians(225 - fraction * 270)
            dot = QPointF(230 + 148 * math.cos(angle), 190 - 148 * math.sin(angle))
            painter.setPen(QPen(QColor(text), 3))
            painter.setBrush(QColor(self.state.color))
            painter.drawEllipse(dot, 9, 9)

        def label(rect, content, size, color, bold=False):
            painter.setFont(QFont(self.font().family(), size, QFont.Bold if bold else QFont.Normal))
            painter.setPen(QColor(color))
            painter.drawText(QRectF(*rect), Qt.AlignCenter, content)

        label((105, 125, 250, 67), self.state.reading, 36, self.state.color, True)
        label((100, 193, 260, 30), self.state.unit, 13, muted)
        label((100, 235, 260, 35), self.state.status, 13, self.state.color, True)
        label((20, 331, 420, 28), self.state.range_note, 12, text)
        label((0, 373, 460, 28), self.state.thresholds, 10, muted)
        painter.end()
