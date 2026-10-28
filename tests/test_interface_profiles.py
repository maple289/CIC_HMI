"""Interface/series regressions using synthetic data only; no physical I/O."""
from dataclasses import asdict, replace
import copy
import os
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication
from prevex_hmi.devices.configuration import default_devices,load_settings
from prevex_hmi.devices.identification import Identification,detect,resolve_profile
from prevex_hmi.gui.connection_dialog import AnalyzerChoice
from prevex_hmi.gui.gauge import CircularGauge
from prevex_hmi.gui.presentation import measurement
from prevex_hmi.gui.serial_ports import SerialPortChoice,require_available_port
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.profiles import profile_for,profile_name
from prevex_hmi.profiles.lel700 import TYPES
from prevex_hmi.profiles.lel670 import MODELS
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.simulator.bus import SimulatedBus


@pytest.fixture
def app():
    result=QApplication.instance() or QApplication([])
    result.setQuitOnLastWindowClosed(False)
    return result


def sample(value=0):
    config=default_devices()[0]
    return dict(config=asdict(config),quality='GOOD',raw={1:round(value*256)&65535,2:0,3:100,4:0},
                register_ages={1:0},age=0,last_success='2026-10-24T12:00:00+00:00',error='')


def test_port_scan_refresh_missing_selection_and_connection_guard(app,monkeypatch):
    ports=[SimpleNamespace(device='COM4',description='USB Serial Port'),SimpleNamespace(device='COM1',description='Built-in UART')]
    monkeypatch.setattr('prevex_hmi.gui.serial_ports.list_ports.comports',lambda:ports)
    chooser=SerialPortChoice('COM4')
    assert chooser.is_valid() and chooser.text()=='COM4'
    assert 'USB Serial Port' in chooser.combo.currentText()
    ports.pop(0);chooser.refresh()
    assert chooser.text()=='COM4' and not chooser.is_valid() and 'unavailable' in chooser.combo.currentText()
    with pytest.raises(ValueError):require_available_port('COM4')
    chooser.combo.setCurrentIndex(chooser.combo.findData('COM1'))
    assert chooser.is_valid()
    ports.clear();chooser.refresh();assert not chooser.is_valid()
    chooser.close()


def test_port_settings_preserve_other_serial_fields(app,tmp_path,monkeypatch):
    monkeypatch.setattr('prevex_hmi.gui.serial_ports.list_ports.comports',lambda:[SimpleNamespace(device='COM8',description='Adapter')])
    settings=load_settings(tmp_path/'settings.json')
    settings['mode']='hardware';settings['connection'].update(port='COM8',parity='N',bytesize=8,stopbits=1)
    dialog=AnalyzerChoice(settings)
    assert dialog.settings()['connection']==settings['connection']
    dialog.close()


def test_no_port_prevents_worker_creation(app,tmp_path,monkeypatch):
    from prevex_hmi.communication.hardware_session import ReadOnlyControllerGrant
    monkeypatch.setattr('prevex_hmi.gui.serial_ports.list_ports.comports',lambda:[])
    settings=load_settings(tmp_path/'settings.json');settings['mode']='hardware'
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False,hardware_grant=ReadOnlyControllerGrant())
    w.start_worker()
    assert w.worker is None and 'available COM port' in w.warning.text()
    w.close()


@pytest.mark.parametrize('action',['connect','test'])
@pytest.mark.parametrize('port',['COM4','COM7'])
def test_normal_controls_use_available_ports_without_session_grants(app,tmp_path,monkeypatch,action,port):
    from prevex_hmi.gui.worker import MonitoringWorker
    from test_monitoring import until
    settings=load_settings(tmp_path/'settings.json');settings['mode']='hardware'
    settings['connection'].update(port=port,baud=9600)
    calls=[]
    class Capture(MonitoringWorker):
        def run(self):calls.append((self.settings['connection']['port'],self.hardware_grant,self.test_only))
    monkeypatch.setattr('prevex_hmi.gui.window.MonitoringWorker',Capture)
    monkeypatch.setattr('prevex_hmi.gui.window.require_available_port',lambda selected:None if selected==port else pytest.fail('Unexpected port'))
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    w.begin(action)
    until(app,lambda:bool(calls) and not w.worker.isRunning())
    assert calls==[(port,None,action=='test')]
    assert w.hardware_grant is None and 'HARDWARE' in w.banner.text() and 'Connected - identified' not in w.banner.text()
    w.close();app.processEvents()



def test_explicit_legacy_bench_api_prepares_only_authorized_session_without_saving_grant(app,tmp_path,monkeypatch):
    settings=load_settings(tmp_path/'settings.json');original=copy.deepcopy(settings)
    path=tmp_path/'settings.json';saved=path.read_bytes()
    w=MainWindow(settings,path,tmp_path,start_worker=False)
    calls=[]
    monkeypatch.setattr(w,'start_worker',lambda **kwargs:calls.append((copy.deepcopy(w.settings),w.hardware_grant)))
    w.start_controller_bench()
    assert len(calls)==1
    prepared,grant=calls[0]
    assert grant.operator_commands and prepared['mode']=='hardware'
    assert prepared['connection']['port']=='COM4' and prepared['connection']['baud']==9600
    assert prepared['devices'][0]['assembly']=='SNR671' and prepared['devices'][0]['address']==1
    assert prepared['devices'][0]['register_profile']=='fta_4x'
    assert settings==original and path.read_bytes()==saved
    from prevex_hmi.devices.models import DeviceConfig
    grant.validate(prepared,DeviceConfig(**prepared['devices'][0]))
    prepared['connection']['port']='COM5'
    with pytest.raises(PermissionError):grant.validate(prepared,DeviceConfig(**prepared['devices'][0]))
    w.close()


def test_test_connection_is_readonly_and_port_change_drops_bench_capability(app,tmp_path,monkeypatch):
    from prevex_hmi.communication.hardware_session import ReadOnlyControllerGrant,controller_bench_settings
    from prevex_hmi.gui.worker import MonitoringWorker
    from test_monitoring import until
    settings=controller_bench_settings(load_settings(tmp_path/'settings.json'))
    calls=[]
    class Capture(MonitoringWorker):
        def run(self):calls.append((self.hardware_grant,self.test_only))
    monkeypatch.setattr('prevex_hmi.gui.window.MonitoringWorker',Capture)
    monkeypatch.setattr('prevex_hmi.gui.window.require_available_port',lambda _:None)
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False,hardware_grant=ReadOnlyControllerGrant(operator_commands=True))
    w.start_worker(test_only=True)
    until(app,lambda:bool(calls) and not w.worker.isRunning())
    assert calls[0][1] and not calls[0][0].operator_commands
    w.settings['connection']['port']='COM7';w.begin('connect')
    until(app,lambda:len(calls)==2 and not w.worker.isRunning())
    assert calls[1]==(None,False) and w.hardware_grant is None
    w.close();app.processEvents()


def test_hold_is_four_seconds_display_only_keeps_zero_and_recovers(app,monkeypatch):
    now=[100.0]
    monkeypatch.setattr('prevex_hmi.gui.gauge.time',SimpleNamespace(monotonic=lambda:now[0]))
    gauge=CircularGauge();snapshot=sample(0);gauge.set_snapshot(snapshot)
    assert gauge.state.reading=='0.00'
    now[0]=101;snapshot['quality']='OFFLINE';gauge.set_snapshot(snapshot)
    assert gauge.state.value==0 and gauge.held and gauge.display_quality=='RETAINED_STALE'
    assert measurement(snapshot)[0] is None
    now[0]=103.99;gauge.expire();assert gauge.state.value==0
    now[0]=104.01;gauge.expire();assert gauge.state.reading=='--'
    gauge.set_snapshot(sample(-20));assert gauge.state.value==-20 and not gauge.held
    assert gauge.display_quality=='CURRENT'
    gauge.close()


def test_hold_age_never_renews_on_cached_words_and_switch_clears(app,monkeypatch):
    now=[100.0]
    monkeypatch.setattr('prevex_hmi.gui.gauge.time',SimpleNamespace(monotonic=lambda:now[0]))
    gauge=CircularGauge();snapshot=sample(12);snapshot['register_ages'][1]=3
    gauge.set_snapshot(snapshot)
    now[0]=100.5;snapshot['register_ages'][1]=3.5;gauge.set_snapshot(snapshot)
    now[0]=101.01;gauge.expire();assert gauge.state.reading=='--'
    gauge.set_snapshot(sample(12))
    other=sample();other['config']['id']='other';other['quality']='OFFLINE'
    gauge.set_snapshot(other);assert gauge.state.reading=='--'
    gauge.close()


@pytest.mark.parametrize('lcd_text',[b'TC2 FAIL  ',b'          '])
def test_native_fault_flashing_has_no_retained_measurement_in_data_pipeline(app,monkeypatch,lcd_text):
    from test_hardware_monitoring import RAW
    now=[100.0]
    monkeypatch.setattr('prevex_hmi.gui.gauge.time',SimpleNamespace(monotonic=lambda:now[0]))
    config=replace(default_devices()[0],assembly='SNR671',version='4.81',register_profile='fta_4x')
    snapshot=sample();snapshot.update(config=asdict(config),raw=dict(RAW))
    gauge=CircularGauge();gauge.set_snapshot(snapshot);assert gauge.state.value==-99
    data=lcd_text
    snapshot['raw'].update({51+i//2:int.from_bytes(data[i:i+2],'big') for i in range(0,10,2)})
    now[0]=102;gauge.set_snapshot(snapshot)
    assert gauge.state.value==-99 and gauge.held
    assert measurement(snapshot)[0] is None and 'fault_lcd_reading' not in snapshot
    now[0]=104.1;gauge.expire()
    assert gauge.state.value==-99 and gauge.lcd_hold
    now[0]=108.1;gauge.expire()  # No fresh LCD/communication replies arrived.
    assert gauge.state.reading=='--'
    gauge.close()


def test_recorded_live_blank_lcd_reply_is_valid_communication_not_a_measurement():
    from prevex_hmi.communication.protocol import decode_read
    config=replace(default_devices()[0],assembly='SNR671',version='4.81',register_profile='fta_4x')
    snapshot=sample();snapshot['config']=asdict(config)
    snapshot['raw'].update({1:0x8001,2:20,4:12})
    numeric='01 03 0C 6A 00 2D 39 39 20 25 4C 46 4C 20 20 9D E9'
    blank='01 03 0C 6A 00 20 20 20 20 20 20 20 20 20 20 24 2C'
    for frame,expected in ((numeric,-99),(blank,None),(numeric,-99)):
        words=decode_read(bytes.fromhex(frame),1,6)  # Includes CRC validation.
        snapshot['raw'].update(dict(enumerate(words,50)))
        value,_=measurement(snapshot)
        assert value==expected
        assert snapshot['quality']=='GOOD' and snapshot['raw'][1]==0x8001


def test_connection_is_independent_of_instrument_fault_and_held_gauge(app,tmp_path):
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path,start_worker=False)
    snapshot=sample();snapshot['raw'][2]=25
    w.snapshot=snapshot
    import time
    w.snapshot_received_at=time.monotonic();w.refresh_connection_status()
    assert 'Connection Established' in w.monitor_status.text()
    w.gauge.set_snapshot(snapshot)
    snapshot['quality']='OFFLINE';w.gauge.set_snapshot(snapshot);w.refresh_connection_status()
    assert 'No Connection' in w.monitor_status.text() and w.gauge.held
    snapshot['quality']='GOOD';w.snapshot_received_at=time.monotonic()-20;w.refresh_connection_status()
    assert 'No Connection' in w.monitor_status.text()
    snapshot['config'].update(assembly='SNR705',version='7.01')
    snapshot['raw'][4]=1<<9;w.indicators.update_snapshot(snapshot)
    service=next(label for (group,_),(label,text) in w.indicators.labels.items() if group==1 and text=='Service Needed')
    assert not service.isHidden() and '#efb753' in service.styleSheet() and service.text()=='Service Needed'
    w.close()


def test_command_led_per_button_three_seconds_and_no_completion_retrigger(app,tmp_path):
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path,start_worker=False)
    led_timer=w.command_buttons[0x300].timer;expiry=QSignalSpy(led_timer.timeout)
    receipt=dict(id='one',code=0x300,state='PENDING',reply_received=True,time='now')
    w.show_command_receipt(receipt)
    assert '#39c66c' in w.command_buttons[0x300].led.styleSheet()
    assert '#303b48' in w.command_buttons[0x400].led.styleSheet()
    assert led_timer.interval()==3000 and led_timer.isSingleShot() and led_timer.isActive()
    # A loaded Windows runner may dispatch a precise Qt timer late. Observe
    # the actual event with a bounded timeout instead of assuming 100ms slack.
    if expiry.count()==0:assert expiry.wait(8000)
    assert expiry.count()==1 and not led_timer.isActive()
    assert '#303b48' in w.command_buttons[0x300].led.styleSheet()
    receipt['state']='COMPLETED_SIMULATED';w.show_command_receipt(receipt)
    assert '#303b48' in w.command_buttons[0x300].led.styleSheet()
    assert not led_timer.isActive() and expiry.count()==1
    w.show_command_receipt(dict(id='two',code=0x400,state='REJECTED',reply_received=False))
    assert '#ed575d' in w.command_buttons[0x400].led.styleSheet()
    w.invalidate();assert '#303b48' in w.command_buttons[0x400].led.styleSheet()
    w.close()


@pytest.mark.parametrize('model',sorted(TYPES.values()))
def test_all_documented_700_models_detect_from_numeric_registers(model):
    config=replace(default_devices()[0],assembly=model,version='7.01')
    bus=BusEngine(SimulatedBus([config]),sleep=lambda _:None)
    try:
        identity=detect(bus,config.addressing)
        raw=bus.transport.devices[1].raw
        assert raw[21]==config.address and raw[33]==0
        assert profile_for(config).register(7).decode(raw[7],'LEL',config.context)[0]==60
        effective,warning,verified=resolve_profile(config,'Auto Detect',identity)
        assert verified and not warning and identity.model==model
        assert profile_name(effective)=='LEL 700 Series'
        assert all(bytes.fromhex(row['hex'])[1]==3 for row in bus.traffic)
        for selected in ('LEL 670 Series','LEL 700 Series'):
            _,warning,verified=resolve_profile(config,selected,identity)
            assert verified==(selected=='LEL 700 Series')
            assert bool(warning)==(selected=='LEL 670 Series')
    finally:bus.close()


@pytest.mark.parametrize('model',sorted(MODELS))
def test_documented_670_model_and_suffix_identification(model):
    config=replace(default_devices()[0],assembly=model)
    bus=BusEngine(SimulatedBus([config]),sleep=lambda _:None)
    try:
        identity=detect(bus,config.addressing)
        effective,warning,verified=resolve_profile(config,'LEL 670 Series',identity)
        assert verified and not warning and profile_name(effective)=='LEL 670 Series'
    finally:bus.close()


def test_undocumented_673_and_generic_prevex_do_not_authorize_controls():
    config=default_devices()[0]
    identity=Identification('LEL','SNR673','5.11',verified=True)
    effective,warning,verified=resolve_profile(config,'Auto Detect',identity)
    assert not verified and 'Undocumented' in warning
    assert measurement(dict(config=asdict(effective),raw={1:256},quality='GOOD'))[0] is None
    generic=Identification('LEL',version='7.01')
    _,warning,verified=resolve_profile(config,'LEL 700 Series',generic)
    assert not verified and warning
    assert profile_for(replace(config,version='7.01')).revision=='670'


@pytest.mark.parametrize('series',['670','700'])
@pytest.mark.parametrize('code',[0x300,0x400,0x500,0x600,0x700,0x800,0x900,0xF00])
def test_series_commands_acknowledgment_and_execution_are_separate(tmp_path,series,code):
    from prevex_hmi.communication.commands import CommandController
    from prevex_hmi.logging_db.store import Historian
    from test_identification_commands import Clock
    clock=Clock()
    config=replace(default_devices()[0],assembly='SNR705' if series=='700' else 'SNR675',version='7.01' if series=='700' else '5.11')
    sim=SimulatedBus([config],clock=clock)
    bus=BusEngine(sim,clock=clock,sleep=clock.sleep)
    store=Historian(tmp_path/'commands.sqlite3')
    try:
        controller=CommandController(bus,config,store,SimpleNamespace(resolve=lambda _:('operator','Operator')),
                                     identity_verified=True,expected_identity=detect(bus,config.addressing),clock=clock)
        controller.execute(code,'token',confirmed=True)
        if series=='700' and code in (0x900,0xF00):
            assert controller.receipt['state']=='REJECTED' and not sim.events
            return
        assert controller.receipt['reply_received']
        packets=[bytes.fromhex(r['hex']) for r in bus.traffic if r['direction']=='TX']
        assert sum(p[1]==6 for p in packets)==1
        if code in range(0x300,0x900,0x100):
            assert controller.pending and controller.receipt['state']=='PENDING'
            for status in (4,5,6,7,0):controller.observe(dict(quality='GOOD',raw={2:status}))
            assert controller.pending is None and controller.receipt['state']=='COMPLETED_SIMULATED'
        elif code==0x900:
            assert controller.receipt['state']=='SENT_UNVERIFIED'
        else:assert controller.receipt['state']=='VERIFIED'
        assert store.audit_rows()
    finally:store.close();bus.close()


def test_delayed_response_timeout_reconnection_and_signed_recovery():
    from test_identification_commands import Clock
    from prevex_hmi.communication.scheduler import PollingScheduler
    clock=Clock();config=replace(default_devices()[0],assembly='SNR705',version='7.01')
    sim=SimulatedBus([config],clock=clock,sleep=clock.sleep)
    bus=BusEngine(sim,clock=clock,sleep=clock.sleep)
    scheduler=PollingScheduler(bus,[config],clock=clock)
    try:
        sim.set_fault(1,'delay');before=clock.now
        scheduler.run_once();assert clock.now-before==pytest.approx(.6)
        assert scheduler.states[config.id].snapshot(clock.now)['quality']=='GOOD'
        sim.set_fault(1,'timeout');clock.now+=10;scheduler.run_once()
        assert scheduler.states[config.id].snapshot(clock.now)['quality']=='OFFLINE'
        sim.set_fault(1,'none');sim.devices[1].forced_reading=-25;clock.now+=20
        scheduler.run_once()
        recovered=scheduler.states[config.id].snapshot(clock.now)
        assert recovered['quality']=='GOOD' and measurement(recovered)[0]==-25
        assert not sim.events
    finally:bus.close()


def test_gui_switches_between_670_and_700_with_one_worker_and_no_old_values(app,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QDialog
    from test_monitoring import until
    settings=load_settings(tmp_path/'settings.json')
    settings.update(analyzer_selection='LEL 670 Series',simulated_lel_revision='legacy')
    settings['devices']=[asdict(default_devices()[0])]
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=True)
    try:
        until(app,lambda:w.snapshot is not None and w.snapshot['quality']=='GOOD')
        assert w.snapshot_family==('LEL','670')
        for series,model in [('700','SNR701D'),('670','SNR674')]:
            previous=w.worker
            target=copy.deepcopy(w.settings)
            target.update(analyzer_selection=f'LEL {series} Series',simulated_lel_revision='700' if series=='700' else 'legacy')
            target['devices'][0].update(id='switch-'+series,assembly=model,version='7.01' if series=='700' else '5.11',register_profile=series)
            class Choice:
                def __init__(self,*_):pass
                def exec(self):return QDialog.Accepted
                def settings(self):return target
            monkeypatch.setattr('prevex_hmi.gui.window.AnalyzerChoice',Choice)
            w.choose_type()
            assert w.snapshot is None and w.gauge.state.reading=='--'
            assert all(label.isHidden() for label,_ in w.indicators.labels.values())
            until(app,lambda:not previous.isRunning())
            assert w.worker is previous  # Saving a profile does not connect.
            w.begin('connect')
            until(app,lambda:w.snapshot is not None and w.snapshot['config']['id']=='switch-'+series and w.snapshot['quality']=='GOOD')
            assert not previous.isRunning() and w.worker is not previous
            assert w.snapshot_family==('LEL',series)
            assert {7,28,29,30,56}<=w.readouts.keys()
            assert (23 in w.readouts)==(series=='670')
            assert not any(button.isEnabled() for button in w.command_buttons.values())
    finally:
        w.close();until(app,lambda:not w.worker.isRunning());app.processEvents()
