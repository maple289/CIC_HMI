"""Operator-facing confirmation; technical checks and audit stay in the worker."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QHBoxLayout,QLabel,QLayout,QPushButton,QStyle,QVBoxLayout
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.profiles import profile_name


COMMAND_NAMES={0x100:'ACKNOWLEDGE',0x200:'RESET ALARMS',0x300:'ZERO CAL',0x400:'SPAN CAL',0x500:'FULL CAL',
               0x600:'ZERO TEST',0x700:'SPAN TEST',0x800:'FULL TEST',0x900:'SAVE ALL',0xF00:'LOCK CAL',0x1000:'UNLOCK CAL'}


def command_effect(code):
    if code in (0x300,0x400,0x500):return 'This command will start analyzer calibration.'
    if code in (0x600,0x700,0x800):return 'This command will start an analyzer test.'
    return {0x200:'This may reset alarms or restart ignition.',0x900:'Saves the analyzer settings permanently.',
            0xF00:'Enables the software calibration lock.',0x1000:'Removes the software calibration lock.'}.get(code,'')


class CommandConfirmation(QDialog):
    def __init__(self,parent,code,config,*,fault=''):
        super().__init__(parent);self.setWindowTitle('Confirm Command');self.setWindowModality(Qt.WindowModal)
        self.confirmed=False
        box=QVBoxLayout(self);box.setContentsMargins(16,14,16,14);box.setSpacing(10);box.setSizeConstraint(QLayout.SetFixedSize)
        self.message=QLabel(f'Execute {COMMAND_NAMES[code]} on the connected analyzer?');self.message.setTextFormat(Qt.PlainText)
        self.message.setWordWrap(True);self.message.setMinimumWidth(360);self.message.setMaximumWidth(400);box.addWidget(self.message)
        target=DeviceConfig(**config)
        self.analyzer=QLabel(f'Analyzer: {profile_name(target)} / {target.assembly}');self.analyzer.setTextFormat(Qt.PlainText)
        self.analyzer.setWordWrap(True);self.analyzer.setMaximumWidth(400);box.addWidget(self.analyzer)
        self.effect=QLabel(command_effect(code));self.effect.setWordWrap(True);self.effect.setMaximumWidth(400)
        if self.effect.text():box.addWidget(self.effect)
        else:self.effect.hide()
        self.fault=QLabel(fault);self.fault.setTextFormat(Qt.PlainText);self.fault.setWordWrap(True);self.fault.setMaximumWidth(400)
        if fault:
            from .theme import semantic_style
            semantic_style(self.fault,'#f27778','font-weight:600;');box.addWidget(self.fault)
        else:self.fault.hide()
        buttons=QHBoxLayout();buttons.addStretch()
        self.confirm_button=QPushButton('Confirm');self.cancel_button=QPushButton('Cancel')
        for button in (self.confirm_button,self.cancel_button):
            button.setAutoDefault(False);button.setDefault(False);buttons.addWidget(button)
        self.confirm_button.clicked.connect(self.confirm_clicked);self.cancel_button.clicked.connect(self.reject);box.addLayout(buttons)

    def confirm_clicked(self):
        self.confirmed=True;self.done(QDialog.Accepted)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Return,Qt.Key_Enter):event.accept();return
        super().keyPressEvent(event)

    def showEvent(self,event):
        super().showEvent(event);self.cancel_button.setFocus(Qt.OtherFocusReason)
        if self.parentWidget():
            parent=self.parentWidget().window()
            position=QStyle.alignedRect(parent.layoutDirection(),Qt.AlignCenter,self.frameGeometry().size(),parent.frameGeometry())
            self.move(position.topLeft())


def confirm_command(parent,code,config,*,fault=''):
    dialog=CommandConfirmation(parent,code,config,fault=fault)
    try:return dialog.exec()==QDialog.Accepted and dialog.confirmed
    finally:dialog.deleteLater()
