"""Saved connection choices are preferences, never a live analyzer identity."""
from dataclasses import asdict,replace
import copy
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QSpinBox,QPushButton
from .serial_ports import SerialPortChoice
from .profile_library import library_config
from prevex_hmi.profiles import normalize_selection
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.devices.configuration import normalize_profiles


class ConnectionScreen(QWidget):
    changed=Signal()
    def __init__(self,settings):
        super().__init__();box=QVBoxLayout(self);box.setContentsMargins(24,16,24,16)
        self.title=QLabel('No Analyzer Connected');self.title.setObjectName('heading');box.addWidget(self.title)
        self.status=QLabel('Connection Status: No Connection');box.addWidget(self.status)
        self.selection=QLabel();self.selection.setWordWrap(True);box.addWidget(self.selection)
        self.last=QLabel();self.last.setWordWrap(True);box.addWidget(self.last)
        fields=QWidget();fields.setMaximumWidth(650);form=QFormLayout(fields);box.addWidget(fields)
        self.mode=QComboBox();self.mode.addItems(['hardware','simulation'])
        self.port=SerialPortChoice(settings['connection']['port'])
        self.baud=QComboBox()
        for baud in (300,600,1200,2400,4800,9600,19200):self.baud.addItem(str(baud),baud)
        self.address=QSpinBox();self.address.setRange(1,255)
        self.profile=QComboBox();self.profile.addItems(['Auto Detect','LEL','BTU','FID'])
        for name,control in (('Connection source',self.mode),('COM port',self.port),('Baud rate / 8N1',self.baud),('Modbus address',self.address),('Auto Detect / Manual Profile',self.profile)):form.addRow(name,control)
        self.note=QLabel('Connect or test to read identification. Opening a port or choosing a profile does not identify an analyzer.');self.note.setWordWrap(True);box.addWidget(self.note)
        row=QHBoxLayout();self.connect_button=QPushButton('Connect to Analyzer');self.test_button=QPushButton('Test Connection');self.settings_button=QPushButton('Advanced Connection Settings')
        for button in (self.connect_button,self.test_button,self.settings_button):row.addWidget(button)
        row.addStretch();box.addLayout(row);box.addStretch()
        self.load(settings)
        for signal in (self.mode.currentIndexChanged,self.profile.currentIndexChanged,self.port.combo.currentIndexChanged,self.baud.currentIndexChanged,self.address.valueChanged):signal.connect(self.changed)

    def load(self,settings):
        controls=(self.mode,self.profile,self.port.combo,self.baud,self.address)
        for control in controls:control.blockSignals(True)
        self.mode.setCurrentText(settings['mode']);self.baud.setCurrentIndex(self.baud.findData(settings['connection']['baud']))
        config=DeviceConfig(**settings['devices'][0]);self.address.setMinimum(2 if config.address_mode=='display_minus_one' else 1);self.address.setValue(config.address)
        selection=settings['analyzer_selection']
        self.profile.setCurrentText(normalize_selection(selection))
        self.port.saved=settings['connection']['port'];self.port.combo.setCurrentIndex(self.port.combo.findData(self.port.saved))
        if self.port.saved and self.port.combo.currentIndex()<0:self.port.combo.addItem(self.port.saved+' — unavailable',self.port.saved);self.port.combo.setCurrentIndex(self.port.combo.count()-1)
        for control in controls:control.blockSignals(False)
        self.port.setEnabled(settings['mode']=='hardware');self.baud.setEnabled(settings['mode']=='hardware')

    def preferences(self,settings):
        result=normalize_profiles(copy.deepcopy(settings));old=DeviceConfig(**result['devices'][0]);selection=self.profile.currentText()
        if selection!='Auto Detect' and self.mode.currentText()=='simulation':result['simulated_family']=selection
        result['devices']=[asdict(replace(old,address=self.address.value()))];result['mode']=self.mode.currentText();result['analyzer_selection']=selection
        result['connection'].update(port=self.port.text(),baud=self.baud.currentData())
        return result
