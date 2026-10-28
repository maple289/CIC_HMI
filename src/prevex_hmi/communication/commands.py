"""Audited simulation command workflow. Physical commands are never exposed."""
from dataclasses import dataclass
import time
import uuid
from prevex_hmi.devices.models import utc_now

from prevex_hmi.profiles import PROFILES, profile_for, commands_for
from prevex_hmi.profiles.common import COMMANDS
from prevex_hmi.simulator.bus import SimulatedBus


def require_current_session(users,token,actor,*,administrator=False):
    name,role=users.resolve(token)
    if name!=actor or role not in ('Operator','Administrator') or administrator and role!='Administrator':
        raise PermissionError('Session changed or was revoked; sign in and confirm again')
    return role


@dataclass
class PendingCommand:
    code: int
    actor: str
    started: float
    saw_active: bool = False
    timeout: float = 60


@dataclass
class PendingLock:
    code: int
    actor: str
    started: float
    timeout: float = 8
    kind: str = 'lock'


@dataclass
class PendingEffect:
    code: int
    actor: str
    started: float
    before: dict
    timeout: float = 8
    kind: str = 'effect'


class CommandController:
    def __init__(self,bus,config,store,users,*,identity_verified=False,expected_identity=None,clock=time.monotonic):
        self.bus,self.config,self.store,self.users=bus,config,store,users
        self.identity_verified=identity_verified
        self.expected_identity=expected_identity
        self.clock=clock
        self.pending=None
        self.ambiguous=False
        self.result="No command issued"
        self.receipt=None

    def record(self,actor,code,result,detail):
        if self.receipt is not None and result in ('UNKNOWN','FAILED','NOT_VERIFIED'):
            detail=('Acknowledgment received; expected effect not confirmed. ' if self.receipt.get('reply_received') else 'No valid command acknowledgment received. ')+detail
        self.store.command_audit(self.config.id,actor,code,result,detail)
        self.result=detail
        if self.receipt is not None and self.receipt['code']==code and (not self.receipt.get('bench') or result in ('EFFECT_OBSERVED','NOT_VERIFIED','UNKNOWN')):
            self.receipt.update(state=result, detail=detail)

    def execute(self,code,token,*,confirmed=False):
        actor,role=self.users.resolve(token)
        self.receipt={'id':uuid.uuid4().hex,'code':code,'state':'CHECKING','reply_received':False,'time':utc_now()}
        sent=False
        try:
            if role not in ("Operator","Administrator"):
                raise PermissionError("Sign in as Operator or Administrator")
            if not confirmed: raise PermissionError("Explicit target confirmation required")
            if code not in commands_for(self.config): raise PermissionError("Unsupported/prohibited command")
            if not self.identity_verified: raise PermissionError("Analyzer identity/profile unresolved")
            if self.ambiguous or self.pending: raise PermissionError("A command is pending or has an unknown outcome; reconnect required")
            if not isinstance(self.bus.transport,SimulatedBus): raise PermissionError("Physical commands disabled")
            from prevex_hmi.devices.identification import detect
            identity=detect(self.bus,self.config.addressing)
            expected=self.expected_identity
            if not identity.verified or (identity.family,identity.model,identity.version) != (self.config.family,self.config.assembly,self.config.version) or (expected and expected.serial and expected.serial != identity.serial):
                self.identity_verified=False
                raise PermissionError("Fresh identification does not match the target; command not issued")
            profile=profile_for(self.config)
            lock_register=27 if profile.revision == "700" else 60
            values=self.bus.read(profile,self.config.addressing,lock_register,1)
            status=self.bus.read(profile,self.config.addressing,2,1)[2]
            if code in range(0x300,0x900,0x100) and (values[lock_register] & (1 if profile.revision == "700" else 3) or status in (4,5,6,7,11,12)):
                raise PermissionError("Calibration is locked or instrument is busy/warming up")
            effect_before=self.bus.read(profile,self.config.addressing,4,1) if code in (0x100,0x200) else None
            if code==0x100 and profile.revision!='700' and 59 in profile.registers:effect_before.update(self.bus.read(profile,self.config.addressing,59,1))
            role=require_current_session(self.users,token,actor)
            self.record(actor,code,"SENDING",f"{COMMANDS[code]} confirmed; sending once")
            # Same transaction lock, pacing and worker owner as polling. There
            # is no path from this simulation-only method to a serial write.
            sent=True
            self.bus.simulated_command(self.config.addressing.packet_address,code,role,pdu=self.config.addressing.pdu(8))
            self.receipt.update(reply_received=True, before_status=status)
            if code in range(0x300,0x900,0x100):
                self.pending=PendingCommand(code,actor,self.clock())
                self.record(actor,code,"PENDING","Monitoring STATUS for sequence and outcome")
            elif code in (0xF00,0x1000):
                lock=self.bus.read(profile,self.config.addressing,60,1)[60]
                self.verify_lock_readback(actor,code,lock)
            else:
                after=self.bus.read(profile,self.config.addressing,2,1)[2]
                self.record(actor,code,"SENT_UNVERIFIED",f"Acknowledgment received; STATUS {status} -> {after}. Execution not proven.")
                if effect_before is not None:self.watch_effect(actor,code,{2:status,**effect_before})
        except TimeoutError as error:
            self.ambiguous=True
            self.record(actor,code,"UNKNOWN",f"{error}. No automatic retry; reconnect and review instrument state.")
        except (OSError,PermissionError,ValueError) as error:
            if sent:self.ambiguous=True
            self.record(actor,code,"UNKNOWN" if sent else "REJECTED",str(error))

    def watch_effect(self,actor,code,before):
        # Only manufacturer-defined alarm/horn relay effects are correlated.
        # A STATUS transition alone, including Normal, is insufficient.
        self.pending=PendingEffect(code,actor,self.clock(),before,timeout=min(30,max(8,self.config.interval*4)))
        self.receipt.update(effect_before=before,before_status=before[2])

    def observe_effect(self,snapshot):
        pending=self.pending;elapsed=max(0,self.clock()-pending.started)
        config=snapshot.get('config')
        if config and any(config.get(key)!=getattr(self.config,key) for key in ('id','family','assembly','version','address','register_profile')):
            self.pending=None;self.ambiguous=True
            self.record(pending.actor,pending.code,'UNKNOWN','Analyzer/profile changed during effect observation; no retry.')
            return
        ages=snapshot.get('register_ages',{});raw=snapshot['raw']
        fresh=snapshot['quality']=='GOOD' and all(n in raw and n in ages and 0<=ages[n]<=min(elapsed,max(5,self.config.interval*3)) for n in (2,4))
        if snapshot['quality']!='GOOD':
            self.pending=None;self.ambiguous=True
            self.record(pending.actor,pending.code,'UNKNOWN','Communication lost during post-command observation; no retry.')
            return
        if elapsed>=pending.timeout:
            self.pending=None
            valid=fresh and raw[2] in profile_for(self.config).statuses and type(raw[4]) is int and 0<=raw[4]<=65535
            if not valid:
                self.ambiguous=True
                self.record(pending.actor,pending.code,'UNKNOWN','No fresh post-command STATUS/RELAYS with a documented operating STATUS at the observation deadline; execution remains unknown. Review and reconnect; no retry.')
            else:
                self.receipt.update(status_after=raw[2],effect_after={2:raw[2],4:raw[4]})
                self.record(pending.actor,pending.code,'NOT_VERIFIED',f'Valid acknowledgment received but no conclusive alarm/horn relay effect within {pending.timeout:g}s. Fresh STATUS {pending.before[2]} -> {raw[2]}; RELAYS {pending.before[4]:04X} -> {raw[4]:04X}. Observation is complete. A new operator-requested action requires its own confirmation and fresh identity, role, lock and busy checks. A later Normal STATUS alone is not execution evidence. No automatic retry.')
            return
        if fresh:
            before=pending.before;mask=(0 if profile_for(self.config).revision=='700' else 8) if pending.code==0x100 else 7
            cleared=(before[4]&mask)&~raw[4]
            service_fresh=59 in before and 59 in raw and 59 in ages and 0<=ages[59]<=min(elapsed,max(5,self.config.interval*3))
            # CHK RDNG remains tied to the reading, so its disappearance alone
            # is not an acknowledgment signature. Ignore undocumented flags.
            service_cleared=pending.code==0x100 and service_fresh and bool((before[59]&0x1F)&~raw[59])
            # Reset may clear only some latched alarms; corroborate each with
            # the corresponding current STATUS/relay rather than Normal alone.
            expected=(bool(cleared) or service_cleared) and (pending.code==0x100 or raw[2] in (0,1,2) and not (raw[4]&7))
            if expected:
                self.pending=None;self.receipt.update(status_after=raw[2],effect_after={2:raw[2],4:raw[4]})
                service_detail=f', SERVICE {before[59]:04X} -> {raw[59]:04X}' if service_fresh else ''
                self.record(pending.actor,pending.code,'EFFECT_OBSERVED',f'Documented effect observed within {elapsed:.1f}s after acknowledgment: STATUS {before[2]} -> {raw[2]}, RELAYS {before[4]:04X} -> {raw[4]:04X}{service_detail}. Expected alarm/horn/service clearing observed; causality and sensor health are not independently established.')
                return

    def verify_lock_readback(self,actor,code,word):
        self.receipt.update(lock_register=60,lock_readback=word)
        if type(word) is not int or word not in (0,1,2,3):
            self.ambiguous=True
            self.record(actor,code,'UNKNOWN',f'CAL LOCK [60] returned invalid/unverified value {word}; execution unknown. No automatic retry.')
        elif bool(word&2)==(code==0xF00):
            self.record(actor,code,'VERIFIED',f'Software lock {"locked" if word&2 else "unlocked"}, verified by CAL LOCK [60]={word}; hardware lock remains independent')
        else:
            self.pending=PendingLock(code,actor,self.clock(),timeout=min(30,max(8,self.config.interval*4)))
            self.record(actor,code,'VERIFYING_LOCK',f'Modbus acknowledgment received; CAL LOCK [60]={word}. Waiting up to{self.pending.timeout:g}s for software-lock readback. Command sent once; no retry.')

    def observe_lock(self,snapshot):
        pending=self.pending;elapsed=max(0,self.clock()-pending.started)
        word=snapshot['raw'].get(60);age=snapshot.get('register_ages',{}).get(60)
        fresh=age is not None and 0<=age<=min(elapsed,max(5,self.config.interval*3))
        if snapshot['quality']!='GOOD':
            self.pending=None;self.ambiguous=True
            self.record(pending.actor,pending.code,'UNKNOWN','Communication lost while verifying CAL LOCK [60]; lock change is unconfirmed. No automatic retry; reconnect and check controller lock state.')
        elif fresh and (type(word) is not int or word not in (0,1,2,3)):
            self.pending=None;self.ambiguous=True
            self.record(pending.actor,pending.code,'UNKNOWN',f'CAL LOCK [60] returned invalid/unverified value {word}; lock compatibility requires verification. No automatic retry.')
        elif fresh and bool(word&2)==(pending.code==0xF00):
            self.pending=None
            self.receipt.update(lock_register=60,lock_readback=word)
            self.record(pending.actor,pending.code,'VERIFIED',f'Software lock {"locked" if word&2 else "unlocked"}, verified by CAL LOCK [60]={word} after{elapsed:.1f}s; hardware lock remains independent')
        elif elapsed>=pending.timeout:
            self.pending=None
            if fresh:
                self.receipt.update(lock_register=60,lock_readback=word)
                self.record(pending.actor,pending.code,'FAILED',f'Software-lock change not confirmed within{pending.timeout:g}s; CAL LOCK [60] still reads {word}. Controller may not have applied the command, or this firmware may report lock state differently. Check CAL LOCK on the controller; no automatic retry.')
            else:
                self.ambiguous=True
                self.record(pending.actor,pending.code,'UNKNOWN','No fresh post-command CAL LOCK [60] verification within the observation period; execution unknown. No automatic retry; reconnect and check controller lock state.')

    def observe(self,snapshot):
        pending=self.pending
        if pending is None: return
        if isinstance(pending,PendingEffect):self.observe_effect(snapshot);return
        if isinstance(pending,PendingLock):self.observe_lock(snapshot);return
        status=snapshot["raw"].get(2)
        age=snapshot.get("register_ages",{}).get(2,0)
        if snapshot["quality"] != "GOOD" or age > max(5,self.config.interval*3):
            self.record(pending.actor,pending.code,"UNKNOWN","Communication lost during command; no retry, reconnect required")
            self.pending=None; self.ambiguous=True
        elif 'register_ages' in snapshot and age>max(0,self.clock()-pending.started):
            return  # A cached pre-command STATUS is not execution evidence.
        elif status in (3,8,9,10) or status in (13,14,15,16,17,18,19,20,21,22,23,24,25,26,27):
            if self.receipt is not None:self.receipt['status_after']=status
            if getattr(self.bus.transport,'physical',False) and not pending.saw_active and self.receipt and self.receipt.get('before_status')==status:
                if self.clock()-pending.started>pending.timeout:
                    self.record(pending.actor,pending.code,'UNKNOWN',f'Existing STATUS {status} unchanged; execution not confirmed within{pending.timeout:g}s; no retry')
                    self.pending=None;self.ambiguous=True
                elif not self.receipt.get('waiting_existing_fault'):
                    self.receipt['waiting_existing_fault']=True
                    self.record(pending.actor,pending.code,'WAITING_STATUS',f'Existing STATUS {status} remains; acknowledgment is not proof of execution. Waiting for a new sequence.')
                return
            self.record(pending.actor,pending.code,"FAILED",f"Command outcome: {profile_for(self.config).status(status)}")
            self.pending=None
        elif status in (4,5,6,7):
            if not pending.saw_active:
                self.record(pending.actor,pending.code,'STARTED',f'STATUS {status}: {profile_for(self.config).status(status)}; execution sequence observed')
            pending.saw_active=True
            if self.receipt is not None:self.receipt['status_after']=status
        elif pending.saw_active and status in (0,1,2):
            if self.receipt is not None:self.receipt['status_after']=status
            physical=getattr(self.bus.transport,'physical',False)
            self.record(pending.actor,pending.code,"COMPLETED_OBSERVED" if physical else "COMPLETED_SIMULATED","Observed STATUS sequence ended; calibration accuracy not independently verified" if physical else "Simulator sequence ended with normal/alarm operating status; not hardware validation")
            self.pending=None
        elif self.clock()-pending.started > pending.timeout:
            self.record(pending.actor,pending.code,"UNKNOWN",f"No conclusive STATUS sequence within{pending.timeout:g}s; no retry")
            self.pending=None; self.ambiguous=True
