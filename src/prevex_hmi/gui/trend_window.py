"""Independent plot window. Recording is owned by the main application."""
from datetime import datetime,timezone
import json
from pathlib import Path
from PySide6.QtCore import Qt,QDateTime,QByteArray,QTimeZone
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,
    QLabel,QComboBox,QCheckBox,QTabWidget,QFileDialog,QMessageBox,QDateTimeEdit)
import pyqtgraph as pg
from prevex_hmi.logging_db.recordings import sessions,history_series,export_csv


class TrendWindow(QMainWindow):
    def __init__(self,owner):
        super().__init__(owner,Qt.Window|Qt.WindowMinMaxButtonsHint|Qt.WindowCloseButtonHint)
        self.owner=owner;self.setWindowTitle('PREVEX HMI — Trend');self.resize(1100,740);self.setMinimumSize(680,480)
        self.geometry_path=owner.data_path/'trend-window.json';self.restored=False
        central=QWidget();box=QVBoxLayout(central);self.setCentralWidget(central)
        row=QHBoxLayout()
        self.mode=QComboBox();self.mode.addItem('Manual','manual');self.mode.addItem('Automatic','automatic');row.addWidget(self.mode)
        self.interval=QComboBox()
        for n in (1,2,5,10):self.interval.addItem(f'{n} second'+('s' if n!=1 else ''),n)
        row.addWidget(self.interval)
        self.main_only=QCheckBox('Main measurement and status only');row.addWidget(self.main_only)
        options=owner.settings.get('recording',{})
        self.mode.setCurrentIndex(max(0,self.mode.findData(options.get('mode','manual'))));self.interval.setCurrentIndex(max(0,self.interval.findData(options.get('interval',1))));self.main_only.setChecked(options.get('main_only',False))
        row.addStretch();box.addLayout(row)
        row=QHBoxLayout();self.start_button=QPushButton('Start Recording');self.stop_button=QPushButton('Stop Recording');self.export_button=QPushButton('Export CSV')
        self.start_button.clicked.connect(lambda:owner.recording_worker.request('start'))
        self.stop_button.clicked.connect(lambda:owner.recording_worker.request('stop'))
        self.export_button.clicked.connect(self.export)
        for w in (self.start_button,self.stop_button,self.export_button):row.addWidget(w)
        self.recording_status=QLabel('Stopped | Elapsed 00:00:00');self.recording_status.setWordWrap(True);row.addWidget(self.recording_status,1);box.addLayout(row)
        self.notice=QLabel('Closing Trend does not stop recording. Intervals limit capture; new values follow the analyzer polling cadence.');self.notice.setWordWrap(True);box.addWidget(self.notice)
        self.tabs=QTabWidget();box.addWidget(self.tabs,1)
        live=QWidget();layout=QVBoxLayout(live);self.live_plot=owner.make_plot()
        self.live_curve=self.live_plot.plot(pen=pg.mkPen('#45cbb0',width=2),connect='finite')
        self.held_curve=self.live_plot.plot(pen=pg.mkPen('#e7b55e',width=2,style=Qt.DashLine),connect='finite');layout.addWidget(self.live_plot)
        self.hold_note=QLabel('Solid: measured | Dashed amber: held display only; never recorded as new data');self.hold_note.setWordWrap(True);layout.addWidget(self.hold_note);self.tabs.addTab(live,'Live trend')
        self.build_sessions()
        self.mode.currentIndexChanged.connect(self.options_changed);self.interval.currentIndexChanged.connect(self.options_changed);self.main_only.toggled.connect(self.options_changed)

    @property
    def paths(self):return [self.owner.data_path/'simulation.sqlite3',self.owner.data_path/'hardware.sqlite3']

    def build_sessions(self):
        page=QWidget();box=QVBoxLayout(page);row=QHBoxLayout()
        self.session_choice=QComboBox();self.session_choice.setMinimumContentsLength(26);self.session_choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);row.addWidget(self.session_choice,1)
        refresh=QPushButton('Refresh sessions');refresh.clicked.connect(self.refresh_sessions);row.addWidget(refresh)
        self.parameter_choice=QComboBox();self.parameter_choice.setMinimumContentsLength(10);self.parameter_choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);row.addWidget(self.parameter_choice)
        load=QPushButton('View recording');load.clicked.connect(self.load_session);row.addWidget(load);box.addLayout(row)
        self.session_note=QLabel('Select a recording session. Incomplete sessions remain available after an unexpected shutdown.');self.session_note.setWordWrap(True);box.addWidget(self.session_note)
        self.recorded_plot=self.owner.make_plot();self.recorded_curve=self.recorded_plot.plot(pen=pg.mkPen('#69a7ed',width=2),connect='finite');box.addWidget(self.recorded_plot,1)
        self.session_choice.currentIndexChanged.connect(self.session_selected)
        self.parameter_choice.currentIndexChanged.connect(self.invalidate_history)
        row=QHBoxLayout();row.addWidget(QLabel('Export scope'))
        self.export_scope=QComboBox();self.export_scope.addItems(['Current recording session','Selected previous session','Date/time range (all sessions)']);row.addWidget(self.export_scope)
        row.addStretch();box.addLayout(row);row=QHBoxLayout()
        self.range_start=QDateTimeEdit(QDateTime.currentDateTimeUtc().addDays(-1));self.range_end=QDateTimeEdit(QDateTime.currentDateTimeUtc())
        for w in (self.range_start,self.range_end):w.setTimeZone(QTimeZone.utc());w.setDisplayFormat('yyyy-MM-dd HH:mm:ss');w.setCalendarPopup(True)
        row.addWidget(QLabel('Capture time UTC from'));row.addWidget(self.range_start);row.addWidget(QLabel('to'));row.addWidget(self.range_end);row.addStretch();box.addLayout(row)
        self.tabs.addTab(page,'Recorded sessions')

    def options_changed(self):
        options=dict(mode=self.mode.currentData(),interval=self.interval.currentData(),main_only=self.main_only.isChecked())
        self.owner.recording_worker.request('options',options['mode'],options['interval'],options['main_only'])
        self.owner.settings['recording']=options
        from prevex_hmi.devices.configuration import save_settings
        try:save_settings(self.owner.settings_path,self.owner.settings)
        except (OSError,ValueError) as error:self.notice.setText(f'Options apply for this run; saving preferences failed: {error}')

    def update_status(self,status):
        elapsed=int(status['elapsed']);hours,rest=divmod(elapsed,3600);minutes,seconds=divmod(rest,60)
        self.recording_status.setText(f"{status['state']} | Elapsed {hours:02}:{minutes:02}:{seconds:02} | {status['samples']} captured frames")
        self.stop_button.setEnabled(bool(status['session'] or status['armed']))
        self.start_button.setEnabled(not status['session'] and not status['armed'])
        if status['error']:self.notice.setText(status['error'])
        if getattr(self,'last_session',None)!=status['session']:
            self.last_session=status['session'];self.refresh_sessions()

    def refresh_sessions(self):
        self.session_generation=getattr(self,'session_generation',0)+1;generation=self.session_generation
        self.owner.record_job(lambda:sessions(self.paths),lambda rows:self.show_sessions(rows) if generation==self.session_generation else None)

    def show_sessions(self,rows):
        previous=self.session_choice.currentData();previous=previous.get('id') if previous else None
        self.session_choice.blockSignals(True);self.session_choice.clear()
        for row in rows:
            config=json.loads(row['config']);label=f"{row['started_at']} | {row['profile']} / {config['assembly']} | {row['source']} | {row['interval_seconds']}s"
            if not row['ended_at']:label+=' | active / unfinished'
            self.session_choice.addItem(label,row)
        index=next((i for i,row in enumerate(rows) if row['id']==previous),0)
        self.session_choice.setCurrentIndex(index if rows else -1);self.session_choice.blockSignals(False)
        if not rows or rows[index]['id']!=previous:self.session_selected()

    def invalidate_history(self,*args):
        self.history_request=None;self.recorded_curve.setData([],[])

    def session_selected(self):
        self.invalidate_history()
        row=self.session_choice.currentData();self.parameter_choice.clear()
        self.recorded_curve.setData([],[])
        if row:
            for p in json.loads(row['parameters']):self.parameter_choice.addItem(f"{p['name']} [{p['number']}] {p['unit']}",p['number'])
            self.session_note.setText(f"Started {row['started_at']} | End: {row['ended_at'] or 'Active or interrupted'} | {row['end_reason'] or ''}")

    def load_session(self):
        row=self.session_choice.currentData();number=self.parameter_choice.currentData()
        if not row or number is None:return
        requested=(row['id'],number);self.history_request=requested
        def loaded(data):
            if getattr(self,'history_request',None)!=requested:return
            points=data['points'];self.recorded_curve.setData([datetime.fromisoformat(t).timestamp() for t,v in points],[v if v is not None else float('nan') for t,v in points],connect='finite')
            self.recorded_plot.setLabel('left',data['name'],units=data['unit']);self.recorded_plot.enableAutoRange()
            self.session_note.setText(f"{len(points)} observations"+(' — display limited to first 50,000; CSV exports all observations' if data['limited'] else ''))
        self.owner.record_job(lambda:history_series(self.paths,row['id'],number),loaded)

    def export(self):
        scope=self.export_scope.currentIndex();selection=self.session_choice.currentData()
        session=self.owner.recording_status.get('session') if scope==0 else selection['id'] if scope==1 and selection else None
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
        try:
            temporary=self.geometry_path.with_suffix('.tmp');temporary.write_text(json.dumps({'geometry':bytes(self.saveGeometry().toBase64()).decode('ascii')}),encoding='utf-8');temporary.replace(self.geometry_path)
        except OSError as error:self.owner.statusBar().showMessage(f'Trend geometry could not be saved: {error}')
        event.accept()
