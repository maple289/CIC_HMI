"""Worker-owned simulator edits; physical parameter changes remain disabled."""
from .commands import require_current_session
from prevex_hmi.devices.identification import detect
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.parameters import PARAMETERS,encode
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
            if not isinstance(c.bus.transport,SimulatedBus):raise PermissionError('Physical parameter adjustments are disabled pending authorization')
            if not current:raise PermissionError('Communication is not current')
            if role!='Administrator' or not confirmed:raise PermissionError('Confirmed Administrator adjustment required')
            if not c.identity_verified or c.pending or c.ambiguous:raise PermissionError('Identity unresolved or previous action pending/unknown')
            c.receipt=None
            if key not in PARAMETERS:raise PermissionError('Unsupported parameter')
            if c.clock()-self.last_attempt.get(key,float('-inf'))<2:raise PermissionError('Duplicate adjustment suppressed')
            identity=detect(c.bus,c.config.addressing)
            if not identity.verified or (identity.family,identity.model,identity.version)!=(c.config.family,c.config.assembly,c.config.version) or c.expected_identity and identity.text!=c.expected_identity.text:
                c.identity_verified=False;raise PermissionError('Fresh identity differs; adjustment not sent')
            profile=profile_for(c.config)
            def read(n):return c.bus.read(profile,c.config.addressing,n,1)[n]
            status=read(2);lock=read(60);old=read(number)
            if status not in profile.statuses or status in (4,5,6,7,11,12):raise PermissionError('STATUS unknown or instrument busy/warming up')
            if lock!=0:raise PermissionError('Calibration lock active or unverified')
            if type(expected) is not int or old!=expected:raise PermissionError('Parameter changed since editor opened; review and confirm again')
            raw=encode(c.config,key,value,previous=old)
            peer=read(6 if key=='warning' else 5) if key in ('warning','danger') else None
            if peer is not None and not (raw<peer if key=='warning' else peer<raw):raise ValueError('WARNING must remain below DANGER')
            require_current_session(c.users,token,actor,administrator=True)
            detail=f'{PARAMETERS[key][1]} [{number}]: raw {old} -> {raw}; STATUS {status} ({profile.status(status)}); lock {lock}'
            c.store.command_audit(c.config.id,actor,code,'SENDING',detail+'; confirmed simulated adjustment, send once')
            sent=True;self.last_attempt[key]=c.clock()
            c.bus.simulated_parameter(c.config,key,raw,previous=old)
            after=read(number);updates[number]=after
            if after!=raw:raise OSError(f'Readback {after} differs from requested {raw}; unconfirmed')
            result='VERIFIED_SIMULATED';detail+='; fresh simulated FC03 readback verified. No hardware validation or EEPROM persistence claim.'
        except (OSError,ValueError,PermissionError,KeyError) as error:
            result='UNKNOWN' if sent else 'REJECTED'
            if sent:c.ambiguous=True
            detail=f'{PARAMETERS.get(key,(0,key))[1]}: {error}'+('; no retry; reconnect and review' if sent else '; adjustment not sent')
        c.store.command_audit(c.config.id,actor,code,result,detail)
        c.result=detail
        return updates
