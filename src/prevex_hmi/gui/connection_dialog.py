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
        fields=QWidget();form=QFormLayout(fields);self.form=form
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
        warning=QLabel("Physical ports and writes remain disabled pending authorization/bench validation. Display range overrides change only the gauge scale, never instrument measurements or configuration.")
        warning.setWordWrap(True);root.addWidget(warning)
        self.packet_address=QLabel();form.addRow("Effective packet address",self.packet_address)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.types.currentRowChanged.connect(self.type_changed)
        self.sim_family.currentTextChanged.connect(lambda _:self.refresh_type())
        self.lel_revision.currentTextChanged.connect(lambda _:self.refresh_type(reset=True))
        self.mode.currentTextChanged.connect(lambda _:self.refresh_type())
        self.address_mode.currentTextChanged.connect(self.update_address)
        self.address.valueChanged.connect(self.update_address)
        # Old settings can contain a previous family's name/model. Normalize
        # family defaults on opening while retaining user-defined names.
        family=self.selected_family()
        prefix={'LEL':('SNR67','SNR70'),'BTU':('SNR69',),'FID':('SNR65',)}[family]
        self.refresh_type(reset=d.family!=family or not d.assembly.startswith(prefix))
        self.update_address()

    def selected_family(self) -> str:
        selection=self.types.currentItem().text()
        if selection != 'Auto Detect':return selection
        return self.sim_family.currentText() if self.mode.currentText()=='simulation' else self.original['devices'][0]['family']

    def type_changed(self,index: int) -> None:
        selection=self.types.currentItem().text()
        if selection != 'Auto Detect':
            self.sim_family.blockSignals(True)
            self.sim_family.setCurrentText(selection)
            self.sim_family.blockSignals(False)
        self.refresh_type(reset=True)

    def refresh_type(self,*,reset: bool=False) -> None:
        family=self.selected_family()
        if self.types.currentRow()!=0:
            self.sim_family.blockSignals(True);self.sim_family.setCurrentText(family);self.sim_family.blockSignals(False)
        defaults=next(d for d in default_devices() if d.family==family)
        if family=='LEL' and self.lel_revision.currentText()=='700':
            defaults=replace(defaults,assembly='SNR705',version='7.01')
        default_names={d.name for d in default_devices()}
        if not self.name.text().strip() or self.name.text() in default_names:
            self.name.setText(defaults.name)
        if reset or getattr(self,'display_family',family)!=family:
            self.assembly.setText(defaults.assembly);self.version.setText(defaults.version)
            self.units.setCurrentText(defaults.units or 'Unknown');self.fullscale.setValue(defaults.fullscale)
            self.manual.setValue(defaults.fullscale)
        self.display_family=family
        simulation=self.mode.currentText()=='simulation'
        self.form.setRowVisible(self.lel_revision,simulation and family=='LEL')
        self.form.setRowVisible(self.units,family=='FID')
        self.form.setRowVisible(self.fullscale,simulation and family=='FID')
        self.form.setRowVisible(self.sim_family,simulation and self.types.currentRow()==0)
        self.sim_family.setEnabled(simulation and self.types.currentRow()==0)

    def update_address(self,*_) -> None:
        minimum=2 if self.address_mode.currentText()=='display_minus_one' else 1
        if self.address.minimum()!=minimum:self.address.setMinimum(minimum)
        packet=self.address.value()-(minimum==2)
        self.packet_address.setText(f'{packet} (address zero is never used)')

    def settings(self):
        data=copy.deepcopy(self.original)
        d=DeviceConfig(**data["devices"][0])
        selection=self.types.currentItem().text()
        family=self.selected_family()
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
