"""Physical adjustment protocol exercised with fake SDK clients ONLY."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from pymodbus.exceptions import ModbusException
from prevex_hmi.communication.serial_transport import ReadOnlySerialTransport,ValidatedOperatingTransport
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.parameters import ParameterAdjustments
from prevex_hmi.communication.validated_commands import ValidatedOperatingCommands
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.devices.identification import detect
from prevex_hmi.logging_db.store import Historian
from prevex_hmi.profiles.parameters import PARAMETERS,encode


@pytest.fixture(params=['5.12','4.81'])
def physical(tmp_path,request):
    config=replace(default_devices()[0],version=request.param,assembly='SNR671' if request.param=='4.81' else 'SNR675',register_profile='fta_4x' if request.param=='4.81' else '670')
    state=dict(raw={1:256,2:0,3:100,4:128,5:40*256,6:50*256,17:0xA5A7,28:1,56:512,60:0},writes=[],clients=[],failure=None,identity_changed=False,after_upgrade=None)
    class Client:
        def __init__(self,**kwargs):
            assert kwargs['retries']==0;self.connected=False;self.closed=False;state['clients'].append(self)
            if len(state['clients'])==2 and state['after_upgrade']:state['after_upgrade']()
        def connect(self):self.connected=True;return True
        def close(self):self.connected=False;self.closed=True
        def read_holding_registers(self,pdu,*,count,device_id):
            assert device_id==1
            identity=(b'TYPE FTAVER 4\xa781 SNR671' if request.param=='4.81' else b'LEL VER5.12 SNR675 S/N UNIT1').ljust(32,b' ')
            if state['identity_changed']:identity=b'LEL VER5.12 SNR674 S/N OTHER'.ljust(32,b' ')
            raw=dict(state['raw']);raw.update({257+i//2:int.from_bytes(identity[i:i+2],'big') for i in range(0,32,2)})
            if state['writes'] and pdu==state['writes'][-1][0]:
                if state['failure']=='readback_timeout':raise ModbusException('Lost readback')
                if state['failure']=='readback_mismatch':raw[pdu+1]=0
            return SimpleNamespace(isError=lambda:False,registers=[raw.get(n,0) for n in range(pdu+1,pdu+count+1)])
        def write_register(self,pdu,raw,*,device_id):
            assert device_id==1;state['writes'].append((pdu,raw,device_id));state['raw'][pdu+1]=raw
            if state['failure']=='lost_ack':raise ModbusException('Lost acknowledgment')
            return SimpleNamespace(isError=lambda:False,address=pdu+int(state['failure']=='bad_echo'),registers=[raw])
    bus=BusEngine(ReadOnlySerialTransport('COM7',hardware_authorized=True,addressing_reviewed=True,client_factory=Client),sleep=lambda _:None)
    store=Historian(tmp_path/'fake-hardware.sqlite3')
    users=SimpleNamespace(resolve=lambda token:('test',{'admin':'Administrator','operator':'Operator'}.get(token,'Viewer')))
    c=ValidatedOperatingCommands(bus,config,store,users,identity_verified=True,expected_identity=detect(bus,config.addressing),connection=dict(port='COM7',baud=9600,timeout=.5))
    yield ParameterAdjustments(c),state,store
    bus.close();store.close()


@pytest.mark.parametrize('token',['operator','admin'])
@pytest.mark.parametrize('key,value',[('cal_time',2),('span_temperature',125),('warning',35),('danger',55),('latches',15)])
def test_authorized_named_parameter_sends_once_and_verifies(physical,token,key,value):
    service,state,store=physical;c=service.controller;number=PARAMETERS[key][0];old=state['raw'][number]
    assert type(c.bus.transport) is ReadOnlySerialTransport and len(state['clients'])==1
    result=service.execute(key,value,old,token,confirmed=True)
    raw=encode(c.config,key,value,previous=old)
    assert result=={number:raw} and state['writes']==[(number-1,raw,1)]
    assert isinstance(c.bus.transport,ValidatedOperatingTransport) and len(state['clients'])==2 and state['clients'][0].closed
    assert store.audit_rows()[0][4]=='VERIFIED_READBACK' and store.audit_rows()[1][4]=='SENDING'
    assert 'SAVE ALL' in store.audit_rows()[0][5]
    if c.config.version=='4.81':assert 'by user instruction' in store.audit_rows()[0][5]
    if key=='latches':assert raw&~15==old&~15
    service.execute(key,value,raw,token,confirmed=True);assert len(state['writes'])==1


@pytest.mark.parametrize('failure',['guest','viewer','confirmation','offline','identity','unsupported','lock','busy','unknown_lock','unknown_status','changed_value','range','alarm_order','invalid_peer','pending','ambiguous','firmware','revoked'])
def test_rejected_before_any_physical_write(physical,failure):
    service,state,store=physical;c=service.controller;token='admin';confirmed=True;current=True;key='cal_time';value=2;expected=1
    if failure in ('guest','viewer'):token=failure
    elif failure=='confirmation':confirmed=False
    elif failure=='offline':current=False
    elif failure=='identity':state['identity_changed']=True
    elif failure=='unsupported':key='failsafe'
    elif failure=='lock':state['raw'][60]=1
    elif failure=='busy':state['raw'][2]=4
    elif failure=='unknown_lock':state['raw'][60]=0x2020
    elif failure=='unknown_status':state['raw'][2]=65535
    elif failure=='changed_value':expected=3
    elif failure=='range':value=5
    elif failure=='alarm_order':key='warning';value=60;expected=state['raw'][5]
    elif failure=='invalid_peer':key='warning';value=35;expected=state['raw'][5];state['raw'][6]=65535
    elif failure=='pending':c.pending=object()
    elif failure=='ambiguous':c.ambiguous=True
    elif failure=='firmware':c.config=replace(c.config,version='5.11',register_profile='670')
    elif failure=='revoked':
        calls=[]
        def resolve(token):calls.append(token);return ('test','Administrator' if len(calls)==1 else 'Viewer')
        c.users.resolve=resolve
    service.execute(key,value,expected,token,confirmed=confirmed,current=current)
    assert not state['writes'] and store.audit_rows()[0][4]=='REJECTED'


@pytest.mark.parametrize('change',['identity','status','lock','value','peer'])
def test_recheck_after_transport_activation(physical,change):
    service,state,store=physical;key='warning' if change=='peer' else 'cal_time';expected=state['raw'][PARAMETERS[key][0]]
    def mutate():
        if change=='identity':state['identity_changed']=True
        elif change=='status':state['raw'][2]=1
        elif change=='lock':state['raw'][60]=2
        elif change=='value':state['raw'][28]=3
        elif change=='peer':state['raw'][6]=55*256
    state['after_upgrade']=mutate
    service.execute(key,35 if key=='warning' else 2,expected,'admin',confirmed=True)
    assert len(state['clients'])==2 and not state['writes'] and store.audit_rows()[0][4]=='REJECTED'
    if change=='identity':assert not service.controller.identity_verified


@pytest.mark.parametrize('failure',['lost_ack','bad_echo','readback_timeout','readback_mismatch'])
def test_unknown_outcome_blocks_all_retries_and_commands(physical,failure):
    service,state,store=physical;state['failure']=failure
    service.execute('cal_time',2,1,'operator',confirmed=True)
    assert len(state['writes'])==1 and service.controller.ambiguous and store.audit_rows()[0][4]=='UNKNOWN'
    service.execute('cal_time',2,1,'operator',confirmed=True)
    service.execute('danger',55,state['raw'][6],'admin',confirmed=True)
    service.controller.execute(0x100,'admin',confirmed=True)
    assert len(state['writes'])==1


def test_fault_is_visible_in_audit_without_bypassing_other_checks(physical):
    service,state,store=physical;state['raw'][2]=25
    service.execute('cal_time',2,1,'operator',confirmed=True)
    assert store.audit_rows()[0][4]=='VERIFIED_READBACK' and 'STATUS 25' in store.audit_rows()[0][5]


def test_default_transport_has_no_adjustment_capability_and_prohibited_keys_stay_blocked(physical):
    service,state,store=physical;c=service.controller
    assert not hasattr(c.bus.transport,'adjust_parameter')
    with pytest.raises(PermissionError):c.bus.validated_parameter(c.config,'cal_time',2,previous=1)
    service.execute('cal_time',2,1,'admin',confirmed=True)
    for key in ('failsafe','address','command','cold_start',18,8):
        with pytest.raises((PermissionError,KeyError)):c.bus.transport.adjust_parameter(key,0,previous=0)
    assert len(state['writes'])==1
