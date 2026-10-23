from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
import re


class UnverifiedDefinition(ValueError):
    """Required manufacturer information or device context is missing."""


@dataclass(frozen=True)
class Context:
    assembly: str = ""
    version: str = ""
    fullscale: int | None = None
    units: Literal["US", "METRIC"] | None = None
    btu_unit: str = "unit unverified"


@dataclass(frozen=True)
class Register:
    number: int
    name: str
    meaning: str
    conversion: str = "raw"
    signed: bool = False
    unit: str = ""
    precision: int = 2
    access: str = "R"
    minimum: str | None = None
    maximum: str | None = None
    choices: tuple[int, ...] = ()
    category: str = "Diagnostics"
    source: str = ""
    restrictions: str = ""
    safe_read: bool = True
    write_policy: str = "blocked"
    required_role: str = "Administrator"
    model_ranges: dict[str, tuple[str, str]] = field(default_factory=dict)

    def scale(self, family: str, context: Context) -> tuple[Decimal, Decimal, str]:
        if self.conversion == "reading":
            if family == "LEL":
                if not re.fullmatch(r"SNR67[1245](?:D|K|P|PL)?", context.assembly.upper()) or not context.version:
                    raise UnverifiedDefinition("LEL reading requires assembly and software version")
                try:
                    parts = tuple(int(n) for n in context.version.split("."))
                    version = (parts + (0, 0))[:2]
                except ValueError as exc:
                    raise UnverifiedDefinition("Unrecognized software version") from exc
                diluted = context.assembly.upper().endswith(("D", "K"))
                factor = "0.0078125" if diluted and version <= (5, 8) else "0.00390625"
                return Decimal(factor), Decimal(0), "%LFL"
            if family == "BTU":
                return Decimal("0.0390625"), Decimal(0), context.btu_unit
            if context.fullscale is None or not 10 <= context.fullscale <= 32000:
                raise UnverifiedDefinition("FID FULLSCLE must be read before converting")
            if context.units not in ("US", "METRIC"):
                raise UnverifiedDefinition("FID unit mode must be verified independently")
            return Decimal("0.0000390625") * context.fullscale, Decimal(0), (
                "PPM" if context.units == "US" else "MG"
            )
        if self.conversion in ("fid_vacuum", "fid_pressure"):
            if context.units not in ("US", "METRIC"):
                raise UnverifiedDefinition("FID unit mode is unknown")
            if self.conversion == "fid_vacuum":
                return (Decimal("0.0351734"), Decimal(0), "inH2O") if context.units == "US" else (
                    Decimal("0.00879336"), Decimal(0), "kPa"
                )
            return (Decimal("0.105882"), Decimal(0), "psi") if context.units == "US" else (
                Decimal("0.729412"), Decimal(0), "kPa"
            )
        factors = {
            "raw": ("1", "0"), "temperature": ("0.24426", "0"),
            "flow": ("0.00172936", "0"), "voltage": ("0.0024426", "0"),
            "current": ("0.000625", "4"), "current_trim": ("0.1", "0"),
            "btu_vacuum": ("0.351734", "0"), "btu_pressure": ("0.105862", "0"),
        }
        factor, offset = factors[self.conversion]
        return Decimal(factor), Decimal(offset), self.unit

    def decode(self, raw: int, family: str, context: Context) -> tuple[Decimal, str]:
        if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= 65535:
            raise ValueError("Register word must be an unsigned 16-bit integer")
        value = raw - 65536 if self.signed and raw & 0x8000 else raw
        factor, offset, unit = self.scale(family, context)
        return Decimal(value) * factor + offset, unit

    def encode(self, value: Decimal | float | str, family: str, context: Context) -> int:
        """Conversion only; callers must separately enforce write policy."""
        engineering = Decimal(str(value))
        if not engineering.is_finite():
            raise ValueError("Value must be finite")
        factor, offset, _ = self.scale(family, context)
        raw = int(((engineering - offset) / factor).to_integral_value(rounding=ROUND_HALF_UP))
        low, high = (-32768, 32767) if self.signed else (0, 65535)
        if not low <= raw <= high:
            raise ValueError("Value exceeds register representation")
        return raw & 0xFFFF

    def validate_simulated_write(self, raw: int, family: str, context: Context) -> None:
        if self.access != "RW" or self.write_policy != "validated":
            raise PermissionError(f"{self.name}: {self.restrictions or 'write not approved'}")
        value, _ = self.decode(raw, family, context)
        minimum, maximum = self.minimum, self.maximum
        if self.model_ranges:
            # Assembly suffixes retain the base-model temperature/flow limits.
            limits = next((r for key, r in self.model_ranges.items() if context.assembly.startswith(key)), None)
            if limits is None:
                raise UnverifiedDefinition("No validated limits for this assembly")
            minimum, maximum = limits
        if self.choices:
            if raw not in self.choices:
                raise ValueError("Unsupported enumerated setting")
        elif minimum is None or maximum is None:
            raise UnverifiedDefinition("Documented range is incomplete")
        # Allow half a raw step at range endpoints after engineering quantization.
        tolerance = abs(self.scale(family, context)[0]) / 2
        if minimum is not None and value < Decimal(minimum) - tolerance:
            raise ValueError("Below documented minimum")
        if maximum is not None and value > Decimal(maximum) + tolerance:
            raise ValueError("Above documented maximum")


@dataclass(frozen=True)
class Profile:
    family: str
    registers: dict[int, Register]
    statuses: dict[int, str]
    identification_end: int
    protocol_documented: bool

    def register(self, number: int) -> Register:
        try:
            return self.registers[number]
        except KeyError as exc:
            raise UnverifiedDefinition(f"{self.family} register {number} is not documented") from exc

    def status(self, code: int) -> str:
        return self.statuses.get(code, f"Unknown status ({code})")


def decode_relays(word: int) -> dict[str, bool]:
    # 0000 0000 TISZ HFDW: bit 0 is W, not T.
    return {name: bool(word & (1 << bit)) for bit, name in enumerate(
        ("Warning / low", "Danger / high", "Fault", "Horn", "Zero valve", "Span valve", "Ignition", "Heater")
    )}


def decode_service(word: int, family: str) -> dict[str, bool]:
    if family == "FID":
        raise UnverifiedDefinition("FID SERVICE is absent from the supplied manual")
    labels = {1: "CHK_ZERO", 2: "CHK_SPAN", 3: "CHK_LED", 4: "CHK_DATA", 5: "CHK_RDNG", 7: "AIR_FUEL"}
    if family == "LEL":
        labels[0] = "CHK_FLOW"
    return {label: bool(word & (1 << bit)) for bit, label in labels.items()}
