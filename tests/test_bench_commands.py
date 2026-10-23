"""Dedicated operator exception tests use a fake client; never physical I/O."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from pymodbus.exceptions import ModbusException
from prevex_hmi.communication.serial_transport import ControllerBenchTransport,ReadOnlySerialTransport
from prevex_hmi.communication.hardware_session import ReadOnlyControllerGrant
from prevex_hmi.communication.bench_commands import BenchOperatorCommands
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.devices.identification import detect
from prevex_hmi.logging_db.store import Historian
from prevex_hmi.security.users import UserStore


@pytest.fixture
def controller(tmp_path):
    class Client:
        connected=True
        def __init__(self,**kwargs):
            assert kwargs['retries']==0
            self.writes=[];self.lost=False;self.clear_service=False
        def connect(self):return True
        def close(self):self.connected=False
        def read_holding_registers(self,address,*,count,device_id):
            identity=b'TYPE FTAVER 4\xa781 SNR671'.ljust(32,b' ')
            raw={1:32769,2:25,3:100,4:4,59:161}
            if self.writes and self.clear_service:raw[59]=0
            raw.update({257+i//2:int.from_bytes(identity[i:i+2],'big') for i in range(0,32,2)})
            return SimpleNamespace(isError=lambda:False,registers=[raw.get(n,0) for n in range(address+1,address+count+1)])
        def write_register(self,address,value,*,device_id):
            self.writes.append((address,value,device_id))
            if self.lost:raise ModbusException('lost response')
            return SimpleNamespace(isError=lambda:False,address=address,registers=[value])
    grant=ReadOnlyControllerGrant(operator_commands=True)
    transport=ControllerBenchTransport('COM4',bench_grant=grant,hardware_authorized=True,addressing_reviewed=True,client_factory=Client,baud=9600)
    bus=BusEngine(transport,sleep=lambda _:None)
    config=replace(default_devices()[0],assembly='SNR671',version='4.81',register_profile='fta_4x')
    users=UserStore(tmp_path/'users.sqlite3');users.create_user('admin','test-password-123')
    token=users.authenticate('admin','test-password-123');store=Historian(tmp_path/'hardware.sqlite3')
    service=BenchOperatorCommands(bus,config,store,users,identity_verified=True,expected_identity=detect(bus,config.addressing))
    yield service,token,transport._client,store
    bus.close();store.close();users.close()


@pytest.mark.parametrize('code',[0x100,0x200])
def test_only_exact_operator_word_sent_once_then_status_observed(controller,code):
    service,token,client,store=controller
    service.execute(code,token,confirmed=True)
    assert client.writes==[(7,code,1)] and store.audit_rows()[0][4]=='SENT_UNVERIFIED'
    assert 'STATUS 25 -> 25' in service.result
    assert service.receipt['reply_received'] and service.receipt['state']=='NO_STATE_CHANGE'
    assert service.receipt['before']['status']==25 and service.receipt['after']['status']==25
    service.execute(code,token,confirmed=True)
    assert len(client.writes)==1


def test_confirmation_roles_profile_and_prohibited_codes_block_writes(controller):
    service,token,client,store=controller
    service.execute(0x100,token,confirmed=False)
    service.execute(0x100,'forged',confirmed=True)
    for code in (0,0x300,0x800,0x900,0xA00,0xB00,0xE00,0xF00,0x1000,65535):service.execute(code,token,confirmed=True)
    service.identity_verified=False;service.execute(0x100,token,confirmed=True)
    assert not client.writes


def test_lost_ack_never_causes_command_retry(controller):
    service,token,client,store=controller;client.lost=True
    service.execute(0x100,token,confirmed=True)
    assert service.ambiguous and store.audit_rows()[0][4]=='UNKNOWN'
    assert service.receipt['state']=='UNKNOWN' and not service.receipt['reply_received']
    service.execute(0x100,token,confirmed=True)
    assert client.writes==[(7,0x100,1)]


def test_visible_receipt_records_observed_effect_separately_from_reply(controller):
    service,token,client,store=controller;client.clear_service=True
    service.execute(0x100,token,confirmed=True)
    assert service.receipt['state']=='STATE_CHANGED' and service.receipt['reply_received']
    assert service.receipt['before']['service']==161 and service.receipt['after']['service']==0
    assert service.receipt['after']['status']==25


def test_default_read_adapter_has_no_commands_and_bench_needs_grant():
    assert not hasattr(ReadOnlySerialTransport,'acknowledge')
    with pytest.raises(PermissionError):ControllerBenchTransport('COM4')
    with pytest.raises(PermissionError):ControllerBenchTransport('COM5',bench_grant=ReadOnlyControllerGrant(operator_commands=True))
