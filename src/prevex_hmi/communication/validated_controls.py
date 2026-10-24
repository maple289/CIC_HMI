"""Fixed register8 controls for documented670 and user-approved4.81 compatibility.

This capability is activated only by a confirmed command, never by Connect.
Firmware4.81 uses the 5.12 map by user instruction, without hardware validation.
Other unknown firmware and register writes remain outside its scope.
"""
from dataclasses import dataclass
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.lel670 import MODELS
from prevex_hmi.profiles.common import COMMANDS

WORDS=frozenset(COMMANDS)


def validated_670(config):
    try:version=tuple(int(p) for p in config.version.split('.'))
    except ValueError:return False
    from prevex_hmi.devices.compatibility import assumed_481
    return bool(config.family=='LEL' and config.assembly in MODELS and (profile_for(config).revision=='670' and len(version)==2 and (5,12)<=version<(6,0) or profile_for(config).revision in ('670','fta_4x') and assumed_481(config.assembly,config.version)))


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
