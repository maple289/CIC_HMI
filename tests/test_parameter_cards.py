"""Named-setting safety, worker readback and per-card editor regressions. No serial I/O."""
from dataclasses import asdict,replace
from types import SimpleNamespace
import time
import pytest
from PySide6.QtWidgets import QDialog,QMessageBox
from prevex_hmi.devices.configuration import default_devices,load_settings
from prevex_hmi.devices.identification import detect
from prevex_hmi.communication.commands import CommandController
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.parameters import ParameterAdjustments
from prevex_hmi.communication.serial_transport import ReadOnlySerialTransport
from prevex_hmi.logging_db.store import Historian
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.parameters import PARAMETERS,encode,limits
from prevex_hmi.gui.parameter_editor import ParameterEditor
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.simulator.bus import SimulatedBus
from test_connection_warning_layout import app
from test_monitoring import until


@pytest.fixture
def service(tmp_path):
    config=default_devices()[0]
    sim=SimulatedBus([config]);bus=BusEngine(sim,sleep=lambda _:None)
    store=Historian(tmp_path/'test.sqlite3')
    users=SimpleNamespace(resolve=lambda token:('test',{'admin':'Administrator','operator':'Operator'}.get(token,'Viewer')))
    c=CommandController(bus,config,store,users,identity_verified=True,expected_identity=detect(bus,config.addressing))
    yield ParameterAdjustments(c),sim.devices[config.addressing.packet_address]
    bus.close();store.close()


@pytest.mark.parametrize('token',['operator','admin'])
@pytest.mark.parametrize('key,value',[('cal_time',4),('span_temperature',125),('warning',35),('danger',55),('latches',15)])
def test_named_adjustments_have_fresh_readback_and_audit(service,key,value,token):
    s,target=service;n=PARAMETERS[key][0];old=target.raw[n]
    if key=='latches':old=target.raw[n]=0xA5A7
    result=s.execute(key,value,old,token,confirmed=True)
    expected=encode(target.config,key,value,previous=old)
    assert result=={n:expected} and target.raw[n]==expected
    rows=s.controller.store.audit_rows()
    assert rows[0][4]=='VERIFIED_SIMULATED' and rows[1][4]=='SENDING'
    writes=[r for r in s.controller.bus.traffic if r['direction']=='TX' and r['family']=='SIMULATED_PARAMETER']
    assert len(writes)==1 and writes[0]['register']==n
    if key=='latches':assert target.raw[n]&~15==0xA5A0
    s.execute(key,value,expected,'admin',confirmed=True)
    assert s.controller.store.audit_rows()[0][4]=='REJECTED'


@pytest.mark.parametrize('failure',['viewer','confirmation','lock','bad_lock','busy','bad_status','identity','pending','unknown','changed','range','alarm_order','unsupported','revoked'])
def test_preflight_blocks_without_simulated_write(service,failure):
    s,target=service;c=s.controller;key='cal_time';value=2;token='admin';confirmed=True
    expected=target.raw[28]
    if failure in ('viewer','operator'):token=failure
    elif failure=='confirmation':confirmed=False
    elif failure=='lock':target.raw[60]=1
    elif failure=='bad_lock':target.raw[60]=0x2020
    elif failure=='busy':target.forced_status=4
    elif failure=='bad_status':target.forced_status=65535
    elif failure=='identity':c.identity_verified=False
    elif failure=='pending':c.pending=object()
    elif failure=='unknown':c.ambiguous=True
    elif failure=='changed':expected=3
    elif failure=='range':value=5
    elif failure=='alarm_order':key='warning';value=60;expected=target.raw[5]
    elif failure=='unsupported':key='failsafe'
    elif failure=='revoked':
        calls=[]
        def resolve(token):
            calls.append(token);return ('test','Administrator' if len(calls)==1 else 'Viewer')
        c.users.resolve=resolve
    s.execute(key,value,expected,token,confirmed=confirmed)
    assert c.store.audit_rows()[0][4]=='REJECTED'
    assert not any(r.get('family')=='SIMULATED_PARAMETER' for r in c.bus.traffic)


@pytest.mark.parametrize('key,value',[('cal_time',1.5),('cal_time',0),('cal_time',5),('span_temperature',104),('span_temperature',141),('warning',4),('danger',61),('latches',16),('cal_time','NaN')])
def test_invalid_input_is_rejected_before_quantizing(service,key,value):
    s,target=service
    with pytest.raises(ValueError):encode(target.config,key,value,previous=target.raw[PARAMETERS[key][0]])


@pytest.mark.parametrize('model,expected',[('SNR671',(105,140)),('SNR672P',(68,140)),('SNR674PL',(68,140)),('SNR675D',(50,70)),('SNR675K',(50,70))])
def test_model_specific_span_limits(model,expected):
    config=replace(default_devices()[0],assembly=model)
    assert limits(config,'span_temperature')==expected


@pytest.mark.parametrize('failure',['timeout','mismatch'])
def test_post_write_failure_is_unknown_and_blocks_other_actions(service,monkeypatch,failure):
    s,target=service;c=s.controller;original=c.bus.read;written=[];send=c.bus.simulated_parameter
    def write(*args,**kwargs):send(*args,**kwargs);written.append(True)
    def read(profile,addressing,start,count):
        if written and start==28:
            if failure=='timeout':raise TimeoutError('lost readback')
            return {28:1}
        return original(profile,addressing,start,count)
    monkeypatch.setattr(c.bus,'simulated_parameter',write);monkeypatch.setattr(c.bus,'read',read)
    s.execute('cal_time',2,1,'admin',confirmed=True)
    assert len(written)==1 and c.ambiguous and c.store.audit_rows()[0][4]=='UNKNOWN'
    s.execute('danger',55,target.raw[6],'admin',confirmed=True)
    assert len(written)==1 and c.store.audit_rows()[0][4]=='REJECTED'


def test_physical_transport_never_receives_setting_or_constructs_writer(service):
    s,target=service;sim=s.controller.bus.transport
    physical=object.__new__(ReadOnlySerialTransport)
    s.controller.bus.transport=physical
    try:
        assert s.execute('cal_time',2,1,'admin',confirmed=True)=={}
        assert s.controller.store.audit_rows()[0][4]=='REJECTED'
        with pytest.raises(PermissionError):s.controller.bus.simulated_parameter(target.config,'cal_time',2,previous=1)
        assert not hasattr(physical,'adjust_parameter')
    finally:s.controller.bus.transport=sim


def test_offline_request_is_audited_without_io(service):
    s,target=service;before=len(s.controller.bus.traffic)
    s.execute('cal_time',2,1,'admin',confirmed=True,current=False)
    assert len(s.controller.bus.traffic)==before
    assert s.controller.store.audit_rows()[0][4]=='REJECTED'


def test_parameter_dialog_cancel_and_latch_bits(app):
    config=default_devices()[0]
    dialog=ParameterEditor(config,'latches',0xA5A7)
    assert dialog.proposed()==7
    dialog.checks[3].setChecked(True);assert dialog.proposed()==15
    dialog.reject();assert dialog.result()==QDialog.Rejected
    blocked=ParameterEditor(config,'cal_time',1,reason='Physical adjustments disabled')
    assert not blocked.save_button.isEnabled()


def test_categories_menus_and_stale_confirmation(app,tmp_path,monkeypatch):
    config=default_devices()[0];settings=load_settings(tmp_path/'settings.json')
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    sim=SimulatedBus([config]);target=sim.devices[config.addressing.packet_address];target.update(time.monotonic())
    bus=BusEngine(sim,sleep=lambda _:None)
    snapshot=dict(config=asdict(config),raw=target.raw.copy(),quality='GOOD',register_ages={n:0 for n in target.raw},age=0,last_success='2026-10-26',error='',control={'verified':True})
    try:
        w.update_data(snapshot,bus.diagnostics())
        assert set(w.readout_groups)=={'Gauges','Calibration parameters','Alarm settings'}
        assert 1 not in w.readouts and 50 not in w.readouts
        assert {7,28,29,30,56,5,6,17,18}<=w.readouts.keys()
        assert set(w.parameter_menus)=={5,6,17,28,56}
        assert all(len(button.menu().actions())==1 for button in w.parameter_menus.values())
        assert 18 not in w.parameter_menus
        calls=[]
        monkeypatch.setattr(w,'parameter_access_reason',lambda key:'')
        monkeypatch.setattr(w,'request',lambda *args:calls.append(args))
        monkeypatch.setattr('prevex_hmi.gui.parameter_editor.ParameterEditor.exec',lambda d:QDialog.Accepted)
        monkeypatch.setattr('prevex_hmi.gui.parameter_editor.ParameterEditor.proposed',lambda d:2)
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.No)
        w.edit_parameter('cal_time');assert not calls
        def changed(*args):w.snapshot['raw'][28]=3;return QMessageBox.Yes
        monkeypatch.setattr(QMessageBox,'question',changed)
        w.edit_parameter('cal_time');assert not calls
        w.snapshot['raw'][28]=1
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
        w.edit_parameter('cal_time')
        assert calls==[('parameter','cal_time',2,1,w.session,True)]
    finally:w.close();bus.close();app.processEvents()


def test_live_worker_adjusts_simulator_and_publishes_readback(app,tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Physical transport must never be opened')
    monkeypatch.setattr(ReadOnlySerialTransport,'__init__',forbidden)
    settings=load_settings(tmp_path/'settings.json')
    settings.update(analyzer_selection='LEL 670 Series',simulated_lel_revision='legacy',devices=[asdict(default_devices()[0])])
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    w.users.create_user('test-admin','test-password')
    w.session=w.users.authenticate('test-admin','test-password')
    w.start_worker()
    try:
        until(app,lambda:w.snapshot is not None and 60 in w.snapshot['raw'] and 28 in w.snapshot['raw'],timeout=12)
        assert not w.parameter_access_reason('cal_time'), (w.parameter_access_reason('cal_time'),w.users.resolve(w.session),w.snapshot)
        w.request('parameter','cal_time',2,w.snapshot['raw'][28],w.session,True)
        until(app,lambda:'fresh simulated FC03 readback verified' in w.command_proof.text(),timeout=8)
        until(app,lambda:w.snapshot['raw'].get(28)==2)
        assert not w.command_dispatching and not w.snapshot['control']['ambiguous']
    finally:
        w.close();until(app,lambda:not w.worker.isRunning());app.processEvents()
