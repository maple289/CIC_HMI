"""Audited simulation command workflow. Physical commands are never exposed."""
from dataclasses import dataclass
import time

from prevex_hmi.profiles import PROFILES, profile_for, commands_for
from prevex_hmi.profiles.common import COMMANDS
from prevex_hmi.simulator.bus import SimulatedBus


@dataclass
class PendingCommand:
    code: int
    actor: str
    started: float
    saw_active: bool = False


class CommandController:
    def __init__(self,bus,config,store,users,*,identity_verified=False,expected_identity=None,clock=time.monotonic):
        self.bus,self.config,self.store,self.users=bus,config,store,users
        self.identity_verified=identity_verified
        self.expected_identity=expected_identity
        self.clock=clock
        self.pending=None
        self.ambiguous=False
        self.result="No command issued"

    def record(self,actor,code,result,detail):
        self.store.command_audit(self.config.id,actor,code,result,detail)
        self.result=detail

    def execute(self,code,token,*,confirmed=False):
        actor,role=self.users.resolve(token)
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
            self.record(actor,code,"SENDING",f"{COMMANDS[code]} confirmed; sending once")
            # Same transaction lock, pacing and worker owner as polling. There
            # is no path from this simulation-only method to a serial write.
            self.bus.simulated_command(self.config.addressing.packet_address,code,role,pdu=self.config.addressing.pdu(8))
            if code in range(0x300,0x900,0x100):
                self.pending=PendingCommand(code,actor,self.clock())
                self.record(actor,code,"PENDING","Monitoring STATUS for sequence and outcome")
            elif code in (0xF00,0x1000):
                lock=self.bus.read(profile,self.config.addressing,60,1)[60]
                ok=bool(lock & 2) == (code == 0xF00)
                self.record(actor,code,"VERIFIED" if ok else "FAILED","Software calibration lock verified" if ok else "Lock readback disagrees")
            else:
                after=self.bus.read(profile,self.config.addressing,2,1)[2]
                self.record(actor,code,"SENT_UNVERIFIED",f"Sent once; STATUS {status} -> {after}. No unique success signature; execution not proven.")
        except TimeoutError as error:
            self.ambiguous=True
            self.record(actor,code,"UNKNOWN",f"{error}. No automatic retry; reconnect and review instrument state.")
        except (OSError,PermissionError,ValueError) as error:
            self.record(actor,code,"REJECTED",str(error))

    def observe(self,snapshot):
        pending=self.pending
        if pending is None: return
        status=snapshot["raw"].get(2)
        age=snapshot.get("register_ages",{}).get(2,0)
        if snapshot["quality"] != "GOOD" or age > max(5,self.config.interval*3):
            self.record(pending.actor,pending.code,"UNKNOWN","Communication lost during command; no retry, reconnect required")
            self.pending=None; self.ambiguous=True
        elif status in (3,8,9,10) or status in (13,14,15,16,17,18,19,20,21,22,23,24,25,26,27):
            self.record(pending.actor,pending.code,"FAILED",f"Command outcome: {profile_for(self.config).status(status)}")
            self.pending=None
        elif status in (4,5,6,7):
            pending.saw_active=True
        elif pending.saw_active and status in (0,1,2):
            self.record(pending.actor,pending.code,"COMPLETED_SIMULATED","Simulator sequence ended with normal/alarm operating status; not hardware validation")
            self.pending=None
        elif self.clock()-pending.started > 60:
            self.record(pending.actor,pending.code,"UNKNOWN","No conclusive STATUS sequence within60s; no retry")
            self.pending=None; self.ambiguous=True
