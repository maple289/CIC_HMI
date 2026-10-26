from __future__ import annotations
from collections import deque
from datetime import datetime
import copy
import csv
from pathlib import Path
import time
from dataclasses import replace
from PySide6.QtCore import Qt,Signal,QTimer
from PySide6.QtWidgets import QAbstractItemView,QComboBox,QDialog,QDoubleSpinBox,QFileDialog,QFrame,QGridLayout,QHBoxLayout,QHeaderView,QLabel,QListWidget,QMainWindow,QMessageBox,QPushButton,QScrollArea,QSpinBox,QStackedWidget,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget,QSizePolicy,QToolButton,QMenu
import pyqtgraph as pg
from prevex_hmi.devices.configuration import save_settings
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.gui.connection_dialog import AnalyzerChoice,LoginDialog
from prevex_hmi.gui.connection_result import ConnectionTestResult
from prevex_hmi.gui.gauge import CircularGauge
from prevex_hmi.gui.compact_readouts import CompactReadouts
from prevex_hmi.gui.analyzer_hero import AnalyzerHero
from prevex_hmi.gui.profile_library import PROFILE_CHOICES,PROFILE_STATUS,library_config
from prevex_hmi.gui.trend_display import DisplayTrend
from prevex_hmi.gui.command_button import CommandButton
from prevex_hmi.gui.serial_ports import require_available_port
from prevex_hmi.gui.indicators import IndicatorPanel
from prevex_hmi.gui.presentation import measurement,severity,uses_controller_fault_display
from prevex_hmi.gui.worker import MonitoringWorker
from prevex_hmi.profiles import PROFILES,profile_for,commands_for,profile_name
from prevex_hmi.profiles.common import COMMANDS
from prevex_hmi.profiles.gauges import GAUGE_REGISTERS,precision,gauges_for
from prevex_hmi.security.users import UserStore


def table(headers):
    w=QTableWidget(0,len(headers));w.setHorizontalHeaderLabels(headers)
    w.setEditTriggers(QAbstractItemView.NoEditTriggers);w.setAlternatingRowColors(True)
    # Live traffic changes continuously. ResizeToContents repeatedly scans the
    # entire table during cell updates and can starve the Qt event loop.
    w.setWordWrap(False)
    header=w.horizontalHeader();header.setSectionResizeMode(QHeaderView.Interactive)
    header.setDefaultSectionSize(160)
    for column,name in enumerate(headers):
        w.setColumnWidth(column,260 if 'timestamp' in name.lower() else 700 if name=='Hexadecimal bytes' else 480 if name in ('Transition','Detail') else 160)
    w.verticalHeader().setSectionResizeMode(QHeaderView.Fixed);w.verticalHeader().hide()
    return w


def fill_table(widget,rows):
    values=tuple(tuple(str(value) for value in row) for row in rows)
    if getattr(widget,'_displayed_rows',None)==values and widget.rowCount()==len(values):return
    updating=widget.updatesEnabled();blocked=widget.blockSignals(True)
    widget.setUpdatesEnabled(False)
    try:
        if widget.rowCount()!=len(values):widget.setRowCount(len(values))
        for i,row in enumerate(values):
            for j,value in enumerate(row):
                item=widget.item(i,j)
                if item is None:widget.setItem(i,j,QTableWidgetItem(value))
                elif item.text()!=value:item.setText(value)
        widget._displayed_rows=values
    finally:
        widget.blockSignals(blocked);widget.setUpdatesEnabled(updating)


class MainWindow(QMainWindow):
    received=Signal()

    def __init__(self,settings,settings_path:Path,data_path:Path,*,start_worker=True,hardware_grant=None):
        super().__init__()
        self.settings,self.settings_path,self.data_path=settings,settings_path,data_path
        self.hardware_grant=hardware_grant
        self.worker=None;self.snapshot=None;self.identity={};self.diagnostics={}
        self.test_in_progress=False;self.test_result_info=None;self.test_result_error='';self.connection_test_dialog=None
        self.test_view_active=False;self.return_page=0
        self.snapshot_received_at=0.0
        self.snapshot_family=None;self.readouts={};self.history_rows=[];self.series=deque(maxlen=1800)
        self.display_trend=DisplayTrend();self.trend_scope=None;self.blank_started_wall=None;self.readout_retained=False
        self.last_sample=None;self.update_count=0;self.closing=False;self.next_action=None
        self.last_receipt_key=None;self.active_command=None
        self.command_dispatching=False;self.session='';self.users=UserStore(data_path/'users.sqlite3')
        self.setWindowTitle('PREVEX HMI | Single analyzer');self.resize(1540,1020);self.setMinimumSize(1100,780)
        central=QWidget();root=QVBoxLayout(central);root.setContentsMargins(18,12,18,12)
        header=QHBoxLayout();brand=QLabel('PREVEX / HMI');brand.setObjectName('brand');header.addWidget(brand)
        self.summary=QLabel('Disconnected');header.addWidget(self.summary,1)
        self.login_button=QPushButton('Sign in / create account');self.login_button.clicked.connect(self.login);header.addWidget(self.login_button)
        self.account_button=QPushButton('My account');self.account_button.setEnabled(False);self.account_button.clicked.connect(self.manage_account);header.addWidget(self.account_button)
        theme=QPushButton('Switch theme');theme.clicked.connect(self.toggle_theme);header.addWidget(theme);root.addLayout(header)
        self.banner=QLabel();self.banner.setObjectName('banner');root.addWidget(self.banner)
        toolbar=QHBoxLayout()
        self.choose_button=QPushButton('Choose Analyzer Type');self.choose_button.clicked.connect(self.choose_type);toolbar.addWidget(self.choose_button)
        self.connect_button=QPushButton('Connect');self.connect_button.clicked.connect(lambda:self.begin('connect'));toolbar.addWidget(self.connect_button)
        self.disconnect_button=QPushButton('Disconnect');self.disconnect_button.clicked.connect(lambda:self.begin('disconnect'));toolbar.addWidget(self.disconnect_button)
        self.test_button=QPushButton('Test Connection');self.test_button.clicked.connect(lambda:self.begin('test'));toolbar.addWidget(self.test_button)
        self.bench_button=QPushButton('Connect SNR671 / COM4');self.bench_button.clicked.connect(self.start_controller_bench);toolbar.addWidget(self.bench_button)
        self.bench_button.setToolTip('Previously authorized controller bench: COM4, 9600, packet address1. Monitoring plus confirmed Operator/Admin Acknowledge/Reset only. No calibration or other physical writes.')
        self.selection_label=QLabel();toolbar.addWidget(self.selection_label,1);root.addLayout(toolbar)
        self.identity_label=QLabel('Instrument identification: not connected');self.identity_label.setWordWrap(True);root.addWidget(self.identity_label)
        self.warning=QLabel();self.warning.setObjectName('warning');self.warning.setWordWrap(True);self.warning.hide();root.addWidget(self.warning)
        body=QHBoxLayout();self.navigation=QListWidget();self.navigation.setFixedWidth(170)
        self.navigation.addItems(['Gauge','Live trends','History / CSV','Alarm history','Diagnostics','Command audit','Profile settings']);body.addWidget(self.navigation)
        self.pages=QStackedWidget();body.addWidget(self.pages,1);root.addLayout(body,1);self.setCentralWidget(central)
        self.build_gauge();self.build_trends();self.build_history();self.build_events();self.build_diagnostics();self.build_audit();self.build_profile_settings()
        self.build_connection_test_page()
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex);self.navigation.setCurrentRow(0)
        self.navigation.currentRowChanged.connect(lambda index:self.refresh_profile_settings() if index==6 else None)
        self.apply_theme();self.refresh_connection_labels();self.build_readouts(self.config.family)
        self.set_connection_status(False)
        self.refresh_profile_settings()
        self.connection_watch=QTimer(self);self.connection_watch.setInterval(250)
        self.connection_watch.timeout.connect(self.refresh_connection_status);self.connection_watch.start()
        self.account_watch=QTimer(self);self.account_watch.setInterval(1000);self.account_watch.timeout.connect(self.update_command_buttons);self.account_watch.start()
        self.statusBar().showMessage(f'Data: {data_path} | No safety function depends on the HMI')
        if start_worker:self.start_worker()

    @property
    def config(self):return DeviceConfig(**self.settings['devices'][0])

    def page(self,title,subtitle):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(14,4,0,0)
        heading=QLabel(title);heading.setObjectName('heading');layout.addWidget(heading)
        label=QLabel(subtitle);label.setWordWrap(True);layout.addWidget(label);self.pages.addWidget(page)
        return layout

    def build_connection_test_page(self):
        self.test_page=QScrollArea();self.test_page.setWidgetResizable(True)
        content=QWidget();self.test_page_layout=QVBoxLayout(content)
        heading=QLabel('Test Connection');heading.setObjectName('heading');self.test_page_layout.addWidget(heading)
        self.test_progress=QLabel('Checking communication and instrument identification...')
        self.test_progress.setWordWrap(True);self.test_page_layout.addWidget(self.test_progress)
        self.test_page_layout.addStretch()
        self.test_page.setWidget(content);self.pages.addWidget(self.test_page)

    def set_test_view(self,active):
        was_active=self.test_view_active
        if active and not self.test_view_active:self.return_page=max(0,self.navigation.currentRow())
        self.test_view_active=active
        self.navigation.setVisible(not active)
        for widget in (self.banner,self.identity_label,self.login_button,self.account_button,self.disconnect_button,self.bench_button):widget.setVisible(not active)
        self.warning.setVisible(not active and bool(self.warning.text()))
        if active:self.pages.setCurrentWidget(self.test_page)
        elif was_active:self.pages.setCurrentIndex(self.return_page)

    def build_gauge(self):
        layout=self.page('Gauge','One active analyzer. Digital parameters follow its manufacturer GAUGES menu.')
        body=QHBoxLayout();layout.addLayout(body,1)
        left=QWidget();left_layout=QVBoxLayout(left);left_layout.setContentsMargins(0,0,0,0)
        self.indicators=IndicatorPanel();self.indicators.summary.setWordWrap(True);left_layout.addWidget(self.indicators)
        scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();content.setMinimumWidth(600)
        self.monitor_scroll=scroll
        readings=QVBoxLayout(content);readings.setContentsMargins(0,0,6,4)
        self.gauge=CircularGauge()
        self.analyzer_info=QFrame();self.analyzer_info.setMinimumWidth(200)
        info=QVBoxLayout(self.analyzer_info);info.setContentsMargins(0,4,0,4);self.monitor_name=QLabel();self.monitor_name.setObjectName('heading');self.monitor_name.setWordWrap(True);info.addWidget(self.monitor_name)
        self.monitor_model=QLabel();self.monitor_model.setWordWrap(True);info.addWidget(self.monitor_model)
        self.monitor_status=QLabel('Connection Status: ● No Connection');self.monitor_status.setWordWrap(True);info.addWidget(self.monitor_status)
        self.monitor_updated=QLabel();self.monitor_updated.setWordWrap(True);info.addWidget(self.monitor_updated)
        self.range_help=QLabel('LEL gray: negative section\nBold marker: zero\nLEL: -100 during fault; -30 normally\nW / D: live alarm thresholds [5 / 6]');self.range_help.setWordWrap(True);info.addWidget(self.range_help);info.addStretch()
        self.controller_display=QLabel();self.controller_display.setWordWrap(True);info.insertWidget(info.count()-1,self.controller_display)
        self.command_result_card=QFrame();self.command_result_card.setObjectName('panel');self.command_result_card.setMinimumWidth(260)
        result_layout=QVBoxLayout(self.command_result_card);result_layout.setContentsMargins(10,10,10,10)
        result_title=QLabel('Command result');result_title.setObjectName('heading');result_layout.addWidget(result_title)
        self.command_result_scroll=QScrollArea();self.command_result_scroll.setWidgetResizable(True)
        result_content=QWidget();result_body=QVBoxLayout(result_content);result_body.setContentsMargins(0,0,0,0)
        self.command_proof=QLabel('No command sent in this session');self.command_proof.setWordWrap(True)
        self.command_proof.setTextFormat(Qt.PlainText);self.command_proof.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.command_proof.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);result_body.addWidget(self.command_proof)
        self.command_message=QLabel('Select an available command after signing in.');self.command_message.setWordWrap(True)
        self.command_message.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);result_body.addWidget(self.command_message);result_body.addStretch()
        self.command_result_scroll.setWidget(result_content);result_layout.addWidget(self.command_result_scroll,1)
        self.hero=AnalyzerHero(self.gauge,self.analyzer_info,self.command_result_card);readings.addWidget(self.hero)
        self.readout_groups={}
        for title in ('Gauges','Calibration parameters','Alarm settings'):
            label=QLabel(title);label.setObjectName('heading');readings.addWidget(label)
            container=CompactReadouts();readings.addWidget(container);self.readout_groups[title]=container
        self.readout_container=self.readout_groups['Gauges'];self.readout_grid=self.readout_container.grid
        self.overview_plot=self.make_plot();self.overview_plot.setMinimumHeight(180);self.overview_curve=self.overview_plot.plot(pen=pg.mkPen('#45cbb0',width=2),connect='finite');readings.addWidget(self.overview_plot)
        self.overview_held_curve=self.overview_plot.plot(pen=pg.mkPen('#e7b55e',width=2,style=Qt.DashLine),connect='finite')
        self.overview_hold_note=QLabel('Solid: measured | Dashed amber: held while LCD is nonnumeric (display only)');self.overview_hold_note.setWordWrap(True);readings.addWidget(self.overview_hold_note)
        scroll.setWidget(content);left_layout.addWidget(scroll,1);body.addWidget(left,1)
        commands=QFrame();commands.setObjectName('panel');commands.setFixedWidth(220);column=QVBoxLayout(commands);column.setSpacing(6);column.setAlignment(Qt.AlignTop)
        label=QLabel('Commands');label.setObjectName('heading');column.addWidget(label)
        self.role_label=QLabel('Guest / Viewer');column.addWidget(self.role_label)
        self.hardware_lock_label=QLabel('Hardware lock: unknown');self.hardware_lock_label.setWordWrap(True);column.addWidget(self.hardware_lock_label)
        self.command_access_note=QLabel(commands);self.command_access_note.hide()
        self.command_access_button=QPushButton('Enable Acknowledge / Reset')
        self.command_access_button.setMinimumHeight(44);self.command_access_button.clicked.connect(self.activate_command_bench)
        result_layout.addWidget(self.command_access_button)
        self.command_buttons={}
        self.lock_command_code=None
        for code,name in COMMANDS.items():
            if code==0x1000:continue
            label={0x300:'ZERO CAL',0x400:'SPAN CAL',0x500:'FULL CAL',0x600:'ZERO TEST',0x700:'SPAN TEST',0x800:'FULL TEST',0x900:'SAVE ALL',0xF00:'LOCK CAL'}.get(code,name.upper())
            button=CommandButton(label,lambda checked=False,code=code:self.send_command(self.lock_command_code if code==0xF00 else code));column.addWidget(button);self.command_buttons[code]=button
        # Both command receipts address one persistent row/LED, even as its action changes.
        self.command_buttons[0x1000]=self.command_buttons[0xF00]
        column.addStretch()
        self.command_scroll=QScrollArea();self.command_scroll.setWidgetResizable(True);self.command_scroll.setFixedWidth(236);self.command_scroll.setWidget(commands);body.addWidget(self.command_scroll)

    def build_readouts(self,family,config=None):
        config=config or self.config
        profile=profile_for(config) if config.family==family else PROFILES[family]
        self.snapshot_family=(family,profile.revision)
        for container in self.readout_groups.values():container.clear_cards()
        self.readouts={};self.readout_names={};self.parameter_menus={}
        from prevex_hmi.profiles.parameters import PARAMETERS,supported
        editable={n:key for key,(n,title) in PARAMETERS.items()} if supported(config) else {}
        numbers=list(gauges_for(config) if config.family==family else (n for n in GAUGE_REGISTERS[family] if n not in (1,50)))
        if family=='BTU':numbers.append(42)
        for i,n in enumerate(numbers):
            r=profile.register(n);frame=QFrame();frame.setObjectName('readout');box=QVBoxLayout(frame)
            title='SPAN °C' if n==56 and family!='FID' else r.name
            name=QLabel(f'{title}  [{n}]');name.setWordWrap(True)
            header=QHBoxLayout();header.setContentsMargins(0,0,0,0);header.setSpacing(2);header.addWidget(name,1);box.addLayout(header)
            if n in editable:
                key=editable[n];button=QToolButton();button.setText('...');button.setFixedSize(24,24);button.setAutoRaise(True)
                button.setStyleSheet('QToolButton::menu-indicator {width:0px;}')
                button.setAccessibleName(f'{title} options');button.setToolTip(f'Adjust {title}')
                menu=QMenu(button);menu.addAction(f'Adjust {title}…',lambda checked=False,k=key:self.edit_parameter(k))
                button.setMenu(menu);button.setPopupMode(QToolButton.InstantPopup);header.addWidget(button,0,Qt.AlignTop)
                self.parameter_menus[n]=button
            if n==18:name.setToolTip('Read-only: FAILSAFE must be changed at the controller panel; Modbus adjustment is prohibited/unverified.')
            self.readout_names[n]=name
            value=QLabel('--');value.setWordWrap(True);value.setObjectName('digitalValue');box.addWidget(value)
            quality=QLabel();quality.hide()
            box.setContentsMargins(6,6,6,6);box.setSpacing(3)
            category='Calibration parameters' if n in (7,28,29,30,56) else 'Alarm settings' if n in (5,6,17,18,72,73,74) else 'Gauges'
            self.readout_groups[category].add_card(frame);self.readouts[n]=(value,quality)
        self.indicators.build(family,config if config.family==family else None)
        self.monitor_name.setText(profile_name(config))
        self.range_help.setText('LEL gray: negative section\nBold marker: zero\nLEL: -100 during fault; -30 normally\nW / D: live alarm thresholds [5 / 6]' if family=='LEL' else 'Blue: negative section\nBold marker: zero\n'+('Low / High: BTU setpoints [5 / 6]' if family=='BTU' else 'Warning / Danger: FID setpoints [5 / 6]'))

    def make_plot(self):
        plot=pg.PlotWidget(axisItems={'bottom':pg.DateAxisItem()},background='#111c2b');plot.showGrid(x=True,y=True,alpha=.15);plot.setLabel('bottom','Time (local)');return plot

    def build_trends(self):
        layout=self.page('Live trends','Signed engineering values. Mouse-wheel zoom and drag to pan; communication gaps break the line.')
        self.trend_plot=self.make_plot();self.trend_curve=self.trend_plot.plot(pen=pg.mkPen('#45cbb0',width=2),connect='finite');layout.addWidget(self.trend_plot)
        self.trend_held_curve=self.trend_plot.plot(pen=pg.mkPen('#e7b55e',width=2,style=Qt.DashLine),connect='finite')
        self.trend_hold_note=QLabel('Solid: measured | Dashed amber: held while LCD is nonnumeric (display only)');self.trend_hold_note.setWordWrap(True);layout.addWidget(self.trend_hold_note)

    def build_history(self):
        layout=self.page('History / CSV','Current instrument stream. Up to5000 primary records per query; UTC timestamps retained in CSV.')
        row=QHBoxLayout();self.history_hours=QComboBox()
        for text,hours in [('Last hour',1),('Last day',24),('Last7 days',168),('Last90 days',2160)]:self.history_hours.addItem(text,hours)
        row.addWidget(self.history_hours);load=QPushButton('Load history');load.clicked.connect(self.load_history);row.addWidget(load)
        export=QPushButton('Export displayed CSV');export.clicked.connect(self.export_history);row.addWidget(export);row.addStretch();layout.addLayout(row)
        self.history_plot=self.make_plot();self.history_curve=self.history_plot.plot(pen=pg.mkPen('#69a7ed',width=2),connect='finite');layout.addWidget(self.history_plot)
        self.history_table=table(['UTC timestamp','Value','Unit','Quality','Status']);layout.addWidget(self.history_table)

    def build_events(self):
        layout=self.page('Alarm and status history','STATUS transitions and communication changes; retained independently of measurement logging.')
        self.event_table=table(['UTC timestamp','Instrument','Transition','Quality']);layout.addWidget(self.event_table)

    def build_audit(self):
        layout=self.page('Command audit','Modbus acknowledgments and STATUS outcomes are distinct. Operating commands require matching identity, permissions, current controller checks and confirmation.')
        self.audit_table=table(['UTC timestamp','Instrument','User','Command word','Result','Detail']);layout.addWidget(self.audit_table)

    def build_profile_settings(self):
        layout=self.page('Profile settings','Documented register inventory. Select a row to read its current value. Factory, communication and unvalidated settings remain read-only; no generic write path.')
        row=QHBoxLayout();row.addWidget(QLabel('Profile'))
        self.profile_selector=QComboBox();self.profile_selector.addItem('Connected analyzer','connected')
        for name in PROFILE_CHOICES:self.profile_selector.addItem(name+(' (preliminary)' if name in ('BTU','FID') else ''),name)
        row.addWidget(self.profile_selector,1)
        use=QPushButton('Use selected profile...');use.clicked.connect(self.use_library_profile);row.addWidget(use);layout.addLayout(row)
        self.profile_note=QLabel();self.profile_note.setWordWrap(True);layout.addWidget(self.profile_note)
        self.setting_group=QComboBox();self.setting_group.addItem('All menus')
        self.setting_group.currentTextChanged.connect(lambda _:self.refresh_profile_settings())
        layout.addWidget(self.setting_group)
        self.settings_table=table(['Register','Menu','Parameter','Raw','Value','Units','Documented access','Restrictions / reference'])
        self.settings_table.setSelectionBehavior(QAbstractItemView.SelectRows);layout.addWidget(self.settings_table)
        self.read_setting_button=QPushButton('Read selected setting (FC03)');self.read_setting_button.clicked.connect(self.read_setting);layout.addWidget(self.read_setting_button)
        self.profile_selector.currentIndexChanged.connect(lambda _:self.refresh_profile_settings())

    def selected_library_profile(self):
        active=DeviceConfig(**self.snapshot['config']) if self.snapshot else self.config
        selection=self.profile_selector.currentData()
        matches=selection in ('connected',profile_name(active))
        return (active if matches else library_config(selection)),matches

    def use_library_profile(self):
        selection=self.profile_selector.currentData()
        proposed=copy.deepcopy(self.settings)
        if selection!='connected':proposed['analyzer_selection']=selection
        dialog=AnalyzerChoice(proposed,self)
        if dialog.exec()!=QDialog.Accepted:return
        settings=dialog.settings()
        try:save_settings(self.settings_path,settings)
        except (OSError,ValueError) as error:QMessageBox.warning(self,'Save failed',str(error));return
        self.settings=settings;self.refresh_connection_labels();self.begin('connect')

    def refresh_profile_settings(self):
        config,matches=self.selected_library_profile()
        profile=profile_for(config)
        self.profile_note.setText(profile_name(config)+' — '+PROFILE_STATUS[profile_name(config)]+(' Current analyzer profile.' if matches else ' Library preview: no live values. Use selected profile to review connection settings and confirm a change.'))
        self.read_setting_button.setEnabled(bool(matches and self.snapshot and self.snapshot['quality']=='GOOD' and self.worker and self.worker.isRunning() and not self.worker.test_only))
        groups=sorted({r.category for r in profile.registers.values() if r.safe_read})
        if [self.setting_group.itemText(i) for i in range(1,self.setting_group.count())]!=groups:
            self.setting_group.blockSignals(True);self.setting_group.clear();self.setting_group.addItems(['All menus',*groups]);self.setting_group.blockSignals(False)
        rows=[]
        for n,r in sorted(profile.registers.items()):
            if not r.safe_read or n>=257 or r.access=='command':continue
            if self.setting_group.currentText() not in ('All menus',r.category):continue
            value,unit=measurement(self.snapshot,n) if self.snapshot and matches else (None,r.unit)
            rows.append((n,r.category,r.name,self.snapshot['raw'].get(n,'--') if self.snapshot and matches else '--',str(value) if value is not None else '--',unit if value is not None else r.unit,r.access,r.restrictions+' | '+r.source))
        fill_table(self.settings_table,rows)

    def read_setting(self):
        if not self.read_setting_button.isEnabled():return
        row=self.settings_table.currentRow()
        if row>=0:self.request('inspect',int(self.settings_table.item(row,0).text()))

    def build_diagnostics(self):
        layout=self.page('Diagnostics','One connection, serialized transactions. Raw traffic limited to500 frames; latest100 displayed.')
        self.diagnostics_summary=QLabel('Disconnected');self.diagnostics_summary.setWordWrap(True);layout.addWidget(self.diagnostics_summary)
        self.simulation_controls=[]
        row=QHBoxLayout();self.fault_kind=QComboBox();self.fault_kind.addItems(['none','timeout','delay','crc','protocol','unknown_identity','ambiguous_command']);row.addWidget(self.fault_kind)
        fault=QPushButton('Apply simulated fault / recovery');fault.clicked.connect(lambda:self.request('fault',self.fault_kind.currentText()));row.addWidget(fault);layout.addLayout(row)
        row=QHBoxLayout();self.forced_value=QDoubleSpinBox();self.forced_value.setRange(-10000,32000);self.forced_value.setDecimals(3);self.forced_value.setValue(-20);row.addWidget(self.forced_value)
        force=QPushButton('Set simulated reading');force.clicked.connect(lambda:self.request('reading',self.forced_value.value()));row.addWidget(force)
        dynamic=QPushButton('Resume dynamic readings');dynamic.clicked.connect(lambda:self.request('reading',None));row.addWidget(dynamic);layout.addLayout(row)
        row=QHBoxLayout();self.forced_status=QSpinBox();self.forced_status.setRange(0,255);row.addWidget(self.forced_status)
        status=QPushButton('Set simulated STATUS');status.clicked.connect(lambda:self.request('status',self.forced_status.value()));row.addWidget(status)
        dynamic_status=QPushButton('Resume dynamic status');dynamic_status.clicked.connect(lambda:self.request('status',None));row.addWidget(dynamic_status);layout.addLayout(row)
        for controls in (self.fault_kind,self.forced_value,self.forced_status,fault,force,dynamic,status,dynamic_status):self.simulation_controls.append(controls)
        row=QHBoxLayout();self.inspect_register=QComboBox();row.addWidget(self.inspect_register)
        inspect=QPushButton('Inspect register (FC03)');inspect.clicked.connect(lambda:self.request('inspect',self.inspect_register.currentData()));row.addWidget(inspect)
        self.inspection_result=QLabel('No manual read');row.addWidget(self.inspection_result,1);layout.addLayout(row)
        self.traffic=table(['UTC timestamp','Direction','Address','Register','Hexadecimal bytes']);layout.addWidget(self.traffic)

    def refresh_connection_labels(self):
        c=self.settings['connection'];d=self.config
        self.selection_label.setText(f"{self.settings['analyzer_selection']} | Address {d.address} | {c['baud']} baud / 8N1 | {self.settings['mode'].upper()}")
        self.banner.setText('SIMULATION MODE | One synthetic instrument | No physical port open' if self.settings['mode']=='simulation' else ('LIVE CONTROLLER BENCH TEST | ACK/RESET require confirmation | Sensor assembly disconnected' if self.hardware_grant.operator_commands else 'LIVE CONTROLLER BENCH TEST | READ ONLY | Sensor assembly disconnected') if self.hardware_grant else f'LIVE HARDWARE | READ ONLY | {c["port"] or "Select a serial port"}')
        for widget in self.simulation_controls:widget.setEnabled(self.settings['mode']=='simulation')

    def invalidate(self,reason='Disconnected'):
        self.snapshot=None;self.identity={};self.series.clear();self.last_sample=None;self.history_rows=[];self.command_dispatching=False
        self.display_trend.clear();self.trend_scope=None;self.blank_started_wall=None;self.readout_retained=False
        self.gauge.set_snapshot(None);self.indicators.update_snapshot(None)
        self.set_connection_status(False);self.monitor_updated.setText('No current measurement');self.identity_label.setText(reason)
        self.controller_display.clear()
        self.command_proof.setText('No command sent in this session');self.command_proof.setStyleSheet('')
        self.last_receipt_key=None;self.active_command=None
        for button in self.command_buttons.values():button.reset()
        for value,quality in self.readouts.values():value.setText('--');quality.setText('UNAVAILABLE')
        for curve in (self.overview_curve,self.trend_curve,self.overview_held_curve,self.trend_held_curve,self.history_curve):curve.setData([],[])
        for label in (self.overview_hold_note,self.trend_hold_note):label.setText('Solid: measured | Dashed amber: held while LCD is nonnumeric (display only)')
        if 1 in self.readouts:self.readouts[1][0].setStyleSheet('');self.readouts[1][0].setToolTip('')
        self.history_table.setRowCount(0);self.event_table.setRowCount(0);self.audit_table.setRowCount(0);self.traffic.setRowCount(0)
        self.summary.setText(reason);self.update_command_buttons()
        self.refresh_profile_settings()

    def begin(self,action):
        if self.connection_test_dialog:
            self.connection_test_dialog.close();self.connection_test_dialog.deleteLater();self.connection_test_dialog=None
        self.test_in_progress=action=='test';self.test_result_info=None;self.test_result_error=''
        self.set_test_view(action=='test');self.test_progress.setVisible(action=='test')
        if action in ('connect','test') and self.settings['mode']=='hardware' and self.hardware_grant is not None:
            try:
                self.hardware_grant.validate(self.settings,self.config)
                if self.config.family!='LEL' or self.settings['analyzer_selection'] not in ('Auto Detect','LEL','LEL 670 Series'):
                    self.hardware_grant=None
            except (PermissionError,ValueError):self.hardware_grant=None
            self.refresh_connection_labels()
        self.next_action=action;self.invalidate('Connection stopped; readings invalidated')
        self.set_connection_buttons(False)
        if self.worker and self.worker.isRunning():self.worker.stop()
        else:self.worker_finished()

    def start_controller_bench(self):
        from prevex_hmi.communication.hardware_session import ReadOnlyControllerGrant,controller_bench_settings
        self.settings=controller_bench_settings(self.settings)
        self.hardware_grant=ReadOnlyControllerGrant(operator_commands=True)
        self.refresh_connection_labels()
        self.begin('connect')

    def set_connection_buttons(self,enabled):
        for button in (self.choose_button,self.connect_button,self.test_button,self.bench_button):button.setEnabled(enabled)

    def start_worker(self,*,test_only=False):
        if test_only:self.test_in_progress=True;self.set_test_view(True)
        if self.settings['mode']=='hardware':
            try:require_available_port(self.settings['connection']['port'])
            except (ValueError,OSError) as error:
                self.worker_error(str(error));self.set_connection_buttons(True)
                if test_only:self.finish_connection_test()
                return
        worker_grant=replace(self.hardware_grant,operator_commands=False) if test_only and self.hardware_grant else self.hardware_grant
        self.worker=MonitoringWorker(copy.deepcopy(self.settings),self.data_path,self,test_only=test_only,hardware_grant=worker_grant)
        owner=self.worker
        def current():return self.worker is owner and not self.next_action and not self.closing
        self.worker.updated.connect(self.update_data);self.worker.identified.connect(self.identification_result)
        self.worker.history_ready.connect(lambda rows:self.update_history(rows) if current() else None);self.worker.events_ready.connect(lambda rows:fill_table(self.event_table,rows) if current() else None)
        self.worker.audit_ready.connect(lambda rows:fill_table(self.audit_table,[(a,b,c,f'Setting [{d-0x10000}]' if d>=0x10000 else f'0x{d:04X}',e,f) for a,b,c,d,e,f in rows]) if current() else None)
        self.worker.parameter_result.connect(lambda text:self.parameter_feedback(text) if current() else None)
        self.worker.inspection_ready.connect(lambda text:self.inspection_result.setText(text) if current() else None);self.worker.command_result.connect(lambda text:self.command_feedback(text) if current() else None)
        self.worker.failed.connect(self.worker_error);self.worker.finished.connect(self.worker_finished)
        self.worker.start();self.set_connection_buttons(False)

    def worker_finished(self):
        if self.closing:self.close();return
        action=self.next_action;self.next_action=None
        self.set_connection_buttons(True)
        if action=='connect':self.start_worker()
        elif action=='test':self.start_worker(test_only=True)
        else:
            self.update_command_buttons()
            if self.test_in_progress:self.finish_connection_test()

    def finish_connection_test(self):
        self.test_in_progress=False
        info=self.test_result_info or {}
        error=self.test_result_error
        if not info and not error:error='The check ended without an identification result.'
        self.connection_test_dialog=ConnectionTestResult(self.settings,info,error,self.test_page,embedded=True)
        self.connection_test_dialog.setMaximumWidth(900)
        self.connection_test_dialog.connect_requested.connect(lambda:self.begin('connect'))
        self.connection_test_dialog.back_requested.connect(lambda:self.begin('disconnect'))
        self.test_page_layout.insertWidget(2,self.connection_test_dialog)
        self.test_progress.hide();self.connection_test_dialog.show();self.set_test_view(True)
        self.summary.setText(self.connection_test_dialog.result_label.text()+' | Monitoring stopped')
        self.indicators.summary.setText('MONITORING STOPPED | One-time test complete; click Connect for live data')
        self.statusBar().showMessage('Test Connection complete. Click Connect and monitor for live data, or Back to return.')

    def identification_result(self,info):
        if self.next_action or self.closing:return
        self.identity=info
        if info.get('test_only'):self.test_result_info=info
        if info.get('config'):
            family=info['config']['family']
            config=DeviceConfig(**info["config"])
            if (family,profile_for(config).revision)!=self.snapshot_family:self.build_readouts(family,config)
        firmware=info.get('version') or 'unavailable'
        if info.get('version_provisional'):firmware+=f" (provisional; reported {info.get('reported_version')})"
        detected=info.get('loaded_profile') if info.get('family') else 'UNKNOWN'
        if info.get('register_revision')=='fta_4x':detected+=' (older-firmware register subset)'
        text=f"Selected: {info.get('selected_profile',self.settings['analyzer_selection'])} | Detected: {detected or info.get('family') or 'UNKNOWN'} | Assembly: {info.get('model') or 'unavailable'} | Software: {firmware} | Serial: {info.get('serial') or 'unavailable'} | Communication: {info.get('communication','not verified')}"
        if info.get('test_only'):text+=' | TEST ONLY: monitoring and controls remain inactive'
        self.identity_label.setText(text);self.warning.setText(info.get('warning',''));self.warning.setVisible(bool(info.get('warning')) and not self.test_view_active)
        self.monitor_model.setText(info.get('text',''))
        self.inspect_register.clear()
        family=info.get('config',{}).get('family',self.config.family)
        profile=profile_for(DeviceConfig(**info["config"])) if info.get("config") else profile_for(self.config)
        for n,r in sorted(profile.registers.items()):
            if r.safe_read:self.inspect_register.addItem(f'{n} - {r.name}',n)
        self.set_connection_buttons(True);self.update_command_buttons()
        self.refresh_profile_settings()

    def update_data(self,snapshot,diagnostics):
        if self.next_action or self.closing:return
        self.update_count+=1;self.snapshot=snapshot;self.diagnostics=diagnostics
        self.snapshot_received_at=time.monotonic()
        config=DeviceConfig(**snapshot['config']);family=config.family
        if (family,profile_for(config).revision)!=self.snapshot_family:self.build_readouts(family,config)
        self.gauge.set_snapshot(snapshot);self.indicators.update_snapshot(snapshot)
        retained=bool(self.gauge.held and self.gauge.lcd_hold)
        self.readout_retained=retained
        if retained and self.blank_started_wall is None:self.blank_started_wall=time.time()
        elif not retained:self.blank_started_wall=None
        lcd_numbers=range(51,56)
        if snapshot.get('source')=='hardware' and all(measurement(snapshot,n)[0] is not None for n in lcd_numbers):
            lcd=b''.join(snapshot['raw'][n].to_bytes(2,'big') for n in lcd_numbers).decode('latin-1').strip()
            self.controller_display.setText(f'Controller display [51–55]: {lcd}\nRaw process [1]: 0x{snapshot["raw"][1]:04X}\nFault-state values; sensor conversion validation pending')
        else:self.controller_display.clear()
        color,status=severity(snapshot);self.monitor_name.setText(profile_name(config))
        self.set_connection_status(snapshot['quality']=='GOOD' and snapshot.get('last_success') is not None)
        self.monitor_updated.setText(f"Last update (UTC):\n{snapshot['last_success'] or 'never'}\n{snapshot['error']}")
        self.summary.setText(f"{profile_name(config)} | {config.assembly}")
        for n,(widget,quality) in self.readouts.items():
            if n==1:self.readout_names[n].setText('READING [LCD51–55; raw1]' if uses_controller_fault_display(snapshot) else 'READING [1]')
            if family=='BTU' and n==42:widget.setText('--');quality.setText('UNAVAILABLE: meaning not documented');continue
            value,unit=measurement(snapshot,n)
            if n==1:
                self.readout_retained=retained
                style='color:#e7b55e;' if retained else ''
                if widget.styleSheet()!=style:widget.setStyleSheet(style)
                widget.setToolTip('Last numeric value held while the controller LCD is nonnumeric; not a new measurement.' if retained else '')
                if retained:value,unit=self.gauge.state.value,self.gauge.state.unit
            if n in (17,18) and value is not None:
                word=int(value);widget.setText(' / '.join(name for i,name in enumerate(('Warning','Danger','Fault','Horn')) if word&(1<<i)) or 'None')
                widget.setToolTip(f'Raw: 0x{word:04X}')
            elif n==2 and value is not None:widget.setText(profile_for(config).status(int(value)))
            else:widget.setText(f'{value:.{precision(family,n,snapshot["raw"].get(3,100))}f} {unit}' if value is not None else '--')
            quality.clear()
            # Fix the wrapped value height at the card's actual inner width;
            # Qt's nested header layout can otherwise underestimate tall values.
            widget.ensurePolished()
            widget.setMinimumHeight(max(0,widget.heightForWidth(self.readout_container.card_width-14)))
        for container in self.readout_groups.values():container.refresh_height()
        value,unit=measurement(snapshot)
        scope=tuple(snapshot['config'].get(k) for k in ('id','family','assembly','version','address','register_profile'))
        if scope!=self.trend_scope:
            self.series.clear();self.display_trend.clear();self.last_sample=None;self.trend_scope=scope
        marker=(snapshot['last_success'],snapshot['quality'],value,retained)
        if marker!=self.last_sample:
            stamp=time.time()  # Display observation time; historian retains actual source timestamps.
            self.series.append((stamp,float(value) if value is not None else float('nan')));self.last_sample=marker
            self.display_trend.append(stamp,value,self.gauge.state.value if retained else None)
            solid,held=self.display_trend.curves()
            for curve in (self.overview_curve,self.trend_curve):curve.setData(*solid)
            for curve in (self.overview_held_curve,self.trend_held_curve):curve.setData(*held)
        note=f"Numeric reading missing since {datetime.fromtimestamp(self.blank_started_wall).strftime('%H:%M:%S')} | Last value held; not logged as new data" if retained else 'Solid: measured | Dashed amber: held while LCD is nonnumeric (display only)'
        for label in (self.overview_hold_note,self.trend_hold_note):label.setText(note)
        if retained:unit=self.gauge.state.unit
        self.overview_plot.setLabel('left','Measurement',units=unit if value is not None else '')
        self.trend_plot.setLabel('left','Measurement',units=unit if value is not None else '')
        stats=diagnostics['bus'];rate=stats['success_rate']
        self.diagnostics_summary.setText(f"Single bus | {diagnostics['baud']} baud / 8N1 | Polls {stats['polls']} | Success {rate if rate is not None else '--'}% | Timeouts {stats['timeouts']} | CRC {stats['crc_errors']} | Protocol {stats['protocol_errors']}\nLast reply {stats['last_response']} | {stats['last_response_ms']:.2f} ms")
        fill_table(self.traffic,[(r['time'],r['direction'],r['address'],r['register'],r['hex']) for r in diagnostics['traffic'][-100:]])
        self.update_command_buttons();self.received.emit()
        if self.navigation.currentRow()==6:self.refresh_profile_settings()
        if snapshot.get('control',{}).get('receipt'):self.show_command_receipt(snapshot['control']['receipt'])

    def set_connection_status(self,connected):
        if getattr(self,'connection_established',None)==connected:return
        self.connection_established=connected
        self.monitor_status.setText('Connection Status: ● '+('Connection Established' if connected else 'No Connection'))
        self.monitor_status.setStyleSheet('color:'+('#39c66c' if connected else '#f27778')+';font-size:16px;font-weight:bold;')

    def refresh_connection_status(self):
        snapshot=self.snapshot
        connected=bool(snapshot and snapshot['quality']=='GOOD' and snapshot.get('last_success') and
                       snapshot.get('age',0) is not None and snapshot.get('age',0)+time.monotonic()-self.snapshot_received_at <= max(5,snapshot['config']['interval']*3))
        self.set_connection_status(connected)
        if not connected and self.readout_retained:
            self.readout_retained=False
            for label in (self.overview_hold_note,self.trend_hold_note):label.setText('No current communication; held display ended')

    def show_command_receipt(self,receipt):
        key=(receipt.get('id') or receipt.get('time'),receipt['code'],receipt.get('reply_received'),receipt['state'])
        if key!=self.last_receipt_key:
            previous=self.last_receipt_key
            self.last_receipt_key=key
            button=self.command_buttons.get(receipt['code'])
            if button and receipt.get('reply_received') and (previous is None or previous[:3]!=key[:3]):button.feedback(True)
            elif button and receipt['state'] in ('UNKNOWN','REJECTED') and not receipt.get('reply_received'):button.feedback(False)
        state=receipt['state'];color='#efb753'
        title={'CHECKING':'Checking target','SENDING':'Command sent; waiting for reply','PENDING':'Acknowledged — monitoring STATUS','VERIFYING_LOCK':'Acknowledged — verifying CAL LOCK [60]','WAITING_STATUS':'Waiting for execution evidence','STARTED':'Execution sequence observed','COMPLETED_OBSERVED':'STATUS sequence ended','CONTROLLER_REPLIED':'Controller replied','STATE_CHANGED':'Controller replied — state changed','NO_STATE_CHANGE':'Controller replied — state unchanged','UNKNOWN':'Outcome unknown — do not retry','REJECTED':'Command not sent'}.get(state,state)
        if state in ('STATE_CHANGED','COMPLETED_SIMULATED','COMPLETED_OBSERVED','VERIFIED'):color='#39c6a4'
        elif state in ('CONTROLLER_REPLIED','NO_STATE_CHANGE'):color='#69a7ed'
        elif state in ('UNKNOWN','REJECTED','FAILED'):color='#f27778'
        lines=[title,COMMANDS.get(receipt['code'],f"0x{receipt['code']:04X}"),f"Reply received: {'YES' if receipt.get('reply_received') else 'NO'}"]
        before=receipt.get('before');after=receipt.get('after')
        if before and after:
            lines.extend([f"STATUS: {before['status']} → {after['status']}",f"RELAYS: {before['relays']:04X} → {after['relays']:04X}",f"SERVICE: {before['service']:04X} → {after['service']:04X}",'Reply confirms receipt; execution is not proven by acknowledgment alone.'])
        if receipt.get('detail'):lines.append(receipt['detail'])
        if 'before_status' in receipt:lines.append(f"STATUS before: {receipt['before_status']}")
        if 'status_after' in receipt:lines.append(f"Observed STATUS: {receipt['status_after']}")
        if receipt.get('reply_received'):lines.append('Green LED = Modbus acknowledgment only. Execution is tracked separately in the command audit.')
        if receipt.get('time'):lines.append(receipt['time'])
        self.command_proof.setText('\n'.join(lines));self.command_proof.setStyleSheet(f'QLabel {{padding:8px;border:1px solid {color};border-radius:5px;color:{color};}}')

    def command_bench_target_matches(self):
        if self.settings['mode']!='hardware' or not self.snapshot or self.snapshot['quality']!='GOOD':return False
        if not self.worker or not self.worker.isRunning() or self.worker.test_only:return False
        from prevex_hmi.communication.hardware_session import ReadOnlyControllerGrant
        from prevex_hmi.devices.identification import Identification
        try:
            grant=ReadOnlyControllerGrant()
            grant.validate(self.settings,DeviceConfig(**self.snapshot['config']))
            grant.validate_identity(Identification(**{key:self.identity[key] for key in Identification.__dataclass_fields__ if key in self.identity}))
            return self.settings['analyzer_selection'] in ('Auto Detect','LEL','LEL 670 Series')
        except (ValueError,PermissionError,KeyError):return False

    def activate_command_bench(self):
        _,role=self.users.resolve(self.session)
        control=self.snapshot.get('control',{}) if self.snapshot else {}
        if role not in ('Operator','Administrator') or not self.command_bench_target_matches() or control.get('pending') or control.get('ambiguous'):
            self.update_command_buttons();return
        # Separate explicit bench action; normal Connect/sign-in stay read-only.
        # Reconnection rechecks identity and sends no operational command.
        self.start_controller_bench()

    def update_command_buttons(self):
        if hasattr(self.users,'session_info'):
            account=self.users.session_info(self.session)
            if self.session and not account:self.session='';self.login_button.setText('Sign in / create account')
            self.account_button.setEnabled(bool(account))
            self.account_button.setText('Password change required' if account and account['must_change'] else 'Account / users' if account and account['role']=='Administrator' else 'My account')
        name,role=self.users.resolve(self.session);self.role_label.setText(f'{name} / {role}')
        snapshot=self.snapshot;control=snapshot.get('control',{}) if snapshot else {}
        bench=bool(self.hardware_grant and self.hardware_grant.operator_commands and self.settings['mode']=='hardware')
        physical=self.settings['mode']=='hardware'
        documented=set(control.get('physical_commands',[])) if physical else set()
        if documented:self.banner.setText(f'LIVE HARDWARE | Documented commands require individual confirmation | {self.settings["connection"]["port"]}')
        current=bool(snapshot and snapshot['quality']=='GOOD' and self.worker and self.worker.isRunning())
        self.command_access_button.setVisible(physical and not bench and not documented)
        self.command_access_button.setEnabled(bool(current and role in ('Operator','Administrator') and self.command_bench_target_matches() and not control.get('pending') and not control.get('ambiguous')))
        if not current:reason='Commands unavailable: no current connection.'
        elif role not in ('Operator','Administrator'):reason='Sign in as Operator or Administrator. Viewer accounts cannot use commands.'
        elif physical and not bench and not documented:
            reason='Read-only connection. Use Enable Acknowledge / Reset for the approved SNR671 bench session.' if self.command_bench_target_matches() else 'Read-only: operating commands are unverified for this firmware/profile.'
        elif control.get('pending'):reason='Verifying software lock through CAL LOCK [60].' if control.get('pending_kind')=='lock' else 'Command pending; waiting for STATUS evidence.'
        elif control.get('ambiguous'):reason='Command outcome unknown. Review state and reconnect; do not retry.'
        elif not control.get('verified'):reason='Commands unavailable: identity or selected profile is unresolved.'
        elif physical and documented:reason='Documented670 operating commands available. Each requires target confirmation. Save All requires Administrator.'
        elif physical:reason='Acknowledge and Reset available. Other commands need applicable firmware documentation.'
        else:reason='Simulator controls. Each command requires target confirmation.'
        if physical and snapshot and snapshot['config'].get('register_profile')=='fta_4x':
            reason+='\nFirmware4.81 uses the 5.12 register/command map by user instruction; hardware compatibility remains unverified.'
        self.command_access_note.setText(reason)
        enabled=bool(snapshot and snapshot['quality']=='GOOD' and control.get('verified') and not control.get('pending') and not control.get('ambiguous') and role in ('Operator','Administrator') and not self.command_dispatching and self.worker and self.worker.isRunning() and (self.settings['mode']=='simulation' or bench or documented))
        active_config=DeviceConfig(**snapshot["config"]) if snapshot else self.config
        profile=profile_for(active_config)
        lock= snapshot['raw'].get(60) if snapshot else None
        elapsed=max(0,time.monotonic()-self.snapshot_received_at) if self.snapshot_received_at else 0
        lock_current=bool(current and snapshot.get('register_ages',{}).get(60,0)+elapsed<=max(5,active_config.interval*3) and type(lock) is int and lock in (0,1,2,3))
        legacy_lock=profile.revision!='700' and 60 in profile.registers
        self.lock_command_code=(0x1000 if lock&2 else 0xF00) if lock_current and legacy_lock else None
        self.hardware_lock_label.setText(('Hardware lock: LOCKED' if lock&1 else 'Hardware lock: unlocked') if lock_current and legacy_lock else '700 lock state: see Security [27]' if profile.revision=='700' else 'Hardware lock: unknown')
        self.hardware_lock_label.setStyleSheet('color:'+('#efb753' if lock_current and legacy_lock and lock&1 else '#adbbcf'))
        for code,button in self.command_buttons.items():
            if code==0x1000:continue
            if code==0xF00:
                button.set_lock_action(bool(lock&2) if lock_current and legacy_lock else None)
                code=self.lock_command_code or 0xF00
            physical=self.settings['mode']=='hardware'
            button.setVisible(True)
            active_config=DeviceConfig(**snapshot["config"]) if snapshot else self.config
            allow=enabled and code in (documented if documented else (0x100,0x200) if bench else commands_for(active_config))
            if code in (0xF00,0x1000):allow=allow and self.lock_command_code is not None
            if physical and code==0x900 and role!='Administrator':allow=False
            if physical and documented and code==0x900 and snapshot and snapshot['raw'].get(60)!=0:allow=False
            if physical and documented and snapshot and snapshot['raw'].get(2) in (4,5,6,7,11,12) and code not in (0x100,0x200):allow=False
            if snapshot and code in range(0x300,0x900,0x100):
                lock_register=27 if profile_for(active_config).revision=='700' else 60
                allow=allow and lock_register in snapshot['raw'] and not snapshot['raw'][lock_register]&(1 if lock_register==27 else 3) and snapshot['raw'].get(2) not in (4,5,6,7,11,12)
            button.setEnabled(bool(allow));button.setToolTip('Verified simulator identity, current communication and Operator/Administrator session required')
            if code not in commands_for(active_config):button.setToolTip('Legacy firmware command behavior is unverified.' if profile_for(active_config).revision=='fta_4x' else '700-series Rev D: Lock/Unlock have no effect over Modbus; Save Settings permits factory changes. Not available in operational controls.' if profile_for(active_config).revision=='700' else 'Not supported by the selected profile.')
            if physical:button.setToolTip(('Real controller:670 Rev Q p90. Operator/Administrator login and explicit confirmation required.' if bench else 'Start the explicitly authorized command bench session to test Acknowledge/Reset.') if code in (0x100,0x200) else 'Unavailable for the current physical firmware/profile; see the command-readiness explanation above.')
            if physical and code in documented:button.setToolTip('Documented670 command. Fresh identity/status/lock checks, target confirmation and audit required. Save All: Administrator only.')
        if control.get('pending'):self.command_message.setText('Verifying software lock: waiting for CAL LOCK [60] readback. Command sent once; duplicate commands disabled.' if control.get('pending_kind')=='lock' else 'Command pending: waiting for STATUS evidence. Duplicate commands disabled.')
        elif control.get('ambiguous'):self.command_message.setText('Unknown command outcome. No retry; reconnect and review state.')
        elif self.settings['mode']=='hardware':self.command_message.setText('Documented commands require individual confirmation; write acknowledgment does not prove execution.' if documented else 'Real controller: sign in as Operator/Administrator to test Acknowledge or Reset. Each action requires confirmation.' if bench else 'Read-only controller test. No commands enabled in this session.')

    def send_command(self,code):
        if code not in COMMANDS or not self.command_buttons[code].isEnabled():return
        if code in (0xF00,0x1000) and code!=self.lock_command_code:return
        config=self.snapshot['config']
        physical=self.settings['mode']=='hardware'
        effects=({0x100:'Can silence horn/service indications.',0x200:'Can clear alarms and initiate ignition after Flameout.',0x300:'Uses zero gas and changes zero calibration.',0x400:'Uses span gas and changes span calibration.',0x500:'Uses zero/span gases and changes calibration.',0x600:'Activates zero-gas test.',0x700:'Activates span-gas test.',0x800:'Activates zero/span gas tests.',0x900:'PERSISTENT CHANGE: saves settings to EEPROM. A reply cannot prove persistence.',0xF00:'Sets software calibration lock.',0x1000:'Clears software calibration lock; does not bypass hardware lock.'}.get(code,'')) if physical else ''
        if physical and config.get('version')=='4.81':
            effects+='\nFirmware4.81: using the 5.12 register/command map by your instruction; physical compatibility remains unverified.'
        if physical and code in range(0x300,0x900,0x100) and self.snapshot['raw'].get(2) not in (0,1,2):
            active=DeviceConfig(**config);status=self.snapshot['raw'].get(2)
            effects+=f'\nCurrent STATUS {status}: {profile_for(active).status(status)}. Command may operate gas valves/change calibration while this condition remains.'
        answer=QMessageBox.question(self,'Confirm analyzer command',f"Target: {config['name']} / {config['family']} / address {config['address']}\n{COMMANDS[code]} (0x{code:04X})\n{effects}\nExecute this {'REAL CONTROLLER' if physical else 'simulated'} command once?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return
        self.update_command_buttons()
        if not self.command_buttons[code].isEnabled() or code in (0xF00,0x1000) and code!=self.lock_command_code:
            self.statusBar().showMessage('Command state changed during confirmation; review the current lock/connection and confirm again.');return
        self.active_command=code
        self.command_dispatching=True;self.update_command_buttons();self.request('command',code,self.session,True)
        self.show_command_receipt({'code':code,'state':'SENDING','reply_received':False})

    def parameter_access_reason(self,key):
        from prevex_hmi.profiles.parameters import PARAMETERS,supported
        snapshot=self.snapshot
        if not snapshot or not self.worker or not self.worker.isRunning():return 'Connect to an analyzer before adjusting a parameter.'
        config=DeviceConfig(**snapshot['config'])
        if not supported(config):return 'Adjustments are unverified for this profile.'
        if self.settings['mode']!='simulation':return 'Physical setting adjustments are disabled pending explicit authorization. No change will be sent.'
        if self.users.resolve(self.session)[1]!='Administrator':return 'Sign in as Administrator to adjust settings.'
        control=snapshot.get('control',{})
        if not control.get('verified') or control.get('pending') or control.get('ambiguous') or self.command_dispatching:return 'Identity unresolved or an action is pending/unknown.'
        elapsed=max(0,time.monotonic()-self.snapshot_received_at)
        limit=max(5,config.interval*3)
        required=(2,60,PARAMETERS[key][0])+((5,6) if key in ('warning','danger') else ())
        if snapshot['quality']!='GOOD' or snapshot.get('age') is None or snapshot['age']+elapsed>limit:return 'Communication is not current.'
        if any(n not in snapshot['raw'] or snapshot.get('register_ages',{}).get(n,float('inf'))+elapsed>limit for n in required):return 'Wait for fresh parameter, STATUS and lock values.'
        if snapshot['raw'][60]!=0:return 'Calibration lock is active or unverified.'
        if snapshot['raw'][2] not in profile_for(config).statuses or snapshot['raw'][2] in (4,5,6,7,11,12):return 'Instrument is busy/warming up or STATUS is unknown.'
        return ''

    def edit_parameter(self,key):
        from prevex_hmi.gui.parameter_editor import ParameterEditor
        from prevex_hmi.profiles.parameters import PARAMETERS,encode
        if not self.snapshot:return
        config=DeviceConfig(**self.snapshot['config']);number,title=PARAMETERS[key]
        raw=self.snapshot['raw'].get(number)
        if raw is None:
            self.statusBar().showMessage('Parameter has not been read yet.');return
        target=copy.deepcopy(self.snapshot['config'])
        dialog=ParameterEditor(config,key,raw,reason=self.parameter_access_reason(key),parent=self)
        if dialog.exec()!=QDialog.Accepted:return
        value=dialog.proposed()
        try:new_raw=encode(config,key,value,previous=raw)
        except (ValueError,PermissionError) as error:QMessageBox.warning(self,'Invalid value',str(error));return
        old_value,unit=profile_for(config).register(number).decode(raw,config.family,config.context)
        new_value,_=profile_for(config).register(number).decode(new_raw,config.family,config.context)
        if new_raw==raw:self.statusBar().showMessage('Value is unchanged.');return
        status=self.snapshot['raw'].get(2)
        answer=QMessageBox.question(self,'Confirm parameter adjustment',f'Target: {config.name} / {config.assembly} / address {config.address}\n{title} [{number}]: {old_value} → {new_value} {unit}\nSTATUS {status}: {profile_for(config).status(status)}\nApply this simulated change once? Readback will be verified.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return
        reason=self.parameter_access_reason(key)
        if reason or not self.snapshot or self.snapshot['config']!=target or self.snapshot['raw'].get(number)!=raw:
            self.statusBar().showMessage(reason or 'Target or value changed; reopen the editor and confirm again.');return
        self.command_dispatching=True;self.update_command_buttons()
        self.command_message.setText(f'Adjusting {title}; waiting for readback…')
        self.request('parameter',key,value,raw,self.session,True)

    def parameter_feedback(self,text):
        self.command_proof.setText(text);self.command_feedback(text)

    def command_feedback(self,text):
        if self.active_command is not None and not self.snapshot.get('control',{}).get('receipt') and ('rejected' in text.lower() or 'not sent' in text.lower()):self.command_buttons[self.active_command].feedback(False)
        self.command_dispatching=False;self.command_message.setText(text);self.statusBar().showMessage(text);self.update_command_buttons()

    def request(self,*message):
        if self.worker and self.worker.isRunning() and not self.worker.test_only:self.worker.request(*message)

    def choose_type(self):
        dialog=AnalyzerChoice(self.settings,self)
        if dialog.exec()!=QDialog.Accepted:return
        settings=dialog.settings()
        try:save_settings(self.settings_path,settings)
        except (OSError,ValueError) as error:QMessageBox.warning(self,'Save failed',str(error));return
        # Stop and invalidate immediately; new profile starts only after old worker closes.
        self.settings=settings;self.refresh_connection_labels();self.begin('connect')

    def login(self):
        if self.session:
            self.users.logout(self.session);self.session='';self.login_button.setText('Sign in');self.update_command_buttons();return
        dialog=LoginDialog(self.users,self)
        if dialog.exec()==QDialog.Accepted:
            self.session=dialog.token;self.login_button.setText('Sign out');self.update_command_buttons()
            info=self.users.session_info(self.session)
            if info and info['must_change']:self.manage_account()

    def manage_account(self):
        from prevex_hmi.gui.accounts import AccountsDialog
        if not self.users.session_info(self.session):
            self.update_command_buttons();QMessageBox.information(self,'Sign in required','Sign in before opening account settings.');return
        try:AccountsDialog(self.users,self.session,self).exec()
        except PermissionError as error:QMessageBox.warning(self,'Account unavailable',str(error))
        info=self.users.session_info(self.session)
        if info and info['must_change']:self.users.logout(self.session)
        self.update_command_buttons()

    def load_history(self):self.request('history',self.history_hours.currentData())

    def update_history(self,rows):
        self.history_rows=rows;fill_table(self.history_table,rows)
        self.history_curve.setData([datetime.fromisoformat(r[0]).timestamp() for r in rows],[r[1] if r[1] is not None else float('nan') for r in rows])

    def export_history(self):
        if not self.history_rows:QMessageBox.information(self,'History','Load history before exporting.');return
        path,_=QFileDialog.getSaveFileName(self,'Export history',str(self.data_path/'history.csv'),'CSV (*.csv)')
        if path:
            try:
                with open(path,'w',newline='',encoding='utf-8-sig') as stream:
                    writer=csv.writer(stream);writer.writerow(['instrument','timestamp_utc','value','unit','quality','status']);writer.writerows([(self.config.id,*r) for r in self.history_rows])
            except OSError as error:QMessageBox.warning(self,'Export failed',str(error))

    def worker_error(self,text):
        if self.test_in_progress:self.test_result_error=text
        self.invalidate('OFFLINE');self.warning.setText(text);self.warning.setVisible(not self.test_view_active);self.statusBar().showMessage(text)

    def apply_theme(self):
        dark=self.settings.get('theme','dark')=='dark';self.gauge.dark=dark;self.gauge.update()
        bg,panel,text=('#0d1625','#182538','#e7edf7') if dark else ('#eef3f8','#ffffff','#172335')
        self.setStyleSheet(f"""QWidget {{background:{bg};color:{text};font-family:'Segoe UI';font-size:13px;}}
        QLabel#brand {{font-size:24px;font-weight:bold;}} QLabel#heading {{font-size:23px;font-weight:600;}}
        QLabel#digitalValue {{font-size:21px;font-weight:600;}} QLabel#banner {{background:#e7b55e;color:#251c10;padding:9px;font-weight:bold;}}
        QLabel#warning {{background:#763d2e;color:#ffe3c2;padding:9px;}}
        QFrame#panel,QFrame#readout,QFrame#indicatorPanel {{background:{panel};border:1px solid #40516a;border-radius:7px;}}
        QFrame#readout QLabel,QFrame#panel QLabel {{background:transparent;}}
        QPushButton,QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox {{background:{panel};border:1px solid #526780;border-radius:5px;padding:7px;}}
        QPushButton:hover {{border-color:#44cab0;}} QPushButton:disabled {{color:#7f8ba0;border-color:#36435a;}}
        QPushButton#industrialCommand {{color:#f1f5fa;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #52647a,stop:1 #283648);border-top:2px solid #8291a4;border-left:2px solid #697c93;border-right:2px solid #121e2b;border-bottom:3px solid #0b1624;border-radius:6px;font-weight:bold;}}
        QPushButton#industrialCommand:pressed {{background:#233244;border-top:3px solid #101c29;border-left:2px solid #101c29;border-bottom:1px solid #667991;padding-top:9px;}}
        QPushButton#industrialCommand:disabled {{color:#788595;background:#26313f;border:1px solid #3c4859;}}
        QListWidget,QTableWidget {{background:{panel};alternate-background-color:{bg};border:0;}}
        QListWidget::item {{padding:14px 8px;}} QListWidget::item:selected {{background:#245a69;color:white;}}
        QHeaderView::section {{background:{panel};color:{text};padding:7px;border:0;}} QScrollArea {{border:0;}}
        """)

    def toggle_theme(self):
        self.settings['theme']='light' if self.settings.get('theme','dark')=='dark' else 'dark'
        try:save_settings(self.settings_path,self.settings)
        except OSError as error:self.statusBar().showMessage(str(error))
        self.apply_theme()

    def closeEvent(self,event):
        self.closing=True;self.next_action=None
        self.account_watch.stop();self.connection_watch.stop()
        if self.worker and self.worker.isRunning():
            self.closing=True;self.worker.stop();self.setEnabled(False);event.ignore()
        else:
            self.users.close();event.accept()
