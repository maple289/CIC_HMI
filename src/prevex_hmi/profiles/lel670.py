"""670-series register definitions, shared by all firmware revisions."""
from dataclasses import replace
from .lel import PROFILE as LEGACY

MODELS = frozenset(('SNR671','SNR671D','SNR672','SNR672D','SNR672P',
                    'SNR672K','SNR674','SNR674D','SNR674P','SNR674PL',
                    'SNR675','SNR675D','SNR675K'))
PROFILE = replace(LEGACY, revision='670', registers=dict(LEGACY.registers))
