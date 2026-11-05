"""Four-family Service settings, simulator only; serial opening is forbidden."""
from dataclasses import asdict,replace
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QMessageBox
from prevex_hmi.devices.configuration import default_devices,load_settings
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.parameters import definitions,definition,encode,validate_word,limits
from prevex_hmi.gui.parameter_editor import ParameterEditor
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.commands import CommandController
from prevex_hmi.communication.parameters import ParameterAdjustments
from prevex_hmi.communication.serial_transport import ReadOnlySerialTransport
from prevex_hmi.devices.identification import detect
from prevex_hmi.simulator.bus import SimulatedBus
from prevex_hmi.logging_db.store import Historian
from test_monitoring import app,until

CONFIGS=[default_devices()[0],replace(default_devices()[0],assembly='SNR705',version='7.01',register_profile='700'),default_devices()[1],default_devices()[2]]
CASES=[(c,k) for c in CONFIGS for k in definitions(c)]


@pytest.fixture(autouse=True)
def no_serial(monkeypatch):
    def forbidden(*a,**k):raise AssertionError('No serial access in simulator tests')
    monkeypatch.setattr(ReadOnlySerialTransport,'__init__',forbidden)


@pytest.mark.parametrize('config,key',CASES,ids=[f'{c.assembly}-{k}' for c,k in CASES])
def test_every_menu_read_write_policy_and_audit(app,tmp_path,config,key):
    spec=definition(config,key)
    sim=SimulatedBus([config]);target=sim.devices[config.addressing.packet_address]
    bus=BusEngine(sim,sleep=lambda _:None);store=Historian(tmp_path/'settings.sqlite3')
    users=SimpleNamespace(resolve=lambda token:('test',token))
    controller=CommandController(bus,config,store,users,identity_verified=True,expected_identity=detect(bus,config.addressing))
    service=ParameterAdjustments(controller)
    raw=target.raw[spec.number]
    if key=='latches' and not spec.reason:raw=target.raw[17]=0xA5A7
    editor=ParameterEditor(config,key,raw)
    try:
        assert spec.title in editor.windowTitle()
        assert len(editor.checks)==len(spec.relays)
        assert [check.isChecked() for check in editor.checks]==[bool(raw&(1<<b)) for b,n in spec.relays]
        before=len(bus.traffic)
        if spec.reason:
            assert not editor.save_button.isEnabled()
            assert all(not check.isEnabled() for check in editor.checks)
            with pytest.raises(PermissionError):encode(config,key,1,previous=raw)
            result=service.execute(key,1,raw,'Administrator',confirmed=True)
            assert result=={} and len(bus.traffic)==before
            assert store.audit_rows()[0][4]=='REJECTED'
        else:
            assert editor.save_button.isEnabled()
            proposed=2 if key=='cal_time' else 0 if spec.mask==1 else 15 if spec.mask else 35 if key=='warning' else 55 if key=='danger' else 120
            expected=encode(config,key,proposed,previous=raw)
            assert service.execute(key,proposed,raw,'Administrator',confirmed=True)=={spec.number:expected}
            assert target.raw[spec.number]==expected and store.audit_rows()[0][4]=='VERIFIED_SIMULATED'
            writes=[t for t in bus.traffic if t['direction']=='TX' and t['family']=='SIMULATED_PARAMETER']
            assert len(writes)==1 and writes[0]['register']==spec.number
            if spec.mask:assert expected & ~spec.mask==raw & ~spec.mask
    finally:editor.close();bus.close();store.close()


@pytest.mark.parametrize('config',CONFIGS)
@pytest.mark.parametrize('role',['Guest','Viewer','Operator'])
def test_only_administrator_can_write(tmp_path,config,role):
    sim=SimulatedBus([config]);bus=BusEngine(sim,sleep=lambda _:None);store=Historian(tmp_path/'test.sqlite3')
    users=SimpleNamespace(resolve=lambda t:('test',role))
    service=ParameterAdjustments(CommandController(bus,config,store,users,identity_verified=True))
    try:
        assert service.execute('cal_time',2,1,'token',confirmed=True)=={}
        assert not bus.traffic and store.audit_rows()[0][4]=='REJECTED'
    finally:bus.close();store.close()


def test_independent_700_map_and_quantization():
    c=CONFIGS[1]
    assert limits(c,'span_temperature')==(50,150)
    assert encode(c,'span_temperature',120)==491
    assert encode(CONFIGS[0],'span_temperature',120)==491
    assert profile_for(c).register(56).scale('LEL',c.context)[0] != profile_for(CONFIGS[0]).register(56).scale('LEL',CONFIGS[0].context)[0]
    assert {definitions(c)[k].number for k in ('warning_latch','danger_latch','fault_latch')}=={72,73,74}
    with pytest.raises(PermissionError):encode(c,'latches',7,previous=7)
    with pytest.raises(PermissionError):encode(c,'warning_latch',1,previous=0x8001)
    with pytest.raises(ValueError):encode(c,'warning_latch',2,previous=0)
    with pytest.raises(PermissionError):validate_word(CONFIGS[0],'latches',0,previous=0xA5A7)


@pytest.mark.parametrize('config',CONFIGS)
def test_refresh_success_error_and_read_only(app,config):
    requests=[]
    editor=ParameterEditor(config,'failsafe',7,refresh=lambda:requests.append(True))
    editor.refresh_button.click()
    assert requests==[True] and editor.current_raw is None and not editor.save_button.isEnabled()
    editor.set_raw(None,'Timed out')
    assert 'Communication error' in editor.read_status.text() and editor.refresh_button.isEnabled()
    editor.refresh_button.click();editor.set_raw(5)
    assert [c.isChecked() for c in editor.checks[:3]]==[True,False,True]
    assert not editor.save_button.isEnabled() and 'Read-only' in editor.access_note.text()
    editor.reject();assert editor.result()==QDialog.Rejected


@pytest.mark.parametrize('config',CONFIGS)
def test_fresh_read_through_worker_and_complete_service_menus(app,tmp_path,config,monkeypatch):
    settings=load_settings(tmp_path/'settings.json')
    settings.update(mode='simulation',analyzer_selection='Auto Detect',simulated_family=config.family,simulated_lel_revision='700' if profile_for(config).revision=='700' else 'legacy',devices=[asdict(config)])
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    w.users.create_user('admin','test-password');w.session=w.users.authenticate('admin','test-password')
    w.start_worker();results=[]
    w.worker.parameter_read.connect(results.append)
    try:
        until(app,lambda:w.snapshot is not None and w.connection_established and 28 in w.snapshot['raw'],timeout=15)
        assert set(w.parameter_menus)=={s.number for s in definitions(config).values()}
        for key,spec in definitions(config).items():
            w.request('parameter_read',key)
            until(app,lambda:any(r['key']==key for r in results),timeout=5)
            result=next(r for r in results if r['key']==key)
            assert 'error' not in result and type(result['raw']) is int
        # Opening FAILSAFE and even programmatically accepting cannot send a write.
        sends=[];original=w.request
        def request(*args):
            sends.append(args);original(*args)
        monkeypatch.setattr(w,'request',request)
        def accept_read_only(dialog):
            QTimer.singleShot(150,dialog.accept)
            return QDialog.exec(dialog)
        monkeypatch.setattr(ParameterEditor,'exec',accept_read_only)
        w.edit_parameter('failsafe')
        assert not any(s[0]=='parameter' for s in sends)
        # Normal saves still use the same confirmed single-write/readback workflow.
        w.request('parameter','cal_time',2,w.snapshot['raw'][28],w.session,True)
        until(app,lambda:'readback verified' in w.command_proof.text(),timeout=8)
        until(app,lambda:w.snapshot['raw'][28]==2,timeout=5)
    finally:
        w.close();until(app,lambda:not w.worker.isRunning());app.processEvents()


@pytest.mark.parametrize('config',CONFIGS[2:])
def test_family_specific_units_without_invented_limits(app,config):
    key='span_voltage' if config.family=='FID' else 'span_temperature'
    raw=819 if config.family=='FID' else 512
    editor=ParameterEditor(config,key,raw)
    assert ('VDC' if config.family=='FID' else 'degC') in editor.current_label.text()
    assert not editor.save_button.isEnabled() and editor.value is None
    if config.family=='FID':
        assert definitions(config)['span_voltage'].title=='SPAN VDC'
        with pytest.raises(PermissionError):encode(config,'span_temperature',120)
    else:assert definitions(config)['warning'].title=='LO ALARM'

@pytest.mark.parametrize('config,key',[(c,k) for c,k in CASES if not definition(c,k).reason])
def test_documented_ranges_reject_outside_endpoints(config,key):
    low,high=limits(config,key)
    for value in (low-1,high+1):
        with pytest.raises(ValueError):encode(config,key,value,previous=0)
    for value in (low,high):
        raw=encode(config,key,value,previous=0)
        assert validate_word(config,key,raw,previous=0)==raw


@pytest.mark.parametrize('config',CONFIGS[1:])
def test_unvalidated_physical_profiles_reject_before_io(tmp_path,config):
    # A stand-in physical transport, never initialized and never opens a port.
    class Physical:
        trace=lambda *a:None
        def close(self):pass
        def read(self,*a):raise AssertionError('Physical I/O forbidden')
    bus=BusEngine(Physical(),sleep=lambda _:None);store=Historian(tmp_path/'test.sqlite3')
    users=SimpleNamespace(resolve=lambda t:('test','Administrator'))
    service=ParameterAdjustments(CommandController(bus,config,store,users,identity_verified=True))
    try:
        assert service.execute('cal_time',2,1,'admin',confirmed=True)=={}
        assert not bus.traffic and store.audit_rows()[0][4]=='REJECTED'
    finally:bus.close();store.close()


def test_700_uses_lock_state_27_not_lock_setting_60(tmp_path):
    config=CONFIGS[1];sim=SimulatedBus([config]);target=sim.devices[config.addressing.packet_address]
    bus=BusEngine(sim,sleep=lambda _:None);store=Historian(tmp_path/'test.sqlite3')
    users=SimpleNamespace(resolve=lambda t:('test','Administrator'))
    service=ParameterAdjustments(CommandController(bus,config,store,users,identity_verified=True,expected_identity=detect(bus,config.addressing)))
    try:
        target.raw[27]=1;target.raw[60]=0
        assert service.execute('cal_time',2,1,'admin',confirmed=True)=={}
        assert not any(t['family']=='SIMULATED_PARAMETER' for t in bus.traffic)
        target.raw[27]=0;target.raw[60]=3
        assert service.execute('cal_time',2,1,'admin',confirmed=True)=={28:2}
    finally:bus.close();store.close()
