"""Permanent, profile-specific recording checkbox section."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,QScrollArea,QWidget,QGridLayout
from prevex_hmi.logging_db.recordings import recording_parameters
from prevex_hmi.profiles import profile_name


class RecordingParameters(QGroupBox):
    changed=Signal()

    def __init__(self,parent=None):
        super().__init__('Recording Parameters',parent)
        self.setToolTip('STATUS and communication quality are always retained as session metadata.')
        self.profile=None;self.descriptors=None;self.checkboxes={};self.chosen=set();self.locked=False
        box=QVBoxLayout(self);row=QHBoxLayout()
        self.profile_label=QLabel();row.addWidget(self.profile_label,1)
        self.select_all=QPushButton('Select All');self.clear_all=QPushButton('Clear All')
        self.select_all.clicked.connect(lambda:self.select_numbers(list(self.checkboxes)))
        self.clear_all.clicked.connect(lambda:self.select_numbers([]))
        row.addWidget(self.select_all);row.addWidget(self.clear_all);box.addLayout(row)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFixedHeight(94)
        self.content=QWidget();self.grid=QGridLayout(self.content);self.grid.setContentsMargins(4,2,4,2)
        self.scroll.setWidget(self.content);box.addWidget(self.scroll)

    def set_analyzer(self,config,selections):
        profile=profile_name(config);descriptors=recording_parameters(config)
        if (profile,descriptors)==(self.profile,self.descriptors):return
        self.profile=profile;self.descriptors=descriptors;self.profile_label.setText(profile)
        while self.grid.count():self.grid.takeAt(0)
        for checkbox in self.checkboxes.values():checkbox.hide();checkbox.deleteLater()
        self.checkboxes={}
        chosen=selections.get(profile,[1]);self.chosen=set(chosen)
        for p in descriptors:
            text=f"{p['name']} [{p['number']}]"+(f" ({p['unit']})" if p['unit'] else '')
            checkbox=QCheckBox(text);checkbox.setToolTip(text);checkbox.setChecked(p['number'] in self.chosen)
            checkbox.toggled.connect(self.selection_changed);self.checkboxes[p['number']]=checkbox
        self.reflow()

    def selected_numbers(self):return [n for n in self.checkboxes if n in self.chosen]

    def select_numbers(self,numbers):
        if self.locked:return
        self.chosen=set(numbers)&self.checkboxes.keys()
        self.restore_checks();self.changed.emit()

    def restore_checks(self):
        for n,checkbox in self.checkboxes.items():
            checkbox.blockSignals(True);checkbox.setChecked(n in self.chosen);checkbox.blockSignals(False)

    def selection_changed(self):
        if self.locked:self.restore_checks();return
        self.chosen={n for n,c in self.checkboxes.items() if c.isChecked()};self.changed.emit()

    def set_locked(self,locked):self.locked=bool(locked);self.setEnabled(not locked)

    def reflow(self):
        # Use the group's new width: the viewport may still have its old size
        # when Qt delivers the parent resize event.
        columns=max(1,(self.width()-32)//300)
        while self.grid.count():self.grid.takeAt(0)
        for i,checkbox in enumerate(self.checkboxes.values()):self.grid.addWidget(checkbox,i//columns,i%columns)
        rows=(len(self.checkboxes)+columns-1)//columns
        self.scroll.setFixedHeight(min(138,max(70,rows*28+6)))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'scroll'):self.reflow()
