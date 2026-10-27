"""Recording lifecycle independent of polling and plot windows."""
import copy
from datetime import datetime,timezone
from queue import Queue,Empty,Full
import sqlite3
import threading
import time
from PySide6.QtCore import QThread,Signal
from .recordings import RecordingStore,INTERVALS,stream_key


class Recorder:
    """Deterministic session state machine, used only on the recording thread."""
    def __init__(self,data_path,*,clock=time.monotonic,store_factory=RecordingStore):
        self.data_path=data_path;self.clock=clock;self.store_factory=store_factory
        self.store=None;self.path=None;self.session=None;self.parameters=[];self.key=None
        self.mode='manual';self.interval=1;self.main_only=False;self.armed=False
        self.seen={};self.started=None;self.elapsed_final=0;self.next_due=0;self.connected=None;self.error='';self.samples=0

    def options(self,mode,interval,main_only):
        if mode not in ('manual','automatic') or interval not in INTERVALS:raise ValueError('Invalid recording options')
        active=self.session is not None;previous_mode=self.mode;previous_armed=self.armed
        self.finish('Recording options changed')
        self.mode=mode;self.interval=interval;self.main_only=bool(main_only)
        self.armed=active or previous_armed and mode==previous_mode or mode=='automatic' and previous_mode!='automatic';self.error=''

    def finish(self,reason):
        if self.started is not None:self.elapsed_final=max(0,self.clock()-self.started);self.started=None
        if self.session:
            session=self.session;self.session=None
            self.store.end(session,reason)
        self.connected=None;self.seen={};self.key=None

    def start(self):self.armed=True;self.error=''

    def stop(self):
        self.armed=False;self.finish('Stopped by operator')

    def tick(self,snapshot,*,received=None):
        now=self.clock()
        good=bool(snapshot and snapshot['quality']=='GOOD' and snapshot.get('last_success') and received is not None and now-received<=max(5,snapshot['config']['interval']*3) and snapshot.get('age') is not None and snapshot['age']+now-received<=max(5,snapshot['config']['interval']*3))
        if snapshot and self.session and stream_key(snapshot)!=self.key:
            self.finish('Analyzer identity/profile changed')
            if self.mode=='manual':self.armed=False
        if not self.session and self.armed and good:
            path=self.data_path/('hardware.sqlite3' if snapshot.get('source')=='hardware' else 'simulation.sqlite3')
            if self.path!=path:
                if self.store:self.store.close()
                self.store=self.store_factory(path);self.path=path
            self.session,self.parameters=self.store.start(snapshot,self.interval,self.main_only,self.mode)
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
        state='Error' if self.error else 'Paused — communication unavailable' if self.session and not self.connected else 'Recording' if self.session else 'Waiting for communication' if self.armed else 'Stopped'
        return dict(state=state,error=self.error,session=self.session,mode=self.mode,interval=self.interval,main_only=self.main_only,armed=self.armed,
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
            recorder.options(self.options.get('mode','manual'),self.options.get('interval',1),self.options.get('main_only',False))
            while not self.stopping.is_set():
                try:
                    try:message=self.commands.get_nowait()
                    except Empty:message=None
                    if message:
                        if message[0]=='options':recorder.options(*message[1:])
                        elif message[0]=='start':recorder.start()
                        elif message[0]=='stop':recorder.stop()
                    with self.lock:snapshot=self.latest;received=self.received
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
