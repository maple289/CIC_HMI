"""Connection lifecycle integration; all traffic is simulated or forbidden."""
from dataclasses import replace
from types import SimpleNamespace
import copy
import pytest
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.devices.configuration import load_settings,save_settings,default_devices
from prevex_hmi.simulator.bus import SimulatedBus,SimulatedAnalyzer
from test_monitoring import app,until


def close(app,w):
    w.close();until(app,lambda:(not w.worker or not w.worker.isRunning()) and not w.recording_worker.isRunning() and not w.record_jobs)


def test_startup_saved_hardware_is_idle_and_manual_selection_is_only_a_preference(app,tmp_path,monkeypatch):
    from prevex_hmi.communication.serial_transport import ReadOnlySerialTransport
    monkeypatch.setattr(ReadOnlySerialTransport,'__init__',lambda *a,**k:pytest.fail('Startup must not open a port'))
    monkeypatch.setattr('prevex_hmi.gui.serial_ports.list_ports.comports',lambda:[SimpleNamespace(device='COM7',description='Test adapter')])
    settings=load_settings(tmp_path/'settings.json');settings['mode']='hardware';settings['connection'].update(port='COM7',baud=9600);settings['devices'][0]['address']=3;save_settings(tmp_path/'settings.json',settings)
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path);w.show();app.processEvents()
    try:
        assert w.worker is None and w.snapshot is None and not w.profile_current
        assert w.summary.text()=='No Analyzer Connected' and 'Unknown' in w.connection_screen.selection.text()
        assert w.connection_screen.status.text()=='Connection Status: No Connection'
        assert w.pages.currentWidget() is w.connection_screen and not w.gauge.isVisibleTo(w)
        assert not w.command_scroll.isVisibleTo(w) and not w.indicators.isVisibleTo(w)
        assert not w.warning.text() and not w.monitor_model.text()
        w.connection_screen.profile.setCurrentText('LEL 670 Series');until(app,lambda:w.settings['analyzer_selection']=='LEL 670 Series')
        assert 'Not Verified' in w.connection_screen.selection.text() and w.worker is None
        assert w.connection_screen.port.text()=='COM7' and w.connection_screen.baud.currentData()==9600 and w.connection_screen.address.value()==3
        w.show_diagnostics();assert w.pages.currentIndex()==4
        w.open_trend();assert w.trend_window.isVisible() and not w.trend_window.start_button.isEnabled()
    finally:close(app,w)
    restarted=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path)
    try:
        assert restarted.worker is None and restarted.last_connected==''
        assert 'Not Verified' in restarted.connection_screen.selection.text() and restarted.connection_screen.port.text()=='COM7'
        assert restarted.connection_screen.baud.currentData()==9600 and restarted.connection_screen.address.value()==3
    finally:close(app,restarted)


@pytest.mark.parametrize('profile,family',[('LEL 670 Series','LEL'),('LEL 700 Series','LEL'),('BTU','BTU'),('FID','FID')])
def test_explicit_connect_identifies_profiles_and_sends_no_commands(app,tmp_path,monkeypatch,profile,family):
    simulations=[]
    def factory(devices):
        sim=SimulatedBus(devices);simulations.append(sim);return sim
    monkeypatch.setattr('prevex_hmi.gui.worker.SimulatedBus',factory)
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path);w.show()
    try:
        w.connection_screen.profile.setCurrentText(profile);app.processEvents()
        assert w.worker is None
        w.connection_screen.connect_button.click()
        until(app,lambda:w.profile_current and w.snapshot is not None and w.snapshot['quality']=='GOOD')
        assert w.identity['family']==family and w.identity['loaded_profile']==profile
        assert w.gauge.isVisibleTo(w) and w.connection_established and 'identified' in w.banner.text()
        assert not any(event.get('code') for event in simulations[0].events)
        w.begin('disconnect');until(app,lambda:not w.worker.isRunning())
        assert not w.profile_current and w.pages.currentWidget() is w.connection_screen
        assert 'Last Connected:' in w.connection_screen.last.text() and not w.identity and not w.warning.text()
    finally:close(app,w)


def test_unknown_valid_response_does_not_load_saved_dashboard(app,tmp_path,monkeypatch):
    sims=[]
    def unknown(devices):
        sim=SimulatedBus(devices);sim.set_fault(devices[0].addressing.packet_address,'unknown_identity');sims.append(sim);return sim
    monkeypatch.setattr('prevex_hmi.gui.worker.SimulatedBus',unknown)
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path);w.show()
    try:
        w.connection_screen.connect_button.click();until(app,lambda:bool(w.identity) and not w.worker.isRunning())
        assert w.identity['communication_ok'] and not w.profile_current
        assert w.connection_screen.title.text()=='Analyzer Type Unknown'
        assert not w.gauge.isVisibleTo(w) and all(not b.isEnabled() for b in w.command_buttons.values())
        assert w.connection_screen.profile.isEnabled() and not w.last_connected
        assert not any(event.get('code') for event in sims[0].events)
    finally:close(app,w)


def test_loss_requires_fresh_identity_before_recovery(app,tmp_path,monkeypatch):
    from prevex_hmi.gui.worker import detect
    calls=[]
    def identification(*args,**kwargs):
        result=detect(*args,**kwargs);calls.append(result);return result
    monkeypatch.setattr('prevex_hmi.gui.worker.detect',identification)
    settings=load_settings(tmp_path/'settings.json');settings['devices'][0]['interval']=.25
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path);w.show();w.begin('connect')
    try:
        until(app,lambda:w.profile_current and w.snapshot is not None and w.snapshot['quality']=='GOOD')
        w.trend_window.mode.setCurrentIndex(w.trend_window.mode.findData('automatic'));w.trend_window.start_button.click()
        until(app,lambda:bool(w.recording_status.get('session')));session=w.recording_status['session']
        w.worker.request('fault','timeout');until(app,lambda:w.link_state=='lost' and not w.profile_current)
        assert w.connection_screen.title.text()=='Connection Lost' and 'Last Connected:' in w.connection_screen.last.text()
        assert not w.identity and not w.gauge.isVisibleTo(w) and not w.command_scroll.isVisibleTo(w)
        assert all(not b.isEnabled() for b in w.command_buttons.values()) and not w.warning.text()
        w.worker.request('fault','none');until(app,lambda:w.profile_current and w.connection_established,timeout=12)
        assert len(calls)>=2 and w.identity['revalidated'] and w.snapshot['identity_current']
        until(app,lambda:w.recording_status.get('session')==session and w.recording_status['state']=='Recording')
    finally:close(app,w)


def test_disconnect_then_connect_different_model_drops_all_old_state(app,tmp_path):
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path);w.show();w.begin('connect')
    try:
        until(app,lambda:w.profile_current and w.snapshot is not None)
        previous=w.worker;w.begin('disconnect');until(app,lambda:not previous.isRunning())
        assert not w.identity and w.snapshot is None and not w.warning.text()
        w.connection_screen.profile.setCurrentText('FID');app.processEvents();w.connection_screen.connect_button.click()
        until(app,lambda:w.profile_current and w.snapshot is not None and w.snapshot['config']['family']=='FID')
        assert w.worker is not previous and w.identity['model'].startswith('SNR65')
        assert w.snapshot_family[0]=='FID' and 15 not in w.readouts
        assert 'LEL 700' not in w.identity_label.text()
    finally:close(app,w)


def test_historical_diagnostics_and_csv_remain_available_without_connection(app,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from prevex_hmi.logging_db.store import Historian
    from prevex_hmi.logging_db.recordings import RecordingStore
    from test_recording_sessions import sample,stamp
    db=Historian(tmp_path/'simulation.sqlite3');db.command_audit('unit','operator',0x200,'SENT_UNVERIFIED','Historical acknowledged reset');db.event(stamp(),'unit','Historical fault','GOOD');db.close()
    store=RecordingStore(tmp_path/'simulation.sqlite3');sid,parameters=store.start(sample(),1,False,'manual',stamp(),selected=[1]);store.append(sid,sample(),parameters,{},stamp());store.end(sid,'Stopped',stamp(1));store.close()
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path);w.show()
    try:
        w.show_diagnostics();until(app,lambda:w.audit_table.rowCount()==1 and w.event_table.rowCount()==1)
        assert not w.worker and not w.profile_current
        w.open_trend();t=w.trend_window;t.refresh_sessions();until(app,lambda:t.session_choice.count()==1)
        assert t.session_choice.currentData()['id']==sid
        target=tmp_path/'offline-export.csv';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a:(str(target),'CSV (*.csv)'))
        t.export_scope.setCurrentIndex(1);t.export();until(app,lambda:target.exists())
        assert 'Capture timestamp UTC' in target.read_text(encoding='utf-8-sig') and w.worker is None
    finally:close(app,w)
