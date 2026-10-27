"""Read-only serial adapter used by the user-approved available-port policy."""
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
        self._client_factory=client_factory
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


class ControllerBenchTransport(ReadOnlySerialTransport):
    """User-authorized670 bench exception: ACK/RESET only, never arbitrary writes.

    Codes:670 SERIES Rev Q p90 (PDF94). Each caller must provide the explicit
    session grant; the worker additionally checks identity, role and confirmation.
    """
    def __init__(self,*args,bench_grant=None,**kwargs):
        if bench_grant is None or not bench_grant.operator_commands:
            raise PermissionError('Explicit Acknowledge/Reset bench authorization required')
        if not args or args[0].upper()!=bench_grant.port or kwargs.get('baud',9600)!=bench_grant.baud:
            raise PermissionError('Bench command transport is restricted to the authorized COM4 endpoint')
        super().__init__(*args,**kwargs)

    def _operator_action(self,code: int) -> None:
        if code not in (0x0100,0x0200):raise PermissionError('Only Acknowledge/Reset are allowed')
        self._received.clear()
        try:
            response=self._client.write_register(7,code,device_id=1)
        except (ModbusException,OSError) as error:
            self._client.close()
            raise TimeoutError('Command response lost; outcome unknown. Never retry automatically.') from error
        if response.isError() or response.address!=7 or response.registers!=[code]:
            raise ProtocolError('Command response did not match; outcome unknown')

    def acknowledge(self) -> None:self._operator_action(0x0100)
    def reset_alarms(self) -> None:self._operator_action(0x0200)


class ValidatedOperatingTransport(ReadOnlySerialTransport):
    """Scoped command8 capability; created only after confirmed role preflight."""
    def __init__(self,*args,control_grant,config,**kwargs):
        control_grant.validate(config)
        if not args or args[0].upper()!=control_grant.port.upper() or kwargs.get('baud',9600)!=control_grant.baud:
            raise PermissionError('Control transport endpoint differs')
        self.control_grant,self.control_config=control_grant,config
        super().__init__(*args,**kwargs)

    def operating_command(self,code):
        from .validated_controls import WORDS
        self.control_grant.validate(self.control_config)
        if code not in WORDS:raise PermissionError('Unsupported/prohibited operating command')
        pdu=self.control_config.addressing.pdu(8)
        self._received.clear()
        try:reply=self._client.write_register(pdu,code,device_id=self.control_grant.address)
        except (ModbusException,OSError) as error:
            raise TimeoutError('Command acknowledgment lost; do not retry') from error
        if reply.isError() or reply.address!=pdu or reply.registers!=[code]:
            raise ProtocolError('Command echo mismatch; outcome unknown')

    def adjust_parameter(self,key,raw,*,previous):
        """Explicitly authorized named settings; no arbitrary register writes."""
        from prevex_hmi.profiles.parameters import PARAMETERS,validate_word
        self.control_grant.validate(self.control_config)
        validate_word(self.control_config,key,raw,previous=previous)
        pdu=self.control_config.addressing.pdu(PARAMETERS[key][0])
        self._received.clear()
        try:reply=self._client.write_register(pdu,raw,device_id=self.control_grant.address)
        except (ModbusException,OSError) as error:
            raise TimeoutError('Adjustment acknowledgment lost; outcome unknown. Do not retry.') from error
        if reply.isError() or reply.address!=pdu or reply.registers!=[raw]:
            raise ProtocolError('Adjustment echo mismatch; outcome unknown')
