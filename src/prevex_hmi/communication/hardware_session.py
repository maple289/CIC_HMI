"""Explicit session scope for the one controller authorized on2026-10-23.

No settings file grants hardware access. A caller must explicitly supply this
grant for each launched process. Default is FC03 only; the explicit operator
flag adds only the user-requested ACK/RESET exception documented in670 Rev Q.
"""
from dataclasses import dataclass
import copy


def controller_bench_settings(settings: dict) -> dict:
    """Prepare only the previously authorized endpoint; never save a grant."""
    result=copy.deepcopy(settings)
    result['mode']='hardware'
    result['analyzer_selection']='Auto Detect'
    result['connection'].update(port='COM4',baud=9600,timeout=.5,identification_page='standard')
    result['devices'][0].update(family='LEL',assembly='SNR671',version='4.81',address=1,address_mode='direct',pdu_offset=-1,register_profile='fta_4x',name='LEL SNR671 — real controller',id='hardware-com4-snr671')
    return result


@dataclass(frozen=True)
class ReadOnlyControllerGrant:
    port: str = 'COM4'
    baud: int = 9600
    packet_address: int = 1
    pdu_offset: int = -1
    operator_commands: bool = False

    def validate(self,settings,config) -> None:
        connection=settings['connection']
        if (connection['port'].upper(),connection['baud'],config.addressing.packet_address,config.pdu_offset)!=(self.port,self.baud,self.packet_address,self.pdu_offset) or connection.get('identification_page','standard')!='standard':
            raise PermissionError('Authorized read-only bench session is COM4 /9600 /packet1 /PDU offset-1 /standard page only. No port was opened.')

    def validate_identity(self,identity) -> None:
        if not identity.legacy_format or identity.family!='LEL' or identity.model!='SNR671' or identity.version!='4.81':
            raise PermissionError('Controller identity differs from the authorized SNR671 legacy endpoint; monitoring stopped.')
