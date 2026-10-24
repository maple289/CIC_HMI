from .lel import PROFILE as LEL
from .btu import PROFILE as BTU
from .fid import PROFILE as FID

PROFILES = {p.family: p for p in (LEL, BTU, FID)}


def profile_for(config):
    """Select the documented firmware/model revision, retaining legacy profiles."""
    if getattr(config,'register_profile','auto')=='fta_4x':
        from .fta import PROFILE
        return PROFILE
    from .lel700 import TYPES
    if config.family == "LEL" and (getattr(config,'register_profile','auto')=='700' or getattr(config,'register_profile','auto')!='670' and config.assembly.upper() in TYPES.values()):
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
    if profile_for(config).revision=='fta_4x':return {}
    # Rev D p118: Lock/Unlock over Modbus no longer have any effect. Save
    # Settings allows factory changes; exclude it from ordinary controls.
    return {code:name for code,name in COMMANDS.items() if profile_for(config).revision != '700' or code not in (0x900,0xF00,0x1000)}


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
