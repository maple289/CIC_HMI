"""Enumerated port chooser; a missing saved port is visible but never valid."""
from serial.tools import list_ports
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class SerialPortChoice(QWidget):
    def __init__(self, saved: str, parent=None):
        super().__init__(parent)
        self.saved = saved
        self.available: set[str] = set()
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout(); layout.addLayout(row)
        self.combo = QComboBox(); row.addWidget(self.combo, 1)
        refresh = QPushButton('Refresh'); refresh.clicked.connect(self.refresh); row.addWidget(refresh)
        self.notice = QLabel(); layout.addWidget(self.notice)
        self.refresh()

    def refresh(self):
        selected = self.combo.currentData() or self.saved
        self.combo.clear()
        try:
            ports = sorted(list_ports.comports(), key=lambda p: p.device)
            self.available = {p.device for p in ports}
            for port in ports:
                self.combo.addItem(f'{port.description or "Serial port"} ({port.device})', port.device)
            self.notice.setText('')
        except OSError as error:
            self.available = set(); self.notice.setText(f'Port scan failed: {error}')
        if selected and selected not in self.available:
            self.combo.addItem(f'{selected} — unavailable', selected)
            self.notice.setText('Previously selected port is unavailable. Refresh or choose another port.')
        if not self.combo.count():
            self.combo.addItem('No serial ports available', '')
            self.notice.setText('Connect a serial adapter and select Refresh.')
        index = self.combo.findData(selected)
        self.combo.setCurrentIndex(index if index >= 0 else 0)

    def text(self):
        return self.combo.currentData() or ''

    def is_valid(self):
        return self.text() in self.available


def require_available_port(port: str) -> None:
    if not port or port not in {p.device for p in list_ports.comports()}:
        raise ValueError('Select an available COM port in Choose Analyzer Type, then Refresh if necessary. No port was opened.')
