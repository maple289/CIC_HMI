"""One profile-defined setting per editor; all I/O stays on the existing worker."""
from PySide6.QtWidgets import QCheckBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QLabel,QSpinBox,QVBoxLayout,QHBoxLayout,QPushButton,QAbstractSpinBox
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.parameters import definition


class ParameterEditor(QDialog):
    def __init__(self,config,key,raw,*,reason='',physical=False,refresh=None,parent=None):
        super().__init__(parent)
        self.config=config;self.key=key;self.spec=definition(config,key)
        self.current_raw=raw;self.reason=self.spec.reason or reason;self.refresh_callback=refresh
        number,title=self.spec.number,self.spec.title
        self.setWindowTitle(f'{"View" if self.reason else "Adjust"} {title}');self.setMinimumWidth(380)
        box=QVBoxLayout(self)
        target=QLabel(f'{config.name} · {config.assembly}\n{title} [{number}]');target.setWordWrap(True);box.addWidget(target)
        self.checks=[];self.value=None
        if self.spec.relays:
            for bit,name in self.spec.relays:
                check=QCheckBox(name);check.setEnabled(not self.reason);box.addWidget(check);self.checks.append(check)
            text=('Checked relays are failsafe (normally energized).' if key=='failsafe' else 'Checked alarms latch until reset. Other bits are preserved.')
            if config.family=='LEL' and profile_for(config).revision!='700' and key=='latches':text+='\nFor FMR approval, DANGER must latch here or through external equipment (670 manual).'
            note=QLabel(text)
        elif self.spec.bounds:
            low,high=self.spec.bounds
            self.value=QSpinBox() if key=='cal_time' else QDoubleSpinBox()
            if key!='cal_time':self.value.setDecimals(2)
            self.value.setRange(low,high)
            _,_,unit=profile_for(config).register(number).scale(config.family,config.context)
            unit=self.spec.unit or unit
            self.value.setSuffix(f' {unit}' if unit else '');self.value.setButtonSymbols(QAbstractSpinBox.NoButtons)
            self.value.setEnabled(not self.reason)
            row=QHBoxLayout();row.addWidget(self.value,1)
            self.decrease_button=QPushButton('−');self.increase_button=QPushButton('+')
            for button,label,step in ((self.decrease_button,'Decrease',-1),(self.increase_button,'Increase',1)):
                button.setFixedSize(44,40);button.setStyleSheet('font-size: 24px; font-weight: bold;')
                button.setAccessibleName(label);button.setToolTip(f'{label} value')
                button.clicked.connect(lambda _,s=step:self.value.stepBy(s));row.addWidget(button)
            self.value.valueChanged.connect(self.update_steps);box.addLayout(row)
            note=QLabel(f'Allowed range: {low}–{high} {unit}')
            if key=='span_temperature' and profile_for(config).revision=='700':
                note.setText(note.text()+'\nCalibration guidance: standard models need at least 100 °C; dilution models need 70 °C or below (Rev D p73).')
        else:
            note=QLabel('Manufacturer adjustment limits are not specified.')
        note.setWordWrap(True);box.addWidget(note)
        self.current_label=QLabel();self.current_label.setWordWrap(True);box.addWidget(self.current_label)
        note='Real controller adjustment. Review and confirm before changing the live setting. SAVE ALL remains separate.' if physical else 'Simulator adjustment. You will review and confirm the change before it is sent.'
        if physical and config.version=='4.81':note+=' Firmware4.81 uses the5.12 map by your instruction.'
        self.access_note=QLabel(self.reason or note);self.access_note.setWordWrap(True);box.addWidget(self.access_note)
        self.read_status=QLabel();self.read_status.setWordWrap(True);box.addWidget(self.read_status)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        self.save_button=buttons.button(QDialogButtonBox.Save);self.save_button.setText('Save')
        self.refresh_button=buttons.addButton('Refresh',QDialogButtonBox.ActionRole)
        self.refresh_button.setEnabled(refresh is not None);self.refresh_button.clicked.connect(self.refresh)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);box.addWidget(buttons)
        self.set_raw(raw)

    def update_steps(self):
        if self.value is not None:
            self.decrease_button.setEnabled(not self.reason and self.current_raw is not None and self.value.value()>self.value.minimum())
            self.increase_button.setEnabled(not self.reason and self.current_raw is not None and self.value.value()<self.value.maximum())

    def set_raw(self,raw,error=''):
        self.current_raw=raw
        self.read_status.setText(f'Communication error: {error}. No change sent.' if error else 'Fresh value read from analyzer.' if self.refresh_callback and raw is not None else '')
        self.refresh_button.setEnabled(self.refresh_callback is not None)
        valid=raw is not None
        if valid:
            try:
                current,unit=profile_for(self.config).register(self.spec.number).decode(raw,self.config.family,self.config.context)
                unit=self.spec.unit or unit
                self.current_label.setText(f'Current value: {current} {unit}')
                for (bit,name),check in zip(self.spec.relays,self.checks):check.setChecked(bool(raw & (1<<bit)))
                if self.value is not None:
                    low,high=self.spec.bounds
                    valid=low-abs(profile_for(self.config).register(self.spec.number).scale(self.config.family,self.config.context)[0])/2 <= current <= high+abs(profile_for(self.config).register(self.spec.number).scale(self.config.family,self.config.context)[0])/2
                    if valid:self.value.setValue(float(current) if self.key!='cal_time' else int(current))
                    else:self.read_status.setText('Current value is outside the documented range; verification is required.')
                if self.spec.mask==1 and raw not in (0,1):valid=False;self.read_status.setText('Unexpected latch bits; verification is required.')
            except ValueError as exc:
                valid=False;self.current_label.setText(f'Raw value: {raw}; engineering conversion unavailable: {exc}')
        else:self.current_label.setText('Current value unavailable')
        self.save_button.setEnabled(valid and not self.reason)
        for check in self.checks:check.setEnabled(valid and not self.reason)
        if self.value is not None:self.value.setEnabled(valid and not self.reason)
        self.update_steps()

    def refresh(self):
        if self.refresh_callback:
            self.set_raw(None);self.refresh_button.setEnabled(False);self.read_status.setText('Reading current value…')
            self.refresh_callback()

    def proposed(self):
        return sum(1<<bit for (bit,name),check in zip(self.spec.relays,self.checks) if check.isChecked()) if self.spec.relays else self.value.value()
