from __future__ import annotations

from collections import deque
from dataclasses import asdict
from datetime import datetime
import csv
import math
from pathlib import Path
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
import pyqtgraph as pg

from prevex_hmi.devices.configuration import save_settings
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.gui.device_dialogs import DeviceManager
from prevex_hmi.gui.presentation import format_reading, measurement, severity
from prevex_hmi.gui.worker import MonitoringWorker
from prevex_hmi.profiles import PROFILES
from prevex_hmi.registers.schema import decode_relays, decode_service


def table(headers: list[str]) -> QTableWidget:
    widget=QTableWidget(0,len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setAlternatingRowColors(True)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.verticalHeader().hide()
    return widget


def fill_table(widget: QTableWidget, rows) -> None:
    widget.setUpdatesEnabled(False)
    widget.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            widget.setItem(i,j,QTableWidgetItem(str(value)))
    widget.setUpdatesEnabled(True)


class MainWindow(QMainWindow):
    received = Signal()

    def __init__(self, settings: dict, settings_path: Path, data_path: Path, *, start_worker=True):
        super().__init__()
        self.settings,self.settings_path,self.data_path=settings,settings_path,data_path
        self.snapshots: dict[str,dict]={}
        self.series: dict[str,deque]={}
        self.last_sample: dict[str,tuple]={}
        self.worker: MonitoringWorker | None=None
        self.restarting=False
        self.closing=False
        self.history_rows=[]
        self.update_count=0
        self.setWindowTitle("PREVEX HMI | Simulation monitoring")
        self.resize(1360,880)
        self.setMinimumSize(1000,700)
        central=QWidget()
        root=QVBoxLayout(central)
        root.setContentsMargins(20,16,20,16)
        title_row=QHBoxLayout()
        brand=QLabel("PREVEX  /  HMI")
        brand.setObjectName("brand")
        title_row.addWidget(brand)
        title_row.addStretch()
        self.summary=QLabel("Starting simulator...")
        title_row.addWidget(self.summary)
        self.theme_button=QPushButton("Switch theme")
        self.theme_button.clicked.connect(self.toggle_theme)
        title_row.addWidget(self.theme_button)
        root.addLayout(title_row)
        banner=QLabel("SIMULATION MODE  |  Synthetic analyzer data  |  No physical connection  |  Controls unavailable")
        banner.setObjectName("simulationBanner")
        root.addWidget(banner)
        body=QHBoxLayout()
        self.navigation=QListWidget()
        self.navigation.setFixedWidth(190)
        self.navigation.addItems(["Overview","Analyzer details","Live trends","History / CSV","Alarm / event history","Diagnostics"])
        body.addWidget(self.navigation)
        self.pages=QStackedWidget()
        body.addWidget(self.pages,1)
        root.addLayout(body,1)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.setCentralWidget(central)
        self.build_overview()
        self.build_details()
        self.build_trends()
        self.build_history()
        self.build_events()
        self.build_diagnostics()
        self.navigation.setCurrentRow(0)
        self.apply_theme()
        self.refresh_devices()
        self.statusBar().showMessage(f"Simulation only | 9600 baud equivalent | Data: {data_path}")
        if start_worker:
            self.start_worker()

    def page(self,title: str,subtitle: str) -> tuple[QWidget,QVBoxLayout]:
        page=QWidget()
        layout=QVBoxLayout(page)
        layout.setContentsMargins(18,12,0,0)
        heading=QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)
        label=QLabel(subtitle)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.pages.addWidget(page)
        return page,layout

    def build_overview(self):
        _,layout=self.page("Analyzer overview","Shared RS485 bus model - refresh rates depend on total bus traffic.")
        row=QHBoxLayout()
        manage=QPushButton("Manage analyzers / arrange cards")
        manage.clicked.connect(self.manage_devices)
        row.addWidget(manage)
        row.addStretch()
        layout.addLayout(row)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        self.card_container=QWidget()
        self.card_layout=QGridLayout(self.card_container)
        self.card_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.card_container)
        layout.addWidget(scroll)
        self.cards={}

    def build_details(self):
        _,layout=self.page("Analyzer details","Only documented parameters for the selected family are shown. -- means unavailable.")
        self.selected=QComboBox()
        self.selected.currentIndexChanged.connect(self.refresh_detail)
        layout.addWidget(self.selected)
        hero=QHBoxLayout()
        self.detail_reading=QLabel("--")
        self.detail_reading.setObjectName("reading")
        hero.addWidget(self.detail_reading)
        self.detail_status=QLabel("Waiting")
        hero.addWidget(self.detail_status,1)
        layout.addLayout(hero)
        self.detail_meta=QLabel()
        self.detail_meta.setWordWrap(True)
        layout.addWidget(self.detail_meta)
        self.parameters=table(["Register","Parameter","Raw","Engineering value","Units"])
        layout.addWidget(self.parameters,2)
        self.relays=QLabel()
        self.relays.setWordWrap(True)
        layout.addWidget(self.relays)
        self.service=QLabel()
        self.service.setWordWrap(True)
        layout.addWidget(self.service)
        self.detail_plot=self.make_plot()
        self.detail_curve=self.detail_plot.plot(pen=pg.mkPen("#3ccbb1",width=2),connect="finite")
        layout.addWidget(self.detail_plot,2)

    def make_plot(self):
        plot=pg.PlotWidget(axisItems={"bottom":pg.DateAxisItem()},background="#111c2b")
        plot.showGrid(x=True,y=True,alpha=0.15)
        plot.setLabel("bottom","Time (local display)")
        plot.setLabel("left","Measurement")
        return plot

    def build_trends(self):
        _,layout=self.page("Live trends","Zoom with the mouse wheel; drag to pan. The latest 1800 points are retained in memory; communication gaps break the line.")
        self.trend_device=QComboBox()
        self.trend_device.currentIndexChanged.connect(self.refresh_trend)
        layout.addWidget(self.trend_device)
        self.trend_plot=self.make_plot()
        self.trend_curve=self.trend_plot.plot(pen=pg.mkPen("#3ccbb1",width=2),connect="finite")
        layout.addWidget(self.trend_plot)

    def build_history(self):
        _,layout=self.page("History and CSV export","Simulation historian only. Displays and exports up to the latest 5000 primary readings in the selected range. Measurement retention: 90 days; events retained separately.")
        row=QHBoxLayout()
        self.history_device=QComboBox()
        self.history_device.currentIndexChanged.connect(self.clear_history)
        row.addWidget(self.history_device,1)
        self.history_hours=QComboBox()
        for text,hours in [("Last hour",1),("Last 24 hours",24),("Last 7 days",168),("Last 90 days",2160)]:
            self.history_hours.addItem(text,hours)
        self.history_hours.setCurrentIndex(1)
        row.addWidget(self.history_hours)
        load=QPushButton("Load history")
        load.clicked.connect(self.load_history)
        row.addWidget(load)
        export=QPushButton("Export displayed CSV")
        export.clicked.connect(self.export_history)
        row.addWidget(export)
        layout.addLayout(row)
        self.history_plot=self.make_plot()
        self.history_curve=self.history_plot.plot(pen=pg.mkPen("#5fa7ed",width=2),connect="finite")
        layout.addWidget(self.history_plot)
        self.history_table=table(["Timestamp (UTC)","Value","Unit","Quality","Status code"])
        layout.addWidget(self.history_table)

    def build_events(self):
        _,layout=self.page("Alarm and event history","Operating-state and communication transitions are recorded even when measurement logging is disabled. Latest 500 events shown.")
        self.event_table=table(["Timestamp (UTC)","Instrument","Transition","Quality"])
        layout.addWidget(self.event_table)

    def build_diagnostics(self):
        _,layout=self.page("Communication diagnostics","In-memory Modbus RTU simulation. No COM port is open. Raw traffic is limited to 500 entries; latest 100 shown below.")
        self.diagnostics_summary=QLabel("Waiting for first poll")
        self.diagnostics_summary.setWordWrap(True)
        layout.addWidget(self.diagnostics_summary)
        self.device_stats=table(["Address","Polls","Successes","Timeouts","CRC errors","Protocol errors","Last reply (ms)"])
        self.device_stats.setMaximumHeight(180)
        layout.addWidget(self.device_stats)
        fault_row=QHBoxLayout()
        self.fault_device=QComboBox()
        self.fault_device.currentIndexChanged.connect(self.refresh_inspector)
        self.fault_kind=QComboBox()
        self.fault_kind.addItems(["none","timeout","crc","protocol"])
        fault_row.addWidget(self.fault_device,1)
        fault_row.addWidget(self.fault_kind)
        inject=QPushButton("Apply simulated fault / recovery")
        inject.clicked.connect(self.inject_fault)
        fault_row.addWidget(inject)
        layout.addLayout(fault_row)
        inspect_row=QHBoxLayout()
        self.inspect_register=QComboBox()
        inspect_row.addWidget(self.inspect_register,1)
        inspect_button=QPushButton("Inspect register (read only)")
        inspect_button.clicked.connect(self.inspect)
        inspect_row.addWidget(inspect_button)
        self.inspection_result=QLabel("No manual read requested")
        inspect_row.addWidget(self.inspection_result,2)
        layout.addLayout(inspect_row)
        self.traffic=table(["Time (UTC)","Direction","Address","Register","Hexadecimal bytes"])
        layout.addWidget(self.traffic)

    def refresh_devices(self):
        self.devices=[DeviceConfig(**r) for r in self.settings["devices"]]
        current_ids={d.id for d in self.devices}
        self.series={id:points for id,points in self.series.items() if id in current_ids}
        while self.card_layout.count():
            item=self.card_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.cards={}
        for index,device in enumerate(self.devices):
            card=QPushButton(f"{device.name}\n{device.family} | address {device.address}\n--\nWaiting for first update")
            card.setMinimumHeight(205)
            card.setObjectName("analyzerCard")
            card.clicked.connect(lambda checked=False,id=device.id:self.open_device(id))
            self.card_layout.addWidget(card,index//2,index%2)
            self.cards[device.id]=card
        for combo in (self.selected,self.trend_device,self.history_device,self.fault_device):
            combo.blockSignals(True)
            combo.clear()
            for device in self.devices:
                combo.addItem(device.name,device.id)
            combo.blockSignals(False)
        self.refresh_inspector()

    def start_worker(self):
        self.worker=MonitoringWorker(self.devices,self.data_path,self)
        self.worker.updated.connect(self.update_data)
        self.worker.history_ready.connect(self.update_history)
        self.worker.events_ready.connect(lambda rows:fill_table(self.event_table,rows))
        self.worker.failed.connect(self.worker_error)
        self.worker.inspection_ready.connect(self.inspection_result_ready)
        self.worker.inspection_failed.connect(self.inspection_result.setText)
        self.worker.finished.connect(self.worker_finished)
        self.worker.start()

    def update_data(self,snapshots,diagnostics):
        self.update_count+=1
        good=0
        for snapshot in snapshots:
            config=snapshot["config"]
            id=config["id"]
            self.snapshots[id]=snapshot
            color,status=severity(snapshot)
            value,unit=measurement(snapshot)
            good+=snapshot["quality"] == "GOOD"
            age=snapshot["age"]
            age_text="never" if age is None else f"{age:.1f}s ago"
            card=self.cards.get(id)
            if card:
                card.setText(f"{config['name']}\n{config['family']}  /  address {config['address']}\n\n{format_reading(snapshot)}  {unit if value is not None else ''}\n\n● {status}  |  {snapshot['quality']}\nLast successful update: {age_text}")
                card.setStyleSheet(f"QPushButton {{ border: 1px solid {color}; border-left: 5px solid {color}; text-align: left; padding: 18px; font-size: 15px; }}")
            marker=snapshot["last_success"],snapshot["quality"]
            if marker != self.last_sample.get(id):
                timestamp=datetime.fromisoformat(snapshot["last_success"]).timestamp() if value is not None else time.time()
                self.series.setdefault(id,deque(maxlen=1800)).append((timestamp,float(value) if value is not None else float("nan")))
                self.last_sample[id]=marker
        self.summary.setText(f"{good}/{len(snapshots)} current  |  SIMULATED BUS")
        self.refresh_detail()
        self.refresh_trend()
        stats=diagnostics["bus"]
        rate=stats["success_rate"]
        self.diagnostics_summary.setText(f"9600 baud equivalent / 8N1 | Polls: {stats['polls']} | Success: {'--' if rate is None else f'{rate:.1f}%'} | Timeouts: {stats['timeouts']} | CRC errors: {stats['crc_errors']} | Last poll: {stats['last_poll']}\nLast response: {stats['last_response']} | Response time: {stats['last_response_ms']:.2f} ms | Shared bus cap: 8 requests/s; retries via bounded scheduler backoff")
        fill_table(self.device_stats,[(a,s["polls"],s["successes"],s["timeouts"],s["crc_errors"],s["protocol_errors"],f"{s['last_response_ms']:.2f}") for a,s in diagnostics["devices"].items()])
        fill_table(self.traffic,[(r["time"],r["direction"],r["address"],r["register"],r["hex"]) for r in diagnostics["traffic"][-100:]])
        self.received.emit()

    def open_device(self,id):
        self.selected.setCurrentIndex(self.selected.findData(id))
        self.navigation.setCurrentRow(1)
        self.refresh_detail()

    def refresh_detail(self,*_):
        id=self.selected.currentData()
        snapshot=self.snapshots.get(id)
        if not snapshot:
            return
        config=snapshot["config"]
        color,status=severity(snapshot)
        value,unit=measurement(snapshot)
        self.detail_reading.setText(f"{format_reading(snapshot)} {unit if value is not None else ''}")
        self.detail_reading.setStyleSheet(f"color: {color};")
        self.detail_status.setText(f"● {status}\n{snapshot['quality']}\n{snapshot['error']}")
        self.detail_meta.setText(f"{config['family']} / {config['assembly']} / configured software {config['version']} / address {config['address']}\nIdentification (simulated): {snapshot['identification'] or 'not yet polled'}\nSerial number: unavailable unless contained in identification | Last successful update (UTC): {snapshot['last_success'] or 'never'}")
        profile=PROFILES[config["family"]]
        rows=[]
        for number in sorted(snapshot["raw"]):
            if number >= 257 or number in (1,2,4): continue
            register=profile.register(number)
            engineering,units=measurement(snapshot,number)
            rows.append((number,register.name,snapshot["raw"][number] if snapshot["quality"] == "GOOD" else "--",f"{engineering:.3f}" if engineering is not None else "--",units))
        fill_table(self.parameters,rows)
        if snapshot["quality"] == "GOOD" and 4 in snapshot["raw"]:
            self.relays.setText("RELAYS  |  "+"  ·  ".join(f"{n}: {'ON' if active else 'off'}" for n,active in decode_relays(snapshot["raw"][4]).items()))
        else:
            self.relays.setText("RELAYS  |  unavailable")
        if config["family"] == "FID":
            self.service.setText("SERVICE: unsupported by supplied FID documentation")
        elif snapshot["quality"] == "GOOD" and 59 in snapshot["raw"]:
            flags=decode_service(snapshot["raw"][59],config["family"])
            self.service.setText("SERVICE  |  "+(", ".join(n for n,v in flags.items() if v) or "No active service flags"))
        else:
            self.service.setText("SERVICE: unavailable / not yet polled")
        self.plot_series(self.detail_curve,self.detail_plot,id)

    def plot_series(self,curve,plot,id):
        samples=self.series.get(id,[])
        curve.setData([t for t,v in samples],[v for t,v in samples])
        snapshot=self.snapshots.get(id)
        if snapshot:
            plot.setLabel("left","Measurement",units=measurement(snapshot)[1] if snapshot["quality"] == "GOOD" else "")

    def refresh_trend(self,*_):
        self.plot_series(self.trend_curve,self.trend_plot,self.trend_device.currentData())

    def load_history(self):
        if self.worker and self.worker.isRunning() and self.history_device.currentData():
            self.worker.request("history",self.history_device.currentData(),self.history_hours.currentData())

    def clear_history(self,*_):
        self.history_rows=[]
        if hasattr(self,"history_table"):
            self.history_table.setRowCount(0)
            self.history_curve.setData([],[])

    def update_history(self,id,rows):
        if id != self.history_device.currentData(): return
        self.history_rows=rows
        fill_table(self.history_table,rows)
        self.history_curve.setData([datetime.fromisoformat(r[0]).timestamp() for r in rows],[r[1] if r[1] is not None else float("nan") for r in rows])

    def export_history(self):
        if not self.history_rows:
            QMessageBox.information(self,"History","Load history before exporting.")
            return
        path,_=QFileDialog.getSaveFileName(self,"Export displayed readings",str(self.data_path/"simulation-history.csv"),"CSV files (*.csv)")
        if path:
            try:
                with open(path,"w",newline="",encoding="utf-8-sig") as stream:
                    writer=csv.writer(stream)
                    writer.writerow(["instrument_id","instrument_name","timestamp_utc","value","unit","quality","status"])
                    writer.writerows([(self.history_device.currentData(),self.history_device.currentText(),*row) for row in self.history_rows])
                self.statusBar().showMessage(f"Exported {len(self.history_rows)} readings to {path}")
            except OSError as error:
                QMessageBox.warning(self,"Export failed",str(error))

    def inject_fault(self):
        id=self.fault_device.currentData()
        device=next((d for d in self.devices if d.id == id),None)
        if device and device.enabled and self.worker and self.worker.isRunning():
            self.worker.request("fault",device.addressing.packet_address,self.fault_kind.currentText())

    def refresh_inspector(self,*_):
        if not hasattr(self,"inspect_register"): return
        self.inspect_register.clear()
        device=next((d for d in self.devices if d.id == self.fault_device.currentData()),None)
        if device:
            for number,register in sorted(PROFILES[device.family].registers.items()):
                if register.safe_read:
                    self.inspect_register.addItem(f"{number} - {register.name}",number)

    def inspect(self):
        if self.worker and self.worker.isRunning() and self.inspect_register.currentData() is not None:
            self.worker.request("inspect",self.fault_device.currentData(),self.inspect_register.currentData())

    def inspection_result_ready(self,id,number,raw):
        snapshot=self.snapshots.get(id)
        text=f"Register {number}: raw {raw} / 0x{raw:04X}"
        if snapshot:
            temporary=dict(snapshot,raw=dict(snapshot["raw"]),quality="GOOD")
            temporary["raw"][number]=raw
            value,unit=measurement(temporary,number)
            if value is not None: text+=f" / {value:.3f} {unit}"
        self.inspection_result.setText(text)

    def manage_devices(self):
        if self.restarting: return
        dialog=DeviceManager(self.devices,self)
        if dialog.exec() != QDialog.Accepted: return
        updated=dict(self.settings,devices=[asdict(d) for d in dialog.devices])
        try:
            save_settings(self.settings_path,updated)
        except (OSError,ValueError) as error:
            QMessageBox.warning(self,"Save failed",str(error))
            return
        self.settings=updated
        self.restarting=True
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        else:
            self.worker_finished()

    def worker_finished(self):
        if self.closing:
            self.close()
        elif self.restarting:
            self.restarting=False
            self.snapshots.clear()
            self.last_sample.clear()
            self.history_rows=[]
            self.history_curve.setData([],[])
            self.history_table.setRowCount(0)
            self.refresh_devices()
            self.start_worker()

    def worker_error(self,message):
        for id,snapshot in self.snapshots.items():
            snapshot["quality"]="OFFLINE"
            snapshot["error"]=message
            card=self.cards.get(id)
            if card: card.setText(f"{snapshot['config']['name']}\nOFFLINE\n--\nMonitoring stopped: {message}")
        self.refresh_detail()
        self.summary.setText("MONITORING STOPPED")
        self.statusBar().showMessage(f"Monitoring stopped: {message}")

    def apply_theme(self):
        dark=self.settings.get("theme","dark") == "dark"
        bg,panel,text,muted=("#0d1625","#172335","#e7edf7","#adbbcf") if dark else ("#f1f4f9","#ffffff","#172335","#425570")
        self.setStyleSheet(f"""
            QWidget {{ background: {bg}; color: {text}; font-family: 'Segoe UI'; font-size: 13px; }}
            QLabel#brand {{ font-size: 23px; font-weight: 700; padding: 8px 0; }}
            QLabel#heading {{ font-size: 25px; font-weight: 600; margin-bottom: 6px; }}
            QLabel#reading {{ font-size: 42px; font-weight: 600; padding: 12px 0; }}
            QLabel#simulationBanner {{ background: #eab65b; color: #251c10; padding: 11px; font-weight: 700; }}
            QPushButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{ background: {panel}; border: 1px solid {muted}; border-radius: 6px; padding: 8px; }}
            QPushButton:hover {{ border-color: #45c9ae; }}
            QListWidget, QTableWidget {{ background: {panel}; alternate-background-color: {bg}; border: 0; }}
            QListWidget::item {{ padding: 15px 10px; border-radius: 6px; }}
            QListWidget::item:selected {{ background: #245a69; color: white; }}
            QHeaderView::section {{ background: {panel}; color: {text}; padding: 8px; border: 0; }}
            QScrollArea {{ border: 0; }}
        """)

    def toggle_theme(self):
        self.settings["theme"]="light" if self.settings.get("theme","dark") == "dark" else "dark"
        try:
            save_settings(self.settings_path,self.settings)
        except OSError as error:
            self.statusBar().showMessage(f"Theme could not be saved: {error}")
        self.apply_theme()

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.closing=True
            self.worker.stop()
            self.setEnabled(False)
            self.statusBar().showMessage("Stopping polling and closing the database...")
            event.ignore()
        else:
            event.accept()
