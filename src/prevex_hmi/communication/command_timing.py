"""Bounded diagnostic timing log; never includes credentials or command tokens."""
from collections import deque
import json,threading,time
from pathlib import Path
from prevex_hmi.devices.models import utc_now

_instances={};_lock=threading.Lock()

class CommandTiming:
    def __init__(self,directory):
        self.path=Path(directory)/'command-timing.jsonl';self.lock=threading.Lock();self.events=deque(maxlen=4096)

    def event(self,stage,request_id,code,**detail):
        row=dict(timestamp_utc=utc_now(),monotonic_ns=time.perf_counter_ns(),stage=stage,request_id=request_id,code=code,**detail)
        with self.lock:
            self.events.append(row)
            try:
                if self.path.exists() and self.path.stat().st_size>2_000_000:self.path.replace(self.path.with_suffix('.jsonl.1'))
                with self.path.open('a',encoding='utf-8') as out:out.write(json.dumps(row,ensure_ascii=True)+'\n')
            except OSError:pass  # Diagnostic failure must not change command safety/audit.

def timing_for(directory):
    key=str(Path(directory).resolve())
    with _lock:return _instances.setdefault(key,CommandTiming(directory))
