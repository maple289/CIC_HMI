"""Read-only adapter. No GUI/CLI path opens hardware in the initial release."""
from __future__ import annotations

from collections.abc import Callable

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from serial.tools import list_ports

from .protocol import CRCError, ProtocolError, check_frame


def available_ports() -> list[str]:
    """Enumerate OS port metadata only; never open a port."""
    return [port.device for port in list_ports.comports()]


class ReadOnlySerialTransport:
    physical = True
    def __init__(self, port: str, *, hardware_authorized: bool = False,
                 addressing_reviewed: bool = False, baud: int = 9600, timeout: float = 0.5,
                 client_factory=ModbusSerialClient):
        if not hardware_authorized or not addressing_reviewed:
            raise PermissionError("Explicit hardware authorization and reviewed read-only addressing plan required")
        if baud not in (300, 600, 1200, 2400, 4800, 9600, 19200) or not 0.05 <= timeout <= 5:
            raise ValueError("Invalid serial settings")
        self.trace: Callable[[bool, bytes], None] = lambda *_: None
        self._received = bytearray()
        self._client = client_factory(port=port, baudrate=baud, bytesize=8, parity="N", stopbits=1,
                                      timeout=timeout, retries=0, trace_packet=self._trace_packet)

    def _trace_packet(self, sending: bool, data: bytes) -> bytes:
        self.trace(sending, data)
        if not sending:
            self._received.extend(data)
        return data

    def read(self, address: int, pdu: int, count: int) -> list[int]:
        if not 1 <= address <= 255:
            raise PermissionError("Zero/broadcast not permitted")
        if not 0 <= pdu <= 65535 or not 1 <= count <= 127:
            raise ValueError("Invalid read request")
        self._received.clear()
        try:
            if not self._client.connected and not self._client.connect():
                raise TimeoutError("Cannot open/reconnect serial port")
            response = self._client.read_holding_registers(pdu, count=count, device_id=address)
        except (ModbusException, OSError) as error:
            self._client.close()
            # PyModbus may reject a corrupted RTU frame and report only timeout.
            # Count CRC only when a complete matching candidate is captured.
            data = bytes(self._received)
            for offset in range(max(0, len(data) - 4)):
                if data[offset] == address and data[offset + 1] in (3, 0x83):
                    size = 5 if data[offset + 1] == 0x83 else 5 + data[offset + 2]
                    if len(data) - offset >= size:
                        try:
                            check_frame(data[offset:offset + size])
                        except CRCError:
                            raise CRCError("Corrupted matching RTU response") from error
            raise TimeoutError(str(error)) from error
        if response.isError():
            raise ProtocolError(f"Modbus exception response: {response}")
        return response.registers

    def close(self) -> None:
        self._client.close()
