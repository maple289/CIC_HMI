from .lel import PROFILE as LEL
from .btu import PROFILE as BTU
from .fid import PROFILE as FID

PROFILES = {p.family: p for p in (LEL, BTU, FID)}


def profile_for(config):
    """Three functional families, with model/series-specific register tables."""
    from .lel700 import TYPES
    from .lel670 import MODELS
    if config.family == "LEL" and (config.assembly.upper() in TYPES.values() or config.assembly.upper() not in MODELS and getattr(config,'register_profile','auto')=='700'):
        from .lel700 import PROFILE
        return PROFILE
    if config.family == 'LEL':
        from .lel670 import PROFILE
        return PROFILE
    return PROFILES[config.family]


def profile_name(config):
    if config.family == 'LEL':
        return 'LEL 700 Series' if profile_for(config).revision=='700' else 'LEL 670 Series'
    return config.family


def commands_for(config):
    from .common import COMMANDS
    # Rev D p118: Lock/Unlock over Modbus no longer have any effect. Save
    # Settings allows factory changes; exclude it from ordinary controls.
    return {code:name for code,name in COMMANDS.items() if profile_for(config).revision != '700' or code not in (0x900,0xF00,0x1000)}


def series_for(config):
    return profile_for(config).revision if config.family=='LEL' else {'BTU':'690','FID':'650'}[config.family]


def normalize_selection(selection):
    return 'LEL' if selection in ('LEL 670 Series','LEL 700 Series') else selection


def relays_for(word,config):
    from prevex_hmi.registers.schema import decode_relays
    values=decode_relays(word)
    if profile_for(config).revision == '700':
        values.pop('Horn')
        values.update({name:bool(word & (1<<bit)) for bit,name in ((8,'Calibrating'),(9,'Service Needed'),(10,'Air/fuel cutoff'))})
    return values


def service_for(word,config):
    from prevex_hmi.registers.schema import decode_service
    if profile_for(config).revision == '700':
        from .lel700 import SERVICE
        return {name:bool(word & (1<<bit)) for bit,name in SERVICE.items()}
    return decode_service(word,config.family)
