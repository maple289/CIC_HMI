from dataclasses import replace
import sqlite3
import pytest
from prevex_hmi.communication.commands import CommandController
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.devices.identification import detect,parse_identity,resolve_profile
from prevex_hmi.logging_db.store import Historian
from prevex_hmi.profiles import PROFILES
from prevex_hmi.security.users import UserStore
from prevex_hmi.simulator.bus import SimulatedBus


class Clock:
    def __init__(self):self.now=100.
    def __call__(self):return self.now
    def sleep(self,t):self.now+=t


def setup(family='LEL'):
    clock=Clock();d=next(d for d in default_devices() if d.family==family)
    sim=SimulatedBus([d],clock=clock);bus=BusEngine(sim,clock=clock,sleep=clock.sleep)
    return d,clock,sim,bus


@pytest.mark.parametrize('family',['LEL','BTU','FID'])
def test_detects_identity_using_only_fc03(family):
    d,_,sim,bus=setup(family);identity=detect(bus,d.addressing)
    assert identity.family==family and identity.model==d.assembly and identity.version==d.version and identity.verified
    assert all(bytes.fromhex(r['hex'])[1]==3 for r in bus.traffic)
    assert identity.serial==('SIM0001' if family=='FID' else '')
    reads=[(r['register'],r['count']) for r in bus.traffic if r['direction']=='TX']
    assert (257,16) in reads
    assert ((273,16) in reads)==(family=='FID')


def test_unknown_conflicting_serial_and_manual_fallback():
    assert parse_identity('BTU FID VER5.11 SNR692').family is None
    assert parse_identity('noise only').family is None
    assert parse_identity('PREVEX VER5.11 SNR675 2026').serial==''
    assert parse_identity('TYPE FID VER4.80 SNR650 99 999').serial=='99 999'
    d,_,sim,bus=setup();sim.set_fault(d.address,'unknown_identity');identity=detect(bus,d.addressing)
    assert not identity.verified
    effective,warning,verified=resolve_profile(d,'LEL',identity)
    assert effective.family=='LEL' and warning and not verified
    assert resolve_profile(d,'Auto Detect',identity)[0] is None


@pytest.mark.parametrize('fault',['timeout','crc','protocol'])
def test_detection_failure_does_not_write_or_guess(fault):
    d,_,sim,bus=setup();sim.set_fault(d.address,fault)
    assert detect(bus,d.addressing).family is None
    assert not sim.events


def test_documented_alternate_page_and_type_crosscheck():
    d,_,sim,bus=setup();identity=detect(bus,d.addressing,alternate_page=True)
    assert identity.verified and identity.family=='LEL'
    sim.devices[d.address].raw[62]=4
    identity=detect(bus,d.addressing)
    assert not identity.verified and 'conflicts' in identity.warning


def test_profile_mismatch_uses_actual_family_but_never_enables_control():
    d,_,_,bus=setup('BTU');identity=detect(bus,d.addressing)
    effective,warning,verified=resolve_profile(d,'FID',identity)
    assert effective.family=='BTU' and 'MISMATCH' in warning and not verified


@pytest.fixture
def controller(tmp_path):
    d,clock,sim,bus=setup()
    users=UserStore(tmp_path/'users.sqlite3');users.create_user('admin','test-password-123')
    token=users.authenticate('admin','test-password-123')
    store=Historian(tmp_path/'history.sqlite3')
    identity=detect(bus,d.addressing)
    c=CommandController(bus,d,store,users,identity_verified=True,expected_identity=identity,clock=clock)
    yield c,token,clock,sim,store,users
    store.close();users.close();bus.close()


def test_passwords_hashed_and_roles_resolved_server_side(controller):
    c,token,_,_,_,users=controller
    row=users.db.execute('SELECT salt,digest FROM users').fetchone()
    assert len(row[0])==32 and len(row[1])==32 and row[1]!=b'test-password-123'
    assert users.resolve(token)==('admin','Administrator')
    with pytest.raises(PermissionError):users.authenticate('admin','wrong')
    users.create_user('viewer','viewer-password-123','Viewer',session=token)
    viewer=users.authenticate('viewer','viewer-password-123')
    c.execute(0x300,viewer,confirmed=True)
    assert c.pending is None and c.store.audit_rows()[0][4]=='REJECTED'
    assert users.resolve('forged-session')==('Guest','Viewer')


def test_revoked_session_cannot_send_after_simulated_preflight(controller,monkeypatch):
    c,token,_,sim,store,users=controller;read=c.bus.read
    def preflight(*args,**kwargs):
        result=read(*args,**kwargs)
        if args[2]==2:users.logout(token)
        return result
    monkeypatch.setattr(c.bus,'read',preflight)
    c.execute(0x300,token,confirmed=True)
    assert not sim.events and store.audit_rows()[0][4]=='REJECTED'


@pytest.mark.parametrize('code',[0xA00,0xB00,0xC00,0xD00,0xE00,0,65535])
def test_prohibited_commands_never_sent(controller,code):
    c,token,_,sim,_,_=controller;c.execute(code,token,confirmed=True)
    assert not sim.events and c.result=='Unsupported/prohibited command'


def test_confirmation_lock_disconnect_and_duplicate_guard(controller):
    c,token,clock,sim,store,_=controller
    c.execute(0x300,token,confirmed=False);assert not sim.events
    sim.devices[c.config.address].raw[60]=1;c.execute(0x300,token,confirmed=True);assert not sim.events
    sim.devices[c.config.address].raw[60]=0;c.execute(0x500,token,confirmed=True)
    assert c.pending is not None
    c.execute(0x500,token,confirmed=True)
    assert len([e for e in sim.events if e.get('code')==0x500])==1
    c.observe({'raw':{2:4},'quality':'GOOD'});c.observe({'raw':{2:7},'quality':'GOOD'});c.observe({'raw':{2:0},'quality':'GOOD'})
    assert c.pending is None and store.audit_rows()[0][4]=='COMPLETED_SIMULATED'


def test_ambiguous_command_applies_once_and_never_retries(controller):
    c,token,_,sim,store,_=controller
    sim.set_fault(c.config.address,'ambiguous_command');c.execute(0x300,token,confirmed=True)
    assert c.ambiguous and store.audit_rows()[0][4]=='UNKNOWN'
    c.execute(0x300,token,confirmed=True)
    assert len([e for e in sim.events if e.get('code')==0x300])==1


def test_identity_rechecked_before_command(controller):
    c,token,_,sim,store,_=controller
    sim.set_fault(c.config.address,'unknown_identity');c.execute(0x300,token,confirmed=True)
    assert not sim.events and store.audit_rows()[0][4]=='REJECTED'


def test_save_is_not_claimed_success_from_write_response(controller):
    c,token,_,_,store,_=controller;c.execute(0x900,token,confirmed=True)
    assert store.audit_rows()[0][4]=='SENT_UNVERIFIED'
