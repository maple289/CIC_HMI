from __future__ import annotations

import logging
from pathlib import Path
from queue import Empty, Queue
import threading
import time

from PySide6.QtCore import QThread, Signal

from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.scheduler import PollingScheduler
from prevex_hmi.devices.models import DeviceConfig, utc_now
from prevex_hmi.gui.presentation import measurement
from prevex_hmi.logging_db.store import Historian
from prevex_hmi.profiles import PROFILES
from prevex_hmi.simulator.bus import SimulatedBus

log = logging.getLogger(__name__)


class MonitoringWorker(QThread):
    updated = Signal(object, object)
    history_ready = Signal(str, object)
    events_ready = Signal(object)
    inspection_ready = Signal(str, int, int)
    inspection_failed = Signal(str)
    failed = Signal(str)

    def __init__(self, devices: list[DeviceConfig], data_path: Path, parent=None):
        super().__init__(parent)
        self.devices, self.data_path = devices, data_path
        self.stop_requested = threading.Event()
        self.messages: Queue[tuple] = Queue(maxsize=100)
        self.last_logged: dict[str, str | None] = {}
        self.last_event: dict[str, tuple] = {}

    def request(self, *message) -> None:
        self.messages.put_nowait(message)

    def stop(self) -> None:
        self.stop_requested.set()

    def run(self) -> None:
        bus, database = None, None
        try:
            simulation = SimulatedBus(self.devices)
            bus = BusEngine(simulation)
            scheduler = PollingScheduler(bus, self.devices)
            database = Historian(self.data_path / "simulation.sqlite3")
            database.retain()
            last_emit = 0.0
            while not self.stop_requested.is_set():
                try:
                    message = self.messages.get_nowait()
                except Empty:
                    message = None
                if message:
                    if message[0] == "fault":
                        simulation.set_fault(message[1], message[2])
                    elif message[0] == "history":
                        self.history_ready.emit(message[1], database.history(message[1], message[2]))
                    elif message[0] == "events":
                        self.events_ready.emit(database.events())
                    elif message[0] == "inspect":
                        state=scheduler.states[message[1]]
                        number=message[2]
                        try:
                            result=bus.read(PROFILES[state.config.family],state.config.addressing,number,1)
                            self.inspection_ready.emit(state.config.id,number,result[number])
                        except OSError as error:
                            self.inspection_failed.emit(f"Read-only inspection failed: {error}")
                scheduler.run_once()
                now = time.monotonic()
                if now - last_emit >= 0.5:
                    snapshots = scheduler.snapshots()
                    for snapshot in snapshots:
                        config = snapshot["config"]
                        instrument = config["id"]
                        status = snapshot["raw"].get(2)
                        transition = snapshot["quality"], status
                        if transition != self.last_event.get(instrument):
                            label=PROFILES[config["family"]].status(status) if status is not None else "No status available"
                            database.event(utc_now(), instrument, f"{self.last_event.get(instrument, 'initial')} -> {transition}: {label}", snapshot["quality"])
                            if config["logging_enabled"] and snapshot["quality"] != "GOOD":
                                database.measurement(utc_now(), instrument, 1, None, "", snapshot["quality"], status)
                            self.last_event[instrument] = transition
                        stamp = snapshot["last_success"]
                        if stamp and stamp != self.last_logged.get(instrument) and snapshot["quality"] == "GOOD":
                            if config["logging_enabled"]:
                                for number in snapshot["raw"]:
                                    if number >= 257:
                                        continue
                                    value, unit = measurement(snapshot, number)
                                    if value is not None:
                                        database.measurement(stamp, instrument, number, float(value), unit, snapshot["quality"], status)
                            self.last_logged[instrument] = stamp
                    database.commit()
                    self.updated.emit(snapshots, bus.diagnostics())
                    self.events_ready.emit(database.events())
                    last_emit = now
                self.stop_requested.wait(0.02)
        except Exception as error:
            log.exception("monitoring_worker_failed")
            self.failed.emit(str(error))
        finally:
            if database is not None:
                database.close()
            if bus is not None:
                bus.close()
