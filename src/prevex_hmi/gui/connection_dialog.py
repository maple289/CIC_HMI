from dataclasses import asdict, replace
import copy
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QMessageBox,QScrollArea,QSpinBox,QVBoxLayout,QWidget
from prevex_hmi.devices.configuration import validate_settings,operator_settings
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.profiles import normalize_selection
from prevex_hmi.gui.serial_ports import SerialPortChoice


class AnalyzerChoice(QDialog):
    def __init__(self,settings,parent=None):
        super().__init__(parent)
        self.original=operator_settings(copy.deepcopy(settings));settings=self.original
        self.setWindowTitle('Choose Analyzer Type');self.resize(800,680)
        root=QVBoxLayout(self)
        note=QLabel('Auto Detect reads identity registers before loading a profile. Manual selection remains available; an unresolved identity or mismatch blocks commands.')
        note.setWordWrap(True);root.addWidget(note)
        row=QHBoxLayout();row.addWidget(QLabel('Analyzer profile'));root.addLayout(row)
        self.types=QComboBox();self.types.addItems(['Auto Detect','LEL','BTU','FID']);self.types.setCurrentText(normalize_selection(settings['analyzer_selection']));row.addWidget(self.types,1)
        self.profile_status=QLabel();self.profile_status.setWordWrap(True);root.addWidget(self.profile_status)
        fields=QWidget();self.form=form=QFormLayout(fields)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(fields);root.addWidget(scroll,1)
        d=DeviceConfig(**settings['devices'][0]);c=settings['connection']
        self.name=QLineEdit(d.name);self.port=SerialPortChoice(c['port'])
        self.baud=QComboBox();self.baud.addItems([str(n) for n in (300,600,1200,2400,4800,9600,19200)]);self.baud.setCurrentText(str(c['baud']))
        self.timeout=QDoubleSpinBox();self.timeout.setRange(.05,5);self.timeout.setValue(c['timeout']);self.timeout.setSuffix(' s')
        self.address=QSpinBox();self.address.setRange(1,255);self.address.setValue(d.address)
        self.address_mode=QComboBox();self.address_mode.addItems(['direct','display_minus_one']);self.address_mode.setCurrentText(d.address_mode)
        self.offset=QComboBox();self.offset.addItems(['-1','0']);self.offset.setCurrentText(str(d.pdu_offset))
        self.page=QComboBox();self.page.addItems(['standard','alternate']);self.page.setCurrentText(c.get('identification_page','standard'))
        self.assembly=QLineEdit(d.assembly);self.version=QLineEdit(d.version)
        self.units=QComboBox();self.units.addItems(['Unknown','US','METRIC']);self.units.setCurrentText(d.units or 'Unknown')
        self.interval=QDoubleSpinBox();self.interval.setRange(.25,60);self.interval.setValue(d.interval);self.interval.setSuffix(' s')
        self.logging_enabled=QCheckBox('Record measurements in local history');self.logging_enabled.setChecked(d.logging_enabled)
        self.range_mode=QComboBox();self.range_mode.addItems(['auto','manual']);self.range_mode.setCurrentText(d.range_mode)
        self.manual=QDoubleSpinBox();self.manual.setDecimals(3);self.manual.setRange(.001,1000000);self.manual.setValue(d.manual_maximum or d.fullscale)
        self.use_fallback=QCheckBox('Use manual maximum if register3 is unavailable');self.use_fallback.setChecked(d.manual_maximum is not None)
        for name,widget in [('Instrument name',self.name),('Serial port',self.port),('Baud rate / 8N1',self.baud),('Timeout',self.timeout),('Displayed ADDRESS',self.address),('Packet-address compatibility',self.address_mode),('Register-to-PDU offset',self.offset),('Identity page',self.page),('Manual assembly fallback',self.assembly),('Firmware information',self.version),('FID unit context (verify physically)',self.units),('Refresh interval',self.interval),('Measurement logging',self.logging_enabled),('Gauge range source',self.range_mode),('Manual display maximum',self.manual),('Fallback',self.use_fallback)]:form.addRow(name,widget)
        warning=QLabel('Available serial ports connect directly for read-only monitoring. Operating commands require a supported identity, sign-in, current controller checks and individual confirmation. Display overrides change only the gauge scale.')
        warning.setWordWrap(True);root.addWidget(warning)
        self.packet_address=QLabel();form.addRow('Effective packet address',self.packet_address)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.types.currentIndexChanged.connect(self.refresh_type);self.address_mode.currentTextChanged.connect(self.update_address);self.address.valueChanged.connect(self.update_address)
        self.refresh_type();self.update_address()

    def selected_family(self):
        return self.types.currentText() if self.types.currentText()!='Auto Detect' else self.original['devices'][0]['family']

    def refresh_type(self,*_):
        from .profile_library import PROFILE_STATUS
        self.profile_status.setText(PROFILE_STATUS.get(self.types.currentText(),'Auto Detect identifies the connected analyzer before loading a profile.'))
        self.form.setRowVisible(self.units,self.selected_family()=='FID')

    def update_address(self,*_):
        minimum=2 if self.address_mode.currentText()=='display_minus_one' else 1
        if self.address.minimum()!=minimum:self.address.setMinimum(minimum)
        self.packet_address.setText(f'{self.address.value()-(minimum==2)} (address zero is never used)')

    def settings(self):
        data=copy.deepcopy(self.original);d=DeviceConfig(**data['devices'][0])
        units=None if self.units.currentText()=='Unknown' else self.units.currentText()
        d=replace(d,id=uuid.uuid4().hex if units!=d.units else d.id,name=self.name.text().strip(),address=self.address.value(),address_mode=self.address_mode.currentText(),pdu_offset=int(self.offset.currentText()),assembly=self.assembly.text().strip(),version=self.version.text().strip(),enabled=True,units=units,interval=self.interval.value(),logging_enabled=self.logging_enabled.isChecked(),range_mode=self.range_mode.currentText(),manual_maximum=self.manual.value() if self.use_fallback.isChecked() or self.range_mode.currentText()=='manual' else None)
        data.update(analyzer_selection=self.types.currentText(),mode='hardware',devices=[asdict(d)],connection={**data['connection'],'port':self.port.text().strip(),'baud':int(self.baud.currentText()),'timeout':self.timeout.value(),'identification_page':self.page.currentText()})
        validate_settings(data);return data

    def accept(self):
        try:
            self.settings()
            if not self.port.is_valid():raise ValueError('Select an available COM port. Refresh to rescan attached adapters.')
        except (ValueError,PermissionError) as error:
            QMessageBox.warning(self,'Invalid connection settings',str(error));return
        super().accept()


class LoginDialog(QDialog):
    def __init__(self,users,parent=None):
        super().__init__(parent)
        self.users=users;self.token=""
        self.setup=not users.has_users()
        self.setWindowTitle("Create local Administrator" if self.setup else "Sign in")
        form=QFormLayout(self)
        note=QLabel("Create the first local administrator to authorize confirmed commands permitted by the connection mode. No default password is provided." if self.setup else "Local accounts only. No Internet connection is required.")
        note.setWordWrap(True);form.addRow(note)
        self.name=QLineEdit();self.password=QLineEdit();self.password.setEchoMode(QLineEdit.Password)
        form.addRow("Username",self.name);form.addRow("Password (8+ characters)",self.password)
        self.confirm=QLineEdit();self.confirm.setEchoMode(QLineEdit.Password)
        if self.setup:form.addRow("Confirm password",self.confirm)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)

    def accept(self):
        try:
            if self.setup:
                if self.password.text()!=self.confirm.text():raise ValueError("Passwords do not match")
                self.users.create_user(self.name.text(),self.password.text())
                self.setup=False
            self.token=self.users.authenticate(self.name.text().strip(),self.password.text())
        except (ValueError,PermissionError) as error:
            QMessageBox.warning(self,"Sign-in failed",str(error));return
        self.password.clear();self.confirm.clear();super().accept()
