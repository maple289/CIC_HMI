"""Provisional read-only legacy LEL profile for the observed TYPE FTA unit.

Uses the supplied legacy LEL conversion table. Firmware4В§81 support is not
established by later manuals; exclude newer zero-filled model/lock registers.
"""
from dataclasses import replace
from .lel import PROFILE as LEGACY

PROFILE=replace(LEGACY,revision='fta_4x',registers={
    n:replace(r,access='R',write_policy='blocked',safe_read=r.safe_read and n not in (8,46))
    for n,r in LEGACY.registers.items() if n<=59 and n!=57 or 257<=n<=272
})

for number,register in list(PROFILE.registers.items()):
    page=89 if number in (1,2,9,11,15,23,24,38,39,42,50) else 90 if number in (7,8,20,28,29,30,43,56) else 92 if number in (5,6,17,18,35) else 91 if number in (19,21,22,25,26,31,32,36,37,44,45,47,48,58) else 93
    PROFILE.registers[number]=replace(register,source=f'670 SERIES Rev Q p.{page}; observed older FTA subset')
PROFILE.registers[8]=replace(PROFILE.registers[8],access='command',restrictions='Only explicit confirmed ACK/RESET bench path; no generic writes or command-register inspection')
