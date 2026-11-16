"""Read-only developer attribution, independent of operator settings and data."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QLabel,QVBoxLayout
from prevex_hmi.security.attribution import developer_information
from .branding import application_icon


class AboutDialog(QDialog):
    def __init__(self,parent=None):
        info=developer_information()  # Verify before constructing/displaying content.
        super().__init__(parent)
        self.setWindowTitle('About PREVEX HMI');self.setWindowIcon(application_icon());self.setMinimumWidth(420)
        box=QVBoxLayout(self)
        icon=QLabel();icon.setPixmap(application_icon().pixmap(80,80));icon.setAlignment(Qt.AlignCenter);box.addWidget(icon)
        for key in ('application','tagline','developer_label','developer','qualification','version','copyright'):
            label=QLabel(info[key]);label.setTextFormat(Qt.PlainText);label.setWordWrap(True);label.setAlignment(Qt.AlignCenter)
            if key in ('application','developer'):label.setStyleSheet('font-size:18px;font-weight:bold;')
            box.addWidget(label)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(self.reject);box.addWidget(buttons)
