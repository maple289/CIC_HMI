"""Physical command API exercised only with fake SDK clients, never a COM port."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from pymodbus.exceptions import ModbusException
from prevex_hmi.communication.serial_transport import ReadOnlySerialTransport,ValidatedOperatingTransport
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.validated_commands import ValidatedOperatingCommands
from prevex_hmi.communication.validated_controls import validated_670,WORDS
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.devices.identification import detect
from prevex_hmi.logging_db.store import Historian


@pytest.fixture(params=['5.12','4.81'])
def control(tmp_path,request):
    state=dict(status=0,lock=0,minutes=4,lost=False,mismatch=False,writes=[],clients=[])
    class Client:
        def __init__(self,**kwargs):
            assert kwargs['retries']==0
            self.connected=False;self.closed=False;state['clients'].append(self)
        def connect(self):self.connected=True;return True
        def close(self):self.connected=False;self.closed=True
        def read_holding_registers(self,pdu,*,count,device_id):
            assert device_id==1
            identity=(b'TYPE FTAVER 4\xa781 SNR671' if request.param=='4.81' else b'LEL VER5.12 SNR675 S/N UNIT1').ljust(32,b' ')
            raw={1:256,2:state['status'],3:100,4:128,28:state['minutes'],60:state['lock'],62:11}
            raw.update({257+i//2:int.from_bytes(identity[i:i+2],'big') for i in range(0,32,2)})
            return SimpleNamespace(isError=lambda:False,registers=[raw.get(n,0) for n in range(pdu+1,pdu+count+1)])
        def write_register(self,pdu,code,*,device_id):
            state['writes'].append((pdu,code,device_id))
            if state['lost']:raise ModbusException('lost echo')
            if code==0xF00:state['lock']|=2
            if code==0x1000:state['lock']&=~2
            return SimpleNamespace(isError=lambda:False,address=pdu+int(state['mismatch']),registers=[code])
    config=replace(default_devices()[0],version=request.param,assembly='SNR671' if request.param=='4.81' else 'SNR675',register_profile='fta_4x' if request.param=='4.81' else '670')
    transport=ReadOnlySerialTransport('COM7',hardware_authorized=True,addressing_reviewed=True,client_factory=Client)
    bus=BusEngine(transport,sleep=lambda _:None)
    identity=detect(bus,config.addressing)
    assert identity.verified
    store=Historian(tmp_path/'commands.sqlite3')
    users=SimpleNamespace(resolve=lambda token:('test',{'admin':'Administrator','operator':'Operator'}.get(token,'Viewer')))
    service=ValidatedOperatingCommands(bus,config,store,users,identity_verified=True,expected_identity=identity,connection=dict(port='COM7',baud=9600,timeout=.5))
    yield service,state,store
    bus.close();store.close()


@pytest.mark.parametrize('code',sorted(WORDS))
def test_documented_words_send_only_register8_once_and_record_receipt(control,code):
    service,state,store=control
    assert type(service.bus.transport) is ReadOnlySerialTransport and not state['writes']
    service.execute(code,'admin',confirmed=True)
    assert state['writes']==[(7,code,1)]
    assert isinstance(service.bus.transport,ValidatedOperatingTransport)
    assert len(state['clients'])==2 and state['clients'][0].closed
    assert service.receipt['reply_received']
    if code in range(0x300,0x900,0x100):
        assert service.pending and service.pending.timeout>=360
        for status in (4,5,6,7,0):service.observe(dict(raw={2:status},quality='GOOD'))
        assert store.audit_rows()[0][4]=='COMPLETED_OBSERVED'
        assert service.receipt['status_after']==0
    elif code in (0xF00,0x1000):assert store.audit_rows()[0][4]=='VERIFIED'
    else:assert store.audit_rows()[0][4]=='SENT_UNVERIFIED'
    service.execute(code,'admin',confirmed=True)
    assert len(state['writes'])==1


@pytest.mark.parametrize('code',[0,0xA00,0xB00,0xC00,0xD00,0xE00,0x1100,0x1700,65535])
def test_prohibited_words_never_construct_writer(control,code):
    service,state,_=control;service.execute(code,'admin',confirmed=True)
    assert not state['writes'] and len(state['clients'])==1


@pytest.mark.parametrize('failure',['role','confirmation','lock','busy','unknown_status','unknown_lock','interval','save_operator','identity'])
def test_preflight_rejects_without_transmission(control,failure):
    service,state,_=control;token='admin';confirmed=True;code=0x300
    if failure=='role':token='viewer'
    elif failure=='confirmation':confirmed=False
    elif failure=='lock':state['lock']=1
    elif failure=='busy':state['status']=4
    elif failure=='unknown_status':state['status']=0x2020
    elif failure=='unknown_lock':state['lock']=0x2020
    elif failure=='interval':state['minutes']=0
    elif failure=='save_operator':token='operator';code=0x900
    elif failure=='identity':service.identity_verified=False
    service.execute(code,token,confirmed=confirmed)
    assert not state['writes'] and len(state['clients'])==1


@pytest.mark.parametrize('failure',['lost','mismatch'])
def test_ambiguous_echo_never_retries(control,failure):
    service,state,store=control;state[failure]=True
    service.execute(0x300,'admin',confirmed=True)
    assert service.ambiguous and store.audit_rows()[0][4]=='UNKNOWN'
    service.execute(0x300,'admin',confirmed=True)
    assert len(state['writes'])==1


@pytest.mark.parametrize('version',['4.80','4.82','5.08','5.11','6.00','7.01','unknown'])
def test_wrong_firmware_never_allowed(version):
    assert not validated_670(replace(default_devices()[0],version=version))


@pytest.mark.parametrize('code,after_role',[(0x300,'Viewer'),(0x900,'Operator')])
def test_revoked_or_reduced_session_during_preflight_never_transmits(control,monkeypatch,code,after_role):
    service,state,_=control;active=[True]
    service.users.resolve=lambda _:('test','Administrator' if active[0] else after_role)
    activate=service.bus.activate_validated_controls
    def switch(*args,**kwargs):
        activate(*args,**kwargs);active[0]=False
    monkeypatch.setattr(service.bus,'activate_validated_controls',switch)
    service.execute(code,'admin',confirmed=True)
    assert not state['writes'] and service.receipt['state']=='REJECTED'
    assert not service.receipt['reply_received'] and not service.ambiguous


def test_cached_precommand_status_is_not_used_for_execution_proof(control):
    service,state,store=control
    service.execute(0x300,'admin',confirmed=True)
    service.observe(dict(raw={2:4},quality='GOOD',register_ages={2:1}))
    assert service.pending and not service.pending.saw_active
    service.observe(dict(raw={2:4},quality='GOOD',register_ages={2:0}))
    assert service.pending.saw_active and store.audit_rows()[0][4]=='STARTED'


@pytest.mark.parametrize('legacy',[False,True])
def test_command_buttons_follow_documented_profile_role_and_lock_state(tmp_path,legacy):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from dataclasses import asdict
    from PySide6.QtWidgets import QApplication
    from prevex_hmi.gui.window import MainWindow
    from prevex_hmi.devices.configuration import load_settings
    app=QApplication.instance() or QApplication([])
    settings=load_settings(tmp_path/'settings.json');settings['mode']='hardware'
    config=replace(default_devices()[0],version='4.81' if legacy else '5.12',assembly='SNR671' if legacy else 'SNR675',register_profile='fta_4x' if legacy else '670')
    settings['devices']=[asdict(config)];settings['connection'].update(port='COM7',baud=9600)
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    w.users.close()
    role=['Administrator']
    w.users=SimpleNamespace(resolve=lambda _:('test',role[0]),close=lambda:None)
    w.worker=SimpleNamespace(isRunning=lambda:True,test_only=False)
    w.snapshot=dict(config=asdict(config),quality='GOOD',raw={2:0,60:0},control=dict(verified=True,pending=False,ambiguous=False,physical_commands=list(WORDS)))
    w.profile_current=True;w.set_connection_status(True)
    try:
        w.update_command_buttons()
        assert {code for code,b in w.command_buttons.items() if b.isEnabled()}==WORDS
        assert w.command_access_button.isHidden()
        w.snapshot['raw'][2]=25;w.update_command_buttons()
        assert all(w.command_buttons[code].isEnabled() for code in range(0x300,0x900,0x100))
        role[0]='Operator';w.update_command_buttons()
        assert not w.command_buttons[0x900].isEnabled() and w.command_buttons[0x300].isEnabled()
        w.snapshot['raw'][60]=1;w.update_command_buttons()
        assert not any(w.command_buttons[code].isEnabled() for code in range(0x300,0x900,0x100))
        assert w.command_buttons[0x100].isEnabled() and w.command_buttons[0x1000].isEnabled()
        role[0]='Viewer';w.update_command_buttons()
        assert not any(b.isEnabled() for b in w.command_buttons.values())
    finally:w.worker=None;w.close();app.processEvents()


@pytest.mark.parametrize('fault',[8,25,26])
@pytest.mark.parametrize('code',[0x300,0x600])
def test_authorized_fault_state_commands_send_once_without_false_outcome(control,fault,code):
    service,state,store=control;state['status']=fault
    service.execute(code,'admin',confirmed=True)
    assert state['writes']==[(7,code,1)] and service.pending and service.receipt['reply_received']
    service.observe(dict(raw={2:fault},quality='GOOD'))
    assert store.audit_rows()[0][4]=='WAITING_STATUS' and service.pending
    count=len(store.audit_rows())
    service.observe(dict(raw={2:fault},quality='GOOD'))
    assert len(store.audit_rows())==count
    if code==0x300:
        for status in (4,6,7,0):service.observe(dict(raw={2:status},quality='GOOD'))
        assert store.audit_rows()[0][4]=='COMPLETED_OBSERVED' and service.pending is None
    else:
        service.clock=lambda:service.pending.started+service.pending.timeout+1
        service.observe(dict(raw={2:fault},quality='GOOD'))
        assert store.audit_rows()[0][4]=='UNKNOWN' and service.pending is None and service.ambiguous
    assert state['writes']==[(7,code,1)]


@pytest.mark.parametrize('text',['TYPE FTAVER 4\xa781 SNR671','TYPE FTAVER 4.81 SNR671','LEL VER4.81 SNR671'])
def test_481_assumption_is_explicit_and_does_not_override_mismatches(text):
    from prevex_hmi.devices.identification import parse_identity,resolve_profile
    from prevex_hmi.profiles import profile_for,commands_for
    from prevex_hmi.communication.protocol import validate_read
    identity=parse_identity(text)
    # Standard ASCII identities still need their normal TYPE cross-check.
    if not identity.legacy_format:identity=replace(identity,verified=True)
    config,warning,ready=resolve_profile(default_devices()[0],'Auto Detect',identity)
    assert ready and identity.compatibility_assumed and 'by explicit user instruction' in warning
    assert validated_670(config) and set(commands_for(config))==WORDS
    assert profile_for(config).registers[60].access=='R'
    validate_read(profile_for(config),60,1)
    assert not resolve_profile(default_devices()[0],'LEL 700 Series',identity)[2]
    assert not resolve_profile(default_devices()[0],'BTU',identity)[2]
    assert not validated_670(replace(config,assembly='SNR673'))
    assert not validated_670(replace(config,family='FID',register_profile='auto'))
