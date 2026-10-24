"""Independent Rev D regressions; no physical instrument access."""
from dataclasses import replace,asdict
from decimal import Decimal
import pytest
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.devices.identification import detect
from prevex_hmi.profiles import profile_for,commands_for,service_for,relays_for
from prevex_hmi.profiles.lel700 import PROFILE,GAUGES
from prevex_hmi.communication.protocol import validate_read
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.scheduler import PollingScheduler
from prevex_hmi.simulator.bus import SimulatedBus
from prevex_hmi.gui.presentation import measurement


@pytest.fixture
def config():return replace(default_devices()[0],assembly='SNR705',version='7.01')


@pytest.mark.parametrize('number,factor',[(1,'0.00390625'),(5,'0.00390625'),(6,'0.00390625'),(7,'0.00390625'),(10,'0.00390625'),(38,'0.00390625'),(39,'0.00390625'),(43,'0.00390625'),(50,'0.00390625'),(91,'0.00390625'),(92,'0.00390625'),(99,'0.00390625'),(9,'0.2442'),(11,'0.2442'),(24,'0.2442'),(29,'0.2442'),(30,'0.2442'),(56,'0.2442'),(71,'0.2442'),(15,'0.00172936'),(23,'0.00172936'),(42,'0.00172936'),(70,'0.00172936'),(12,'0.0001'),(13,'0.0001'),(66,'0.0001'),(67,'0.0001'),(68,'0.0001'),(69,'0.0001'),(95,'0.0001'),(96,'0.0001'),(14,'0.01'),(97,'0.01'),(93,'0.01'),(94,'0.01'),(25,'0.1'),(26,'0.00390625'),(32,'0.00390625'),(44,'0.00390625'),(40,'0.01'),(98,'0.01'),(101,'0.1'),(106,'0.1')])
def test_rev_d_exact_factors_and_signed_words(config,number,factor):
    r=PROFILE.register(number)
    assert r.decode(1000,'LEL',config.context)[0] == Decimal(factor)*1000
    assert r.decode(65535,'LEL',config.context)[0] == -Decimal(factor)


def test_revision_is_independent_of_legacy(config):
    assert profile_for(config).revision=='700'
    assert profile_for(default_devices()[0]).revision=='670'
    assert PROFILE.status(15)=='12VDC failed' and PROFILE.status(22)=='Fuel pressure low'
    assert PROFILE.register(12).name=='FUEL PRESSURE'
    assert PROFILE.register(40).safe_read
    assert not profile_for(default_devices()[0]).register(40).safe_read
    assert {29,30}<=set(GAUGES) and not {23,42,50}&set(GAUGES)


def test_numeric_identity_replaces_removed_ascii_registers(config):
    transport=SimulatedBus([config]);bus=BusEngine(transport,sleep=lambda _:None)
    try:
        result=detect(bus,config.addressing)
        assert (result.family,result.model,result.version,result.serial,result.verified)==('LEL','SNR705','7.01','26-101',True)
        assert not transport.events
        assert {257,62,40,63,65}<={r['register'] for r in bus.traffic if r['direction']=='TX'}
        transport.devices[1].raw[40]=0
        assert not detect(bus,config.addressing).verified
        transport.devices[1].raw[40]=701
        transport.set_fault(1,'unknown_identity')
        assert not detect(bus,config.addressing).verified
    finally:bus.close()


def test_poll_plan_never_uses_removed_or_ambiguous_pages(config):
    bus=BusEngine(SimulatedBus([config]),sleep=lambda _:None)
    scheduler=PollingScheduler(bus,[config]);numbers={n for job in scheduler.jobs for n in range(job.start,job.start+job.count)}
    assert set(GAUGES)<={*numbers} and 27 in numbers
    assert 257 not in numbers and 106 not in numbers
    for start,count in ((257,16),(1281,1),(106,1),(64,2)):
        with pytest.raises((ValueError,PermissionError)):validate_read(PROFILE,start,count)
    bus.close()


def test_new_relay_and_service_maps(config):
    relays=relays_for((1<<10)|(1<<9)|(1<<8)|8,config)
    assert relays['Air/fuel cutoff'] and relays['Service Needed'] and relays['Calibrating']
    assert 'Horn' not in relays
    flags=service_for((1<<14)|(1<<11)|8,config)
    assert flags['Check TC3'] and flags['Check Utilities']
    assert len(flags)==12 and 'CHK_LED' not in flags


@pytest.mark.parametrize('code',[0x900,0xA00,0xB00,0xC00,0xD00,0xE00,0xF00,0x1000,0x1100,0x1200,0x1700])
def test_revision_command_restrictions(config,code):
    assert code not in commands_for(config)
    simulator=SimulatedBus([config])
    with pytest.raises(PermissionError):simulator.command(1,code,role='Administrator',confirmed=True)
    assert not simulator.events


def test_lock_state_two_allows_calibration_but_one_blocks(config):
    simulator=SimulatedBus([config]);simulator.devices[1].raw[27]=1
    with pytest.raises(PermissionError):simulator.command(1,0x300,role='Operator',confirmed=True)
    simulator.devices[1].raw[27]=2
    simulator.command(1,0x300,role='Operator',confirmed=True)
    assert len(simulator.events)==1


def test_negative_measurement_uses_new_profile_without_invented_fault(config):
    transport=SimulatedBus([config]);transport.devices[1].forced_reading=-20
    bus=BusEngine(transport,sleep=lambda _:None)
    raw=bus.read(PROFILE,config.addressing,1,4)
    value,unit=measurement(dict(config=asdict(config),raw=raw,quality='GOOD'))
    assert value==Decimal('-20') and unit=='%LFL' and raw[2]==0
    bus.close()
