"""Confirmed named670 adjustments, using the existing serialized bus owner."""
from .commands import require_current_session
from .validated_controls import validated_670,ValidatedControlGrant
from prevex_hmi.devices.identification import detect
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.parameters import PARAMETERS,encode,validate_word
from prevex_hmi.simulator.bus import SimulatedBus


class ParameterAdjustments:
    def __init__(self,controller):
        self.controller=controller
        self.last_attempt={}

    def execute(self,key,value,expected,token,*,confirmed=False,current=True):
        c=self.controller;actor,role=c.users.resolve(token);sent=False;updates={}
        number=PARAMETERS.get(key,(0,''))[0]
        code=0x10000+number  # Separate audit namespace from operating commands.
        try:
            physical=not isinstance(c.bus.transport,SimulatedBus)
            if not current:raise PermissionError('Communication is not current')
            if role not in ('Operator','Administrator') or not confirmed:raise PermissionError('Confirmed Operator/Administrator adjustment required')
            if physical and not validated_670(c.config):raise PermissionError('Physical adjustment compatibility is unverified')
            if not c.identity_verified or c.pending or c.ambiguous:raise PermissionError('Identity unresolved or previous action pending/unknown')
            c.receipt=None
            if key not in PARAMETERS:raise PermissionError('Unsupported parameter')
            if c.clock()-self.last_attempt.get(key,float('-inf'))<2:raise PermissionError('Duplicate adjustment suppressed')
            identity=detect(c.bus,c.config.addressing)
            if not identity.verified or (identity.family,identity.model,identity.version)!=(c.config.family,c.config.assembly,c.config.version) or c.expected_identity and identity.text!=c.expected_identity.text:
                c.identity_verified=False;raise PermissionError('Fresh identity differs; adjustment not sent')
            profile=profile_for(c.config)
            def read(n):return c.bus.read(profile,c.config.addressing,n,1)[n]
            def preflight():
                status=read(2);lock=read(60);old=read(number)
                if status not in profile.statuses or status in (4,5,6,7,11,12):raise PermissionError('STATUS unknown or instrument busy/warming up')
                if lock!=0:raise PermissionError('Calibration lock active or unverified')
                if type(expected) is not int or old!=expected:raise PermissionError('Parameter changed since editor opened; review and confirm again')
                raw=encode(c.config,key,value,previous=old)
                peer=read(6 if key=='warning' else 5) if key in ('warning','danger') else None
                if peer is not None:
                    validate_word(c.config,'danger' if key=='warning' else 'warning',peer)
                    if not (raw<peer if key=='warning' else peer<raw):raise ValueError('WARNING must remain below DANGER')
                return status,lock,old,raw,peer
            before=preflight()
            if physical:
                connection=getattr(c,'connection',None)
                if not connection:raise PermissionError('Physical adjustment endpoint is unavailable')
                grant=ValidatedControlGrant(connection['port'],connection['baud'],c.config.addressing.packet_address,c.config.pdu_offset,c.config.assembly,c.config.version,identity.text,connection['timeout'])
                c.bus.activate_validated_controls(grant,c.config,confirmed=confirmed,role=role)
                try:grant.validate_identity(detect(c.bus,c.config.addressing))
                except PermissionError:c.identity_verified=False;raise
                if preflight()!=before:raise PermissionError('Instrument state changed during preflight; review and confirm again')
            require_current_session(c.users,token,actor)
            status,lock,old,raw,peer=before
            detail=f'{PARAMETERS[key][1]} [{number}]: raw {old} -> {raw}; STATUS {status} ({profile.status(status)}); lock {lock}'
            if physical and c.config.version=='4.81':detail+='; firmware4.81 uses the5.12 map by user instruction; compatibility not independently validated'
            c.end_previous_effect()
            c.store.command_audit(c.config.id,actor,code,'SENDING',detail+f'; confirmed {"REAL CONTROLLER" if physical else "simulated"} adjustment, send once')
            sent=True;self.last_attempt[key]=c.clock()
            if physical:c.bus.validated_parameter(c.config,key,raw,previous=old)
            else:c.bus.simulated_parameter(c.config,key,raw,previous=old)
            after=read(number);updates[number]=after
            if after!=raw:raise OSError(f'Readback {after} differs from requested {raw}; unconfirmed')
            result='VERIFIED_READBACK' if physical else 'VERIFIED_SIMULATED'
            detail+='; fresh FC03 readback verified. EEPROM persistence requires separately confirmed SAVE ALL.' if physical else '; fresh simulated FC03 readback verified. No hardware validation or EEPROM persistence claim.'
        except (OSError,ValueError,PermissionError,KeyError) as error:
            result='UNKNOWN' if sent else 'REJECTED'
            if sent:c.ambiguous=True
            detail=f'{PARAMETERS.get(key,(0,key))[1]}: {error}'+('; no retry; reconnect and review' if sent else '; adjustment not sent')
        c.store.command_audit(c.config.id,actor,code,result,detail)
        c.result=detail
        return updates
