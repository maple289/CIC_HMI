from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.profiles import PROFILES
from prevex_hmi.registers.schema import UnverifiedDefinition


def measurement(snapshot: dict, number: int = 1) -> tuple[Decimal | None, str]:
    if snapshot["quality"] != "GOOD":
        return None, "unavailable"
    raw = snapshot["raw"]
    if number not in raw:
        return None, "not yet polled"
    device = DeviceConfig(**snapshot["config"])
    context = device.context
    if device.family == "FID":
        context = replace(context, fullscale=raw.get(3))
    try:
        return PROFILES[device.family].register(number).decode(raw[number], device.family, context)
    except UnverifiedDefinition as error:
        return None, str(error)


def severity(snapshot: dict) -> tuple[str, str]:
    if snapshot["quality"] != "GOOD":
        return "#8290a5", snapshot["quality"]
    status = snapshot["raw"].get(2)
    if status is None:
        return "#8290a5", "Waiting for status"
    family = snapshot["config"]["family"]
    text = PROFILES[family].status(status)
    if status == 0:
        return "#39c6a4", text
    if status == 1 or status in (4,5,6,7,11,12):
        return "#efb753", text
    return "#f27778", text


def format_reading(snapshot: dict) -> str:
    value, unit = measurement(snapshot)
    if value is None:
        return "--"
    precision = (1 if snapshot["raw"].get(3,100) <= 100 else 0) if snapshot["config"]["family"] == "FID" else 2
    return f"{value:.{precision}f}"
