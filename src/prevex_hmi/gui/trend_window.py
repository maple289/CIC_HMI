"""Independent plot window. Recording is owned by the main application."""
from datetime import datetime,timezone
import json
from pathlib import Path
from PySide6.QtCore import Qt,QDateTime,QByteArray,QTimeZone
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,
    QLabel,QComboBox,QCheckBox,QTabWidget,QFileDialog,QMessageBox,QDateTimeEdit)
import pyqtgraph as pg
from prevex_hmi.logging_db.recordings import sessions,history_series,export_csv,normalize_selections
from prevex_hmi.gui.recording_parameters import RecordingParameters
from prevex_hmi.gui.history_view import HistoricalParameters,HistoricalPlots,LocalTimeAxis,display_zone,friendly_time,session_label


class TrendWindow(QMainWindow):
    def __init__(self,owner):
        super().__init__(owner,Qt.Window|Qt.WindowMinMaxButtonsHint|Qt.WindowCloseButtonHint)
        self.owner=owner;self.setWindowTitle('PREVEX HMI — Trend');self.resize(1100,740);self.setMinimumSize(680,480)
        self.geometry_path=owner.data_path/'trend-window.json';self.restored=False
        self.start_pending=False;self.stop_pending=False;self.pending_options=None;self.latest_recorded_session=None
        central=QWidget();box=QVBoxLayout(central);self.setCentralWidget(central)
        row=QHBoxLayout()
        self.mode=QComboBox();self.mode.addItem('Manual','manual');self.mode.addItem('Automatic','automatic');row.addWidget(self.mode)
        self.interval=QComboBox()
        for n in (1,2,5,10):self.interval.addItem(f'{n} second'+('s' if n!=1 else ''),n)
        row.addWidget(self.interval)
        options=owner.settings.get('recording',{})
        self.mode.setCurrentIndex(max(0,self.mode.findData(options.get('mode','manual'))));self.interval.setCurrentIndex(max(0,self.interval.findData(options.get('interval',1))))
        row.addStretch();row.addWidget(QLabel('Display timezone'))
        self.timezone_choice=QComboBox();self.timezone_choice.setMaximumWidth(240)
        self.timezone_choice.addItem('Windows local time','system');self.timezone_choice.addItem('UTC','UTC')
        for zone_id in QTimeZone.availableTimeZoneIds():
            key=bytes(zone_id).decode()
            if key!='UTC':self.timezone_choice.addItem(key,key)
        self.timezone_choice.setCurrentIndex(max(0,self.timezone_choice.findData(owner.settings.get('trend_timezone','system'))))
        row.addWidget(self.timezone_choice);box.addLayout(row)
        self.recording_parameters=RecordingParameters();box.addWidget(self.recording_parameters)
        self.recording_parameters.set_analyzer(owner.config,options.get('parameters_by_profile',{}))
        row=QHBoxLayout();self.start_button=QPushButton('Start Recording');self.stop_button=QPushButton('Stop Recording');self.export_button=QPushButton('Export CSV')
        self.start_button.clicked.connect(self.start_recording)
        self.stop_button.clicked.connect(self.stop_recording)
        self.export_button.clicked.connect(self.export)
        for w in (self.start_button,self.stop_button,self.export_button):row.addWidget(w)
        self.manage_button=QPushButton('Manage Recorded Data');self.manage_button.clicked.connect(self.manage_data);row.addWidget(self.manage_button)
        self.recording_status=QLabel('Stopped | Elapsed 00:00:00');self.recording_status.setWordWrap(True);row.addWidget(self.recording_status,1);box.addLayout(row)
        self.notice=QLabel('Closing Trend does not stop recording. Intervals limit capture; new values follow the analyzer polling cadence.');self.notice.setWordWrap(True);box.addWidget(self.notice)
        self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        live=QWidget();layout=QVBoxLayout(live);self.live_plot=owner.make_plot()
        self.live_curve=self.live_plot.plot(pen=pg.mkPen('#45cbb0',width=2),connect='finite')
        self.held_curve=self.live_plot.plot(pen=pg.mkPen('#e7b55e',width=2,style=Qt.DashLine),connect='finite');layout.addWidget(self.live_plot)
        self.hold_note=QLabel('Solid: measured | Dashed amber: held display only; never recorded as new data');self.hold_note.setWordWrap(True);layout.addWidget(self.hold_note);self.tabs.addTab(live,'Live trend')
        self.build_sessions()
        self.timezone_choice.currentIndexChanged.connect(self.timezone_changed)
        self.apply_timezone()
        self.mode.currentIndexChanged.connect(self.options_changed);self.interval.currentIndexChanged.connect(self.options_changed);self.recording_parameters.changed.connect(self.options_changed)
        owner.recording_worker.failed.connect(self.recording_request_failed)
        self.update_controls()

    @property
    def paths(self):return [self.owner.data_path/'simulation.sqlite3',self.owner.data_path/'hardware.sqlite3']

    def apply_theme(self,dark):
        from .theme import apply_palette,style_plot
        self.setStyleSheet(self.owner.styleSheet());apply_palette(self,dark)
        self.history_plots.set_theme(dark)
        for plot in self.findChildren(pg.PlotWidget):style_plot(plot,dark)

    def manage_data(self):
        from .recording_management import RecordingManagementWindow
        if not hasattr(self,'management_window'):self.management_window=RecordingManagementWindow(self)
        else:self.management_window.refresh()
        self.management_window.apply_theme();self.management_window.show();self.management_window.raise_();self.management_window.activateWindow()

    def build_sessions(self):
        page=QWidget();box=QVBoxLayout(page);row=QHBoxLayout()
        self.session_choice=QComboBox();self.session_choice.setMinimumContentsLength(26);self.session_choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);row.addWidget(self.session_choice,1)
        refresh=QPushButton('Refresh sessions');refresh.clicked.connect(self.refresh_sessions);row.addWidget(refresh)
        load=QPushButton('View recording');load.clicked.connect(self.load_session);row.addWidget(load);box.addLayout(row)
        self.history_parameters=HistoricalParameters();box.addWidget(self.history_parameters)
        self.session_note=QLabel('Select a recording session. Incomplete sessions remain available after an unexpected shutdown.');self.session_note.setWordWrap(True);box.addWidget(self.session_note)
        self.history_plots=HistoricalPlots();box.addWidget(self.history_plots,1);self.draw_history([])
        self.session_choice.currentIndexChanged.connect(self.session_selected)
        self.history_parameters.changed.connect(self.invalidate_history)
        row=QHBoxLayout();row.addWidget(QLabel('Export scope'))
        self.export_scope=QComboBox();self.export_scope.addItems(['Current / latest recording session','Selected previous session','Date/time range (all sessions)']);row.addWidget(self.export_scope)
        row.addStretch();box.addLayout(row);row=QHBoxLayout()
        self.range_start=QDateTimeEdit(QDateTime.currentDateTimeUtc().addDays(-1));self.range_end=QDateTimeEdit(QDateTime.currentDateTimeUtc())
        for w in (self.range_start,self.range_end):w.setDisplayFormat('yyyy-MM-dd HH:mm:ss ttt');w.setCalendarPopup(True)
        row.addWidget(QLabel('Capture time from'));row.addWidget(self.range_start);row.addWidget(QLabel('to'));row.addWidget(self.range_end);row.addStretch();box.addLayout(row)
        self.tabs.addTab(page,'Recorded sessions')

    def options_changed(self):
        if self.controls_locked():
            status=self.pending_options or self.owner.recording_status
            for combo,key in ((self.mode,'mode'),(self.interval,'interval')):
                combo.blockSignals(True);combo.setCurrentIndex(max(0,combo.findData(status.get(key,combo.currentData()))));combo.blockSignals(False)
            return
        options=self.current_options()
        self.owner.recording_worker.request('selection_options',options['mode'],options['interval'],options['parameters_by_profile'])
        self.owner.settings['recording']=options
        from prevex_hmi.devices.configuration import save_settings
        try:save_settings(self.owner.settings_path,self.owner.settings)
        except (OSError,ValueError) as error:self.notice.setText(f'Options apply for this run; saving preferences failed: {error}')
        self.update_controls()

    def current_options(self):
        selections=normalize_selections(self.owner.settings.get('recording',{}).get('parameters_by_profile',{}))
        selections[self.recording_parameters.profile]=self.recording_parameters.selected_numbers()
        return dict(mode=self.mode.currentData(),interval=self.interval.currentData(),parameters_by_profile=selections)

    def controls_locked(self):
        status=self.owner.recording_status
        return bool(self.start_pending or self.stop_pending or status.get('session') or status.get('armed'))

    def update_controls(self):
        locked=self.controls_locked();self.recording_parameters.set_locked(locked)
        connected=bool(self.owner.profile_current and getattr(self.owner,'connection_established',False))
        self.recording_parameters.setVisible(connected)
        self.interval.setEnabled(not locked);self.mode.setEnabled(not locked)
        self.start_button.setEnabled(connected and not locked and bool(self.recording_parameters.selected_numbers()))
        self.stop_button.setEnabled(bool(self.owner.recording_status.get('session') or self.owner.recording_status.get('armed')) and not self.stop_pending)

    def set_analyzer(self,config):
        self.recording_parameters.set_analyzer(config,self.owner.settings.get('recording',{}).get('parameters_by_profile',{}));self.update_controls()

    def start_recording(self):
        if not self.owner.profile_current or not getattr(self.owner,'connection_established',False):return
        if self.controls_locked() or not self.recording_parameters.selected_numbers():return
        options=self.current_options();self.pending_options=options;self.start_pending=True;self.update_controls()
        self.owner.recording_worker.request('start_selection',options['mode'],options['interval'],options['parameters_by_profile'],self.recording_parameters.profile)

    def stop_recording(self):
        self.stop_pending=True;self.update_controls();self.owner.recording_worker.request('stop')

    def recording_request_failed(self,error):
        self.start_pending=False;self.stop_pending=False;self.pending_options=None
        self.notice.setText(error);self.update_controls()

    def update_status(self,status):
        if status.get('session'):self.latest_recorded_session=status['session']
        if self.start_pending and (status.get('session') or status.get('armed') or status.get('error')):self.start_pending=False;self.pending_options=None
        if self.stop_pending and not status.get('session') and not status.get('armed'):self.stop_pending=False;self.start_pending=False;self.pending_options=None
        elapsed=int(status['elapsed']);hours,rest=divmod(elapsed,3600);minutes,seconds=divmod(rest,60)
        self.recording_status.setText(f"{status['state']} | Elapsed {hours:02}:{minutes:02}:{seconds:02} | {status['samples']} captured frames")
        self.update_controls()
        if status['error']:self.notice.setText(status['error'])
        if getattr(self,'last_session',None)!=status['session']:
            self.last_session=status['session'];self.refresh_sessions()

    def refresh_sessions(self):
        self.session_generation=getattr(self,'session_generation',0)+1;generation=self.session_generation
        self.owner.record_job(lambda:sessions(self.paths,summaries=True),lambda rows:self.show_sessions(rows) if generation==self.session_generation else None)

    def show_sessions(self,rows):
        rows=sorted(rows,key=lambda r:datetime.fromisoformat(r['started_at']).timestamp(),reverse=True)
        previous_row=self.session_choice.currentData();previous=previous_row.get('id') if previous_row else None
        self.session_choice.blockSignals(True);self.session_choice.clear()
        for row in rows:
            label=session_label(row,self.display_timezone);self.session_choice.addItem(label,row)
            self.session_choice.setItemData(self.session_choice.count()-1,label,Qt.ToolTipRole)
        index=next((i for i,row in enumerate(rows) if row['id']==previous),0)
        self.session_choice.setCurrentIndex(index if rows else -1);self.session_choice.blockSignals(False)
        if not rows or rows[index]['id']!=previous or rows[index].get('saved_parameters')!=previous_row.get('saved_parameters'):self.session_selected()

    def invalidate_history(self,*args):
        self.history_request=None;self.draw_history([])

    def session_selected(self):
        self.invalidate_history()
        row=self.session_choice.currentData()
        parameters=[p for p in json.loads(row['parameters']) if p['number'] in row.get('saved_parameters',[p['number'] for p in json.loads(row['parameters'])])] if row else []
        self.history_parameters.set_parameters(parameters)
        if row:
            self.session_note.setText(f"{session_label(row,self.display_timezone)} | End: {friendly_time(row['ended_at'],self.display_timezone)} | {row['end_reason'] or ''}")

    def load_session(self):
        row=self.session_choice.currentData();numbers=self.history_parameters.selected_numbers()
        if not row or not numbers:
            self.session_note.setText('Select at least one historical parameter.');return
        requested=(row['id'],tuple(numbers),object());self.history_request=requested
        def loaded(data):
            if getattr(self,'history_request',None)!=requested:return
            self.draw_history(data)
            count=sum(sum(v is not None for t,v in series['points']) for series in data)
            self.session_note.setText(f"{session_label(row,self.display_timezone)} | {count} parameter observations. Markers show saved points; lines require at least three consecutive observations. Gaps remain disconnected."+(' Display limited to first 50,000 per parameter; CSV exports all observations.' if any(s['limited'] for s in data) else ''))
        self.owner.record_job(lambda:[history_series(self.paths,row['id'],number) for number in numbers],loaded)

    @property
    def display_timezone(self):return display_zone(self.timezone_choice.currentData())

    def draw_history(self,data):
        self.history_plots.render(data,self.display_timezone)
        self.recorded_plot=self.history_plots.plots[0];self.recorded_curve=self.history_plots.curves[0]

    def apply_timezone(self):
        zone=self.display_timezone
        self.live_plot.setAxisItems({'bottom':LocalTimeAxis(zone)})
        self.live_plot.setLabel('bottom',f"Time ({bytes(zone.id()).decode()})")
        for editor in (self.range_start,self.range_end):
            instant=editor.dateTime();editor.setTimeZone(zone);editor.setDateTime(instant.toTimeZone(zone))
        self.draw_history(self.history_plots.data)
        rows=[self.session_choice.itemData(i) for i in range(self.session_choice.count())]
        self.show_sessions(rows)
        row=self.session_choice.currentData()
        if row:self.session_note.setText(f"{session_label(row,zone)} | End: {friendly_time(row['ended_at'],zone)} | {row['end_reason'] or ''}")

    def timezone_changed(self):
        self.apply_timezone();self.owner.settings['trend_timezone']=self.timezone_choice.currentData()
        from prevex_hmi.devices.configuration import save_settings
        try:save_settings(self.owner.settings_path,self.owner.settings)
        except (OSError,ValueError) as error:self.notice.setText(f'Timezone applies for this run; saving preference failed: {error}')

    def export(self):
        scope=self.export_scope.currentIndex();selection=self.session_choice.currentData()
        session=(self.owner.recording_status.get('session') or self.latest_recorded_session) if scope==0 else selection['id'] if scope==1 and selection else None
        if scope in (0,1) and not session:
            self.notice.setText('No session selected. Choose a previous session or a date/time range.');return
        start=end=None
        if scope==2:
            start=self.range_start.dateTime().toUTC().toPython().replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds')
            end=self.range_end.dateTime().toUTC().toPython().replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds')
            if start>end:self.notice.setText('Start must precede end.');return
        profile=(selection or {}).get('profile',self.owner.identity.get('loaded_profile','Analyzer')).replace(' ','').replace('Series','')
        suggested=f'PREVEX_{profile}_{datetime.now().strftime("%Y-%m-%d_%H%M%S")}.csv'
        path,_=QFileDialog.getSaveFileName(self,'Export recorded data',str(self.owner.data_path/suggested),'CSV (*.csv)')
        if not path:return
        self.export_button.setEnabled(False);self.notice.setText('Exporting SQLite observations… recording and monitoring continue.')
        def done(count):self.export_button.setEnabled(True);self.notice.setText(f'Exported {count} frames to {path}')
        def failed(error):self.export_button.setEnabled(True);self.notice.setText(f'CSV export failed: {error}')
        self.owner.record_job(lambda:export_csv(self.paths,path,session=session,start=start,end=end),done,failed)

    def open(self):
        if not self.restored:
            self.restored=True
            try:
                state=json.loads(self.geometry_path.read_text(encoding='utf-8'))
                self.restoreGeometry(QByteArray.fromBase64(state['geometry'].encode('ascii')))
            except (OSError,ValueError,KeyError):pass
        self.setStyleSheet(self.owner.styleSheet())
        if self.isMinimized():self.showNormal()
        self.show()
        if not any(self.frameGeometry().intersects(screen.availableGeometry()) for screen in QGuiApplication.screens()):
            self.move(QGuiApplication.primaryScreen().availableGeometry().center()-self.rect().center())
        self.raise_();self.activateWindow();self.refresh_sessions()

    def closeEvent(self,event):
        if hasattr(self,'management_window'):self.management_window.close()
        try:
            temporary=self.geometry_path.with_suffix('.tmp');temporary.write_text(json.dumps({'geometry':bytes(self.saveGeometry().toBase64()).decode('ascii')}),encoding='utf-8');temporary.replace(self.geometry_path)
        except OSError as error:self.owner.statusBar().showMessage(f'Trend geometry could not be saved: {error}')
        event.accept()
