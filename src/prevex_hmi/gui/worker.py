from __future__ import annotations
from dataclasses import asdict, replace
import logging
from pathlib import Path
from queue import Empty, Full, Queue
import threading
import time
import uuid
from PySide6.QtCore import QThread, Signal
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.commands import CommandController
from prevex_hmi.communication.scheduler import PollingScheduler
from prevex_hmi.devices.identification import detect, resolve_profile
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.devices.models import DeviceConfig, utc_now
from prevex_hmi.gui.presentation import measurement,uses_controller_fault_display
from prevex_hmi.logging_db.store import Historian,MonitoringHistorian
from prevex_hmi.security.users import UserStore
from prevex_hmi.profiles import PROFILES, profile_for,profile_name
from prevex_hmi.simulator.bus import SimulatedBus
from prevex_hmi.communication.validated_controls import validated_670
from prevex_hmi.profiles.common import COMMANDS

log=logging.getLogger(__name__)

class MonitoringWorker(QThread):
    updated=Signal(object,object)
    identified=Signal(object)
    history_ready=Signal(object)
    events_ready=Signal(object)
    audit_ready=Signal(object)
    inspection_ready=Signal(str)
    command_result=Signal(str)
    parameter_result=Signal(str)
    failed=Signal(str)
    storage_warning=Signal(str)

    def __init__(self,settings:dict,data_path:Path,parent=None,*,test_only=False,hardware_grant=None):
        super().__init__(parent)
        if len(settings['devices']) != 1: raise ValueError('One active analyzer required')
        self.settings,self.data_path=settings,data_path
        self.test_only=test_only
        self.hardware_grant=hardware_grant
        self.stop_requested=threading.Event()
        self.messages=Queue(maxsize=50)

    def request(self,*message):
        try: self.messages.put_nowait(message)
        except Full: self.command_result.emit('Request queue full; action not sent')

    def stop(self): self.stop_requested.set()

    def run(self):
        from prevex_hmi.logging_db.maintenance import gate_for
        gate=gate_for(self.data_path)
        while not gate.enter_monitoring():
            if self.stop_requested.wait(.1):return
        try:self.run_monitoring()
        finally:gate.leave_monitoring()

    def run_monitoring(self):
        from prevex_hmi.logging_db.maintenance import gate_for
        maintenance_gate=gate_for(self.data_path);command_lease=False
        bus=database=users=controller=None
        try:
            configured=DeviceConfig(**self.settings['devices'][0])
            connection=self.settings['connection']
            simulation=None
            physical=self.settings['mode']=='hardware'
            if physical:
                from prevex_hmi.communication.serial_transport import ReadOnlySerialTransport,ControllerBenchTransport,available_ports
                if self.hardware_grant is not None:self.hardware_grant.validate(self.settings,configured)
                elif connection['port'] not in available_ports():
                    raise ValueError('Select an available serial port. No port was opened.')
                from prevex_hmi.devices.compatibility import assumed_481
                bench=bool(self.hardware_grant and self.hardware_grant.operator_commands and not assumed_481(configured.assembly,configured.version))
                factory=ControllerBenchTransport if bench else ReadOnlySerialTransport
                options={'bench_grant':self.hardware_grant} if bench else {}
                transport=factory(connection['port'],hardware_authorized=True,addressing_reviewed=True,baud=connection['baud'],timeout=connection['timeout'],**options)
            else:
                actual=next(d for d in default_devices() if d.family == self.settings['simulated_family'])
                actual=replace(actual,id=configured.id,name=configured.name,address=configured.address,address_mode=configured.address_mode,pdu_offset=configured.pdu_offset,enabled=True,interval=configured.interval,range_mode=configured.range_mode,manual_maximum=configured.manual_maximum,gauge_minimum=configured.gauge_minimum,logging_enabled=configured.logging_enabled)
                selection=self.settings['analyzer_selection']
                if actual.family == "LEL" and (selection=='LEL 700 Series' or selection=='Auto Detect' and self.settings.get("simulated_lel_revision","legacy") == "700"):
                    from prevex_hmi.profiles.lel700 import TYPES
                    model=configured.assembly if configured.assembly in TYPES.values() else 'SNR705'
                    actual=replace(actual,assembly=model,version="7.01",fullscale=100)
                elif actual.family == 'LEL':
                    from prevex_hmi.profiles.lel670 import MODELS
                    actual=replace(actual,assembly=configured.assembly if configured.assembly in MODELS else actual.assembly,version='5.11')
                if actual.family == 'FID':actual=replace(actual,fullscale=configured.fullscale,units=configured.units or 'US')
                simulation=SimulatedBus([actual]);transport=simulation
            bus=BusEngine(transport,baud=connection['baud'])
            identity=detect(bus,configured.addressing,alternate_page=connection.get('identification_page') == 'alternate')
            if physical and self.hardware_grant:self.hardware_grant.validate_identity(identity)
            effective,warning,verified=resolve_profile(configured,self.settings['analyzer_selection'],identity)
            controls_verified=bool(self.hardware_grant and self.hardware_grant.operator_commands and self.settings['analyzer_selection'] in ('Auto Detect','LEL','LEL 670 Series') and 'PROFILE MISMATCH' not in warning) if physical else verified
            validated_controls=bool(physical and effective and verified and validated_670(effective))
            if validated_controls:controls_verified=True
            info={**asdict(identity),'warning':warning,'controls_verified':bool(controls_verified and not self.test_only),'test_only':self.test_only,'selected_profile':self.settings['analyzer_selection']}
            if effective:
                if effective.family == 'FID': effective=replace(effective,units=configured.units or 'US')
                effective=replace(effective,enabled=True)
                info['config']=asdict(effective)
                bus.read(profile_for(effective),effective.addressing,1,4)
                info['loaded_profile']=profile_name(effective)
                info['register_revision']=profile_for(effective).revision
            info['communication']='Valid Modbus response' if bus.stats.successes else 'No valid Modbus response'
            info['communication_ok']=bool(bus.stats.successes)
            self.identified.emit(info)
            if self.test_only or effective is None: return
            scheduler=PollingScheduler(bus,[effective])
            state=scheduler.states[effective.id]
            state.identification=identity.text
            database=MonitoringHistorian(self.data_path/('hardware.sqlite3' if physical else 'simulation.sqlite3'),self.storage_warning.emit,factory=Historian)
            database.retain()
            users=UserStore(self.data_path/'users.sqlite3')
            command_class=CommandController
            if validated_controls:
                from prevex_hmi.communication.validated_commands import ValidatedOperatingCommands
                command_class=ValidatedOperatingCommands
            elif physical and self.hardware_grant and self.hardware_grant.operator_commands:
                from prevex_hmi.communication.bench_commands import BenchOperatorCommands
                command_class=BenchOperatorCommands
            controller=command_class(bus,effective,database,users,identity_verified=controls_verified,expected_identity=identity,**({'connection':connection} if validated_controls else {}))
            from prevex_hmi.communication.parameters import ParameterAdjustments
            adjustments=ParameterAdjustments(controller)
            last_emit=last_identity=time.monotonic()
            last_logged=last_event=None
            identity_current=identity.verified;needs_identity_recheck=False
            while not self.stop_requested.is_set():
                if state.snapshot(time.monotonic())['quality']!='GOOD':controller.identity_verified=False
                try: message=self.messages.get_nowait()
                except Empty: message=None
                if message:
                    try:
                        kind=message[0]
                        if kind in ('parameter','command') and not command_lease:
                            if not maintenance_gate.enter_command():
                                text='Database maintenance is running; no controller command sent. Review and confirm again after it finishes.'
                                if kind=='parameter':self.parameter_result.emit(text)
                                else:self.command_result.emit(text)
                                continue
                            command_lease=True
                        if physical and kind in ('fault','reading','status'):
                            raise PermissionError('Simulation injection is unavailable for a real controller')
                        if kind == 'fault': simulation.set_fault(effective.addressing.packet_address,message[1])
                        elif kind == 'history': self.history_ready.emit(database.history(effective.id,message[1]))
                        elif kind == 'inspect':
                            number=message[1]
                            raw=bus.read(profile_for(effective),effective.addressing,number,1)[number]
                            state.raw[number]=raw;state.register_times[number]=time.monotonic()
                            state.register_timestamps[number]=utc_now()
                            self.inspection_ready.emit(f'Register {number}: {raw} / 0x{raw:04X}')
                        elif kind == 'reading':
                            target=simulation.devices[effective.addressing.packet_address]
                            if message[1] is not None: profile_for(effective).register(1).encode(message[1],effective.family,target.config.context)
                            target.forced_reading=message[1]
                        elif kind == 'status': simulation.devices[effective.addressing.packet_address].forced_status=message[1]
                        elif kind == 'parameter':
                            snapshot=state.snapshot(time.monotonic())
                            updates=adjustments.execute(message[1],message[2],message[3],message[4],confirmed=message[5],current=snapshot['quality']=='GOOD')
                            state.raw.update(updates);state.register_times.update({n:time.monotonic() for n in updates})
                            state.register_timestamps.update({n:utc_now() for n in updates})
                            self.parameter_result.emit(controller.result)
                        elif kind == 'command':
                            snapshot=state.snapshot(time.monotonic())
                            if snapshot['quality'] != 'GOOD':
                                actor,_=users.resolve(message[2])
                                controller.receipt={'id':uuid.uuid4().hex,'code':message[1],'state':'REJECTED','reply_received':False,'time':utc_now()}
                                controller.record(actor,message[1],'REJECTED','Communication is not current; command not sent')
                            else: controller.execute(message[1],message[2],confirmed=message[3])
                            receipt=controller.receipt or {}
                            if receipt.get('lock_register')==60 and 'lock_readback' in receipt:
                                # Publish the actual FC03 verification, never an optimistic toggle.
                                state.raw[60]=receipt['lock_readback'];state.register_times[60]=time.monotonic()
                                state.register_timestamps[60]=utc_now()
                            self.command_result.emit(controller.result)
                    except (OSError,ValueError,PermissionError,KeyError) as error: self.command_result.emit(str(error))
                    finally:
                        if command_lease and not controller.pending:maintenance_gate.leave_command();command_lease=False
                scheduler.run_once()
                now=time.monotonic()
                quality=state.snapshot(now)['quality']
                if quality!='GOOD':
                    needs_identity_recheck=bool(identity.verified);identity_current=False;controller.identity_verified=False
                elif needs_identity_recheck:
                    # Use the same serialized bus after recovery; cached GOOD
                    # measurements cannot restore a previous identity grant.
                    check=detect(bus,effective.addressing)
                    if not check.verified or (check.family,check.model,check.version,check.serial,check.text)!=(identity.family,identity.model,identity.version,identity.serial,identity.text):
                        raise OSError('Analyzer identity changed or could not be revalidated after communication loss. Connect to Analyzer to identify the current instrument.')
                    identity_current=True;needs_identity_recheck=False;last_identity=now;controller.identity_verified=controls_verified
                    self.identified.emit({**info,'revalidated':True,'communication_ok':True,'communication':'Fresh identity verified after communication recovery'})
                elif identity_current:controller.identity_verified=controls_verified
                if now-last_identity >= 30:
                    check=detect(bus,effective.addressing)
                    if physical and self.hardware_grant:self.hardware_grant.validate_identity(check)
                    last_identity=now
                    if (identity.verified and (not check.verified or (check.family,check.model,check.version,check.serial) != (identity.family,identity.model,identity.version,identity.serial))) or (check.family and check.family != effective.family):
                        raise OSError('Instrument identity changed or became unverifiable. Polling stopped; reconnect to identify again.')
                if now-last_emit >= 0.25:
                    snapshot=state.snapshot(now)
                    snapshot['identity_current']=identity_current
                    # Display-only retention belongs to CircularGauge. Never
                    # attach retained LCD data to logging/command snapshots.
                    snapshot['source']='hardware' if physical else 'simulation'
                    snapshot['instrument_quality']='INSTRUMENT_FAULT' if snapshot['raw'].get(2) not in (None,0,1,2,4,5,6,7,11,12) else 'GOOD'
                    snapshot['reading_source']='controller_lcd_fault' if uses_controller_fault_display(snapshot) else 'process_register'
                    try:controller.observe(snapshot)
                    except PermissionError as error:
                        controller.pending=None;controller.ambiguous=True;self.storage_warning.emit(str(error))
                    if command_lease and not controller.pending:maintenance_gate.leave_command();command_lease=False
                    if database.error:controller.ambiguous=True
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
                                if value is not None: database.measurement(snapshot['last_success'],effective.id,number,float(value),unit,'INSTRUMENT_FAULT_LCD' if number==1 and snapshot['reading_source']=='controller_lcd_fault' else snapshot['instrument_quality'],status)
                        last_logged=snapshot['last_success']
                    database.commit()
                    snapshot['control']={'verified':controller.identity_verified,'pending':controller.pending is not None,'pending_kind':getattr(controller.pending,'kind','status'),'ambiguous':controller.ambiguous,'blocked_commands':sorted(controller.blocked_commands),'message':controller.result,'receipt':getattr(controller,'receipt',None),'physical_commands':list(COMMANDS) if validated_controls else []}
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
                try:controller.record(pending.actor,pending.code,'UNKNOWN','Session disconnected during command; never retried')
                except PermissionError as error:self.storage_warning.emit(str(error))
            try:
                if database:database.close()
            finally:
                if command_lease:maintenance_gate.leave_command()
            if users: users.close()
            if bus: bus.close()
