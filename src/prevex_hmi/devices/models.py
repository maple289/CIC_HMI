from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math

from prevex_hmi.communication.protocol import Addressing
from prevex_hmi.profiles import PROFILES
from prevex_hmi.registers.schema import Context


@dataclass(frozen=True)
class DeviceConfig:
    id: str
    name: str
    family: str
    address: int
    assembly: str
    version: str
    interval: float = 2.0
    enabled: bool = True
    fullscale: int = 100
    units: str | None = None
    btu_unit: str = "unit unverified"
    address_mode: str = "direct"
    pdu_offset: int = -1
    logging_enabled: bool = True
    range_mode: str = "auto"
    manual_maximum: float | None = None
    gauge_minimum: float = -30.0

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip() or self.family not in PROFILES:
            raise ValueError("Device needs an ID, name and supported family")
        if not math.isfinite(self.interval) or self.interval < 0.25:
            raise ValueError("Poll interval must be finite and at least 0.25s")
        self.addressing.packet_address
        self.addressing.pdu(1)
        if self.units not in (None, "US", "METRIC"):
            raise ValueError("Unknown unit context")
        if self.range_mode not in ("auto", "manual"):
            raise ValueError("Range mode must be auto or manual")
        if self.manual_maximum is not None and (not math.isfinite(self.manual_maximum) or self.manual_maximum <= 0):
            raise ValueError("Manual maximum must be finite and positive")
        if self.range_mode == "manual" and self.manual_maximum is None:
            raise ValueError("Manual range requires a maximum")
        if not math.isfinite(self.gauge_minimum) or self.gauge_minimum > -30:
            raise ValueError("Negative gauge endpoint must be -30 or lower")

    @property
    def addressing(self) -> Addressing:
        return Addressing(self.address, self.address_mode, self.pdu_offset)

    @property
    def context(self) -> Context:
        return Context(self.assembly, self.version, self.fullscale, self.units, self.btu_unit)


def validate_devices(devices: list[DeviceConfig]) -> None:
    ids, names, addresses = set(), set(), set()
    for device in devices:
        if device.id in ids or device.name.casefold() in names:
            raise ValueError("Device IDs and names must be unique")
        ids.add(device.id)
        names.add(device.name.casefold())
        if device.enabled:
            address = device.addressing.packet_address
            if address in addresses:
                raise ValueError("Duplicate active packet address")
            addresses.add(address)


@dataclass
class DeviceState:
    config: DeviceConfig
    raw: dict[int, int] = field(default_factory=dict)
    last_success: float | None = None
    last_success_utc: str | None = None
    online: bool = False
    error: str = "Waiting for first response"
    failures: int = 0
    identification: str = ""
    register_times: dict[int, float] = field(default_factory=dict)

    def snapshot(self, now: float) -> dict:
        age = None if self.last_success is None else max(0, now - self.last_success)
        stale = age is None or age > max(5, self.config.interval * 3)
        quality = "DISABLED" if not self.config.enabled else "OFFLINE" if not self.online else "STALE" if stale else "GOOD"
        return {
            "config": asdict(self.config), "raw": self.raw.copy(), "quality": quality,
            "age": age, "last_success": self.last_success_utc, "error": self.error,
            "identification": self.identification,
            "register_ages": {n:max(0,now-t) for n,t in self.register_times.items()},
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
