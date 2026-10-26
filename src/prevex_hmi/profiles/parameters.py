"""Named 670 adjustments, separate from generic register access permissions.

670 Rev Q printed 45, 90, 92. Firmware 4.81 applicability is user-assumed.
"""
from decimal import Decimal
from . import profile_for
from .lel670 import MODELS

PARAMETERS = {
    'cal_time': (28, 'CAL TIME'),
    'span_temperature': (56, 'SPAN °C'),
    'warning': (5, 'WARNING'),
    'danger': (6, 'DANGER'),
    'latches': (17, 'LATCHES'),
}


def supported(config):
    from prevex_hmi.devices.compatibility import assumed_481
    return config.family == 'LEL' and config.assembly in MODELS and (
        profile_for(config).revision == '670' or
        profile_for(config).revision == 'fta_4x' and assumed_481(config.assembly, config.version))


def limits(config, key):
    if not supported(config) or key not in PARAMETERS:
        raise PermissionError('Adjustment is unavailable for this profile')
    if key == 'cal_time': return 1, 4
    if key == 'warning': return 5, 60
    if key == 'danger': return 10, 60
    if key == 'latches': return 0, 15
    model = config.assembly
    return (50, 70) if model.endswith(('D', 'K')) else (68, 140) if model.endswith(('P', 'PL')) else (105, 140)


def validate_word(config, key, raw, *, previous=None):
    low, high = limits(config, key)
    if type(raw) is not int or not 0 <= raw <= 65535:
        raise ValueError('Setting must be a 16-bit word')
    if key == 'latches':
        if type(previous) is not int or not 0 <= previous <= 65535 or raw & ~15 != previous & ~15:
            raise PermissionError('Only Warning/Danger/Fault/Horn latch bits may change')
    else:
        value, _ = profile_for(config).register(PARAMETERS[key][0]).decode(raw, config.family, config.context)
        factor = profile_for(config).register(PARAMETERS[key][0]).scale(config.family, config.context)[0]
        if not Decimal(low)-abs(factor)/2 <= value <= Decimal(high)+abs(factor)/2:
            raise ValueError(f'Allowed range: {low}–{high}')
    return raw


def encode(config, key, value, *, previous=None):
    low, high = limits(config, key)
    value = Decimal(str(value))
    if not value.is_finite() or not low <= value <= high:
        raise ValueError(f'Allowed range: {low}–{high}')
    if key in ('cal_time', 'latches') and value != value.to_integral_value():
        raise ValueError('A whole number is required')
    raw = ((previous & ~15) | int(value)) if key == 'latches' and type(previous) is int else profile_for(config).register(PARAMETERS[key][0]).encode(value, config.family, config.context)
    return validate_word(config, key, raw, previous=previous)
