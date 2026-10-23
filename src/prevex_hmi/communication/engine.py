from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import logging
import struct
import threading
import time
from typing import Callable, Protocol

from prevex_hmi.communication.protocol import Addressing, CRCError, ProtocolError, frame, validate_read
from prevex_hmi.devices.models import utc_now
from prevex_hmi.registers.schema import Profile

log = logging.getLogger(__name__)


class Transport(Protocol):
    trace: Callable[[bool, bytes], None]
    def read(self, address: int, pdu: int, count: int) -> list[int]: ...
    def close(self) -> None: ...


@dataclass
class Statistics:
    polls: int = 0
    successes: int = 0
    timeouts: int = 0
    crc_errors: int = 0
    protocol_errors: int = 0
    last_poll: str | None = None
    last_response: str | None = None
    last_response_ms: float = 0


class BusEngine:
    """One lock serializes pacing, connection and I/O across every analyzer.

    No state-changing API is exposed by the physical bus engine. Transport/library
    retries are zero; the scheduler owns bounded backoff between future polls.
    """

    def __init__(self, transport: Transport, baud: int = 9600, *, clock=time.monotonic, sleep=time.sleep):
        if baud not in (300, 600, 1200, 2400, 4800, 9600, 19200):
            raise ValueError("Unsupported baud rate")
        self.transport = transport
        self.baud = baud
        self.clock, self.sleep = clock, sleep
        self._lock = threading.Lock()
        self._last_start: float | None = None
        self._last_end: float | None = None
        self.stats = Statistics()
        self.device_stats: dict[int, Statistics] = {}
        self.traffic: deque[dict] = deque(maxlen=500)
        self._active: dict = {}
        self.transport.trace = self._trace
        self.closed = False

    def _trace(self, sending: bool, data: bytes) -> None:
        self.traffic.append({"time": utc_now(), "direction": "TX" if sending else "RX", "hex": data.hex(" ").upper(), **self._active})

    @property
    def minimum_interval(self) -> float:
        return 1 / min(16, 8 * self.baud / 9600)

    def read(self, profile: Profile, addressing: Addressing, start: int, count: int) -> dict[int, int]:
        if getattr(self.transport, "physical", False) and not profile.protocol_documented:
            raise PermissionError(f"Physical {profile.family} register-page/protocol definition is unverified")
        mapping = validate_read(profile, start, count)
        address = addressing.packet_address
        pdu = addressing.pdu(start)
        with self._lock:
            if self.closed:
                raise RuntimeError("Bus has been closed")
            deadline = self.clock()
            if self._last_start is not None:
                deadline = max(deadline, self._last_start + self.minimum_interval)
            if self._last_end is not None:
                deadline = max(deadline, self._last_end + 3.5 * 10 / self.baud)
            self.sleep(max(0, deadline - self.clock()))
            started = self.clock()
            self._last_start = started
            self._active = {"address": address, "register": start, "count": count, "family": profile.family}
            per_device = self.device_stats.setdefault(address, Statistics())
            groups = (self.stats, per_device)
            for stats in groups:
                stats.polls += 1
                stats.last_poll = utc_now()
            try:
                words = self.transport.read(address, pdu, count)
                if len(words) != count or any(type(w) is not int or not 0 <= w <= 65535 for w in words):
                    raise ProtocolError("Invalid response register words")
                for stats in groups:
                    stats.successes += 1
                    stats.last_response = utc_now()
                    stats.last_response_ms = (self.clock() - started) * 1000
                return {number: ((word & 255) << 8 | word >> 8) if swapped else word
                        for (number, swapped), word in zip(mapping, words)}
            except (TimeoutError, CRCError, ProtocolError, OSError) as error:
                key = "crc_errors" if isinstance(error, CRCError) else "timeouts" if isinstance(error, TimeoutError) else "protocol_errors"
                for stats in groups:
                    setattr(stats, key, getattr(stats, key) + 1)
                log.warning("bus_read_failed", extra={"device_address": address, "register_number": start, "error_kind": type(error).__name__, "detail": str(error)})
                raise
            finally:
                self._last_end = self.clock()

    def diagnostics(self) -> dict:
        with self._lock:
            data = asdict(self.stats)
            data["success_rate"] = 100 * self.stats.successes / self.stats.polls if self.stats.polls else None
            return {"bus": data, "devices": {str(n): asdict(s) for n,s in self.device_stats.items()}, "traffic": list(self.traffic), "baud": self.baud}

    def close(self) -> None:
        with self._lock:
            self.transport.close()
            self.closed = True

    def simulated_command(self,address,code,role,*,pdu=7):
        from prevex_hmi.simulator.bus import SimulatedBus
        if not isinstance(self.transport,SimulatedBus):
            raise PermissionError("No physical write implementation")
        if not 1 <= address <= 255: raise PermissionError("Broadcast prohibited")
        with self._lock:
            if self.closed: raise RuntimeError("Bus closed")
            deadline=max(self.clock(),(self._last_start or 0)+self.minimum_interval,(self._last_end or 0)+35/self.baud)
            self.sleep(max(0,deadline-self.clock()))
            self._last_start=self.clock()
            self._active={"address":address,"register":8,"count":1,"family":"SIMULATED_COMMAND"}
            packet=frame(struct.pack(">BBHH",address,6,pdu,code))
            self._trace(True,packet)
            try:
                result=self.transport.command(address,code,role=role,confirmed=True)
                self._trace(False,packet)
                return result
            finally:
                self._last_end=self.clock()

    def bench_operator_command(self,code: int) -> None:
        from .serial_transport import ControllerBenchTransport
        if not isinstance(self.transport,ControllerBenchTransport) or code not in (0x100,0x200):
            raise PermissionError('No authorized operator bench command')
        with self._lock:
            if self.closed:raise RuntimeError('Bus closed')
            deadline=max(self.clock(),(self._last_start or 0)+self.minimum_interval,(self._last_end or 0)+35/self.baud)
            self.sleep(max(0,deadline-self.clock()));self._last_start=self.clock()
            self._active={'address':1,'register':8,'count':1,'family':'LEL_BENCH_OPERATOR'}
            try:
                if code==0x100:self.transport.acknowledge()
                else:self.transport.reset_alarms()
            finally:self._last_end=self.clock()
