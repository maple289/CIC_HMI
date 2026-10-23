from __future__ import annotations
from dataclasses import asdict, replace
import logging
from pathlib import Path
from queue import Empty, Full, Queue
import threading
import time
from PySide6.QtCore import QThread, Signal
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.commands import CommandController
from prevex_hmi.communication.scheduler import PollingScheduler
from prevex_hmi.devices.identification import detect, resolve_profile
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.devices.models import DeviceConfig, utc_now
from prevex_hmi.gui.presentation import measurement
from prevex_hmi.logging_db.store import Historian
from prevex_hmi.security.users import UserStore
from prevex_hmi.profiles import PROFILES, profile_for
from prevex_hmi.simulator.bus import SimulatedBus

log=logging.getLogger(__name__)

class MonitoringWorker(QThread):
    updated=Signal(object,object)
    identified=Signal(object)
    history_ready=Signal(object)
    events_ready=Signal(object)
    audit_ready=Signal(object)
    inspection_ready=Signal(str)
    command_result=Signal(str)
    failed=Signal(str)

    def __init__(self,settings:dict,data_path:Path,parent=None,*,test_only=False):
        super().__init__(parent)
        if len(settings['devices']) != 1: raise ValueError('One active analyzer required')
        self.settings,self.data_path=settings,data_path
        self.test_only=test_only
        self.stop_requested=threading.Event()
        self.messages=Queue(maxsize=50)

    def request(self,*message):
        try: self.messages.put_nowait(message)
        except Full: self.command_result.emit('Request queue full; action not sent')

    def stop(self): self.stop_requested.set()

    def run(self):
        bus=database=users=controller=None
        try:
            if self.settings['mode'] != 'simulation':
                raise PermissionError('Physical access is disabled pending explicit authorization and hardware validation. No port was opened.')
            configured=DeviceConfig(**self.settings['devices'][0])
            actual=next(d for d in default_devices() if d.family == self.settings['simulated_family'])
            actual=replace(actual,id=configured.id,name=configured.name,address=configured.address,address_mode=configured.address_mode,pdu_offset=configured.pdu_offset,enabled=True,interval=configured.interval,range_mode=configured.range_mode,manual_maximum=configured.manual_maximum,gauge_minimum=configured.gauge_minimum,logging_enabled=configured.logging_enabled)
            if actual.family == "LEL" and self.settings.get("simulated_lel_revision","legacy") == "700":
                actual=replace(actual,assembly="SNR705",version="7.01",fullscale=100)
            if actual.family == 'FID': actual=replace(actual,fullscale=configured.fullscale,units=configured.units or 'US')
            simulation=SimulatedBus([actual])
            connection=self.settings['connection']
            bus=BusEngine(simulation,baud=connection['baud'])
            identity=detect(bus,configured.addressing,alternate_page=connection.get('identification_page') == 'alternate')
            effective,warning,verified=resolve_profile(configured,self.settings['analyzer_selection'],identity)
            info={**asdict(identity),'warning':warning,'controls_verified':verified,'test_only':self.test_only}
            if effective:
                if effective.family == 'FID': effective=replace(effective,units=configured.units or 'US')
                effective=replace(effective,enabled=True)
                info['config']=asdict(effective)
                bus.read(profile_for(effective),effective.addressing,1,4)
            self.identified.emit(info)
            if self.test_only or effective is None: return
            scheduler=PollingScheduler(bus,[effective])
            state=scheduler.states[effective.id]
            state.identification=identity.text
            database=Historian(self.data_path/'simulation.sqlite3')
            database.retain()
            users=UserStore(self.data_path/'users.sqlite3')
            controller=CommandController(bus,effective,database,users,identity_verified=verified,expected_identity=identity)
            last_emit=last_identity=time.monotonic()
            last_logged=last_event=None
            while not self.stop_requested.is_set():
                try: message=self.messages.get_nowait()
                except Empty: message=None
                if message:
                    try:
                        kind=message[0]
                        if kind == 'fault': simulation.set_fault(effective.addressing.packet_address,message[1])
                        elif kind == 'history': self.history_ready.emit(database.history(effective.id,message[1]))
                        elif kind == 'inspect':
                            number=message[1]
                            raw=bus.read(profile_for(effective),effective.addressing,number,1)[number]
                            self.inspection_ready.emit(f'Register {number}: {raw} / 0x{raw:04X}')
                        elif kind == 'reading':
                            target=simulation.devices[effective.addressing.packet_address]
                            if message[1] is not None: profile_for(effective).register(1).encode(message[1],effective.family,target.config.context)
                            target.forced_reading=message[1]
                        elif kind == 'status': simulation.devices[effective.addressing.packet_address].forced_status=message[1]
                        elif kind == 'command':
                            snapshot=state.snapshot(time.monotonic())
                            if snapshot['quality'] != 'GOOD':
                                actor,_=users.resolve(message[2])
                                controller.record(actor,message[1],'REJECTED','Communication is not current; command not sent')
                            else: controller.execute(message[1],message[2],confirmed=message[3])
                            self.command_result.emit(controller.result)
                    except (OSError,ValueError,PermissionError,KeyError) as error: self.command_result.emit(str(error))
                scheduler.run_once()
                now=time.monotonic()
                if now-last_identity >= 30:
                    check=detect(bus,effective.addressing)
                    last_identity=now
                    if (identity.verified and (not check.verified or (check.family,check.model,check.version,check.serial) != (identity.family,identity.model,identity.version,identity.serial))) or (check.family and check.family != effective.family):
                        raise OSError('Instrument identity changed or became unverifiable. Polling stopped; reconnect to identify again.')
                if now-last_emit >= 0.25:
                    snapshot=state.snapshot(now)
                    controller.observe(snapshot)
                    status=snapshot['raw'].get(2)
                    event=(snapshot['quality'],status)
                    if event != last_event:
                        label=profile_for(effective).status(status) if status is not None else 'No status'
                        database.event(utc_now(),effective.id,f'{last_event or "initial"} -> {event}: {label}',snapshot['quality'])
                        if effective.logging_enabled and snapshot['quality'] != 'GOOD': database.measurement(utc_now(),effective.id,1,None,'',snapshot['quality'],status)
                        last_event=event
                    if snapshot['last_success'] and snapshot['last_success'] != last_logged and snapshot['quality'] == 'GOOD':
                        if effective.logging_enabled:
                            for number in snapshot['raw']:
                                if number >= 257: continue
                                value,unit=measurement(snapshot,number)
                                if value is not None: database.measurement(snapshot['last_success'],effective.id,number,float(value),unit,'GOOD',status)
                        last_logged=snapshot['last_success']
                    database.commit()
                    snapshot['control']={'verified':controller.identity_verified,'pending':controller.pending is not None,'ambiguous':controller.ambiguous,'message':controller.result}
                    self.updated.emit(snapshot,bus.diagnostics())
                    self.events_ready.emit(database.events())
                    self.audit_ready.emit(database.audit_rows())
                    last_emit=now
                self.stop_requested.wait(0.01)
        except Exception as error:
            log.exception('single_analyzer_worker_failed')
            self.failed.emit(str(error))
        finally:
            if controller and controller.pending:
                pending=controller.pending
                controller.record(pending.actor,pending.code,'UNKNOWN','Session disconnected during command; never retried')
            if database: database.close()
            if users: users.close()
            if bus: bus.close()
