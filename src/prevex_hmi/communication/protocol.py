from __future__ import annotations

from dataclasses import dataclass
import struct

from prevex_hmi.registers.schema import Profile, UnverifiedDefinition


class ProtocolError(IOError):
    pass


class CRCError(ProtocolError):
    pass


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def frame(payload: bytes) -> bytes:
    return payload + struct.pack("<H", crc16(payload))


def check_frame(data: bytes) -> bytes:
    if len(data) < 5:
        raise ProtocolError("Short RTU frame")
    if crc16(data[:-2]) != int.from_bytes(data[-2:], "little"):
        raise CRCError("RTU CRC mismatch")
    return data[:-2]


def decode_read(data: bytes, address: int, count: int) -> list[int]:
    payload = check_frame(data)
    if payload[0] != address:
        raise ProtocolError("Unexpected responding address")
    if payload[1] == 0x83:
        raise ProtocolError(f"Modbus exception {payload[2]}")
    if payload[1] != 3 or payload[2] != count * 2 or len(payload) != 3 + count * 2:
        raise ProtocolError("Unexpected function, byte count or frame length")
    return list(struct.unpack(f">{count}H", payload[3:]))


@dataclass(frozen=True)
class Addressing:
    displayed_address: int
    mode: str = "direct"
    pdu_offset: int = -1
    verified: bool = False

    @property
    def packet_address(self) -> int:
        if not 1 <= self.displayed_address <= 255:
            raise ValueError("Displayed address must be 1..255")
        if self.mode not in ("direct", "display_minus_one"):
            raise ValueError("Unknown addressing mode")
        result = self.displayed_address - (self.mode == "display_minus_one")
        if not 1 <= result <= 255:
            raise PermissionError("Packet address zero and broadcast are prohibited")
        return result

    def pdu(self, register: int) -> int:
        if self.pdu_offset not in (-1, 0):
            raise ValueError("Explicit PDU offset must be -1 or 0")
        return register + self.pdu_offset


def canonical(profile: Profile, register: int) -> tuple[int, bool]:
    if profile.protocol_documented:
        if 1025 <= register <= 1040:
            return register - 768, True
        if 1281 <= register <= 1344:
            return register - 1280, True
    return register, False


def validate_read(profile: Profile, start: int, count: int) -> list[tuple[int, bool]]:
    if not 1 <= count <= 127:
        raise ValueError("FC03 length must be 1..127")
    windows = [(1, 64), (257, profile.identification_end)]
    if profile.protocol_documented:
        windows += [(1025, 1040), (1281, 1344)]
    if not any(lo <= start <= start + count - 1 <= hi for lo, hi in windows):
        raise UnverifiedDefinition("Read crosses a documented register window")
    result = [canonical(profile, n) for n in range(start, start + count)]
    for number, _ in result:
        if not profile.register(number).safe_read:
            raise PermissionError(f"Register {number} is not approved for inspection")
    return result


def block_reads(profile: Profile, numbers: list[int]) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    for n in sorted(set(numbers)):
        validate_read(profile, n, 1)
        if blocks:
            start, count = blocks[-1]
            if n == start + count:
                try:
                    validate_read(profile, start, count + 1)
                except (ValueError, PermissionError):
                    pass
                else:
                    blocks[-1] = start, count + 1
                    continue
        blocks.append((n, 1))
    return blocks
