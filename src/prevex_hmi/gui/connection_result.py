"""Explicit results for a one-shot, read-only connection check."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QDialog,QLabel,QPushButton,QVBoxLayout


class ConnectionTestResult(QDialog):
    connect_requested=Signal()
    back_requested=Signal()

    def __init__(self,settings,info=None,error='',parent=None,*,embedded=False):
        super().__init__(parent)
        if embedded:self.setWindowFlags(Qt.Widget)
        info=info or {}
        responding=bool(info.get('communication_ok') and not error)
        identified=bool(responding and info.get('family') and info.get('config'))
        self.setWindowTitle('Test Connection result')
        self.setMinimumWidth(520);self.resize(620,440)
        layout=QVBoxLayout(self)
        title=('Connection test passed' if identified else 'Communication established; identification unresolved' if responding else 'Connection test failed')
        self.result_label=QLabel(title);self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet('font-size:20px;font-weight:bold;color:'+('#39c66c' if identified else '#e7b55e' if responding else '#f27778'))
        layout.addWidget(self.result_label)
        c=settings['connection'];d=settings['devices'][0]
        firmware=info.get('version') or 'Unavailable'
        if info.get('version_provisional'):firmware+=f" (reported {info.get('reported_version')}; provisional interpretation)"
        lines=[f"Mode: {settings['mode'].upper()}",f"Port: {c['port'] or 'Not selected'} | {c['baud']} baud / 8N1",f"Configured address: {d['address']} ({d['address_mode']})",f"Selected profile: {settings['analyzer_selection']}",f"Detected profile: {info.get('loaded_profile') or info.get('family') or 'Unrecognized'}",f"Model: {info.get('model') or 'Unavailable'}",f"Firmware: {firmware}",f"Serial number: {info.get('serial') or 'Unavailable'}",f"Communication: {'Valid Modbus response received' if responding else 'Not confirmed'}"]
        if error:lines+=['',f'Error: {error}']
        if info.get('warning'):lines+=['',f"Compatibility / identification: {info['warning']}"]
        self.details=QLabel('\n'.join(lines));self.details.setWordWrap(True);self.details.setTextFormat(Qt.PlainText);self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.details)
        self.instructions=QLabel('This was a one-time read-only check. Monitoring is stopped and the serial port has been released. No operating commands were sent. '+('Click Connect and monitor to start live readings, or Back to return without connecting.' if embedded else 'Close this result and click Connect to start continuous monitoring.'))
        self.instructions.setWordWrap(True);layout.addWidget(self.instructions)
        if embedded:
            connect=QPushButton('Connect and monitor');connect.clicked.connect(self.connect_requested);layout.addWidget(connect)
            back=QPushButton('Back');back.clicked.connect(self.back_requested);layout.addWidget(back)
        else:
            close=QPushButton('OK');close.clicked.connect(self.accept);layout.addWidget(close)
