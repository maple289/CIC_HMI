from __future__ import annotations

from dataclasses import asdict, replace
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
        initial=replace(default_devices()[0],assembly="SNR705",version="7.01")
        settings = {"schema_version": 2, "mode": "simulation", "theme": "dark", "analyzer_selection":"Auto Detect", "simulated_family":"LEL", "simulated_lel_revision":"700", "connection":{"port":"", "baud":19200,"timeout":0.5,"identification_page":"standard"}, "devices": [asdict(initial)]}
        save_settings(path, settings)
        return settings
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") == 1:
        original=path.read_text(encoding="utf-8")
        devices=[DeviceConfig(**row) for row in data["devices"]]
        active=next((d for d in devices if d.id == data.get("selected_device")), devices[0] if devices else default_devices()[0])
        data.update(schema_version=2,analyzer_selection="Auto Detect",simulated_family=active.family,connection={"port":"","baud":9600,"timeout":0.5,"identification_page":"standard"},devices=[asdict(replace(active,enabled=True))])
        backup=path.with_suffix(".v1-backup.json")
        if not backup.exists(): backup.write_text(original,encoding="utf-8")
        save_settings(path,data)
    validate_settings(data)
    return data


def validate_settings(settings):
    if settings.get("schema_version") != 2 or settings.get("mode") not in ("simulation","hardware"):
        raise ValueError("Unsupported configuration schema or connection mode")
    if settings.get("analyzer_selection") not in ("Auto Detect","LEL","LEL 670 Series","LEL 700 Series","BTU","FID") or settings.get("simulated_family") not in ("LEL","BTU","FID"):
        raise ValueError("Invalid analyzer type")
    if settings.get("simulated_lel_revision","legacy") not in ("legacy","700"):
        raise ValueError("Invalid simulated LEL revision")
    recording=settings.get('recording',{})
    if not isinstance(recording,dict) or recording.get('mode','manual') not in ('manual','automatic') or type(recording.get('interval',1)) is not int or recording.get('interval',1) not in (1,2,5,10) or type(recording.get('main_only',False)) is not bool:
        raise ValueError('Invalid recording preferences')
    if len(settings["devices"]) != 1:
        raise ValueError("Exactly one active analyzer is supported")
    validate_devices([DeviceConfig(**row) for row in settings["devices"]])
    connection=settings["connection"]
    if connection["baud"] not in (300,600,1200,2400,4800,9600,19200) or not 0.05 <= connection["timeout"] <= 5:
        raise ValueError("Invalid serial settings")
    if connection.get("identification_page","standard") not in ("standard","alternate"):
        raise ValueError("Invalid identity page")


def save_settings(path: Path, settings: dict) -> None:
    validate_settings(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    os.replace(temporary, path)
