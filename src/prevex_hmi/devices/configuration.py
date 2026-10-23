from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import os

from .models import DeviceConfig, validate_devices


def default_devices() -> list[DeviceConfig]:
    return [
        DeviceConfig("lel-1", "LEL - Process line 1", "LEL", 1, "SNR675", "5.11"),
        DeviceConfig("btu-2", "BTU - Fuel quality", "BTU", 2, "SNR692", "5.20", fullscale=1000),
        DeviceConfig("fid-3", "FID - Emissions", "FID", 3, "SNR650", "4.80", fullscale=100, units="US"),
        DeviceConfig("lel-4", "LEL - Process line 2", "LEL", 4, "SNR674D", "5.08", fullscale=200),
    ]


def load_settings(path: Path) -> dict:
    if not path.exists():
        settings = {"schema_version": 1, "mode": "simulation", "theme": "dark", "devices": [asdict(d) for d in default_devices()]}
        save_settings(path, settings)
        return settings
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("mode") != "simulation":
        raise ValueError("Only schema version 1 / simulation mode is supported")
    validate_devices([DeviceConfig(**row) for row in data["devices"]])
    return data


def save_settings(path: Path, settings: dict) -> None:
    validate_devices([DeviceConfig(**row) for row in settings["devices"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    os.replace(temporary, path)
