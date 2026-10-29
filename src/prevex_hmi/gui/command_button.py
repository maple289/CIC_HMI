"""Raised industrial button with independent acknowledgment LED."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


def lock_icon(locked,dark=True):
    """Native vector-style padlock: no dependence on emoji/font support."""
    pixmap=QPixmap(24,24);pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(('#efb753' if locked else '#e7edf7') if dark else ('#95651B' if locked else '#243447')),2))
    painter.drawArc(7,2,10,14,0 if locked else 30*16,180*16)
    painter.drawLine(7,9,7,12)
    if locked:painter.drawLine(17,9,17,12)
    painter.drawRoundedRect(4,11,16,11,2,2);painter.drawLine(12,15,12,18);painter.end()
    return QIcon(pixmap)


class CommandButton(QWidget):
    def __init__(self, text, callback, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48);self.dark=True;self.led_color='#303b48'
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(9)
        self.button = QPushButton(text); self.button.setObjectName('industrialCommand')
        self.button.setMinimumHeight(46); self.button.clicked.connect(callback); row.addWidget(self.button, 1)
        self.led = QLabel(); self.led.setFixedSize(16, 16); row.addWidget(self.led)
        self.timer = QTimer(self); self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setSingleShot(True); self.timer.timeout.connect(self.reset)
        self.reset()

    def reset(self):
        self.timer.stop(); self.set_led('#303b48', 'No recent acknowledgment')

    def set_led(self, color, detail):
        from .theme import display_color
        self.led_color=color
        shade=display_color(color,self.dark) if color!='#303b48' or self.dark else '#C4CFD9'
        self.led.setStyleSheet(f'background:{shade};border:2px solid {"#17202c" if self.dark else "#9EADBA"};border-radius:8px;')
        self.led.setToolTip(detail); self.led.setAccessibleName(detail)

    def set_theme(self,dark):
        self.dark=dark;self.set_led(self.led_color,self.led.toolTip())
        state=self.button.property('lockState')
        if state in ('True','False'):self.button.setIcon(lock_icon(state=='True',dark))

    def feedback(self, accepted):
        self.set_led('#39c66c' if accepted else '#ed575d',
                     'Modbus acknowledgment received; execution is not confirmed' if accepted else 'Command rejected or transmission failed')
        self.timer.start(3000)

    def setEnabled(self, enabled):
        # Keep the result LED legible even while the command button is disabled.
        self.button.setEnabled(enabled)

    def isEnabled(self):
        return self.button.isEnabled()

    def set_lock_action(self, locked):
        if self.button.property('lockState')==str(locked):return
        self.button.setProperty('lockState',str(locked))
        self.button.setText('CAL LOCK — ?' if locked is None else 'UNLOCK CAL' if locked else 'LOCK CAL')
        self.button.setIcon(QIcon() if locked is None else lock_icon(locked,self.dark))
        self.button.setAccessibleName(self.button.text()+(' — lock state unavailable' if locked is None else ' — software lock locked' if locked else ' — software lock unlocked'))
