"""One parameter per editor; edits are submitted to the existing worker."""
from PySide6.QtWidgets import QCheckBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QLabel,QSpinBox,QVBoxLayout
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.parameters import PARAMETERS,limits


class ParameterEditor(QDialog):
    def __init__(self,config,key,raw,*,reason='',parent=None):
        super().__init__(parent)
        number,title=PARAMETERS[key];self.key=key
        self.setWindowTitle(f'Adjust {title}');self.setMinimumWidth(380)
        box=QVBoxLayout(self)
        target=QLabel(f'{config.name} · {config.assembly}\n{title} [{number}]');target.setWordWrap(True);box.addWidget(target)
        low,high=limits(config,key)
        self.checks=[]
        if key=='latches':
            for bit,name in enumerate(('Warning','Danger','Fault','Horn')):
                check=QCheckBox(name);check.setChecked(bool(raw&(1<<bit)));box.addWidget(check);self.checks.append(check)
            note=QLabel('Checked alarms latch until reset. Other bits are preserved.\nFor FMR approval, DANGER must latch here or through external equipment (670 manual).')
        else:
            self.value=QSpinBox() if key=='cal_time' else QDoubleSpinBox()
            if key!='cal_time':self.value.setDecimals(2)
            self.value.setRange(low,high)
            current,unit=profile_for(config).register(number).decode(raw,config.family,config.context)
            self.value.setValue(float(current) if key!='cal_time' else int(current))
            self.value.setSuffix(f' {unit}' if unit else '');box.addWidget(self.value)
            note=QLabel(f'Allowed range: {low}–{high} {unit}\nCurrent value: {current} {unit}')
        note.setWordWrap(True);box.addWidget(note)
        self.access_note=QLabel(reason or 'Simulator adjustment. You will review and confirm the change before it is sent.');self.access_note.setWordWrap(True);box.addWidget(self.access_note)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        self.save_button=buttons.button(QDialogButtonBox.Save);self.save_button.setText('Review change');self.save_button.setEnabled(not reason)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);box.addWidget(buttons)

    def proposed(self):
        return sum(1<<i for i,check in enumerate(self.checks) if check.isChecked()) if self.key=='latches' else self.value.value()
