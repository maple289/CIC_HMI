from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import re

from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.profiles import PROFILES, profile_for
from prevex_hmi.registers.schema import UnverifiedDefinition


def uses_controller_fault_display(snapshot: dict) -> bool:
    """Observed legacy FTA fault word: use the actual LCD, never invent -128%."""
    config=snapshot['config'];raw=snapshot['raw'];ages=snapshot.get('register_ages',{})
    if snapshot['quality']!='GOOD' or config.get('register_profile')!='fta_4x' or raw.get(1)!=0x8001:return False
    limit=max(5,config['interval']*3);status=raw.get(2)
    fault=(ages.get(2,0)<=limit and status in profile_for(DeviceConfig(**config)).statuses and status not in (0,1,2,4,5,6,7,11,12)) or (ages.get(4,0)<=limit and bool(raw.get(4,0)&4))
    return bool(fault)


def direct_controller_fault_reading(snapshot: dict):
    raw=snapshot['raw'];ages=snapshot.get('register_ages',{})
    limit=max(5,snapshot['config']['interval']*3)
    if not all(n in raw and ages.get(n,0)<=limit for n in range(51,56)):
        return None,'fault display awaiting LCD'
    text=b''.join(raw[n].to_bytes(2,'big') for n in range(51,56)).decode('latin-1').strip()
    match=re.fullmatch(r'\s*([+-]?\d+(?:\.\d+)?)\s*%\s*LFL\s*',text,re.I)
    if not match:return None,'controller LCD is not showing %LFL'
    return Decimal(match[1]),'%LFL'


def fresh_missing_lcd(snapshot: dict) -> bool:
    """Retain through fresh nonnumeric fault LCD replies, never a lost link."""
    if not uses_controller_fault_display(snapshot):return False
    raw=snapshot['raw'];ages=snapshot.get('register_ages',{})
    limit=max(5,snapshot['config']['interval']*3)
    if snapshot.get('age',0) is None or snapshot.get('age',0)>limit:return False
    if not all(n in raw and ages.get(n,0)<=limit for n in range(51,56)):return False
    return direct_controller_fault_reading(snapshot)[0] is None



def measurement(snapshot: dict, number: int = 1) -> tuple[Decimal | None, str]:
    if snapshot["quality"] != "GOOD":
        return None, "unavailable"
    raw = snapshot["raw"]
    age=snapshot.get("register_ages",{}).get(number)
    if age is not None and age > max(5,snapshot["config"]["interval"]*3):
        return None,"stale"
    if number not in raw:
        return None, "not yet polled"
    if number==1 and uses_controller_fault_display(snapshot):
        return direct_controller_fault_reading(snapshot)
    device = DeviceConfig(**snapshot["config"])
    context = device.context
    if device.family == "FID":
        context = replace(context, fullscale=raw.get(3))
    try:
        return profile_for(device).register(number).decode(raw[number], device.family, context)
    except UnverifiedDefinition as error:
        return None, str(error)


def severity(snapshot: dict) -> tuple[str, str]:
    if snapshot["quality"] != "GOOD":
        return "#8290a5", snapshot["quality"]
    status = snapshot["raw"].get(2)
    if status is None:
        return "#8290a5", "Waiting for status"
    family = snapshot["config"]["family"]
    text = profile_for(DeviceConfig(**snapshot["config"])).status(status)
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


def monitor_condition(snapshot: dict | None) -> tuple[str,str]:
    """Operator summary uses fresh STATUS/RELAYS; never changes measurement quality."""
    if not snapshot:return '#8290a5','Measurement Unavailable'
    limit=max(5,snapshot['config']['interval']*3)
    age=snapshot.get('age',0)
    if snapshot['quality']!='GOOD' or age is None or age>limit:return '#f27778','Communication Lost'
    raw=snapshot['raw'];ages=snapshot.get('register_ages',{})
    status=raw.get(2) if ages.get(2,0)<=limit else None
    relays=raw.get(4) if ages.get(4,0)<=limit else None
    profile=profile_for(DeviceConfig(**snapshot['config']))
    fault=status in profile.statuses and status not in (0,1,2,4,5,6,7,11,12)
    if fault or relays is not None and relays&4:return '#f27778','Analyzer Fault Active'
    if measurement(snapshot)[0] is None:return '#8290a5','Measurement Unavailable'
    if status in (4,5,6,7) or profile.revision=='700' and relays is not None and relays&(1<<8):return '#efb753','Calibration in Progress'
    if status in (11,12):return '#efb753',profile.status(status)
    if status not in profile.statuses or relays is None:return '#efb753','Analyzer Status Unavailable'
    if status in (1,2) or relays&3:return '#efb753','Process Alarm Active'
    return '#39c6a4','Normal Operation'
