"""Non-modal recorded-data manager; database work uses existing job threads."""
from datetime import datetime,timezone
import json,sqlite3
from pathlib import Path
from PySide6.QtCore import Qt,QDateTime,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QComboBox,QPushButton,
    QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QDateTimeEdit,QFileDialog,QMessageBox)
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
        self.trend=trend;self.owner=trend.owner;self.service=self.owner.recording_management;self.busy=False
        self.setWindowTitle('PREVEX HMI — Manage Recorded Data');self.resize(1100,680);self.setMinimumSize(720,500)
        box=QVBoxLayout(self);self.sizes=QLabel();self.sizes.setWordWrap(True);box.addWidget(self.sizes)
        row=QHBoxLayout();self.automatic=QCheckBox('Automatic cleanup');row.addWidget(self.automatic)
        self.days=QComboBox()
        for n in PERIODS:self.days.addItem(f'{n} days',n)
        row.addWidget(self.days);self.apply=QPushButton('Apply retention policy');self.apply.clicked.connect(self.apply_policy);row.addWidget(self.apply)
        self.refresh_button=QPushButton('Refresh');self.refresh_button.clicked.connect(self.refresh);row.addWidget(self.refresh_button);row.addStretch();box.addLayout(row)
        note=QLabel('Only completed, unprotected sessions can be deleted. Keep protects important sessions. Automatic cleanup is initially off; the default period is 30 days.');note.setWordWrap(True);box.addWidget(note)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(['Recording time','Analyzer / model','Identification / source','Duration','Saved samples','Approx. storage','Keep','State'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.ExtendedSelection);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.table.horizontalHeader().setStretchLastSection(True);box.addWidget(self.table,1)
        row=QHBoxLayout();self.keep_button=QPushButton('Mark Keep');self.unkeep_button=QPushButton('Remove Keep');self.delete_button=QPushButton('Delete selected');self.export_button=QPushButton('Export selected CSV')
        for b in (self.keep_button,self.unkeep_button,self.delete_button,self.export_button):row.addWidget(b)
        self.keep_button.clicked.connect(lambda:self.keep(True));self.unkeep_button.clicked.connect(lambda:self.keep(False));self.delete_button.clicked.connect(lambda:self.delete(False));self.export_button.clicked.connect(self.export_selected);box.addLayout(row)
        row=QHBoxLayout();row.addWidget(QLabel('Completed before'))
        self.before=QDateTimeEdit(QDateTime.currentDateTime().addDays(-30));self.before.setTimeZone(trend.display_timezone);self.before.setDisplayFormat('yyyy-MM-dd HH:mm:ss ttt');self.before.setCalendarPopup(True);row.addWidget(self.before)
        self.older_button=QPushButton('Delete older recordings');self.older_button.clicked.connect(lambda:self.delete(True));row.addWidget(self.older_button);row.addStretch();box.addLayout(row)
        self.backup_first=QCheckBox('Create verified SQLite backup before manual deletion / optimization');self.backup_first.setChecked(True);box.addWidget(self.backup_first)
        row=QHBoxLayout();self.backup_button=QPushButton('Back up databases');self.backup_button.clicked.connect(self.backup);row.addWidget(self.backup_button)
        self.optimize_button=QPushButton('Optimize database size');self.optimize_button.clicked.connect(self.optimize);row.addWidget(self.optimize_button);row.addStretch();box.addLayout(row)
        self.message=QLabel('Administrator sign-in is required to change policy, protection or stored data.');self.message.setWordWrap(True);box.addWidget(self.message)
        self.admin_controls=(self.apply,self.automatic,self.days,self.keep_button,self.unkeep_button,self.delete_button,self.older_button,self.backup_button,self.optimize_button,self.backup_first,self.before)
        self.watch=QTimer(self);self.watch.setInterval(500);self.watch.timeout.connect(self.update_access);self.watch.start();self.update_access();self.refresh()

    def update_access(self):
        admin=not self.owner.closing and self.owner.users.resolve(self.owner.session)[1]=='Administrator'
        for control in self.admin_controls:control.setEnabled(admin and not self.busy)
        self.export_button.setEnabled(not self.busy);self.refresh_button.setEnabled(not self.busy)

    def selected(self):
        return [self.table.item(i,0).data(Qt.UserRole) for i in sorted({index.row() for index in self.table.selectedIndexes()})]

    def job(self,operation,done=None):
        if self.busy:return
        self.busy=True;self.update_access();self.message.setText('Working with recorded data… monitoring remains independent.')
        def completed(result):
            self.busy=False;self.update_access()
            message=result.get('warning','Completed') if isinstance(result,dict) else 'Completed: '+', '.join(result) if isinstance(result,list) and result else 'Completed'
            self.message.setText(message)
            if done:done(result)
            self.trend.refresh_sessions()
        def failed(error):
            self.busy=False;self.update_access();self.message.setText(f'Database operation failed: {error}')
            self.trend.refresh_sessions()
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

    def show_inventory(self,data):
        selected={r['id'] for r in self.selected()};self.rows=data['sessions'];self.table.setRowCount(len(self.rows))
        self.sizes.setText('SQLite size (database + WAL/shared-memory): '+' | '.join(f"{Path(p['path']).name}: {size_text(p['bytes'])}" for p in data['databases'])+'\nSession storage is an estimate; freed pages may remain allocated until optimization.')
        self.automatic.setChecked(data['policy']['enabled']);self.days.setCurrentIndex(self.days.findData(data['policy']['days']))
        for i,row in enumerate(self.rows):
            config=json.loads(row['config']);identity=json.loads(row['identity']);end=row['ended_at'] or row.get('last_sample_at')
            seconds=max(0,int((datetime.fromisoformat(end)-datetime.fromisoformat(row['started_at'])).total_seconds())) if end else 0
            hours,rest=divmod(seconds,3600);minutes,seconds=divmod(rest,60)
            values=[friendly_time(row['started_at'],self.trend.display_timezone),f"{row['profile']} / {config['assembly']}",f"{identity.get('text') or identity.get('serial') or config['id']} | {row['source'].title()}",f'{hours:02}:{minutes:02}:{seconds:02}',str(row['sample_count']),size_text(row['approximate_bytes']),'Keep' if row['protected'] else 'Unprotected','Completed' if row['ended_at'] else 'Active / unfinished']
            for col,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(value);self.table.setItem(i,col,item)
            self.table.item(i,0).setData(Qt.UserRole,row)
            if row['id'] in selected:self.table.selectRow(i)
        self.message.setText(f"{len(self.rows)} sessions. Administrator required for changes; recording/export data remain UTC.")

    def apply_policy(self):
        enabled=self.automatic.isChecked();days=self.days.currentData();token=self.owner.session
        if QMessageBox.question(self,'Retention policy',f"{'Enable' if enabled else 'Disable'} automatic deletion of completed, unprotected recordings older than {days} days? This policy persists after restart. Automatic cleanup does not create backups. Export/back up important data and mark Keep before enabling it.")!=QMessageBox.Yes:return
        self.job(lambda:self.service.set_policy(token,enabled,days),lambda _:self.owner.schedule_retention(force=True))

    def keep(self,protected):
        ids=[r['id'] for r in self.selected()];token=self.owner.session
        if not ids:self.message.setText('Select recordings first.');return
        if not protected and QMessageBox.question(self,'Remove Keep','Remove protection from the selected recordings? They may then expire under the retention policy.')!=QMessageBox.Yes:return
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
