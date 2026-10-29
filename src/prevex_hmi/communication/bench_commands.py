"""Confirmed, audited ACK/RESET exception for the user-authorized real controller."""
import time
import uuid
from .commands import CommandController,require_current_session
from .hardware_session import ReadOnlyControllerGrant
from prevex_hmi.devices.identification import detect
from prevex_hmi.profiles import profile_for
from prevex_hmi.devices.models import utc_now


class BenchOperatorCommands(CommandController):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.last_attempt={};self.receipt=None

    def execute(self,code,token,*,confirmed=False):
        actor,role=self.users.resolve(token);sent=False
        self.receipt={'id':self.request_id or uuid.uuid4().hex,'bench':True,'code':code,'state':'CHECKING','reply_received':False,'time':utc_now()}
        try:
            if code not in (0x100,0x200) or role not in ('Operator','Administrator') or not confirmed:
                raise PermissionError('Only explicitly confirmed Operator/Administrator Acknowledge or Reset is allowed')
            if not self.identity_verified:raise PermissionError('Selected profile does not match the authorized controller')
            if self.pending or self.ambiguous:raise PermissionError('Outcome pending/unknown; no duplicate or retry')
            if self.clock()<self.cooldown_until:raise PermissionError('Short command anti-repeat cooldown active')
            identity=detect(self.bus,self.config.addressing)
            ReadOnlyControllerGrant().validate_identity(identity)
            if self.expected_identity and identity.text!=self.expected_identity.text:raise PermissionError('Controller identity changed')
            profile=profile_for(self.config)
            before=self.bus.read(profile,self.config.addressing,1,4)
            service_before=self.bus.read(profile,self.config.addressing,59,1)[59]
            if before[2] in (4,5,6,7,11,12):raise PermissionError('Controller busy or warming up')
            name='Acknowledge' if code==0x100 else 'Reset'
            require_current_session(self.users,token,actor)
            self.end_previous_effect()
            self.record(actor,code,'SENDING',f'{name}: confirmed real-controller bench action; send once')
            self.receipt.update(state='SENDING',before={'status':before[2],'relays':before[4],'service':service_before})
            sent=True
            self.last_attempt[code]=self.clock()
            self.bus.bench_operator_command(code)
            self.receipt.update(state='CONTROLLER_REPLIED',reply_received=True)
            self.record(actor,code,'SENT_UNVERIFIED',f'{name} acknowledged; STATUS before {before[2]}. Effect observation uses normal polling; execution not proven.')
            self.watch_effect(actor,code,{2:before[2],4:before[4],**({59:service_before} if code==0x100 else {})})
        except (OSError,ValueError,PermissionError) as error:
            if sent:self.ambiguous=True
            self.receipt.update(state='UNKNOWN' if sent or self.ambiguous else 'REJECTED',detail=str(error),time=utc_now())
            self.record(actor,code,'UNKNOWN' if sent else 'REJECTED',f'{error}. No automatic retry.')
