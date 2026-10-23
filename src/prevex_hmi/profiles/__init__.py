from .lel import PROFILE as LEL
from .btu import PROFILE as BTU
from .fid import PROFILE as FID

PROFILES = {p.family: p for p in (LEL, BTU, FID)}
