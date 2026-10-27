from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import time


class Historian:
    """Owned by the polling worker; no SQLite connection crosses threads."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path,timeout=.25)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, instrument TEXT NOT NULL,
                register_number INTEGER NOT NULL, value REAL, unit TEXT NOT NULL,
                quality TEXT NOT NULL, status INTEGER);
            CREATE INDEX IF NOT EXISTS measurement_lookup
                ON measurements(instrument, register_number, timestamp);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, instrument TEXT NOT NULL,
                description TEXT NOT NULL, quality TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS command_audit (
                id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, instrument TEXT NOT NULL,
                actor TEXT NOT NULL, code INTEGER NOT NULL, result TEXT NOT NULL, detail TEXT NOT NULL);
        """)

    def measurement(self, timestamp: str, instrument: str, number: int, value: float | None, unit: str, quality: str, status: int | None) -> None:
        self.db.execute("INSERT INTO measurements(timestamp,instrument,register_number,value,unit,quality,status) VALUES (?,?,?,?,?,?,?)", (timestamp,instrument,number,value,unit,quality,status))

    def event(self, timestamp: str, instrument: str, description: str, quality: str) -> None:
        self.db.execute("INSERT INTO events(timestamp,instrument,description,quality) VALUES (?,?,?,?)", (timestamp,instrument,description,quality))

    def commit(self) -> None:
        self.db.commit()

    def command_audit(self,instrument,actor,code,result,detail):
        from prevex_hmi.devices.models import utc_now
        self.db.execute("INSERT INTO command_audit(timestamp,instrument,actor,code,result,detail) VALUES (?,?,?,?,?,?)",(utc_now(),instrument,actor,code,result,detail))
        self.db.commit()

    def audit_rows(self):
        return self.db.execute("SELECT timestamp,instrument,actor,code,result,detail FROM command_audit ORDER BY id DESC LIMIT 500").fetchall()

    def history(self, instrument: str, hours: int = 24, limit: int = 5000) -> list[tuple]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="milliseconds")
        return list(reversed(self.db.execute("SELECT timestamp,value,unit,quality,status FROM measurements WHERE instrument=? AND register_number=1 AND timestamp>=? ORDER BY timestamp DESC,id DESC LIMIT ?", (instrument,since,limit)).fetchall()))

    def events(self) -> list[tuple]:
        return self.db.execute("SELECT timestamp,instrument,description,quality FROM events ORDER BY id DESC LIMIT 500").fetchall()

    def retain(self, days: int = 90) -> None:
        if not 1 <= days <= 3650:
            raise ValueError("Retention must be 1..3650 days")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="milliseconds")
        self.db.execute("DELETE FROM measurements WHERE timestamp < ?", (cutoff,))
        # Alarm/event history is deliberately retained independently.
        self.db.commit()

    def close(self) -> None:
        self.db.commit()
        self.db.close()


class MonitoringHistorian:
    """A storage fault must not take the serial monitoring loop down.

    Audit-dependent commands fail closed. Logging stays stopped after an error
    until reconnect; no command or measurement write is retried implicitly.
    """
    def __init__(self,path,on_error,*,factory=Historian):
        from .maintenance import gate_for
        self.gate=gate_for(Path(path).parent);self.history_lease=False;self.pending=[]
        self.store=None;self.error='';self.on_error=on_error
        while not self.gate.enter_history():time.sleep(.05)
        try:self.store=factory(path)
        except (sqlite3.Error,OSError) as error:self.disable(error)
        finally:self.gate.leave_history()

    def release_history(self):
        if self.history_lease:self.gate.leave_history();self.history_lease=False

    def disable(self,error):
        self.error=str(error);self.on_error('History storage unavailable: '+self.error)

    def call(self,name,*args,default=None):
        if self.error or self.store is None:return default
        writing=name in ('measurement','event','commit','retain','command_audit')
        if writing and not self.history_lease:
            if not self.gate.enter_history():
                if name=='command_audit':raise PermissionError('Command audit temporarily unavailable during database maintenance; no command sent')
                if name!='commit':
                    if len(self.pending)>=100000:self.disable('Maintenance history buffer full; reconnect after maintenance')
                    else:self.pending.append((name,args))
                return default
            self.history_lease=True
        try:
            if writing and self.pending:
                for pending_name,pending_args in self.pending:getattr(self.store,pending_name)(*pending_args)
                self.pending=[]
            return getattr(self.store,name)(*args)
        except (sqlite3.Error,OSError) as error:
            try:self.store.db.rollback()
            except sqlite3.Error:pass
            self.disable(error);return default
        finally:
            if self.error or writing and name in ('commit','retain','command_audit'):self.release_history()

    def measurement(self,*args):self.call('measurement',*args)
    def event(self,*args):self.call('event',*args)
    def commit(self):self.call('commit')
    def retain(self):self.call('retain')
    def history(self,*args):return self.call('history',*args,default=[])
    def events(self):return self.call('events',default=[])
    def audit_rows(self):return self.call('audit_rows',default=[])
    def command_audit(self,*args):
        self.call('command_audit',*args)
        if self.error:raise PermissionError('Command audit unavailable; reconnect after resolving storage: '+self.error)
    def close(self):
        if self.store:
            try:
                if not self.error:
                    while not self.history_lease:
                        if self.gate.enter_history():self.history_lease=True
                        else:time.sleep(.05)
                    self.call('commit')
            except (sqlite3.Error,OSError) as error:self.disable(error)
            finally:self.release_history();self.store.db.close()
