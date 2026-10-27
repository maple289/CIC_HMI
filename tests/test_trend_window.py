"""Detached Qt window and recording/export integration, simulation only."""
from dataclasses import asdict
from pathlib import Path
import json,sqlite3,time
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication,QFileDialog
import pyqtgraph as pg
from prevex_hmi.devices.configuration import load_settings,default_devices
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.logging_db.recordings import sessions,export_csv
from prevex_hmi.logging_db.recordings import RecordingStore
from prevex_hmi.communication.serial_transport import ReadOnlySerialTransport
from test_monitoring import app,until


@pytest.fixture
def window(app,tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('No serial transport in recording/window tests')
    monkeypatch.setattr(ReadOnlySerialTransport,'__init__',forbidden)
    settings=load_settings(tmp_path/'settings.json')
    settings['devices'][0]['interval']=.25
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path);w.show()
    until(app,lambda:w.snapshot is not None and len(w.snapshot['register_timestamps'])>10)
    yield w
    w.close();until(app,lambda:not w.worker.isRunning() and not w.recording_worker.isRunning() and not w.record_jobs)
    app.processEvents()


def test_independent_single_window_minimize_maximize_and_reopen(app,window):
    w=window;trend=w.trend_window
    assert not w.pages.widget(0).findChildren(pg.PlotWidget)
    w.open_trend();app.processEvents()
    assert trend.isWindow() and trend.windowModality()==Qt.NonModal and trend in QApplication.topLevelWidgets()
    assert trend.live_plot.window() is trend and trend.windowFlags()&Qt.WindowMinMaxButtonsHint
    trend.move(20,30);trend.resize(720,520);app.processEvents()
    w.open_trend();assert w.trend_window is trend
    trend.showMinimized();app.processEvents();assert not w.isMinimized()
    w.open_trend();assert not trend.isMinimized()
    trend.showMaximized();app.processEvents();assert trend.isMaximized()
    trend.showNormal();trend.move(20,30);trend.resize(720,520);app.processEvents()
    position=trend.pos();size=trend.size();before=w.update_count
    trend.close();assert not trend.isVisible() and w.isVisible()
    until(app,lambda:w.update_count>before+2)
    w.open_trend();assert trend.size()==size and trend.pos()==position
    assert json.loads((w.data_path/'trend-window.json').read_text())['geometry']


def test_geometry_restores_across_application_instances(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json')
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    w.open_trend();app.processEvents();w.trend_window.resize(720,520);w.trend_window.move(20,30);app.processEvents()
    geometry=w.trend_window.geometry();w.close();until(app,lambda:not w.record_jobs)
    other=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    try:
        other.open_trend();app.processEvents()
        assert other.trend_window.size()==geometry.size()
        assert (other.trend_window.pos()-geometry.topLeft()).manhattanLength()<15
    finally:other.close();until(app,lambda:not other.record_jobs)


def test_recording_survives_hidden_window_and_shutdown_ends_session(app,window):
    w=window;w.open_trend();trend=w.trend_window
    trend.start_button.click();until(app,lambda:w.recording_status['session'] is not None)
    session=w.recording_status['session'];until(app,lambda:w.recording_status['samples']>=1)
    samples=w.recording_status['samples'];updates=w.update_count;trend.close()
    until(app,lambda:w.recording_status['samples']>samples and w.update_count>updates+2,timeout=5)
    assert not trend.isVisible() and w.recording_status['session']==session
    w.open_trend();assert 'Recording' in trend.recording_status.text()
    trend.stop_button.click();until(app,lambda:w.recording_status['session'] is None)
    row=next(row for row in sessions(trend.paths) if row['id']==session);assert row['end_reason']=='Stopped by operator'
    trend.start_button.click();until(app,lambda:w.recording_status['session'] is not None)
    last=w.recording_status['session'];w.close();until(app,lambda:not w.worker.isRunning() and not w.recording_worker.isRunning() and not w.record_jobs)
    assert not trend.isVisible() and next(r for r in sessions(trend.paths) if r['id']==last)['end_reason']=='Application shutdown'


def test_automatic_pause_and_recovery_reuses_session(app,window):
    w=window;w.open_trend();trend=w.trend_window
    trend.mode.setCurrentIndex(1);until(app,lambda:w.recording_status['session'] is not None)
    session=w.recording_status['session'];w.request('fault','timeout')
    until(app,lambda:w.recording_status['state'].startswith('Paused'),timeout=8)
    samples=w.recording_status['samples'];until(app,lambda:w.snapshot['quality']=='OFFLINE')
    w.request('fault','none');until(app,lambda:w.recording_status['state']=='Recording' and w.recording_status['samples']>samples,timeout=12)
    assert w.recording_status['session']==session
    assert load_settings(w.settings_path)['recording']['mode']=='automatic'


def test_historical_view_and_export_use_read_jobs(app,window,tmp_path,monkeypatch):
    w=window;w.open_trend();t=w.trend_window;t.main_only.setChecked(True);t.start_button.click()
    assert t.range_start.timeZone().id()==b'UTC' and t.range_end.timeZone().id()==b'UTC'
    until(app,lambda:w.recording_status['samples']>=1);session=w.recording_status['session']
    t.stop_button.click();until(app,lambda:w.recording_status['session'] is None)
    t.refresh_sessions();until(app,lambda:t.session_choice.count()>0)
    t.tabs.setCurrentIndex(1);t.load_session();until(app,lambda:t.recorded_curve.getData()[0] is not None)
    assert t.recorded_plot.zero_line.value()==0 and t.live_plot.zero_line.value()==0
    destination=tmp_path/'export.csv';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(destination),'CSV (*.csv)'))
    t.export_scope.setCurrentIndex(1);t.export();until(app,lambda:destination.exists() and t.export_button.isEnabled())
    assert 'Session' in destination.read_text(encoding='utf-8-sig') and session in destination.read_text(encoding='utf-8-sig')
    before=w.update_count
    t.export_scope.setCurrentIndex(2);t.range_start.setDateTime(t.range_end.dateTime().addSecs(1));t.export()
    assert 'Start must precede end' in t.notice.text()
    until(app,lambda:w.update_count>before)


def test_export_failure_does_not_stop_recording_or_polling(app,window,tmp_path,monkeypatch):
    w=window;w.open_trend();t=w.trend_window;t.start_button.click();until(app,lambda:w.recording_status['samples']>=1)
    before=w.update_count;samples=w.recording_status['samples']
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(tmp_path/'missing'/'export.csv'),'CSV (*.csv)'))
    t.export();until(app,lambda:'CSV export failed' in t.notice.text())
    until(app,lambda:w.update_count>before+2 and w.recording_status['samples']>samples,timeout=5)
    assert w.worker.isRunning() and w.snapshot['quality']=='GOOD'


def test_recording_disk_failure_stops_only_recording(app,window,monkeypatch):
    w=window
    def fail(*args,**kwargs):raise sqlite3.OperationalError('database or disk is full')
    monkeypatch.setattr(RecordingStore,'append',fail)
    w.recording_worker.request('start');until(app,lambda:bool(w.recording_status['error']))
    before=w.update_count;until(app,lambda:w.update_count>before+3)
    assert w.worker.isRunning() and w.snapshot['quality']=='GOOD' and w.recording_status['session'] is None


def test_negative_live_readings_and_zero_reference_remain_when_hidden(app,window):
    w=window;w.request('reading',-10);until(app,lambda:w.gauge.state.value is not None and w.gauge.state.value<0)
    w.open_trend();w.trend_window.close();before=w.update_count
    until(app,lambda:w.update_count>before+3)
    xs,ys=w.trend_curve.getData();assert any(y<0 for y in ys) and w.trend_plot.zero_line.value()==0


def test_monitoring_history_disk_failure_does_not_stop_polling(app,window,monkeypatch):
    from prevex_hmi.logging_db.store import Historian
    w=window
    def fail(*args):raise sqlite3.OperationalError('database or disk is full')
    monkeypatch.setattr(Historian,'measurement',fail)
    until(app,lambda:'History storage unavailable' in w.statusBar().currentMessage())
    before=w.update_count;until(app,lambda:w.update_count>before+3)
    assert w.worker.isRunning() and w.snapshot['quality']=='GOOD' and w.snapshot['control']['ambiguous']
