"""Recording lifecycle independent of polling and plot windows."""
import copy
from datetime import datetime,timezone
from queue import Queue,Empty,Full
import sqlite3
import threading
import time
from PySide6.QtCore import QThread,Signal
from .recordings import RecordingStore,INTERVALS,stream_key,normalize_selections,recording_parameters
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.profiles import profile_name


class Recorder:
    """Deterministic session state machine, used only on the recording thread."""
    def __init__(self,data_path,*,clock=time.monotonic,store_factory=RecordingStore):
        from .maintenance import gate_for
        self.gate=gate_for(data_path);self.recording_lease=False;self.maintenance_waiting=False
        self.data_path=data_path;self.clock=clock;self.store_factory=store_factory
        self.store=None;self.path=None;self.session=None;self.parameters=[];self.key=None
        self.mode='manual';self.interval=1;self.main_only=False;self.armed=False
        self.selections=None;self.recording_profile=None;self.expected_profile=None
        self.seen={};self.started=None;self.elapsed_final=0;self.next_due=0;self.connected=None;self.error='';self.samples=0

    def options(self,mode,interval,main_only):
        if mode not in ('manual','automatic') or interval not in INTERVALS:raise ValueError('Invalid recording options')
        active=self.session is not None;previous_mode=self.mode;previous_armed=self.armed
        self.finish('Recording options changed')
        self.mode=mode;self.interval=interval;self.main_only=bool(main_only)
        self.armed=active or previous_armed and mode==previous_mode or mode=='automatic' and previous_mode!='automatic';self.error=''

    def configure(self,mode,interval,selections):
        if self.session:raise ValueError('Stop recording before changing parameters or interval')
        selections=normalize_selections(selections)
        self.options(mode,interval,False);self.selections=selections

    def start_selected(self,mode,interval,selections,snapshot,expected_profile):
        if self.session:raise ValueError('Recording is already active')
        selections=normalize_selections(selections)
        if snapshot and profile_name(DeviceConfig(**snapshot['config']))!=expected_profile:raise ValueError('Analyzer profile changed; review recording parameters')
        chosen=selections.get(expected_profile,[1])
        if not chosen:raise ValueError('Select at least one recording parameter')
        self.configure(mode,interval,selections);self.start();self.expected_profile=expected_profile

    def finish(self,reason):
        if self.started is not None:self.elapsed_final=max(0,self.clock()-self.started);self.started=None
        if self.session:
            session=self.session;self.session=None
            try:self.store.end(session,reason)
            finally:
                if self.recording_lease:self.gate.leave_recording();self.recording_lease=False
        elif self.recording_lease:self.gate.leave_recording();self.recording_lease=False
        self.connected=None;self.seen={};self.key=None;self.expected_profile=None

    def start(self):self.armed=True;self.error='';self.expected_profile=None

    def stop(self):
        self.armed=False;self.finish('Stopped by operator')

    def tick(self,snapshot,*,received=None):
        now=self.clock()
        good=bool(snapshot and snapshot['quality']=='GOOD' and snapshot.get('last_success') and received is not None and now-received<=max(5,snapshot['config']['interval']*3) and snapshot.get('age') is not None and snapshot['age']+now-received<=max(5,snapshot['config']['interval']*3))
        if snapshot and self.session and stream_key(snapshot)!=self.key:
            self.finish('Analyzer identity/profile changed')
            if self.mode=='manual':self.armed=False
        if not self.session and self.armed and good:
            config=DeviceConfig(**snapshot['config']);key=profile_name(config)
            if self.expected_profile and key!=self.expected_profile:
                self.armed=False;self.error='Analyzer profile changed; review recording parameters';return
            selected=self.selections.get(key,[1]) if self.selections is not None else None
            if selected==[]:self.armed=False;return
            if not self.recording_lease:
                if not self.gate.enter_recording():self.maintenance_waiting=True;return
                self.recording_lease=True;self.maintenance_waiting=False
            path=self.data_path/('hardware.sqlite3' if snapshot.get('source')=='hardware' else 'simulation.sqlite3')
            if self.path!=path:
                if self.store:self.store.close()
                self.store=self.store_factory(path);self.path=path
            self.session,self.parameters=self.store.start(snapshot,self.interval,self.main_only,self.mode,selected=selected)
            self.recording_profile=key
            self.expected_profile=None
            self.key=stream_key(snapshot);self.started=now;self.elapsed_final=0;self.next_due=now;self.seen={};self.samples=0;self.connected=True
        if not self.session:return
        if not good:
            if self.connected is not False:self.store.gap(self.session,snapshot['quality'] if snapshot and snapshot['quality']!='GOOD' else 'OFFLINE')
            self.connected=False;return
        if self.connected is False:
            self.store.gap(self.session,'RESUMED');self.next_due=now
        self.connected=True
        if now>=self.next_due:
            count=self.store.append(self.session,snapshot,self.parameters,self.seen)
            if count:self.samples+=1
            self.next_due=now+self.interval

    def fail(self,error):
        self.error=f'Recording stopped: {error}';self.armed=False
        try:self.finish('Storage error: '+str(error))
        except (sqlite3.Error,OSError):self.session=None

    def status(self):
        state='Error' if self.error else 'Paused — communication unavailable' if self.session and not self.connected else 'Recording' if self.session else 'Waiting for database maintenance' if self.armed and self.maintenance_waiting else 'Waiting for communication' if self.armed else 'Stopped'
        return dict(state=state,error=self.error,session=self.session,mode=self.mode,interval=self.interval,main_only=self.main_only,armed=self.armed,
                    selected_parameters=[p['number'] for p in self.parameters] if self.session else [],recording_profile=self.recording_profile,
                    elapsed=max(0,self.clock()-self.started) if self.started is not None else self.elapsed_final,samples=self.samples)

    def close(self):
        try:self.finish('Application shutdown')
        finally:
            if self.store:self.store.close()


class RecordingWorker(QThread):
    status_ready=Signal(object)
    failed=Signal(str)

    def __init__(self,data_path,options=None,parent=None):
        super().__init__(parent);self.data_path=data_path;self.options=options or {}
        self.commands=Queue(maxsize=64);self.lock=threading.Lock();self.latest=None;self.received=None
        self.stopping=threading.Event();self.wake=threading.Event()

    def observe(self,snapshot):
        with self.lock:self.latest=copy.deepcopy(snapshot);self.received=time.monotonic()
        self.wake.set()

    def request(self,*message):
        try:self.commands.put_nowait(message);self.wake.set()
        except Full:self.failed.emit('Recording request queue is full; request was not accepted')

    def stop(self):self.stopping.set();self.wake.set()

    def run(self):
        recorder=Recorder(self.data_path);last_emit=0
        try:
            recorder.configure(self.options.get('mode','manual'),self.options.get('interval',1),self.options.get('parameters_by_profile',{}))
            while not self.stopping.is_set():
                try:
                    try:message=self.commands.get_nowait()
                    except Empty:message=None
                    with self.lock:snapshot=self.latest;received=self.received
                    if message:
                        try:
                            if message[0]=='options':
                                if recorder.session:raise ValueError('Stop recording before changing options')
                                recorder.options(*message[1:])
                            elif message[0]=='selection_options':recorder.configure(*message[1:])
                            elif message[0]=='start_selection':recorder.start_selected(*message[1:4],snapshot,message[4])
                            elif message[0]=='start':recorder.start()
                            elif message[0]=='stop':recorder.stop()
                        except ValueError as error:self.failed.emit(str(error))
                    recorder.tick(snapshot,received=received)
                except (sqlite3.Error,OSError,ValueError) as error:
                    recorder.fail(error);self.failed.emit(recorder.error)
                now=time.monotonic()
                if now-last_emit>=.25:self.status_ready.emit(recorder.status());last_emit=now
                self.wake.wait(.05);self.wake.clear()
        finally:
            try:recorder.close()
            except (sqlite3.Error,OSError) as error:self.failed.emit(f'Recording shutdown: {error}; session may be unfinished')


class RecordingJob(QThread):
    completed=Signal(object)
    failed=Signal(str)

    def __init__(self,operation,parent=None):super().__init__(parent);self.operation=operation

    def run(self):
        try:self.completed.emit(self.operation())
        except (sqlite3.Error,OSError,ValueError,KeyError) as error:self.failed.emit(str(error))
