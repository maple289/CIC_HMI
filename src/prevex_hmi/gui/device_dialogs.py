from __future__ import annotations

from dataclasses import replace
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QMessageBox, QPushButton, QSpinBox, QVBoxLayout

from prevex_hmi.devices.models import DeviceConfig, validate_devices


class DeviceEditor(QDialog):
    def __init__(self, config: DeviceConfig | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Simulated analyzer")
        self.original = config
        layout = QFormLayout(self)
        self.name = QLineEdit(config.name if config else "New analyzer")
        self.family = QComboBox()
        self.family.addItems(["LEL", "BTU", "FID"])
        self.family.setCurrentText(config.family if config else "LEL")
        self.address = QSpinBox()
        self.address.setRange(1,255)
        self.address.setValue(config.address if config else 5)
        self.assembly = QLineEdit(config.assembly if config else "SNR675")
        self.version = QLineEdit(config.version if config else "5.11")
        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.25,3600)
        self.interval.setSuffix(" s")
        self.interval.setValue(config.interval if config else 2)
        self.scale = QSpinBox()
        self.scale.setRange(10,32000)
        self.scale.setValue(config.fullscale if config else 100)
        self.units = QComboBox()
        self.units.addItems(["Unknown", "US", "METRIC"])
        self.units.setCurrentText(config.units or "Unknown" if config else "Unknown")
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(config.enabled if config else True)
        self.logging = QCheckBox("Record measurements")
        self.logging.setChecked(config.logging_enabled if config else True)
        for label,widget in [("Name",self.name),("Family",self.family),("Packet address (simulation)",self.address),("Assembly",self.assembly),("Software version",self.version),("Primary poll interval",self.interval),("Full scale (FID)",self.scale),("FID unit context",self.units),("Availability",self.enabled),("Historian",self.logging)]:
            layout.addRow(label,widget)
        self.family.currentTextChanged.connect(self.family_changed)
        buttons=QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def family_changed(self, family: str) -> None:
        self.assembly.setText({"LEL":"SNR675","BTU":"SNR692","FID":"SNR650"}[family])
        self.version.setText("4.80" if family == "FID" else "5.11")
        self.units.setCurrentText("US" if family == "FID" else "Unknown")
        self.scale.setValue(1000 if family == "BTU" else 100)

    def config(self) -> DeviceConfig:
        units=None if self.units.currentText() == "Unknown" else self.units.currentText()
        # A family/unit change creates a new stream identity so old history and
        # live curves cannot silently mix incompatible measurements.
        preserve_id=self.original and self.original.family == self.family.currentText() and self.original.units == units
        return DeviceConfig(
            id=self.original.id if preserve_id else uuid.uuid4().hex,
            name=self.name.text().strip(), family=self.family.currentText(), address=self.address.value(),
            assembly=self.assembly.text().strip(), version=self.version.text().strip(), interval=self.interval.value(),
            enabled=self.enabled.isChecked(), fullscale=self.scale.value(), units=units,
            btu_unit=self.original.btu_unit if self.original else "unit unverified",
            logging_enabled=self.logging.isChecked(),
        )


class DeviceManager(QDialog):
    """Order is the saved analyzer-selector order; no physical connection settings."""
    def __init__(self, devices: list[DeviceConfig], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage simulated analyzers / selector order")
        self.resize(650,450)
        self.devices=list(devices)
        layout=QVBoxLayout(self)
        self.list=QListWidget()
        layout.addWidget(self.list)
        row=QHBoxLayout()
        for text, action in [("Add",self.add),("Edit",self.edit),("Enable / disable",self.toggle),("Remove",self.remove),("Move up",lambda:self.move(-1)),("Move down",lambda:self.move(1))]:
            button=QPushButton(text)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)
        sort_row=QHBoxLayout()
        for text,key in [("Sort by name",lambda d:d.name.casefold()),("Sort by family",lambda d:(d.family,d.name.casefold()))]:
            button=QPushButton(text)
            button.clicked.connect(lambda checked=False,key=key:self.sort(key))
            sort_row.addWidget(button)
        sort_row.addStretch()
        layout.addLayout(sort_row)
        buttons=QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self, selection=0):
        self.list.clear()
        self.list.addItems([f"{d.name} | {d.family} | address {d.address} | {'enabled' if d.enabled else 'disabled'}" for d in self.devices])
        self.list.setCurrentRow(min(selection,len(self.devices)-1))

    def apply_editor(self, index=None):
        editor=DeviceEditor(self.devices[index] if index is not None else None,self)
        while editor.exec() == QDialog.Accepted:
            try:
                device=editor.config()
                updated=self.devices.copy()
                if index is None:
                    updated.append(device)
                else:
                    updated[index]=device
                validate_devices(updated)
            except (ValueError,PermissionError) as error:
                QMessageBox.warning(self,"Invalid configuration",str(error))
                continue
            self.devices=updated
            self.refresh(index or 0)
            break

    def add(self):
        self.apply_editor()

    def edit(self):
        index=self.list.currentRow()
        if index >= 0:
            self.apply_editor(index)

    def toggle(self):
        index=self.list.currentRow()
        if index >= 0:
            updated=self.devices.copy()
            updated[index]=replace(updated[index],enabled=not updated[index].enabled)
            try:
                validate_devices(updated)
            except ValueError as error:
                QMessageBox.warning(self,"Invalid configuration",str(error))
                return
            self.devices=updated
            self.refresh(index)

    def remove(self):
        index=self.list.currentRow()
        if index >= 0:
            self.devices.pop(index)
            self.refresh(index)

    def move(self,direction):
        index=self.list.currentRow()
        other=index+direction
        if 0 <= index < len(self.devices) and 0 <= other < len(self.devices):
            self.devices[index],self.devices[other]=self.devices[other],self.devices[index]
            self.refresh(other)

    def sort(self,key):
        self.devices.sort(key=key)
        self.refresh()
