from __future__ import annotations

from dataclasses import dataclass
import time

from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.protocol import ProtocolError, block_reads
from prevex_hmi.devices.models import DeviceConfig, DeviceState, utc_now, validate_devices
from prevex_hmi.profiles import PROFILES, profile_for
from prevex_hmi.profiles.gauges import GAUGE_REGISTERS, gauges_for


@dataclass
class PollJob:
    device_id: str
    start: int
    count: int
    interval: float
    priority: int
    next_due: float


class PollingScheduler:
    def __init__(self, bus: BusEngine, devices: list[DeviceConfig], *, clock=time.monotonic):
        validate_devices(devices)
        self.bus, self.clock = bus, clock
        self.states = {d.id: DeviceState(d) for d in devices}
        self.jobs: list[PollJob] = []
        self.backoff_until: dict[str, float] = {}
        for index, device in enumerate(devices):
            if not device.enabled:
                continue
            now = self.clock()
            self.jobs.append(PollJob(device.id, 1, 4, device.interval, 0, now))
            profile = profile_for(device)
            gauge_numbers=set(gauges_for(device)) | {5,6} | ({60} if 60 in profile.registers else set()) | ({27} if profile.revision == "700" else set())
            # Removing a duplicate card does not remove the existing output
            # observation from Diagnostics/history on legacy LEL/BTU profiles.
            if profile.revision!='700' and 50 in GAUGE_REGISTERS[device.family]:gauge_numbers.add(50)
            if profile.revision=='fta_4x':gauge_numbers.update(range(51,56))
            if 59 in profile.registers: gauge_numbers.add(59)
            gauge_numbers-= {1,2}
            for start,count in block_reads(profile,sorted(gauge_numbers)):
                self.jobs.append(PollJob(device.id,start,count,device.interval,1,now+0.1))
            ancillary = [n for n in (7,28,29,30,43,56) if n in profile.registers and n not in gauge_numbers]
            for start, count in block_reads(profile, ancillary):
                self.jobs.append(PollJob(device.id, start, count, max(5, device.interval * 5), 1, now + 1))
            if profile.identification_end >= 257:
                self.jobs.append(PollJob(device.id, 257, profile.identification_end - 256, 60, 2, now + 2))

    def run_once(self) -> bool:
        now = self.clock()
        candidates = [job for job in self.jobs if max(job.next_due, self.backoff_until.get(job.device_id, 0)) <= now]
        if not candidates:
            return False
        # Primary process/status reads precede diagnostics. An overloaded bus may
        # defer slow jobs: never promise uniform refresh for sixteen analyzers.
        job = min(candidates, key=lambda j: (j.priority, j.next_due))
        state = self.states[job.device_id]
        config = state.config
        try:
            values = self.bus.read(profile_for(config), config.addressing, job.start, job.count)
            state.raw.update(values)
            state.register_times.update({n:self.clock() for n in values})
            state.failures = 0
            self.backoff_until.pop(config.id, None)
            if job.start == 1:
                state.online = True
                state.error = ""
                state.last_success = self.clock()
                state.last_success_utc = utc_now()
            if job.start == 257:
                data = b"".join(w.to_bytes(2, "big") for _,w in sorted(values.items()))
                state.identification = data.decode("ascii", errors="replace").strip("\x00 ")
        except (OSError, ProtocolError) as error:
            state.online = False
            state.error = str(error)
            state.failures = min(state.failures + 1, 10)
            delay = min(60, max(config.interval, 1) * (2 ** state.failures))
            self.backoff_until[config.id] = self.clock() + delay
        finally:
            job.next_due = self.clock() + job.interval
        return True

    def snapshots(self) -> list[dict]:
        return [state.snapshot(self.clock()) for state in self.states.values()]
