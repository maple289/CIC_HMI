"""Audited confirmed commands for the manufacturer-documented6705.12+ set."""
import uuid
from .commands import CommandController,PendingCommand
from .validated_controls import ValidatedControlGrant,WORDS,validated_670
from prevex_hmi.devices.identification import detect
from prevex_hmi.devices.models import utc_now
from prevex_hmi.profiles import profile_for
from prevex_hmi.profiles.common import COMMANDS


class ValidatedOperatingCommands(CommandController):
    def __init__(self,*args,connection,**kwargs):
        super().__init__(*args,**kwargs)
        self.connection=connection;self.last_attempt={}

    def execute(self,code,token,*,confirmed=False):
        actor,role=self.users.resolve(token);sent=False
        self.receipt={'id':uuid.uuid4().hex,'code':code,'state':'CHECKING','reply_received':False,'time':utc_now()}
        try:
            if role not in ('Operator','Administrator'):raise PermissionError('Operator/Administrator sign-in required')
            if not confirmed:raise PermissionError('Explicit target confirmation required')
            if code==0x900 and role!='Administrator':raise PermissionError('Save All requires Administrator')
            if code not in WORDS or not validated_670(self.config):raise PermissionError('Unsupported command/model/firmware')
            if not self.identity_verified:raise PermissionError('Identity/profile unresolved')
            if self.pending or self.ambiguous:raise PermissionError('Previous command pending/unknown; no retry')
            if self.clock()-self.last_attempt.get(code,float('-inf'))<2:raise PermissionError('Duplicate command suppressed')
            identity=detect(self.bus,self.config.addressing)
            if not identity.verified or (identity.family,identity.model,identity.version)!=(self.config.family,self.config.assembly,self.config.version) or self.expected_identity and identity.text!=self.expected_identity.text:
                self.identity_verified=False;raise PermissionError('Fresh identity differs or is unverified')
            profile=profile_for(self.config)
            grant=ValidatedControlGrant(self.connection['port'],self.connection['baud'],self.config.addressing.packet_address,self.config.pdu_offset,self.config.assembly,self.config.version,identity.text,self.connection['timeout'])
            before=self.bus.read(profile,self.config.addressing,2,1)[2]
            if before not in profile.statuses:raise PermissionError('Operating STATUS is undocumented/unverified')
            if code not in (0x100,0x200) and before in (4,5,6,7,11,12):raise PermissionError('Instrument busy/warming up')
            timeout=60
            if code not in (0x100,0x200):
                lock=self.bus.read(profile,self.config.addressing,60,1)[60]
                if lock not in (0,1,2,3):raise PermissionError('Calibration lock state invalid/unverified')
                if code==0x900 and lock:raise PermissionError('Calibration/security lock active; Save All blocked')
                if code in range(0x300,0x900,0x100):
                    if lock:raise PermissionError('Hardware/software calibration lock active')
                    minutes=self.bus.read(profile,self.config.addressing,28,1)[28]
                    if not 1<=minutes<=4:raise PermissionError('Calibration interval invalid/unverified')
                    timeout=minutes*60*(2 if code in (0x500,0x800) else 1)+120
            self.bus.activate_validated_controls(grant,self.config,confirmed=confirmed,role=role)
            # Re-identify and recheck locks after the transport closes/reopens.
            grant.validate_identity(detect(self.bus,self.config.addressing))
            status=self.bus.read(profile,self.config.addressing,2,1)[2]
            if status!=before:raise PermissionError('Status changed during preflight; review and confirm again')
            if code not in (0x100,0x200) and self.bus.read(profile,self.config.addressing,60,1)[60]!=lock:
                raise PermissionError('Calibration lock changed during preflight')
            if code in range(0x300,0x900,0x100) and self.bus.read(profile,self.config.addressing,28,1)[28]!=minutes:
                raise PermissionError('Calibration interval changed during preflight')
            self.record(actor,code,'SENDING',f'{COMMANDS[code]} confirmed; send once')
            sent=True;self.last_attempt[code]=self.clock()
            self.bus.validated_operating_command(code)
            self.receipt.update(reply_received=True,before_status=before)
            if code in range(0x300,0x900,0x100):
                self.pending=PendingCommand(code,actor,self.clock(),timeout=timeout)
                self.record(actor,code,'PENDING','Modbus acknowledgment received; monitor STATUS start/outcome')
            elif code in (0xF00,0x1000):
                after=self.bus.read(profile,self.config.addressing,60,1)[60]
                ok=after in (0,1,2,3) and bool(after&2)==(code==0xF00)
                self.record(actor,code,'VERIFIED' if ok else 'FAILED',f'Software lock readback {after}; hardware lock remains independent')
            else:
                after=self.bus.read(profile,self.config.addressing,2,1)[2]
                self.record(actor,code,'SENT_UNVERIFIED',f'Modbus acknowledgment received; STATUS {before} -> {after}. Execution/EEPROM persistence not proven')
        except (OSError,ValueError,PermissionError,RuntimeError) as error:
            if sent:self.ambiguous=True
            self.record(actor,code,'UNKNOWN' if sent else 'REJECTED',f'{error}. No automatic retry.')
