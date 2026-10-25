"""Display-only trend retention; held points never enter the historian."""
from collections import deque
from dataclasses import dataclass
from math import isfinite,nan


@dataclass(frozen=True)
class DisplayPoint:
    timestamp: float
    value: float | None
    held: bool


class DisplayTrend:
    def __init__(self,maximum=1800):self.points=deque(maxlen=maximum)

    def clear(self):self.points.clear()

    def append(self,timestamp,value,retained=None):
        held=value is None and retained is not None
        value=retained if held else value
        if value is not None and not isfinite(float(value)):value=None;held=False
        self.points.append(DisplayPoint(timestamp,None if value is None else float(value),held))

    def curves(self):
        solid_x=[];solid_y=[];held_x=[];held_y=[]
        last_mode=None
        for previous,current in zip(self.points,list(self.points)[1:]):
            if previous.value is None or current.value is None:last_mode=None;continue
            mode='held' if previous.held or current.held else 'solid'
            xs,ys=(held_x,held_y) if mode=='held' else (solid_x,solid_y)
            if mode!=last_mode:xs.extend((nan,previous.timestamp));ys.extend((nan,previous.value))
            if mode=='held':
                # Zero-order hold until the next actual sample, then its jump.
                xs.extend((current.timestamp,current.timestamp));ys.extend((previous.value,current.value))
            else:
                xs.append(current.timestamp);ys.append(current.value)
            last_mode=mode
        return (solid_x,solid_y),(held_x,held_y)
