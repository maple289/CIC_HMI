from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
import math
import struct
import threading
import time

from prevex_hmi.communication.protocol import ProtocolError, canonical, decode_read, frame, validate_read
from prevex_hmi.devices.models import DeviceConfig, validate_devices
from prevex_hmi.profiles import PROFILES, profile_for, commands_for
from prevex_hmi.profiles.common import COMMANDS


@dataclass
class SimulatedAnalyzer:
    config: DeviceConfig
    raw: dict[int, int] = field(default_factory=dict)
    fault: str = "none"
    calibration_started: float | None = None
    calibration_span: bool = False
    calibration_full: bool = False
    calibration_failure: bool = False
    forced_reading: float | None = None
    forced_status: int | None = None
    peak_initialized: bool = False

    def __post_init__(self) -> None:
        self.profile = profile_for(self.config)
        self.raw = {n: 0 for n in self.profile.registers}
        self.raw[3] = self.config.fullscale
        for number, value in ((5, 40 if self.config.family != "BTU" else 300), (6,50 if self.config.family != "BTU" else 700), (9,120), (11,500), (24,120), (28,1), (15,1.8), (10,0 if self.profile.revision == "700" else -40 if self.config.family == "FID" else 40), (23,1.4 if self.config.family == "LEL" else -40 if self.config.family == "FID" else 40), (33,20), (56,2 if self.config.family == "FID" else 125)):
            if number in self.raw:
                self.raw[number] = self.profile.register(number).encode(value, self.config.family, self.config.context)
        self.raw[4] = 0x80
        self.raw[16] = 506
        if self.profile.revision == "700":
            self.raw[3]=100
            self.raw[40]=int(Decimal(self.config.version)*100)
            self.raw[63]=101;self.raw[65]=2026
            self.raw[29]=self.profile.register(29).encode(500,"LEL",self.config.context)
            self.raw[30]=self.profile.register(30).encode(80,"LEL",self.config.context)
        from prevex_hmi.devices.identification import LEL_TYPES
        if self.config.family == "LEL":
            self.raw[62]=next((code for code,model in LEL_TYPES.items() if model == self.config.assembly),0)
        identity = f"{self.config.family} VER {self.config.version} {self.config.assembly} 2026"
        if self.config.family == "FID": identity += " S/N SIM0001"
        length = (self.profile.identification_end - 256) * 2
        identity_bytes = identity.encode("ascii", errors="replace")[:length].ljust(length, b" ")
        for offset in range(0, length, 2):
            self.raw[257 + offset // 2] = int.from_bytes(identity_bytes[offset:offset + 2], "big")

    def update(self, now: float) -> None:
        family = self.config.family
        baseline, amplitude = (450, 110) if family == "BTU" else (25, 18)
        reading = baseline + amplitude * math.sin(now / 12 + self.config.address)
        if self.forced_reading is not None: reading=self.forced_reading
        self.raw[1] = self.profile.register(1).encode(reading, family, self.config.context)
        signed=lambda word: word-65536 if word & 0x8000 else word
        if not self.peak_initialized:
            self.raw[38]=self.raw[39]=self.raw[1]
            self.peak_initialized=True
        self.raw[38]=max((self.raw[38],self.raw[1]),key=signed)
        self.raw[39]=min((self.raw[39],self.raw[1]),key=signed)
        if 12 in self.raw: self.raw[12]=self.profile.register(12).encode(0.4,family,self.config.context)
        if 50 in self.raw:
            self.raw[50] = self.raw[1]
        if self.calibration_started is not None:
            elapsed = now - self.calibration_started
            sequence = [4, 5, 6, 7] if self.calibration_full else [5 if self.calibration_span else 4, 6, 7]
            index = int(elapsed / 2)
            if index < len(sequence):
                self.raw[2] = sequence[index]
            else:
                self.raw[2] = (9 if self.calibration_span else 8) if self.calibration_failure else 0
                self.calibration_started = None
        elif self.raw[2] not in (8, 9):
            if family == "BTU":
                self.raw[2] = 1 if signed(self.raw[1]) < signed(self.raw[5]) else 2 if signed(self.raw[1]) > signed(self.raw[6]) else 0
            else:
                self.raw[2] = 2 if signed(self.raw[1]) > signed(self.raw[6]) else 1 if signed(self.raw[1]) > signed(self.raw[5]) else 0
        if self.forced_status is not None: self.raw[2]=self.forced_status
        code = self.raw[2]
        self.raw[4] = 0x80 | (1 if code == 1 else 2 if code == 2 else 4 if code in (3,8,9,10,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27) else 0)
        if self.profile.revision == "700":
            if code in (4,5,6,7):self.raw[4] |= 1<<8
            if self.raw[59]:self.raw[4] |= 1<<9
        if code in (4, 5):
            self.raw[4] |= 0x10 if code == 4 else 0x20


class SimulatedBus:
    """In-memory RTU responses, including CRC validation and injectable faults.

    No sockets, COM ports, instrument access or system drivers are used.
    """
    physical = False

    def __init__(self, devices: list[DeviceConfig], *, clock=time.monotonic):
        validate_devices(devices)
        self.devices = {d.addressing.packet_address: SimulatedAnalyzer(d) for d in devices if d.enabled}
        self.clock = clock
        self.trace = lambda *_: None
        self.closed = False
        self._inflight = threading.Lock()
        self.events: list[dict] = []

    def read(self, address: int, pdu: int, count: int) -> list[int]:
        if self.closed:
            raise OSError("Simulator closed")
        if not self._inflight.acquire(blocking=False):
            raise ProtocolError("Concurrent bus transaction")
        try:
            if not 1 <= address <= 255:
                raise PermissionError("No broadcast")
            self.trace(True, frame(struct.pack(">BBHH", address, 3, pdu, count)))
            device = self.devices.get(address)
            if device is None or device.fault == "timeout":
                raise TimeoutError("Simulated analyzer did not reply")
            start = pdu - device.config.pdu_offset
            if device.profile.revision == "700" and start == 257 and count == 16:
                # Rev D p127 returns ASCII blanks for legacy identification.
                self.trace(False,frame(bytes((address,3,32))+struct.pack('>16H',*([0x2020]*16))))
                return [0x2020]*16
            mapping = validate_read(device.profile, start, count)
            device.update(self.clock())
            words = []
            for number, swapped in mapping:
                word = device.raw[number]
                if device.fault == "unknown_identity" and (number >= 257 or (device.profile.revision == '700' and number == 62)): word=0
                words.append(((word & 255) << 8 | word >> 8) if swapped else word)
            response = frame(bytes((address, 3, count * 2)) + struct.pack(f">{count}H", *words))
            if device.fault == "crc":
                response = response[:-1] + bytes((response[-1] ^ 1,))
            if device.fault == "protocol":
                response = frame(bytes((address, 0x83, 2)))
            self.trace(False, response)
            return decode_read(response, address, count)
        finally:
            self._inflight.release()

    def configure(self, address: int, number: int, raw: int, *, role: str, confirmed: bool) -> int:
        """Simulator-only verified configuration; cannot be routed to physical I/O."""
        if role != "Administrator" or not confirmed:
            raise PermissionError("Confirmed Administrator action required")
        device = self.devices[address]
        register = device.profile.register(number)
        register.validate_simulated_write(raw, device.config.family, device.config.context)
        if number in (5, 6):
            warning, danger = (raw, device.raw[6]) if number == 5 else (device.raw[5], raw)
            if warning >= danger:
                raise ValueError("Warning/low threshold must be below danger/high")
        old = device.raw[number]
        device.raw[number] = raw
        if number == 3:
            device.config = replace(device.config, fullscale=raw)
        # Actual simulated readback (FC03), not the local write acknowledgment.
        result = self.read(address, device.config.addressing.pdu(number), 1)[0]
        if result != raw:
            raise ProtocolError("Configuration readback mismatch")
        self.events.append({"type": "configuration", "address": address, "register": number, "old": old, "new": raw})
        return result

    def command(self, address: int, code: int, *, role: str, confirmed: bool) -> str:
        if role not in ("Operator", "Administrator") or not confirmed:
            raise PermissionError("Confirmed Operator/Administrator action required")
        device = self.devices[address]
        if code not in commands_for(device.config):
            raise PermissionError("Unsupported or prohibited command")
        if device.fault not in ("none","ambiguous_command"):
            raise TimeoutError("Communication not verified; command not issued")
        if (device.raw[27] & 1 if device.profile.revision == "700" else device.raw[60]) and code in range(0x300, 0x900, 0x100):
            raise PermissionError("Calibration is locked")
        if device.calibration_started is not None:
            raise PermissionError("A calibration sequence is already active")
        if code in range(0x300, 0x900, 0x100):
            device.calibration_started = self.clock()
            device.calibration_span = code in (0x400, 0x700)
            device.calibration_full = code in (0x500, 0x800)
        elif code == 0xF00:
            device.raw[60] |= 2
        elif code == 0x1000:
            device.raw[60] &= ~2
        elif code == 0x200:
            device.raw[2] = 0
        elif code == 0x100 and 59 in device.raw:
            device.raw[59] = 0
        device.raw[8] = 0
        self.events.append({"type": "command", "address": address, "code": code, "name": COMMANDS[code]})
        if device.fault == "ambiguous_command":
            raise TimeoutError("Simulated lost command acknowledgment; execution unknown")
        return "Accepted by software simulator; monitor STATUS (not physical verification)"

    def set_fault(self, address: int, fault: str) -> None:
        if fault not in ("none", "timeout", "crc", "protocol", "unknown_identity", "ambiguous_command"):
            raise ValueError("Unsupported simulated fault")
        self.devices[address].fault = fault

    def close(self) -> None:
        self.closed = True
