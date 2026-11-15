"""Existing manufacturer-based profiles and their validation scope."""
from dataclasses import replace
from prevex_hmi.devices.configuration import default_devices


PROFILE_CHOICES=('LEL','BTU','FID')
PROFILE_STATUS={
    'LEL':'670/700 Series. Series-specific definitions and manufacturer write restrictions apply; 700 physical controls remain unvalidated.',
    'LEL 670 Series':'670 Series. Documented controls with matching identity, locks, roles and confirmation.',
    'LEL 700 Series':'Documentation and simulator tested. Physical hardware verification pending.',
    'BTU':'Preliminary profile from the BTU register manual. Engineering-unit/protocol ambiguities and physical verification remain pending.',
    'FID':'Preliminary profile from the FID register manual. Unit/protocol ambiguities and physical verification remain pending.',
}


def library_config(name):
    family='LEL' if name.startswith('LEL') else name
    config=next(d for d in default_devices() if d.family==family)
    if name=='LEL 700 Series':return replace(config,assembly='SNR705',version='7.01',register_profile='700')
    if name=='LEL 670 Series':return replace(config,version='5.12',register_profile='670')
    return config
