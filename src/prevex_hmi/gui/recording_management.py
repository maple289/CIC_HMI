"""Non-modal recorded-data manager; database work uses existing job threads."""
from datetime import datetime,timezone
import json,sqlite3
from pathlib import Path
from PySide6.QtCore import Qt,QDateTime,QTimer,QItemSelectionModel
from PySide6.QtGui import QPalette,QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QComboBox,QPushButton,
    QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QDateTimeEdit,QFileDialog,QMessageBox,QGroupBox)
from prevex_hmi.logging_db.maintenance import RecordingManagement,PERIODS
from prevex_hmi.logging_db.recordings import export_csv
from .history_view import friendly_time


def size_text(value):
    for unit in ('B','KiB','MiB','GiB'):
        if value<1024 or unit=='GiB':return f'{value:.1f} {unit}'
        value/=1024


class RecordingManagementWindow(QDialog):
    def __init__(self,trend):
        super().__init__(trend,Qt.Window|Qt.WindowMinMaxButtonsHint|Qt.WindowCloseButtonHint)
        self.trend=trend;self.owner=trend.owner;self.service=self.owner.recording_management;self.busy=False;self.status_pending=False
        self.setWindowTitle('PREVEX HMI — Database Manager');self.resize(1160,900);self.setMinimumSize(820,700)
        box=QVBoxLayout(self);box.setSpacing(6)
        self.automatic_section=QGroupBox('Automatic Cleanup');automatic_box=QVBoxLayout(self.automatic_section);box.addWidget(self.automatic_section)
        row=QHBoxLayout();self.automatic=QCheckBox('Enable automatic cleanup');row.addWidget(self.automatic)
        row.addWidget(QLabel('Retention period'));self.days=QComboBox()
        for n in PERIODS:self.days.addItem(f'{n} days',n)
        row.addWidget(self.days);self.apply=QPushButton('Apply Settings');self.apply.clicked.connect(self.apply_policy);row.addWidget(self.apply)
        row.addStretch();self.refresh_button=QPushButton('Refresh');self.refresh_button.clicked.connect(self.refresh);row.addWidget(self.refresh_button);automatic_box.addLayout(row)
        self.policy_status=QLabel('Loading active policy…');self.policy_status.setWordWrap(True);automatic_box.addWidget(self.policy_status)
        self.cleanup_status=QLabel('Last cleanup: not recorded');self.cleanup_status.setWordWrap(True);automatic_box.addWidget(self.cleanup_status)
        note=QLabel('Only completed, unprotected recordings can be deleted. Protected and in-progress recordings are kept.');note.setWordWrap(True);automatic_box.addWidget(note)
        self.recordings_section=QGroupBox('Recording Management');records_box=QVBoxLayout(self.recordings_section);box.addWidget(self.recordings_section,1)
        row=QHBoxLayout();hint=QLabel('Select a row; use Ctrl or Shift for multiple recordings.');row.addWidget(hint,1)
        self.selection_summary=QLabel('No recordings selected');self.selection_summary.setObjectName('selectionSummary');row.addWidget(self.selection_summary);records_box.addLayout(row)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Recording date','Analyzer','Duration','Samples','Size','Protection','State'])
        self.table.setObjectName('recordingSessions');self.table.setAlternatingRowColors(True);self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header=self.table.horizontalHeader();header.setSectionResizeMode(QHeaderView.Interactive);header.setMinimumSectionSize(50);header.setStretchLastSection(False)
        for column,width in enumerate((205,180,85,85,65,100,105)):self.table.setColumnWidth(column,width)
        header.setSectionResizeMode(1,QHeaderView.Stretch);self.table.verticalHeader().setDefaultSectionSize(30);records_box.addWidget(self.table,1)
        row=QHBoxLayout();self.keep_button=QPushButton('Protect Recording');self.unkeep_button=QPushButton('Remove Protection')
        self.export_button=QPushButton('Export Selected Recording');self.delete_button=QPushButton('Delete Selected Recordings');self.delete_button.setObjectName('deleteRecording')
        for button in (self.keep_button,self.unkeep_button,self.export_button,self.delete_button):row.addWidget(button)
        self.keep_button.clicked.connect(lambda:self.keep(True));self.unkeep_button.clicked.connect(lambda:self.keep(False));self.export_button.clicked.connect(self.export_selected);self.delete_button.clicked.connect(lambda:self.delete(False));records_box.addLayout(row)
        row=QHBoxLayout();row.addWidget(QLabel('Delete completed before'))
        self.before=QDateTimeEdit(QDateTime.currentDateTime().addDays(-30));self.before.setTimeZone(trend.display_timezone);self.before.setDisplayFormat('yyyy-MM-dd HH:mm:ss ttt');self.before.setCalendarPopup(True);row.addWidget(self.before)
        self.older_button=QPushButton('Review Older Recordings…');self.older_button.clicked.connect(lambda:self.delete(True));row.addWidget(self.older_button);row.addStretch();records_box.addLayout(row)
        self.maintenance_section=QGroupBox('Database Maintenance');tools_box=QVBoxLayout(self.maintenance_section);box.addWidget(self.maintenance_section)
        self.sizes=QLabel('Loading database sizes…');self.sizes.setWordWrap(True);tools_box.addWidget(self.sizes)
        row=QHBoxLayout();self.backup_button=QPushButton('Backup Databases');self.backup_button.clicked.connect(self.backup);row.addWidget(self.backup_button)
        self.optimize_button=QPushButton('Optimize Database Storage');self.optimize_button.clicked.connect(self.optimize);row.addWidget(self.optimize_button);row.addStretch();tools_box.addLayout(row)
        self.backup_status=QLabel('Last backup: not recorded');self.backup_status.setWordWrap(True);tools_box.addWidget(self.backup_status)
        self.optimization_status=QLabel('Last optimization: not recorded');self.optimization_status.setWordWrap(True);tools_box.addWidget(self.optimization_status)
        self.optimization_hint=QLabel('Deleting recordings frees reusable space; optimization can reduce the database file size.');self.optimization_hint.setWordWrap(True);tools_box.addWidget(self.optimization_hint)
        self.backup_first=QCheckBox('Back up before manual deletion or optimization (recommended)');self.backup_first.setChecked(True);box.addWidget(self.backup_first)
        self.message=QLabel('Administrator sign-in is required to change stored data or settings.');self.message.setWordWrap(True);box.addWidget(self.message)
        tips={self.automatic:'Enable scheduled deletion of expired, completed, unprotected recordings. Changes take effect after Apply Settings.',
            self.days:'Keep completed recordings for 30, 90, 180 or 365 days. Protected recordings do not expire.',self.apply:'Save and apply these retention settings. Administrator permission is required.',
            self.refresh_button:'Refresh recordings, database sizes, active policy and recent maintenance results.',self.table:'Resize column dividers as needed. Hover over the analyzer for identification and data source.',
            self.keep_button:'Protect selected recordings from automatic and manual deletion.',self.unkeep_button:'Remove protection after confirmation. This does not delete the recording.',
            self.export_button:'Export the selected recording or recordings to CSV without deleting data.',self.delete_button:'Permanently delete selected completed, unprotected recordings after reviewing the count and estimated size.',
            self.older_button:'Review completed, unprotected recordings older than this local date before permanent deletion.',self.before:'Local cutoff time for the older-recording deletion review.',
            self.backup_button:'Save verified SQLite backups of the simulation and hardware databases.',self.optimize_button:'Reclaim unused SQLite storage. Recording and monitoring must be inactive; no recording is deleted.',
            self.backup_first:'Create a verified database backup before manual deletion or optimization. Automatic cleanup does not create backups.'}
        for control,tip in tips.items():control.setToolTip(tip)
        self.admin_controls=(self.apply,self.automatic,self.days,self.keep_button,self.unkeep_button,self.delete_button,self.older_button,self.backup_button,self.optimize_button,self.backup_first,self.before)
        self.table.itemSelectionChanged.connect(self.update_access)
        self.watch=QTimer(self);self.watch.setInterval(500);self.watch.timeout.connect(self.update_access);self.watch.start();self.apply_theme();self.update_access();self.refresh()

    def apply_theme(self):
        dark=self.owner.settings.get('theme','dark')=='dark'
        highlight,foreground=('#226fa5','#ffffff') if dark else ('#b8d9f5','#102a43')
        palette=self.table.palette()
        for group in (QPalette.Active,QPalette.Inactive,QPalette.Disabled):
            palette.setColor(group,QPalette.Highlight,QColor(highlight));palette.setColor(group,QPalette.HighlightedText,QColor(foreground))
        self.table.setPalette(palette)
        self.setStyleSheet(self.owner.styleSheet()+f'''
            QTableWidget#recordingSessions {{selection-background-color:{highlight};selection-color:{foreground};}}
            QTableWidget#recordingSessions::item {{padding:5px 6px;}}
            QTableWidget#recordingSessions::item:selected,
            QTableWidget#recordingSessions::item:selected:active,
            QTableWidget#recordingSessions::item:selected:!active {{background:{highlight};color:{foreground};font-weight:600;}}
            QLabel#selectionSummary {{font-weight:600;padding:5px 0;}}
            QPushButton#deleteRecording:enabled {{border-color:{'#e89494' if dark else '#a73c3c'};}}
            QGroupBox {{border:1px solid #526780;border-radius:5px;margin-top:12px;padding:12px 8px 8px;}}
            QGroupBox::title {{subcontrol-origin:margin;left:10px;padding:0 4px;}}
        ''')

    def update_access(self):
        admin=not self.owner.closing and self.owner.users.resolve(self.owner.session)[1]=='Administrator'
        for control in self.admin_controls:control.setEnabled(admin and not self.busy)
        rows=self.selected();ready=not self.busy
        self.export_button.setEnabled(ready and bool(rows));self.refresh_button.setEnabled(ready)
        self.export_button.setText('Export Selected Recordings' if len(rows)>1 else 'Export Selected Recording')
        self.keep_button.setEnabled(admin and ready and any(not r['protected'] for r in rows))
        self.unkeep_button.setEnabled(admin and ready and any(r['protected'] for r in rows))
        self.delete_button.setEnabled(admin and ready and any(r['ended_at'] and not r['protected'] for r in rows))
        reason=self.service.optimization_blocker()
        if not reason and any(not r['ended_at'] for r in getattr(self,'rows',[])):reason='Active or unfinished recordings prevent optimization.'
        self.optimize_button.setEnabled(admin and ready and not reason and bool(getattr(self,'database_bytes',0)))
        self.optimization_hint.setText((reason+' ' if reason else '')+'Deleting recordings frees reusable space; optimization can reduce file size without deleting recordings.')
        self.selection_summary.setText(f"{len(rows)} selected · {sum(r['protected'] for r in rows)} protected · {sum(not r['ended_at'] for r in rows)} active / unfinished" if rows else 'No recordings selected')

    def selected(self):
        return [self.table.item(i,0).data(Qt.UserRole) for i in sorted({index.row() for index in self.table.selectedIndexes()}) if self.table.item(i,0) and self.table.item(i,0).data(Qt.UserRole)]

    def job(self,operation,done=None):
        if self.busy:return
        self.busy=True;self.update_access();self.message.setText('Working with recorded data… monitoring remains independent.')
        def completed(result):
            self.busy=False;self.update_access()
            message=result.get('warning','Completed') if isinstance(result,dict) else 'Completed: '+', '.join(result) if isinstance(result,list) and result else 'Completed'
            self.message.setText(message)
            if done:done(result)
            self.refresh_summaries()
            self.trend.refresh_sessions()
        def failed(error):
            self.busy=False;self.update_access();self.message.setText(f'Database operation failed: {error}')
            self.trend.refresh_sessions()
            self.refresh_summaries()
        actor=self.owner.users.resolve(self.owner.session)[0]
        def audited():
            try:return operation()
            except (OSError,ValueError,KeyError,sqlite3.Error) as error:
                try:self.service.log(actor,'MANUAL_OPERATION_FAILED',str(error))
                except OSError:pass
                raise
        self.owner.record_job(audited,completed,failed)

    def showEvent(self,event):self.watch.start();super().showEvent(event)

    def closeEvent(self,event):self.watch.stop();super().closeEvent(event)

    def refresh(self):self.job(self.service.inventory,self.show_inventory)

    def refresh_summaries(self):
        if self.status_pending or self.owner.closing:return
        self.status_pending=True
        def done(data):self.status_pending=False;self.show_summaries(data)
        def failed(error):self.status_pending=False;self.cleanup_status.setToolTip(f'Status refresh failed: {error}')
        self.owner.record_job(self.service.summary,done,failed)

    def show_summaries(self,data):
        policy=data['policy'];self.policy_status.setText(f"Active policy: {'Enabled — retain completed recordings for '+str(policy['days'])+' days' if policy['enabled'] else 'Automatic cleanup disabled — saved retention period '+str(policy['days'])+' days'}")
        operations=data.get('operations',{})
        for key,label,title in (('cleanup',self.cleanup_status,'Last cleanup'),('backup',self.backup_status,'Last backup'),('optimization',self.optimization_status,'Last optimization')):
            event=operations.get(key)
            if not event:label.setText(title+': not recorded');continue
            operation=event['operation'];detail=event.get('detail',{})
            state='Did not complete' if operation.endswith('FAILED') else 'Started — completion not recorded' if operation.endswith('STARTED') else 'Completed'
            if key=='cleanup' and isinstance(detail,dict):state+=f" — {len(detail.get('deleted',[]))} recordings deleted"
            label.setText(f"{title}: {friendly_time(event['timestamp'],self.trend.display_timezone)} | {state}")
            label.setToolTip(str(detail))
        attempt=operations.get('cleanup_attempt',{})
        if attempt.get('operation')=='DEFERRED':self.cleanup_status.setText(self.cleanup_status.text()+' | Last attempt deferred: '+str(attempt.get('detail','Database busy')))

    def show_inventory(self,data):
        selected={r['id'] for r in self.selected()};self.rows=data['sessions'];self.table.blockSignals(True);self.table.clearSelection();self.table.setRowCount(len(self.rows))
        self.database_bytes=sum(p['bytes'] for p in data['databases'])
        self.sizes.setText(' | '.join(f"{Path(p['path']).stem.title()} database: {size_text(p['bytes'])}" for p in data['databases']))
        self.sizes.setToolTip('Includes each SQLite database and its WAL/shared-memory files.\n'+'\n'.join(p['path'] for p in data['databases']))
        self.automatic.setChecked(data['policy']['enabled']);self.days.setCurrentIndex(self.days.findData(data['policy']['days']))
        self.show_summaries(data)
        for i,row in enumerate(self.rows):
            config=json.loads(row['config']);identity=json.loads(row['identity']);end=row['ended_at'] or row.get('last_sample_at')
            seconds=max(0,int((datetime.fromisoformat(end)-datetime.fromisoformat(row['started_at'])).total_seconds())) if end else 0
            hours,rest=divmod(seconds,3600);minutes,seconds=divmod(rest,60)
            values=[friendly_time(row['started_at'],self.trend.display_timezone),f"{row['profile'].replace(' Series','')} / {config['assembly']}",f'{hours:02}:{minutes:02}:{seconds:02}',str(row['sample_count']),size_text(row['approximate_bytes']),'Protected' if row['protected'] else 'Unprotected','Completed' if row['ended_at'] else 'Active / unfinished']
            for col,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(value);self.table.setItem(i,col,item)
            self.table.item(i,0).setData(Qt.UserRole,row)
            self.table.item(i,1).setToolTip(f"{values[1]}\nIdentification: {identity.get('text') or identity.get('serial') or config['id']}\nSource: {row['source'].title()}")
            if row['id'] in selected:self.table.selectionModel().select(self.table.model().index(i,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
        self.table.blockSignals(False);self.update_access()
        self.message.setText(f"{len(self.rows)} recordings. Select rows to export, protect or delete." if self.owner.users.resolve(self.owner.session)[1]=='Administrator' else f"{len(self.rows)} recordings. Export is available; Administrator sign-in is required for changes.")

    def apply_policy(self):
        enabled=self.automatic.isChecked();days=self.days.currentData();token=self.owner.session
        if QMessageBox.question(self,'Retention policy',f"{'Enable' if enabled else 'Disable'} automatic deletion of completed, unprotected recordings older than {days} days? This policy persists after restart. Automatic cleanup does not create backups. Export/back up important data and protect recordings before enabling it.")!=QMessageBox.Yes:return
        self.job(lambda:self.service.set_policy(token,enabled,days),lambda _:self.owner.schedule_retention(force=True))

    def keep(self,protected):
        ids=[r['id'] for r in self.selected()];token=self.owner.session
        if not ids:self.message.setText('Select recordings first.');return
        if not protected and QMessageBox.question(self,'Remove Protection','Remove protection from the selected recordings? They may then expire under the retention policy. This does not delete them.')!=QMessageBox.Yes:return
        self.job(lambda:self.service.keep(token,ids,protected),lambda _:self.refresh())

    def backup_directory(self):return QFileDialog.getExistingDirectory(self,'Choose backup folder',str(self.owner.data_path))

    def delete(self,older):
        candidates=getattr(self,'rows',[]) if older else self.selected();cutoff=self.before.dateTime().toUTC().toPython().replace(tzinfo=timezone.utc).isoformat() if older else None
        rows=[r for r in candidates if r['ended_at'] and not r['protected'] and (not cutoff or datetime.fromisoformat(r['ended_at'])<datetime.fromisoformat(cutoff))]
        if not rows:self.message.setText('No eligible completed, unprotected recordings selected.');return
        if QMessageBox.question(self,'Permanently delete recordings',f"Permanently delete {len(rows)} completed recordings (approximately {size_text(sum(r['approximate_bytes'] for r in rows))})? Measurements and session metadata cannot be recovered without a backup. Protected and unfinished sessions are excluded.")!=QMessageBox.Yes:return
        destination=self.backup_directory() if self.backup_first.isChecked() else None
        if self.backup_first.isChecked() and not destination:return
        ids=[r['id'] for r in rows];token=self.owner.session
        def operation():
            if destination:self.service.backup(token,destination)
            return self.service.delete(token,ids,confirmed=True,cutoff=cutoff)
        self.job(operation,lambda result:self.after_delete(result))

    def after_delete(self,result):
        self.refresh();self.message.setText(f"Deleted {len(result['deleted'])} sessions; skipped {len(result['skipped'])} protected/unfinished/ineligible sessions.")

    def export_selected(self):
        rows=self.selected()
        if not rows:self.message.setText('Select recordings to export.');return
        if len(rows)==1:
            name=f"PREVEX_{rows[0]['profile'].replace(' ','')}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
            target,_=QFileDialog.getSaveFileName(self,'Export recording CSV',str(self.owner.data_path/name),'CSV (*.csv)')
            targets=[(rows[0]['id'],target)] if target else []
        else:
            folder=QFileDialog.getExistingDirectory(self,'Export selected recordings',str(self.owner.data_path))
            targets=[(r['id'],str(Path(folder)/f"PREVEX_{r['profile'].replace(' ','')}_{r['id']}.csv")) for r in rows] if folder else []
        if not targets:return
        def operation():
            with self.service.gate.reading():return sum(export_csv(self.service.paths,path,session=sid) for sid,path in targets)
        self.job(operation,lambda count:self.message.setText(f'Exported {count} frames to CSV. No recordings deleted.'))

    def backup(self):
        destination=self.backup_directory();token=self.owner.session
        if destination:self.job(lambda:self.service.backup(token,destination))

    def optimize(self):
        if QMessageBox.question(self,'Optimize database','Optimize SQLite files? Recording and monitoring must be stopped; active/unfinished sessions and current exports prevent optimization. Temporary disk space is checked before VACUUM.')!=QMessageBox.Yes:return
        destination=self.backup_directory() if self.backup_first.isChecked() else None
        if self.backup_first.isChecked() and not destination:return
        token=self.owner.session
        def operation():
            if destination:self.service.backup(token,destination)
            return self.service.optimize(token,confirmed=True)
        self.job(operation,lambda _:self.refresh())
