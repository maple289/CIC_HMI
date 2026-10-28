"""Retention/maintenance tests use isolated data and simulated I/O only."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import csv,json,sqlite3,threading,time
from types import SimpleNamespace
import pytest
from PySide6.QtWidgets import QMessageBox,QFileDialog
from prevex_hmi.logging_db.maintenance import RecordingManagement,Busy,gate_for,PERIODS
from prevex_hmi.logging_db.recordings import RecordingStore,sessions,history_series,export_csv
from prevex_hmi.logging_db.recorder import Recorder
from prevex_hmi.security.users import UserStore
from prevex_hmi.devices.configuration import load_settings
from prevex_hmi.gui.window import MainWindow
from test_monitoring import app,until
from test_recording_sessions import sample,stamp

NOW=datetime(2026,10,27,12,tzinfo=timezone.utc)


@pytest.fixture
def management(tmp_path):
    users=UserStore(tmp_path/'users.sqlite3');users.create_user('admin','password8');token=users.authenticate('admin','password8')
    service=RecordingManagement(tmp_path)
    def add(age,*,ended=True,source='simulation'):
        data=sample();data['source']=source;when=(NOW-timedelta(days=age)).isoformat()
        store=RecordingStore(tmp_path/f'{source}.sqlite3');sid,params=store.start(data,1,False,'manual',when,selected=[1,9]);store.append(sid,data,params,{},when)
        if ended:store.end(sid,'Stopped',when)
        store.close();return sid
    yield service,users,token,add
    users.close()


@pytest.mark.parametrize('days',PERIODS)
@pytest.mark.parametrize('source',['simulation','hardware'])
def test_retention_boundaries_protection_completed_only_and_restart(management,days,source):
    service,users,token,add=management
    expired=add(days+1,source=source);boundary=add(days,source=source);new=add(days-1,source=source);kept=add(days+3,source=source);unfinished=add(days+5,source=source,ended=False)
    assert service.policy()==dict(enabled=False,days=30)
    assert service.retention(NOW)['disabled'] and len(service.inventory()['sessions'])==5
    service.keep(token,[kept],True);service.set_policy(token,True,days)
    restarted=RecordingManagement(service.directory);result=restarted.retention(NOW)
    assert result['deleted']==[expired]
    assert {r['id'] for r in restarted.inventory()['sessions']}=={boundary,new,kept,unfinished}
    row=next(r for r in restarted.inventory()['sessions'] if r['id']==kept);assert row['protected']
    with sqlite3.connect(service.directory/f'{source}.sqlite3') as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert not db.execute('SELECT 1 FROM recording_values WHERE session_id=?',(expired,)).fetchone()
        assert not db.execute('SELECT 1 FROM recording_frames WHERE session_id=?',(expired,)).fetchone()
        logs=db.execute("SELECT detail FROM recording_maintenance WHERE operation='DELETE'").fetchall()
        assert len(logs)==1 and json.loads(logs[0][0])['session']==expired


def test_manual_confirm_keep_unkeep_cutoff_and_consistent_deletion(management):
    s,u,t,add=management;old=add(100);new=add(1);kept=add(100);active=add(200,ended=False)
    s.keep(t,[kept],True)
    with pytest.raises(PermissionError):s.delete(t,[old])
    result=s.delete(t,[old,new,kept,active],confirmed=True,cutoff=(NOW-timedelta(days=30)).isoformat())
    assert result['deleted']==[old] and set(result['skipped'])=={new,kept,active}
    s.keep(t,[kept],False);assert s.delete(t,[kept],confirmed=True)['deleted']==[kept]
    assert {r['id'] for r in s.inventory()['sessions']}=={new,active}


@pytest.mark.parametrize('action',['delete','keep','policy','backup','vacuum'])
@pytest.mark.parametrize('role',['Guest','Viewer','Operator','Revoked'])
def test_admin_required_for_all_mutations(management,action,role,tmp_path):
    s,u,admin,add=management;sid=add(200);token=''
    if role in ('Viewer','Operator'):
        u.create_user('user','password8',role,session=admin);token=u.authenticate('user','password8')
    elif role=='Revoked':token=admin;u.logout(admin)
    operation={'delete':lambda:s.delete(token,[sid],confirmed=True),'keep':lambda:s.keep(token,[sid],True),'policy':lambda:s.set_policy(token,True,30),'backup':lambda:s.backup(token,tmp_path/'backup'),'vacuum':lambda:s.optimize(token,confirmed=True)}[action]
    with pytest.raises(PermissionError):operation()
    assert len(sessions(s.paths))==1 and not s.policy()['enabled']


def test_recording_export_backup_and_monitoring_coordination(management,tmp_path):
    s,u,t,add=management;sid=add(100)
    r=Recorder(tmp_path,clock=lambda:0);r.start();r.tick(sample(),received=0)
    with pytest.raises(Busy):s.delete(t,[sid],confirmed=True)
    with pytest.raises(Busy):s.optimize(t,confirmed=True)
    r.stop();r.close()
    with s.gate.reading():
        with pytest.raises(Busy):s.delete(t,[sid],confirmed=True)
        with pytest.raises(Busy):s.optimize(t,confirmed=True)
    assert s.gate.enter_monitoring()
    try:
        with pytest.raises(Busy,match='Disconnect'):s.optimize(t,confirmed=True)
        assert s.delete(t,[sid],confirmed=True)['deleted']==[sid]
    finally:s.gate.leave_monitoring()
    with s.gate.maintenance():
        assert not s.gate.enter_monitoring()
        with pytest.raises(Busy):export_csv(s.paths,tmp_path/'blocked.csv')
        r=Recorder(tmp_path,clock=lambda:0);r.start();r.tick(sample(),received=0)
        assert r.session is None and 'maintenance' in r.status()['state']
    r.tick(sample(),received=0);assert r.session;r.close()
    assert s.gate.recorders==0 and not s.gate.exclusive and s.gate.readers==0


def test_export_holds_reader_lease_while_streaming(management,tmp_path,monkeypatch):
    from prevex_hmi.logging_db import recordings
    s,u,t,add=management;sid=add(100);original=recordings._export_csv
    def stream(*args,**kwargs):
        assert s.gate.readers==1
        with pytest.raises(Busy):s.delete(t,[sid],confirmed=True)
        return original(*args,**kwargs)
    monkeypatch.setattr(recordings,'_export_csv',stream)
    assert export_csv(s.paths,tmp_path/'export.csv',session=sid)==1
    assert s.gate.readers==0


def test_online_backup_integrity_while_recording_and_storage_estimates(management,tmp_path):
    s,u,t,add=management;sid=add(10);r=Recorder(tmp_path,clock=lambda:0);r.start();r.tick(sample(),received=0)
    try:backups=s.backup(t,tmp_path/'backups')
    finally:r.close()
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as db:
        assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert db.execute('SELECT 1 FROM recording_sessions WHERE id=?',(sid,)).fetchone()
    inventory=s.inventory();assert all(row['approximate_bytes']>0 for row in inventory['sessions'])
    size=next(d['bytes'] for d in inventory['databases'] if d['path'].endswith('simulation.sqlite3'))
    assert size>=Path(s.paths[0]).stat().st_size>0


def test_vacuum_reclaims_space_and_preserves_history_and_audit(management):
    s,u,t,add=management;old=add(100);kept=add(10);s.keep(t,[kept],True)
    with sqlite3.connect(s.paths[0]) as db:
        db.execute('CREATE TABLE unrelated_history(payload TEXT)');db.execute('INSERT INTO unrelated_history VALUES (?)',('x'*1000000,))
        db.execute('DELETE FROM unrelated_history')
    before=history_series(s.paths,kept);s.delete(t,[old],confirmed=True)
    with sqlite3.connect(s.paths[0]) as db:size=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]
    assert s.optimize(t,confirmed=True)==[str(s.paths[0])]
    assert Path(s.paths[0]).stat().st_size<size and history_series(s.paths,kept)==before
    assert s.inventory()['sessions'][0]['protected']
    with sqlite3.connect(s.paths[0]) as db:
        assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert db.execute('SELECT COUNT(*) FROM unrelated_history').fetchone()[0]==0
        assert db.execute("SELECT 1 FROM recording_maintenance WHERE operation='VACUUM_COMPLETE'").fetchone()


def test_insufficient_space_unfinished_sessions_and_invalid_policy_fail_safe(management,tmp_path,monkeypatch):
    from prevex_hmi.logging_db import maintenance
    s,u,t,add=management;sid=add(100,ended=False)
    with pytest.raises(Busy,match='unfinished'):s.optimize(t,confirmed=True)
    with sqlite3.connect(s.paths[0]) as db:db.execute('UPDATE recording_sessions SET ended_at=started_at')
    monkeypatch.setattr(maintenance.shutil,'disk_usage',lambda p:SimpleNamespace(free=0))
    with pytest.raises(OSError,match='space'):s.optimize(t,confirmed=True)
    with pytest.raises(OSError,match='space'):s.backup(t,tmp_path/'backups')
    s.policy_path.write_text('{"enabled":true,"days":1}')
    with pytest.raises(ValueError):s.retention(NOW)
    assert len(sessions(s.paths))==1 and not s.gate.exclusive


def test_failed_delete_rolls_back_metadata_values_and_deletion_audit(management,monkeypatch):
    s,u,t,add=management;sid=add(100)
    with sqlite3.connect(s.paths[0]) as db:
        db.execute("CREATE TRIGGER deny_delete BEFORE DELETE ON recording_frames BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.Error):s.delete(t,[sid],confirmed=True)
    assert len(history_series(s.paths,sid)['points'])==1 and len(sessions(s.paths))==1
    with sqlite3.connect(s.paths[0]) as db:assert not db.execute("SELECT 1 FROM recording_maintenance WHERE operation='DELETE'").fetchone()
    assert not s.gate.exclusive


def test_failed_start_releases_maintenance_lease(tmp_path):
    def fail(path):raise OSError('disk full')
    r=Recorder(tmp_path,clock=lambda:0,store_factory=fail);r.start()
    with pytest.raises(OSError):r.tick(sample(),received=0)
    r.fail(OSError('disk full'));assert gate_for(tmp_path).recorders==0;r.close()


def test_management_window_admin_access_confirmation_and_monitoring(app,tmp_path,monkeypatch):
    settings=load_settings(tmp_path/'settings.json');settings['devices'][0]['interval']=.25
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=True);w.show()
    try:
        until(app,lambda:w.snapshot is not None);w.trend_window.manage_data();dialog=w.trend_window.management_window
        until(app,lambda:not dialog.busy);assert not dialog.delete_button.isEnabled() and not dialog.apply.isEnabled()
        w.users.create_user('admin','password8');token=w.users.authenticate('admin','password8');w.session=token;dialog.update_access()
        assert not dialog.delete_button.isEnabled() and dialog.apply.isEnabled()  # no selected recording yet
        store=RecordingStore(tmp_path/'simulation.sqlite3');sid,params=store.start(sample(),1,False,'manual','2020-01-01T00:00:00+00:00',selected=[1]);store.append(sid,sample(),params,{},stamp());store.end(sid,'Stopped','2020-01-01T01:00:00+00:00');store.close()
        dialog.refresh();until(app,lambda:not dialog.busy);assert dialog.table.rowCount()==1
        dialog.table.selectRow(0);monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.No)
        dialog.delete(False);assert len(sessions(dialog.service.paths))==1
        destination=tmp_path/'before-delete.csv';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(destination),'CSV (*.csv)'))
        dialog.export_selected();until(app,lambda:destination.exists() and not dialog.busy)
        before=w.update_count;dialog.backup_first.setChecked(False);monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
        dialog.delete(False);until(app,lambda:not dialog.busy)
        assert not sessions(dialog.service.paths),dialog.message.text()
        until(app,lambda:w.update_count>before+2);assert w.worker.isRunning() and w.snapshot['quality']=='GOOD'
        # A slow cleanup cannot hold the polling loop or GUI heartbeat. History
        # writes are buffered until its maintenance lease is released.
        deadline=time.monotonic()+5
        while True:
            try:
                with dialog.service.gate.maintenance():
                    before=w.update_count;until(app,lambda:w.update_count>before+2)
                break
            except Busy:
                if time.monotonic()>deadline:raise
                app.processEvents();time.sleep(.05)
        w.users.logout(token);dialog.update_access();assert not dialog.keep_button.isEnabled()
    finally:
        w.close();until(app,lambda:not w.worker.isRunning() and not w.recording_worker.isRunning() and not w.record_jobs)


def test_legacy_history_buffers_during_maintenance_without_blocking_or_losing_samples(tmp_path):
    from prevex_hmi.logging_db.store import MonitoringHistorian
    errors=[];path=tmp_path/'simulation.sqlite3';store=MonitoringHistorian(path,errors.append);gate=gate_for(tmp_path)
    with gate.maintenance():
        store.measurement(stamp(), 'test',1,-2.5,'%LFL','GOOD',0);store.event(stamp(),'test','Offline','OFFLINE');store.commit()
        assert len(store.pending)==2 and not errors
        with pytest.raises(PermissionError,match='maintenance'):store.command_audit('test','admin',256,'SENDING','not sent')
        assert not store.error
    store.commit();assert not store.pending and gate.history_writers==0
    assert store.store.db.execute('SELECT timestamp,value FROM measurements').fetchone()==(stamp(),-2.5)
    assert store.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==1
    store.measurement(stamp(1),'test',1,2,'%LFL','GOOD',0)
    with pytest.raises(Busy):
        with gate.maintenance():pass
    store.commit();store.close();assert gate.history_writers==0


def test_scheduled_retention_runs_after_restart_without_stopping_monitoring(app,tmp_path):
    s=RecordingManagement(tmp_path);u=UserStore(tmp_path/'users.sqlite3');u.create_user('admin','password8');token=u.authenticate('admin','password8')
    store=RecordingStore(tmp_path/'simulation.sqlite3');sid,params=store.start(sample(),1,False,'manual','2020-01-01T00:00:00+00:00',selected=[1]);store.append(sid,sample(),params,{},stamp());store.end(sid,'Stopped','2020-01-01T01:00:00+00:00');store.close()
    s.set_policy(token,True,30);u.close()
    settings=load_settings(tmp_path/'settings.json');settings['devices'][0]['interval']=.25
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=True)
    try:
        until(app,lambda:w.snapshot is not None)
        # Retry normally deferred history transactions without changing policy.
        deadline=time.monotonic()+10
        while sessions(s.paths) and time.monotonic()<deadline:
            w.schedule_retention(force=True);app.processEvents();time.sleep(.05)
        assert not sessions(s.paths)
        before=w.update_count;until(app,lambda:w.update_count>before+2)
        assert w.worker.isRunning() and not w.snapshot['control'].get('ambiguous')
        assert s.policy()==dict(enabled=True,days=30)
    finally:w.close();until(app,lambda:not w.worker.isRunning() and not w.recording_worker.isRunning() and not w.record_jobs)


def test_pending_controller_actions_defer_cleanup_and_maintenance_rejects_new_actions(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json');settings['devices'][0]['interval']=.25
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=True)
    try:
        until(app,lambda:w.snapshot is not None and w.snapshot['control']['verified'])
        w.users.create_user('admin','password8');token=w.users.authenticate('admin','password8');gate=w.recording_management.gate
        w.request('command',0x600,token,True)
        until(app,lambda:w.snapshot['control']['pending'])
        assert gate.commands==1
        with pytest.raises(Busy,match='controller action'):w.recording_management.delete(token,[],confirmed=True)
        until(app,lambda:not w.snapshot['control']['pending'],timeout=12)
        assert gate.commands==0 and not w.snapshot['control']['ambiguous']
        replies=[];w.worker.command_result.connect(replies.append)
        deadline=time.monotonic()+5
        while True:
            try:
                with gate.maintenance():
                    w.request('command',0x600,token,True)
                    until(app,lambda:any('no controller command sent' in r for r in replies))
                    assert gate.commands==0
                break
            except Busy:
                if time.monotonic()>deadline:raise
                app.processEvents();time.sleep(.05)
    finally:w.close();until(app,lambda:not w.worker.isRunning() and not w.recording_worker.isRunning() and not w.record_jobs)


def test_policy_reports_applied_state_if_only_completion_log_fails(management,monkeypatch):
    s,u,t,add=management;original=s.log
    def log(actor,operation,detail):
        if operation=='POLICY_SAVED':raise OSError('injected full log volume')
        original(actor,operation,detail)
    monkeypatch.setattr(s,'log',log);result=s.set_policy(t,True,90)
    assert s.policy()==dict(enabled=True,days=90) and result['enabled'] and 'Policy applied' in result['warning']

def test_operation_summaries_survive_restart_and_partial_journal(management,tmp_path):
    s,u,t,add=management;add(100);s.set_policy(t,True,30);s.retention(NOW)
    s.backup(t,tmp_path/'backups');s.optimize(t,confirmed=True)
    status=RecordingManagement(s.directory).summary()
    assert status['policy']==dict(enabled=True,days=30)
    assert status['operations']['cleanup']['operation']=='DELETE_COMPLETE'
    assert status['operations']['backup']['operation']=='BACKUP_COMPLETE'
    assert status['operations']['optimization']['operation']=='OPTIMIZE_COMPLETE'
    s.log('Automatic retention','DEFERRED','Recording active')
    assert s.summary()['operations']['cleanup_attempt']['operation']=='DEFERRED'
    assert s.summary()['operations']['cleanup']['operation']=='DELETE_COMPLETE'
    journal=s.directory/'recording-maintenance.jsonl'
    with journal.open('ab') as out:out.write(b'bad json\n{"timestamp":"2026-10-28T00:00:00+00:00","operation":3}\n{"timestamp":')
    assert s.summary()['operations']['backup']['operation']=='BACKUP_COMPLETE'
    with journal.open('ab') as out:out.write(b'"2026-10-28T00:00:00+00:00","operation":"BACKUP_FAILED","detail":"disk full"}\n')
    assert s.summary()['operations']['backup']['detail']=='disk full'


def test_failure_results_and_optimization_blocker(management,tmp_path,monkeypatch):
    s,u,t,add=management;add(1)
    def fail(*args,**kwargs):raise OSError('disk full')
    monkeypatch.setattr(s,'_backup',fail);monkeypatch.setattr(s,'_optimize',fail)
    with pytest.raises(OSError):s.backup(t,tmp_path/'backups')
    with pytest.raises(OSError):s.optimize(t,confirmed=True)
    status=RecordingManagement(s.directory).summary()['operations']
    assert status['backup']['operation']=='BACKUP_FAILED' and status['optimization']['operation']=='OPTIMIZE_FAILED'
    assert not s.optimization_blocker()
    s.gate.monitors+=1
    try:assert 'Disconnect monitoring' in s.optimization_blocker()
    finally:s.gate.monitors-=1
