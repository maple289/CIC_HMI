"""Series-scoped 670 controls. Firmware is informational; other series remain unvalidated."""
from dataclasses import dataclass
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.lel670 import MODELS
from prevex_hmi.profiles.common import COMMANDS

WORDS=frozenset(COMMANDS)


def validated_670(config):
    return bool(config.family=='LEL' and config.assembly in MODELS and profile_for(config).revision=='670')


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

    def scope_key(self):
        from prevex_hmi.devices.identification import identity_key,parse_identity
        return self.port.upper(),self.baud,self.address,self.pdu_offset,self.model,identity_key(parse_identity(self.identity_text)),self.timeout

    def validate(self,config):
        if not validated_670(config) or (config.addressing.packet_address,config.pdu_offset,config.assembly)!=(self.address,self.pdu_offset,self.model):
            raise PermissionError('Control scope does not match documented670 series/endpoint')
        config.addressing.pdu(8)

    def validate_identity(self,identity):
        from prevex_hmi.devices.identification import identity_key,parse_identity
        if not identity.verified or identity_key(identity)!=identity_key(parse_identity(self.identity_text)) or identity.model!=self.model:
            raise PermissionError('Fresh control identity differs; no command sent')
