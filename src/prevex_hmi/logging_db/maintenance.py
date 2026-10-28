"""Recording retention/maintenance; no analyzer transport dependencies."""
from contextlib import contextmanager,closing
from datetime import datetime,timedelta,timezone
import hashlib,json,shutil,sqlite3,threading,time,uuid,tempfile,copy
from pathlib import Path
from .recordings import sessions,read_connection

PERIODS=(30,90,180,365)
_gates={};_registry_lock=threading.Lock()


class Busy(ValueError):pass


class DataGate:
    def __init__(self):
        self.lock=threading.Lock();self.recorders=0;self.readers=0;self.monitors=0;self.commands=0;self.history_writers=0;self.exclusive=False

    def enter_recording(self):
        with self.lock:
            if self.exclusive:return False
            self.recorders+=1;return True

    def leave_recording(self):
        with self.lock:self.recorders-=1

    def enter_monitoring(self):
        with self.lock:
            if self.exclusive:return False
            self.monitors+=1;return True

    def leave_monitoring(self):
        with self.lock:self.monitors-=1

    def enter_history(self):
        with self.lock:
            if self.exclusive:return False
            self.history_writers+=1;return True

    def leave_history(self):
        with self.lock:self.history_writers-=1

    def enter_command(self):
        with self.lock:
            if self.exclusive:return False
            self.commands+=1;return True

    def leave_command(self):
        with self.lock:self.commands-=1

    @contextmanager
    def reading(self):
        with self.lock:
            if self.exclusive:raise Busy('Database maintenance is running; try again when it finishes')
            self.readers+=1
        try:yield
        finally:
            with self.lock:self.readers-=1

    @contextmanager
    def maintenance(self,*,vacuum=False):
        deadline=time.monotonic()+2
        while True:
            with self.lock:
                if self.exclusive or self.recorders or self.readers:raise Busy('Stop recording and wait for CSV exports/backups before maintenance')
                if self.commands:raise Busy('A controller action is pending; wait for its verification before maintenance')
                if vacuum and self.monitors:raise Busy('Disconnect monitoring before optimization; it shares this SQLite database')
                if not self.history_writers:self.exclusive=True;break
                if time.monotonic()>=deadline:raise Busy('A history transaction is still active; retry maintenance when it finishes')
            time.sleep(.01)
        try:yield
        finally:
            with self.lock:self.exclusive=False


def gate_for(directory):
    key=str(Path(directory).resolve()).casefold()
    with _registry_lock:return _gates.setdefault(key,DataGate())


class RecordingManagement:
    def __init__(self,directory):
        self.directory=Path(directory);self.gate=gate_for(directory)
        self.paths=[self.directory/'simulation.sqlite3',self.directory/'hardware.sqlite3']
        self.policy_path=self.directory/'recording-retention.json'
        self.history_lock=threading.Lock();self.history_offset=0;self.history_identity=None;self.history_cache={}

    def operation_status(self):
        """Incrementally project the existing journal; recording rows stay read-only."""
        path=self.directory/'recording-maintenance.jsonl'
        with self.history_lock:
            if path.exists():
                stat=path.stat();identity=(stat.st_dev,stat.st_ino)
                if identity!=self.history_identity or stat.st_size<self.history_offset:
                    self.history_offset=0;self.history_cache={};self.history_identity=identity
                with path.open('rb') as stream:
                    stream.seek(self.history_offset)
                    while True:
                        start=stream.tell();line=stream.readline()
                        if not line:break
                        if not line.endswith(b'\n'):stream.seek(start);break
                        try:event=json.loads(line)
                        except (ValueError,UnicodeError):continue
                        if not isinstance(event,dict) or not event.get('timestamp'):continue
                        operation=event.get('operation','')
                        if not isinstance(operation,str):continue
                        if event.get('actor')=='Automatic retention' and operation in ('DELETE_COMPLETE','DEFERRED'):
                            self.history_cache['cleanup_attempt']=event
                            if operation=='DELETE_COMPLETE':self.history_cache['cleanup']=event
                        elif operation.startswith('BACKUP_') or operation=='BACKUP':
                            if operation!='BACKUP' or self.history_cache.get('backup',{}).get('operation')!='BACKUP_STARTED':self.history_cache['backup']=event
                        elif operation.startswith('OPTIMIZE_') or operation=='VACUUM_FAILED':self.history_cache['optimization']=event
                    self.history_offset=stream.tell()
            result=copy.deepcopy(self.history_cache)
        # Older builds recorded successful VACUUM only in the SQLite ledger.
        if 'optimization' not in result:
            for database in self.paths:
                if not database.exists():continue
                with closing(read_connection(database)) as db:
                    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='recording_maintenance'").fetchone():continue
                    row=db.execute("SELECT timestamp,detail FROM recording_maintenance WHERE operation='VACUUM_COMPLETE' ORDER BY id DESC LIMIT 1").fetchone()
                    if row and (not result.get('optimization') or row['timestamp']>result['optimization']['timestamp']):result['optimization']=dict(timestamp=row['timestamp'],operation='OPTIMIZE_COMPLETE',detail=json.loads(row['detail']))
        return result

    def summary(self):return dict(policy=self.policy(),operations=self.operation_status())

    def optimization_blocker(self):
        with self.gate.lock:
            if self.gate.recorders:return 'Stop recording before optimizing storage.'
            if self.gate.monitors:return 'Disconnect monitoring before optimizing storage.'
            if self.gate.exclusive or self.gate.readers or self.gate.history_writers or self.gate.commands:return 'Wait for current database operations or controller verification to finish.'
        return ''

    def admin(self,token):
        path=self.directory/'users.sqlite3'
        if not token or not path.exists():raise PermissionError('Administrator sign-in required')
        with closing(read_connection(path)) as db:
            row=db.execute('SELECT u.name,u.role,u.must_change FROM sessions s JOIN users u ON u.name=s.name WHERE s.token_hash=? AND s.expires>? AND u.active=1',
                           (hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        if not row or row[1]!='Administrator' or row[2]:raise PermissionError('Current Administrator sign-in required')
        return row[0]

    def policy(self):
        if not self.policy_path.exists():return dict(enabled=False,days=30)
        data=json.loads(self.policy_path.read_text(encoding='utf-8'))
        if type(data.get('enabled')) is not bool or type(data.get('days')) is not int or data['days'] not in PERIODS:raise ValueError('Invalid retention policy; automatic deletion is disabled')
        return data

    def log(self,actor,operation,detail):
        self.directory.mkdir(parents=True,exist_ok=True)
        with (self.directory/'recording-maintenance.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat(),actor=actor,operation=operation,detail=detail))+'\n')

    def set_policy(self,token,enabled,days):
        actor=self.admin(token)
        if type(enabled) is not bool or type(days) is not int or days not in PERIODS:raise ValueError('Invalid retention period')
        with self.gate.reading():
            self.log(actor,'POLICY_REQUEST',dict(enabled=enabled,days=days))
            temporary=self.policy_path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_text(json.dumps(dict(enabled=enabled,days=days)),encoding='utf-8');self.admin(token);temporary.replace(self.policy_path)
            finally:temporary.unlink(missing_ok=True)
            try:self.log(actor,'POLICY_SAVED',dict(enabled=enabled,days=days))
            except OSError as error:return dict(enabled=enabled,days=days,warning=f'Policy applied; completion log failed: {error}')
            return dict(enabled=enabled,days=days)

    @staticmethod
    def schema(db):
        db.execute('CREATE TABLE IF NOT EXISTS recording_kept (session_id TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE IF NOT EXISTS recording_maintenance (id INTEGER PRIMARY KEY,timestamp TEXT NOT NULL,actor TEXT NOT NULL,operation TEXT NOT NULL,detail TEXT NOT NULL)')

    @staticmethod
    def audit(db,actor,operation,detail):
        db.execute('INSERT INTO recording_maintenance(timestamp,actor,operation,detail) VALUES (?,?,?,?)',
                   (datetime.now(timezone.utc).isoformat(),actor,operation,json.dumps(detail)))

    def inventory(self):
        with self.gate.reading():
            rows=sessions(self.paths,summaries=True);sizes=[]
            for path in self.paths:
                total=sum(p.stat().st_size for p in (path,Path(str(path)+'-wal'),Path(str(path)+'-shm')) if p.exists())
                sizes.append(dict(path=str(path),bytes=total))
                own=[r for r in rows if r['path']==str(path)]
                if not own:continue
                with closing(read_connection(path)) as db:
                    kept={r[0] for r in db.execute('SELECT session_id FROM recording_kept')} if db.execute("SELECT 1 FROM sqlite_master WHERE name='recording_kept'").fetchone() else set()
                    usage={r[0]:r[1] for r in db.execute('SELECT session_id,SUM(80+length(acquired_at)+COALESCE(length(value),0)+length(unit)+length(quality)) FROM recording_values GROUP BY session_id')}
                    frames={r[0]:r[1] for r in db.execute('SELECT session_id,COUNT(*) FROM recording_frames GROUP BY session_id')}
                    for row in own:row.update(protected=row['id'] in kept,approximate_bytes=usage.get(row['id'],0)+frames.get(row['id'],0)*100+len(row['config'])+len(row['identity'])+len(row['parameters'])+200)
            return dict(sessions=rows,databases=sizes,policy=self.policy(),operations=self.operation_status())

    def keep(self,token,ids,protected):
        actor=self.admin(token)
        with self.gate.reading():
            for path in self.paths:
                if not path.exists():continue
                with closing(sqlite3.connect(path,timeout=.25)) as db,db:
                    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='recording_sessions'").fetchone():continue
                    self.schema(db);self.admin(token)
                    for sid in set(ids):
                        if not db.execute('SELECT 1 FROM recording_sessions WHERE id=?',(sid,)).fetchone():continue
                        if protected:db.execute('INSERT OR IGNORE INTO recording_kept VALUES (?)',(sid,))
                        else:db.execute('DELETE FROM recording_kept WHERE session_id=?',(sid,))
                        self.audit(db,actor,'KEEP' if protected else 'UNKEEP',dict(session=sid))

    def delete(self,token,ids,*,confirmed=False,cutoff=None):
        self.admin(token)
        if not confirmed:raise PermissionError('Permanent deletion requires confirmation')
        if not isinstance(ids,(list,tuple,set)) or any(not isinstance(sid,str) for sid in ids):raise ValueError('Choose explicit recording session IDs')
        if cutoff and datetime.fromisoformat(cutoff).tzinfo is None:raise ValueError('Deletion cutoff requires a timezone')
        return self._delete(ids,token=token,cutoff=cutoff)

    def _delete(self,ids=None,*,token=None,cutoff=None,automatic=False):
        removed=[];skipped=[]
        with self.gate.maintenance():
            actor='Automatic retention' if automatic else self.admin(token)
            self.log(actor,'DELETE_REQUEST',dict(sessions=list(ids) if ids is not None else None,cutoff=cutoff,automatic=automatic))
            for path in self.paths:
                if not path.exists():continue
                with closing(sqlite3.connect(path,timeout=.25)) as db:
                    db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
                    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='recording_sessions'").fetchone():continue
                    with db:
                        self.schema(db)
                    # Each completed session is removed atomically with its
                    # measurements and persistent deletion ledger entry.
                    candidates=db.execute('SELECT * FROM recording_sessions').fetchall()
                    for row in candidates:
                        sid=row['id']
                        if ids is not None and sid not in ids:continue
                        if not row['ended_at'] or cutoff and datetime.fromisoformat(row['ended_at'])>=datetime.fromisoformat(cutoff):skipped.append(sid);continue
                        with db:
                            db.execute('BEGIN IMMEDIATE')
                            if token:self.admin(token)
                            fresh=db.execute('SELECT * FROM recording_sessions WHERE id=?',(sid,)).fetchone()
                            if not fresh or not fresh['ended_at'] or db.execute('SELECT 1 FROM recording_kept WHERE session_id=?',(sid,)).fetchone():skipped.append(sid);continue
                            if cutoff and datetime.fromisoformat(fresh['ended_at'])>=datetime.fromisoformat(cutoff):skipped.append(sid);continue
                            self.audit(db,actor,'DELETE',dict(session=sid,started_at=fresh['started_at'],ended_at=fresh['ended_at'],profile=fresh['profile'],config=json.loads(fresh['config']),automatic=automatic))
                            db.execute('DELETE FROM recording_values WHERE session_id=?',(sid,))
                            db.execute('DELETE FROM recording_frames WHERE session_id=?',(sid,))
                            db.execute('DELETE FROM recording_kept WHERE session_id=?',(sid,))
                            db.execute('DELETE FROM recording_sessions WHERE id=?',(sid,))
                        removed.append(sid)
            self.log(actor,'DELETE_COMPLETE',dict(deleted=removed,skipped=skipped))
        return dict(deleted=removed,skipped=skipped)

    def retention(self,now=None):
        try:
            policy=self.policy()
            if not policy['enabled']:return dict(deleted=[],skipped=[],disabled=True)
            now=now or datetime.now(timezone.utc)
            cutoff=(now-timedelta(days=policy['days'])).isoformat()
            return self._delete(cutoff=cutoff,automatic=True)
        except (ValueError,OSError,sqlite3.Error) as error:
            try:self.log('Automatic retention','DEFERRED',str(error))
            except OSError:pass
            raise

    def backup(self,token,destination):
        actor=self.admin(token);self.log(actor,'BACKUP_STARTED',str(destination))
        try:result=self._backup(token,destination)
        except (OSError,ValueError,sqlite3.Error) as error:
            try:self.log(actor,'BACKUP_FAILED',str(error))
            except OSError:pass
            raise
        self.log(actor,'BACKUP_COMPLETE',dict(files=result));return result

    def _backup(self,token,destination):
        actor=self.admin(token);destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True);created=[]
        with self.gate.reading():
            for path in self.paths:
                if not path.exists():continue
                size=sum(p.stat().st_size for p in (path,Path(str(path)+'-wal')) if p.exists())
                if shutil.disk_usage(destination).free<size*2+16*1024*1024:raise OSError('Insufficient disk space for a safe backup')
                target=destination/f"PREVEX_{path.stem}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.sqlite3"
                self.admin(token);deadline=time.monotonic()+120
                def progress(*args):
                    if time.monotonic()>deadline:raise OSError('Backup timed out; retry when recording is stopped')
                try:
                    with closing(read_connection(path)) as source,closing(sqlite3.connect(target)) as output:
                        source.backup(output,pages=256,progress=progress,sleep=.01)
                        if output.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise OSError('Backup integrity check failed')
                except BaseException:target.unlink(missing_ok=True);raise
                created.append(str(target));self.log(actor,'BACKUP',dict(source=str(path),destination=str(target)))
        return created

    def optimize(self,token,*,confirmed=False):
        actor=self.admin(token)
        if not confirmed:raise PermissionError('Optimization requires confirmation')
        self.log(actor,'OPTIMIZE_STARTED','Storage optimization requested')
        try:result=self._optimize(token,confirmed=confirmed)
        except (OSError,ValueError,sqlite3.Error) as error:
            try:self.log(actor,'OPTIMIZE_FAILED',str(error))
            except OSError:pass
            raise
        self.log(actor,'OPTIMIZE_COMPLETE',dict(databases=result));return result

    def _optimize(self,token,*,confirmed=False):
        actor=self.admin(token)
        if not confirmed:raise PermissionError('Optimization requires confirmation')
        results=[]
        with self.gate.maintenance(vacuum=True):
            for path in self.paths:
                if not path.exists():continue
                with closing(sqlite3.connect(path,timeout=.25)) as db:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='recording_sessions'").fetchone() and db.execute('SELECT 1 FROM recording_sessions WHERE ended_at IS NULL LIMIT 1').fetchone():raise Busy('An active or unfinished session prevents optimization')
                    size=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]
                    # Check both the database and OS temporary volumes: SQLite
                    # may need up to twice the database size in temporary space.
                    if any(shutil.disk_usage(p).free<size*2+16*1024*1024 for p in (path.parent,Path(tempfile.gettempdir()))):raise OSError('Insufficient disk space for VACUUM (requires twice the database size plus16 MiB)')
                    self.admin(token);self.schema(db);self.audit(db,actor,'VACUUM_REQUEST',dict(bytes=size));db.commit()
                    self.log(actor,'VACUUM_REQUEST',str(path))
                    try:
                        checkpoint=db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
                        if checkpoint and checkpoint[0]:raise Busy('Other database readers/writers prevent optimization; retry when they are idle')
                        db.execute('VACUUM')
                        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise OSError('Database integrity check failed after optimization')
                        self.audit(db,actor,'VACUUM_COMPLETE',dict(before=size,after=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]));db.commit()
                        checkpoint=db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
                        if checkpoint and checkpoint[0]:raise Busy('Optimization completed; other readers prevent final size reclamation. Retry when idle')
                    except (OSError,ValueError,sqlite3.Error) as error:
                        self.log(actor,'VACUUM_FAILED',str(error));raise
                    results.append(str(path))
        return results
