"""Raised industrial button with independent acknowledgment LED."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class CommandButton(QWidget):
    def __init__(self, text, callback, parent=None):
        super().__init__(parent)
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
        self.led.setStyleSheet(f'background:{color};border:2px solid #17202c;border-radius:8px;')
        self.led.setToolTip(detail); self.led.setAccessibleName(detail)

    def feedback(self, accepted):
        self.set_led('#39c66c' if accepted else '#ed575d',
                     'Modbus acknowledgment received; execution is not confirmed' if accepted else 'Command rejected or transmission failed')
        self.timer.start(3000)

    def setEnabled(self, enabled):
        # Keep the result LED legible even while the command button is disabled.
        self.button.setEnabled(enabled)

    def isEnabled(self):
        return self.button.isEnabled()
