"""Fixed register8 operating controls for documented670 firmware5.12+.

This capability is activated only by a confirmed command, never by Connect.
Unknown firmware and other register writes are deliberately outside its scope.
"""
from dataclasses import dataclass
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.lel670 import MODELS
from prevex_hmi.profiles.common import COMMANDS

WORDS=frozenset(COMMANDS)


def validated_670(config):
    try:version=tuple(int(p) for p in config.version.split('.'))
    except ValueError:return False
    return bool(config.family=='LEL' and profile_for(config).revision=='670' and config.assembly in MODELS and len(version)==2 and (5,12)<=version<(6,0))


@dataclass(frozen=True)
class ValidatedControlGrant:
    port: str
    baud: int
    address: int
    pdu_offset: int
    model: str
    version: str
    identity_text: str
    timeout: float = .5

    def validate(self,config):
        if not validated_670(config) or (config.addressing.packet_address,config.pdu_offset,config.assembly,config.version)!=(self.address,self.pdu_offset,self.model,self.version):
            raise PermissionError('Control scope does not match documented670 firmware/endpoint')
        config.addressing.pdu(8)

    def validate_identity(self,identity):
        if not identity.verified or (identity.family,identity.model,identity.version,identity.text)!=('LEL',self.model,self.version,self.identity_text):
            raise PermissionError('Fresh control identity differs; no command sent')
