"""Functional analyzer choices with series-aware internal profile selection.

The operator chooses LEL, BTU or FID. Identified assembly determines the
actual register map; historical series-specific choices remain loadable.
"""
from dataclasses import replace
from prevex_hmi.devices.configuration import default_devices

PROFILE_CHOICES = ('LEL', 'BTU', 'FID')
LEGACY_PROFILE_CHOICES = ('LEL 670 Series', 'LEL 700 Series')
PROFILE_STATUS = {
    'LEL': 'LEL (670/700 series). Actual hardware series is identified automatically; series-specific Modbus definitions remain distinct.',
    'LEL 670 Series': 'Legacy 670 selection, shown as LEL in the new interface.',
    'LEL 700 Series': 'Legacy 700 selection, shown as LEL in the new interface.',
    'BTU': '690 series. Physical hardware verification and engineering-unit ambiguities remain pending.',
    'FID': '650 series. Physical hardware verification and unit ambiguities remain pending.',
}


def normalized_selection(name: str) -> str:
    return 'LEL' if name in ('LEL', *LEGACY_PROFILE_CHOICES) else name


def library_config(name):
    family = normalized_selection(name)
    if family not in PROFILE_CHOICES:
        raise ValueError(f'Unknown analyzer function: {name}')
    config = next(d for d in default_devices() if d.family == family)
    if name == 'LEL 700 Series':
        return replace(config, assembly='SNR705', version='7.01', register_profile='700')
    if name == 'LEL 670 Series':
        return replace(config, version='5.12', register_profile='670')
    return config
