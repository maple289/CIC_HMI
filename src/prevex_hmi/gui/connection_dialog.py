from dataclasses import asdict, replace
import copy
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QMessageBox,QScrollArea,QSpinBox,QVBoxLayout,QWidget
from prevex_hmi.devices.configuration import default_devices,validate_settings
from prevex_hmi.devices.models import DeviceConfig


class AnalyzerChoice(QDialog):
    def __init__(self,settings,parent=None):
        super().__init__(parent)
        self.original=copy.deepcopy(settings)
        self.setWindowTitle("Choose Analyzer Type")
        self.resize(800,680)
        root=QVBoxLayout(self)
        note=QLabel("Auto Detect reads identity registers before loading a profile. Manual selection remains available; an unresolved identity or mismatch blocks commands.")
        note.setWordWrap(True);root.addWidget(note)
        row=QHBoxLayout();root.addLayout(row,1)
        self.types=QListWidget();self.types.addItems(["Auto Detect","LEL","BTU","FID"])
        self.types.setFixedWidth(180);self.types.setCurrentRow(["Auto Detect","LEL","BTU","FID"].index(settings["analyzer_selection"]))
        row.addWidget(self.types)
        fields=QWidget();form=QFormLayout(fields)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(fields);row.addWidget(scroll,1)
        d=DeviceConfig(**settings["devices"][0]);c=settings["connection"]
        self.name=QLineEdit(d.name)
        self.mode=QComboBox();self.mode.addItems(["simulation","hardware"]);self.mode.setCurrentText(settings["mode"])
        self.sim_family=QComboBox();self.sim_family.addItems(["LEL","BTU","FID"]);self.sim_family.setCurrentText(settings["simulated_family"])
        self.lel_revision=QComboBox();self.lel_revision.addItems(["700","legacy"]);self.lel_revision.setCurrentText(settings.get("simulated_lel_revision","legacy"))
        form.addRow("Simulated LEL generation",self.lel_revision)
        self.port=QLineEdit(c["port"])
        self.baud=QComboBox();self.baud.addItems([str(n) for n in (300,600,1200,2400,4800,9600,19200)]);self.baud.setCurrentText(str(c["baud"]))
        self.timeout=QDoubleSpinBox();self.timeout.setRange(.05,5);self.timeout.setValue(c["timeout"]);self.timeout.setSuffix(" s")
        self.address=QSpinBox();self.address.setRange(1,255);self.address.setValue(d.address)
        self.address_mode=QComboBox();self.address_mode.addItems(["direct","display_minus_one"]);self.address_mode.setCurrentText(d.address_mode)
        self.offset=QComboBox();self.offset.addItems(["-1","0"]);self.offset.setCurrentText(str(d.pdu_offset))
        self.page=QComboBox();self.page.addItems(["standard","alternate"]);self.page.setCurrentText(c.get("identification_page","standard"))
        self.assembly=QLineEdit(d.assembly);self.version=QLineEdit(d.version)
        self.units=QComboBox();self.units.addItems(["Unknown","US","METRIC"]);self.units.setCurrentText(d.units or "Unknown")
        self.fullscale=QSpinBox();self.fullscale.setRange(10,32000);self.fullscale.setValue(d.fullscale)
        self.interval=QDoubleSpinBox();self.interval.setRange(.25,60);self.interval.setValue(d.interval);self.interval.setSuffix(" s")
        self.logging_enabled=QCheckBox("Record measurements in local history");self.logging_enabled.setChecked(d.logging_enabled)
        form.addRow("Measurement logging",self.logging_enabled)
        self.range_mode=QComboBox();self.range_mode.addItems(["auto","manual"]);self.range_mode.setCurrentText(d.range_mode)
        self.manual=QDoubleSpinBox();self.manual.setDecimals(3);self.manual.setRange(.001,1000000);self.manual.setValue(d.manual_maximum or d.fullscale)
        self.use_fallback=QCheckBox("Use manual maximum if register3 is unavailable");self.use_fallback.setChecked(d.manual_maximum is not None)
        for name,widget in [("Instrument name",self.name),("Connection source",self.mode),("Simulated instrument",self.sim_family),("COM port (saved, live access gated)",self.port),("Baud rate / 8N1",self.baud),("Timeout",self.timeout),("Displayed ADDRESS",self.address),("Packet-address compatibility",self.address_mode),("Register-to-PDU offset",self.offset),("Identity page",self.page),("Manual assembly fallback",self.assembly),("Manual software fallback",self.version),("FID unit context (verify physically)",self.units),("Simulated FID FULLSCLE",self.fullscale),("Refresh interval",self.interval),("Gauge range source",self.range_mode),("Manual display maximum",self.manual),("Fallback",self.use_fallback)]:form.addRow(name,widget)
        warning=QLabel("Physical ports and writes remain disabled pending authorization/bench validation. Display range overrides do not modify the instrument or FID measurement conversion.")
        warning.setWordWrap(True);root.addWidget(warning)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.types.currentRowChanged.connect(self.type_changed)

    def type_changed(self,index):
        if index:
            d=next(d for d in default_devices() if d.family == self.types.currentItem().text())
            self.assembly.setText(d.assembly);self.version.setText(d.version);self.units.setCurrentText(d.units or "Unknown");self.fullscale.setValue(d.fullscale)

    def settings(self):
        data=copy.deepcopy(self.original)
        d=DeviceConfig(**data["devices"][0])
        selection=self.types.currentItem().text()
        family=selection if selection != "Auto Detect" else d.family
        new_stream=(selection != data["analyzer_selection"] or self.sim_family.currentText() != data["simulated_family"] or self.lel_revision.currentText() != data.get("simulated_lel_revision","legacy") or (self.units.currentText() or "Unknown") != (d.units or "Unknown"))
        d=replace(d,id=uuid.uuid4().hex if new_stream else d.id,name=self.name.text().strip(),family=family,address=self.address.value(),address_mode=self.address_mode.currentText(),pdu_offset=int(self.offset.currentText()),assembly=self.assembly.text().strip(),version=self.version.text().strip(),enabled=True,fullscale=self.fullscale.value(),units=None if self.units.currentText()=="Unknown" else self.units.currentText(),interval=self.interval.value(),logging_enabled=self.logging_enabled.isChecked(),range_mode=self.range_mode.currentText(),manual_maximum=self.manual.value() if self.use_fallback.isChecked() or self.range_mode.currentText()=="manual" else None)
        data.update(analyzer_selection=selection,mode=self.mode.currentText(),simulated_family=self.sim_family.currentText(),devices=[asdict(d)],connection={"port":self.port.text().strip(),"baud":int(self.baud.currentText()),"timeout":self.timeout.value(),"identification_page":self.page.currentText()})
        data['simulated_lel_revision']=self.lel_revision.currentText()
        validate_settings(data)
        return data

    def accept(self):
        try:self.settings()
        except (ValueError,PermissionError) as error:
            QMessageBox.warning(self,"Invalid connection settings",str(error));return
        super().accept()


class LoginDialog(QDialog):
    def __init__(self,users,parent=None):
        super().__init__(parent)
        self.users=users;self.token=""
        self.setup=not users.has_users()
        self.setWindowTitle("Create local Administrator" if self.setup else "Sign in")
        form=QFormLayout(self)
        note=QLabel("Create the first local administrator to authorize simulated commands. No default password is provided." if self.setup else "Local accounts only. No Internet connection is required.")
        note.setWordWrap(True);form.addRow(note)
        self.name=QLineEdit();self.password=QLineEdit();self.password.setEchoMode(QLineEdit.Password)
        form.addRow("Username",self.name);form.addRow("Password (12+ characters)",self.password)
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
