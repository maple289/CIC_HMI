from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import struct
import threading
import time

import pytest

from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.protocol import Addressing, CRCError, ProtocolError, block_reads, crc16, decode_read, frame, validate_read
from prevex_hmi.communication.scheduler import PollingScheduler
from prevex_hmi.communication.serial_transport import ReadOnlySerialTransport
from prevex_hmi.devices.models import DeviceConfig, validate_devices
from prevex_hmi.profiles import PROFILES
from prevex_hmi.registers.schema import UnverifiedDefinition
from prevex_hmi.simulator.bus import SimulatedBus


class Clock:
    def __init__(self):
        self.now = 100.0
    def __call__(self):
        return self.now
    def sleep(self, duration):
        self.now += duration


def device(number=1, family="LEL"):
    return DeviceConfig(str(number), f"Analyzer {number}", family, number,
                        {"LEL":"SNR675", "BTU":"SNR692", "FID":"SNR650"}[family],
                        "4.80" if family == "FID" else "5.11", units="US" if family == "FID" else None)


def setup(devices=None):
    clock = Clock()
    devices = devices or [device()]
    transport = SimulatedBus(devices, clock=clock)
    bus = BusEngine(transport, clock=clock, sleep=clock.sleep)
    return clock, transport, bus


def test_known_modbus_crc_and_decoding():
    # Standard published FC03 request: 01 03 00 00 00 0A C5 CD.
    assert frame(bytes.fromhex("01 03 00 00 00 0A")) == bytes.fromhex("01 03 00 00 00 0A C5 CD")
    data = frame(bytes.fromhex("01 03 04 00 01 FF FF"))
    assert decode_read(data, 1, 2) == [1, 65535]
    with pytest.raises(CRCError):
        decode_read(data[:-1] + b"\x00", 1, 2)
    with pytest.raises(ProtocolError):
        decode_read(data, 2, 2)
    with pytest.raises(ProtocolError):
        decode_read(data, 1, 1)


def test_address_compatibility_and_zero_guard():
    assert Addressing(5).packet_address == 5
    assert Addressing(5, "display_minus_one").packet_address == 4
    assert Addressing(5, pdu_offset=-1).pdu(257) == 256
    assert Addressing(5, pdu_offset=0).pdu(257) == 257
    with pytest.raises(PermissionError):
        Addressing(1, "display_minus_one").packet_address
    for value in (0, -1, 256):
        with pytest.raises(ValueError):
            Addressing(value).packet_address


@pytest.mark.parametrize("start,count", [(64,2),(272,2),(1040,2),(1344,2),(1,128),(0,1),(65,1)])
def test_read_page_boundaries(start,count):
    with pytest.raises(ValueError):
        validate_read(PROFILES["LEL"],start,count)


def test_unsafe_holes_and_block_planning():
    with pytest.raises(PermissionError):
        validate_read(PROFILES["LEL"],40,1)
    with pytest.raises(UnverifiedDefinition):
        validate_read(PROFILES["FID"],59,1)
    assert block_reads(PROFILES["LEL"],[1,2,3,4,9,11,15]) == [(1,4),(9,1),(11,1),(15,1)]
    assert block_reads(PROFILES["LEL"],[64,257]) == [(64,1),(257,1)]


def test_alternate_pages_reverse_each_word_once():
    _, sim, bus = setup()
    sim.devices[1].raw[16] = 0x1234
    assert bus.read(PROFILES["LEL"],Addressing(1),16,1) == {16:0x1234}
    assert bus.read(PROFILES["LEL"],Addressing(1),1296,1) == {16:0x1234}
    assert bus.read(PROFILES["LEL"],Addressing(1),257,16) == bus.read(PROFILES["LEL"],Addressing(1),1025,16)
    with pytest.raises(ValueError):
        validate_read(PROFILES["FID"],1281,1)


@pytest.mark.parametrize("baud,interval", [(300,4.0),(9600,0.125),(19200,0.0625)])
def test_bus_wide_traffic_pacing_including_failures(baud,interval):
    clock = Clock()
    sim = SimulatedBus([device(1),device(2)],clock=clock)
    bus = BusEngine(sim,baud,clock=clock,sleep=clock.sleep)
    starts=[]
    for address in (1,2,1):
        bus.read(PROFILES["LEL"],Addressing(address),1,4)
        starts.append(clock())
    assert starts[1]-starts[0] == pytest.approx(interval)
    assert starts[2]-starts[1] == pytest.approx(interval)
    sim.set_fault(1,"timeout")
    with pytest.raises(TimeoutError):
        bus.read(PROFILES["LEL"],Addressing(1),1,4)
    failed_at = clock()
    bus.read(PROFILES["LEL"],Addressing(2),1,4)
    assert clock()-failed_at == pytest.approx(interval)


def test_no_concurrent_transaction_even_from_multiple_threads():
    class Probe:
        trace=lambda *_: None
        def __init__(self):
            self.active=0
            self.peak=0
        def read(self,*args):
            self.active+=1
            self.peak=max(self.peak,self.active)
            time.sleep(0.005)
            self.active-=1
            return [0]
        def close(self):
            pass
    probe = Probe()
    bus = BusEngine(probe,19200)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:bus.read(PROFILES["LEL"],Addressing(1),2,1),range(8)))
    assert probe.peak == 1
    assert len(results) == bus.stats.successes == 8


def test_error_statistics_and_bounded_traffic():
    _, sim, bus = setup()
    for fault,error in [("timeout",TimeoutError),("crc",CRCError),("protocol",ProtocolError)]:
        sim.set_fault(1,fault)
        with pytest.raises(error):
            bus.read(PROFILES["LEL"],Addressing(1),1,4)
    assert (bus.stats.timeouts,bus.stats.crc_errors,bus.stats.protocol_errors) == (1,1,1)
    sim.set_fault(1,"none")
    for _ in range(300):
        bus.read(PROFILES["LEL"],Addressing(1),1,4)
    assert len(bus.traffic) == 500
    assert bus.diagnostics()["bus"]["success_rate"] == pytest.approx(300/303*100)


def test_sixteen_devices_and_failed_device_isolation_recovery():
    devices=[device(n,("LEL","BTU","FID")[(n-1)%3]) for n in range(1,17)]
    clock,sim,bus=setup(devices)
    scheduler=PollingScheduler(bus,devices,clock=clock)
    sim.set_fault(1,"timeout")
    for _ in range(16):
        assert scheduler.run_once()
    assert not scheduler.states["1"].online
    assert all(scheduler.states[str(n)].online for n in range(2,17))
    polls=bus.device_stats[1].polls
    for _ in range(10):
        scheduler.run_once()
    assert bus.device_stats[1].polls == polls
    sim.set_fault(1,"none")
    clock.sleep(5)
    for _ in range(100):
        scheduler.run_once()
    assert scheduler.states["1"].online
    clock.sleep(20)
    assert scheduler.states["2"].snapshot(clock())["quality"] == "STALE"


def test_duplicate_address_conflicts_include_compatibility_mapping():
    with pytest.raises(ValueError):
        validate_devices([device(),replace(device(2),address_mode="display_minus_one")])
    validate_devices([device(),replace(device(2),address=1,enabled=False)])


def test_simulated_write_validation_and_real_readback():
    _,sim,_=setup()
    assert sim.configure(1,28,3,role="Administrator",confirmed=True) == 3
    assert sim.events[-1]["old"] == 1
    with pytest.raises(ValueError):
        sim.configure(1,28,5,role="Administrator",confirmed=True)
    with pytest.raises(PermissionError):
        sim.configure(1,18,0,role="Administrator",confirmed=True)
    with pytest.raises(PermissionError):
        sim.configure(1,28,2,role="Viewer",confirmed=True)


def test_commands_once_lock_and_status_sequences():
    clock,sim,bus=setup()
    with pytest.raises(PermissionError):
        sim.command(1,0xA00,role="Administrator",confirmed=True)
    for code in (0xB00,0xC00,0xD00,0xE00):
        with pytest.raises(PermissionError):
            sim.command(1,code,role="Administrator",confirmed=True)
    sim.command(1,0xF00,role="Operator",confirmed=True)
    with pytest.raises(PermissionError):
        sim.command(1,0x300,role="Operator",confirmed=True)
    sim.command(1,0x1000,role="Operator",confirmed=True)
    sim.command(1,0x500,role="Operator",confirmed=True)
    assert sim.devices[1].raw[8] == 0
    statuses=[]
    for _ in range(4):
        statuses.append(bus.read(PROFILES["LEL"],Addressing(1),2,1)[2])
        clock.sleep(2)
    assert statuses == [4,5,6,7]
    assert len([e for e in sim.events if e.get("code") == 0x500]) == 1


def test_physical_access_gates_do_not_construct_client():
    def forbidden(**_):
        pytest.fail("Physical client should never be constructed")
    with pytest.raises(PermissionError):
        ReadOnlySerialTransport("COM1",client_factory=forbidden)


def test_mocked_physical_transport_reconnect_close_and_no_write_api():
    class Response:
        registers=[1]
        def isError(self): return False
    class Client:
        connected=False
        def __init__(self,**kwargs):
            assert kwargs["retries"] == 0 and kwargs["timeout"] == 0.5
            assert (kwargs["bytesize"],kwargs["parity"],kwargs["stopbits"]) == (8,"N",1)
            self.connects=0
        def connect(self):
            self.connects+=1
            self.connected=True
            return True
        def read_holding_registers(self,*args,**kwargs): return Response()
        def close(self): self.connected=False
    transport=ReadOnlySerialTransport("FAKE",hardware_authorized=True,addressing_reviewed=True,client_factory=Client)
    assert transport.read(1,0,1) == [1]
    transport.close()
    assert transport.read(1,0,1) == [1]
    assert transport._client.connects == 2
    assert not hasattr(transport,"write") and not hasattr(transport,"command")
    bus=BusEngine(transport)
    with pytest.raises(PermissionError):
        bus.read(PROFILES["FID"],Addressing(1),1,1)
    bus.close()
    assert not transport._client.connected
