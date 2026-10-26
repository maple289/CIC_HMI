"""Reviewed GAUGES menu entries, including read-only setpoints and copies."""
GAUGE_REGISTERS = {
    "LEL": (1,2,38,39,9,24,15,23,42,11,50),
    "BTU": (1,2,38,39,9,24,10,23,11,33,50),
    "FID": (1,2,38,39,9,24,10,23,33,11,12),
}


def gauges_for(config):
    from . import profile_for
    if profile_for(config).revision == '700':
        from .lel700 import GAUGES
        base = GAUGES
    else:
        base = GAUGE_REGISTERS[config.family]
    # The main gauge already presents register1. Register50 is an output copy.
    extras = (29,30,28,7,56,5,6,72,73,74) if profile_for(config).revision=='700' else (29,30,28,7,56,5,6,17,18)
    profile = profile_for(config)
    return tuple(dict.fromkeys(n for n in (*base,*extras) if n not in (1,50) and n in profile.registers))


def precision(family, number, fullscale):
    if number in (28,72,73,74):return 0
    if number in (1,38,39,50):
        return (1 if fullscale <= 100 else 0) if family == "FID" else 2
    return 3 if family == "FID" and number == 12 else 2
