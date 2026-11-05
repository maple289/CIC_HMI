"""Profile-specific named settings. Manufacturer access is not a physical grant."""
from dataclasses import dataclass
from decimal import Decimal
from . import profile_for
from .lel670 import MODELS

# Stable keys/numbers used by the serialized worker and audit namespace.
PARAMETERS = {
    'cal_time': (28, 'CAL TIME'), 'span_temperature': (56, 'SPAN °C'),
    'span_voltage': (56, 'SPAN VDC'), 'warning': (5, 'WARNING'),
    'danger': (6, 'DANGER'), 'latches': (17, 'LATCHES'),
    'failsafe': (18, 'FAILSAFE'), 'warning_latch': (72, 'WARNING LATCH'),
    'danger_latch': (73, 'DANGER LATCH'), 'fault_latch': (74, 'FAULT LATCH'),
}


@dataclass(frozen=True)
class Parameter:
    number: int
    title: str
    bounds: tuple | None = None
    relays: tuple = ()  # (bit, meaningful name)
    mask: int = 0
    reason: str = ''
    unit: str = ''


def definitions(config):
    profile = profile_for(config)
    if config.family not in ('LEL', 'BTU', 'FID'): return {}
    if config.family == 'LEL' and profile.revision != '700':
        from prevex_hmi.devices.compatibility import assumed_481
        if config.assembly not in MODELS or not (profile.revision == '670' or profile.revision == 'fta_4x' and assumed_481(config.assembly, config.version)):
            return {}
    names = ('Low Alarm', 'High Alarm', 'Fault', 'Horn') if config.family == 'BTU' else ('Warning', 'Danger', 'Fault', 'Horn')
    relays = tuple(enumerate(names))
    result = {'cal_time': Parameter(28, 'CALIBRATION TIME' if profile.revision == '700' else 'CAL TIME', (1, 4), unit='min')}
    if config.family == 'LEL':
        model = config.assembly
        span = (50, 150) if profile.revision == '700' else (50, 70) if model.endswith(('D', 'K')) else (68, 140) if model.endswith(('P', 'PL')) else (105, 140)
        result.update(span_temperature=Parameter(56, 'SPAN TEMP SET' if profile.revision == '700' else 'SPAN °C', span),
                      warning=Parameter(5, 'WARNING LEVEL' if profile.revision == '700' else 'WARNING', (5, 60)),
                      danger=Parameter(6, 'DANGER LEVEL' if profile.revision == '700' else 'DANGER', (10, 60)))
    else:
        missing='Read-only: manufacturer adjustment limits are unspecified; verification is required before enabling writes.'
        key='span_voltage' if config.family == 'FID' else 'span_temperature'
        result[key]=Parameter(56, 'SPAN VDC' if config.family == 'FID' else 'SPAN °C', reason=missing)
        result['warning']=Parameter(5, 'LO ALARM' if config.family == 'BTU' else 'WARNING', reason=missing)
        result['danger']=Parameter(6, 'HI ALARM' if config.family == 'BTU' else 'DANGER', reason=missing)
    if profile.revision == '700':
        relays=relays[:3]
        result['latches']=Parameter(17, 'ALARM LATCH', relays=relays, reason='Read-only legacy indication. Adjust the separate WARNING LATCH [72], DANGER LATCH [73] and FAULT LATCH [74] settings.')
        for bit,key in enumerate(('warning_latch','danger_latch','fault_latch')):
            number,title=PARAMETERS[key]
            result[key]=Parameter(number,title,(0,1),((0,names[bit]),),1)
        reason='Read-only: SAFETY RELAYS is always 0x0007; Warning, Danger and Fault are permanently failsafe (700 Rev D p127).'
    else:
        result['latches']=Parameter(17,'LATCHES',(0,15),relays,15)
        reason=('Read-only: FAILSAFE Modbus writes are prohibited. Change settings at the analyzer operator panel. '+
                ('Warning, Danger and Fault are permanently failsafe.' if config.family == 'LEL' else 'Fault is always failsafe.')) if config.family != 'FID' else 'Read-only: FID FAILSAFE remote-write behavior and safe bit mask require verification. Adjust at the analyzer operator panel.'
    failsafe_relays=relays if profile.revision == '700' else relays+tuple(enumerate(('Zero valve','Span valve','Ignition','Heater'),4))
    result['failsafe']=Parameter(18,'SAFETY RELAYS' if profile.revision == '700' else 'FAILSAFE',relays=failsafe_relays,reason=reason)
    return result


def supported(config):
    return bool(definitions(config))


def definition(config,key):
    try:return definitions(config)[key]
    except KeyError:raise PermissionError('Adjustment is unavailable for this profile') from None


def limits(config, key):
    spec=definition(config,key)
    if spec.reason or spec.bounds is None:raise PermissionError(spec.reason or 'Manufacturer range is unverified')
    return spec.bounds


def validate_word(config, key, raw, *, previous=None):
    low, high = limits(config, key)
    spec=definition(config,key)
    if type(raw) is not int or not 0 <= raw <= 65535:
        raise ValueError('Setting must be a 16-bit word')
    if spec.mask:
        if type(previous) is not int or not 0 <= previous <= 65535 or raw & ~spec.mask != previous & ~spec.mask:
            raise PermissionError('Only documented relay latch bits may change; reserved bits must be preserved')
        if spec.mask == 1 and raw & ~1:
            raise PermissionError('Latch setting must be exactly 0 or 1; unexpected bits require verification')
    else:
        register=profile_for(config).register(spec.number)
        value, _ = register.decode(raw, config.family, config.context)
        factor = register.scale(config.family, config.context)[0]
        if not Decimal(low)-abs(factor)/2 <= value <= Decimal(high)+abs(factor)/2:
            raise ValueError(f'Allowed range: {low}–{high}')
    return raw


def encode(config, key, value, *, previous=None):
    low, high = limits(config, key)
    spec=definition(config,key)
    value = Decimal(str(value))
    if not value.is_finite() or not low <= value <= high:
        raise ValueError(f'Allowed range: {low}–{high}')
    if (key == 'cal_time' or spec.mask) and value != value.to_integral_value():
        raise ValueError('A whole number is required')
    raw = ((previous & ~spec.mask) | int(value)) if spec.mask and type(previous) is int else profile_for(config).register(spec.number).encode(value, config.family, config.context)
    return validate_word(config, key, raw, previous=previous)
