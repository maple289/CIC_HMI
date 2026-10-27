"""Session recording from acquired cache observations; no transport dependency."""
from datetime import datetime,timezone
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import uuid

from prevex_hmi.devices.models import DeviceConfig,utc_now
from prevex_hmi.gui.presentation import measurement,uses_controller_fault_display
from prevex_hmi.profiles import profile_for,profile_name
from prevex_hmi.profiles.gauges import GAUGE_REGISTERS

INTERVALS=(1,2,5,10)
EXCLUDED_RECORDING_PARAMETERS=frozenset((2,23,24,38,39,42,50))


def normalize_selections(selections):
    from prevex_hmi.profiles.lel700 import GAUGES
    menus={'LEL 670 Series':GAUGE_REGISTERS['LEL'],'LEL 700 Series':GAUGES,'BTU':GAUGE_REGISTERS['BTU'],'FID':GAUGE_REGISTERS['FID']}
    if not isinstance(selections,dict):raise ValueError('Recording selections must be a profile map')
    result={}
    for key,numbers in selections.items():
        if key not in menus or not isinstance(numbers,list) or any(type(n) is not int or n not in menus[key] for n in numbers) or len(set(numbers))!=len(numbers):
            raise ValueError('Invalid GAUGES parameter selection')
        result[key]=[n for n in numbers if n not in EXCLUDED_RECORDING_PARAMETERS]
    return result


def recording_parameters(config,main_only=False,*,selected=None):
    profile=profile_for(config)
    if main_only:numbers=(1,2)
    elif profile.revision=='700':
        from prevex_hmi.profiles.lel700 import GAUGES
        numbers=GAUGES
    else:numbers=GAUGE_REGISTERS[config.family]
    result=[]
    available=tuple(dict.fromkeys((1,2,*numbers)))
    if not main_only:available=tuple(n for n in available if n not in EXCLUDED_RECORDING_PARAMETERS)
    if selected is not None:
        if not isinstance(selected,list) or any(type(n) is not int or n not in available for n in selected) or len(set(selected))!=len(selected):raise ValueError('Invalid GAUGES parameter selection')
        available=tuple(n for n in available if n in selected)
    for number in available:
        r=profile.register(number)
        try:unit=r.scale(config.family,config.context)[2]
        except ValueError:unit=r.unit or 'unit unverified'
        result.append(dict(number=number,name=r.name,unit=unit))
    return result


def stream_key(snapshot):
    config=DeviceConfig(**snapshot['config'])
    return (snapshot.get('source','simulation'),config.id,config.family,profile_for(config).revision,
            config.assembly,config.version,config.address,config.address_mode,config.pdu_offset,
            config.units,snapshot.get('raw',{}).get(3,config.fullscale),config.btu_unit,snapshot.get('identity',{}).get('serial',''),snapshot.get('identity',{}).get('text',''))


class RecordingStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.path,timeout=.25)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS recording_sessions (
                id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
                end_reason TEXT, config TEXT NOT NULL, identity TEXT NOT NULL,
                source TEXT NOT NULL, profile TEXT NOT NULL, interval_seconds INTEGER NOT NULL,
                parameters TEXT NOT NULL, mode TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS recording_frames (
                id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES recording_sessions(id),
                timestamp TEXT NOT NULL, quality TEXT NOT NULL, status INTEGER, status_timestamp TEXT);
            CREATE INDEX IF NOT EXISTS recording_frame_lookup ON recording_frames(session_id,timestamp,id);
            CREATE TABLE IF NOT EXISTS recording_values (
                frame_id INTEGER NOT NULL REFERENCES recording_frames(id), session_id TEXT NOT NULL,
                register_number INTEGER NOT NULL, acquired_at TEXT NOT NULL,
                value TEXT, unit TEXT NOT NULL, quality TEXT NOT NULL,
                UNIQUE(session_id,register_number,acquired_at));
            CREATE INDEX IF NOT EXISTS recording_value_lookup ON recording_values(session_id,register_number,acquired_at);
        ''')

    def start(self,snapshot,interval,main_only,mode,stamp=None,*,selected=None):
        if interval not in INTERVALS or mode not in ('manual','automatic'):raise ValueError('Invalid recording options')
        saved_config=dict(snapshot['config'])
        if type(snapshot['raw'].get(3)) is int and snapshot['raw'][3]>0:saved_config['fullscale']=snapshot['raw'][3]
        config=DeviceConfig(**saved_config);session=uuid.uuid4().hex
        parameters=recording_parameters(config,main_only,selected=selected)
        if not parameters:raise ValueError('Select at least one recording parameter')
        with self.db:
            self.db.execute('INSERT INTO recording_sessions VALUES (?,?,NULL,NULL,?,?,?,?,?,?,?)',
                (session,stamp or utc_now(),json.dumps(saved_config),json.dumps(snapshot.get('identity',{})),
                 snapshot.get('source','simulation'),profile_name(config),interval,json.dumps(parameters),mode))
        return session,parameters

    def end(self,session,reason,stamp=None):
        with self.db:self.db.execute('UPDATE recording_sessions SET ended_at=?,end_reason=? WHERE id=?',(stamp or utc_now(),reason,session))

    def append(self,session,snapshot,parameters,seen,stamp=None):
        """Sparse frames: a cached observation is stored only once per session.

        Each value has its own response timestamp. The frame timestamp is the
        capture time, never a substitute acquisition time for ancillary values.
        """
        stamp=stamp or utc_now();config=DeviceConfig(**snapshot['config'])
        quality=snapshot['quality'];times=snapshot.get('register_timestamps',{})
        values=[]
        if quality=='GOOD':
            for parameter in parameters:
                number=parameter['number'];acquired=times.get(number)
                if number==1 and uses_controller_fault_display(snapshot):
                    lcd=[times.get(n) for n in range(51,56)]
                    acquired=max(lcd) if all(lcd) else None
                if not acquired or seen.get(number)==acquired:continue
                value,unit=measurement(snapshot,number)
                age=snapshot.get('register_ages',{}).get(number,float('inf'))
                if age>max(5,config.interval*3):continue
                q=('INSTRUMENT_FAULT_LCD' if number==1 and uses_controller_fault_display(snapshot) else snapshot.get('instrument_quality','GOOD')) if value is not None else 'UNAVAILABLE'
                values.append((number,acquired,None if value is None else str(value),unit if value is not None else parameter['unit'],q))
        if not values:return 0
        status_value,_=measurement(snapshot,2)
        status=int(status_value) if status_value is not None else None
        with self.db:
            frame=self.db.execute('INSERT INTO recording_frames(session_id,timestamp,quality,status,status_timestamp) VALUES (?,?,?,?,?)',
                (session,stamp,quality,status,times.get(2))).lastrowid
            self.db.executemany('INSERT INTO recording_values VALUES (?,?,?,?,?,?,?)',
                [(frame,session,*value) for value in values])
        seen.update({n:t for n,t,*_ in values})
        return len(values)

    def gap(self,session,quality,stamp=None):
        with self.db:self.db.execute('INSERT INTO recording_frames(session_id,timestamp,quality) VALUES (?,?,?)',(session,stamp or utc_now(),quality))

    def close(self):self.db.close()


def read_connection(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=.25)
    db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON')
    return db


def sessions(paths):
    result=[]
    for path in paths:
        if not Path(path).exists():continue
        with closing(read_connection(path)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='recording_sessions'").fetchone():continue
            result.extend(dict(row,path=str(path)) for row in db.execute('SELECT * FROM recording_sessions ORDER BY started_at DESC'))
    return sorted(result,key=lambda row:row['started_at'],reverse=True)


def selected_sessions(paths,session=None,start=None,end=None):
    if start and end and start>end:raise ValueError('Start must precede end')
    return [row for row in sessions(paths) if (not session or row['id']==session) and (not end or row['started_at']<=end) and (not start or not row['ended_at'] or row['ended_at']>=start)]


def frame_rows(db,session,start=None,end=None):
    sql='SELECT * FROM recording_frames WHERE session_id=?';args=[session]
    if start:sql+=' AND timestamp>=?';args.append(start)
    if end:sql+=' AND timestamp<=?';args.append(end)
    return db.execute(sql+' ORDER BY timestamp,id',args)


def export_csv(paths,destination,*,session=None,start=None,end=None):
    """Streaming read-only SQLite export, UTF-8 BOM and CRLF for Excel."""
    chosen=selected_sessions(paths,session,start,end)
    descriptors={}
    for row in chosen:
        for p in json.loads(row['parameters']):
            key=(row['profile'],p['number'],p['name'],p['unit']);descriptors[key]=p
    keys=sorted(descriptors)
    headers=['Session','Profile','Model','Firmware','Analyzer identification','Source','Session start UTC','Session end UTC','Recording interval (s)','Capture timestamp UTC','STATUS','STATUS acquired UTC','Communication quality']
    for profile,number,name,unit in keys:
        label=f'{profile}: {name} [{number}]'+(f' ({unit})' if unit else '')
        headers.extend((label,label+' acquired UTC',label+' quality'))
    # Write beside the destination, replacing only when the entire export succeeds.
    destination=Path(destination);temporary=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
    count=0
    try:
        with temporary.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(headers)
            for row in chosen:
                config=json.loads(row['config']);identity=json.loads(row['identity'])
                with closing(read_connection(row['path'])) as db:
                    db.execute('BEGIN')
                    for frame in frame_rows(db,row['id'],start,end):
                        values={r['register_number']:r for r in db.execute('SELECT * FROM recording_values WHERE frame_id=?',(frame['id'],))}
                        identity_text=identity.get('text','')
                        if identity_text.startswith(('=','+','-','@','\t','\r')):identity_text="'"+identity_text
                        output=[row['id'],row['profile'],config['assembly'],config['version'],identity_text,row['source'],row['started_at'],row['ended_at'] or '',row['interval_seconds'],frame['timestamp'],frame['status'] if frame['status'] is not None else '',frame['status_timestamp'] or '',frame['quality']]
                        own={p['number']:p for p in json.loads(row['parameters'])}
                        for profile,number,name,unit in keys:
                            v=values.get(number) if profile==row['profile'] and number in own and (own[number]['name'],own[number]['unit'])==(name,unit) else None
                            output.extend((v['value'] if v and v['value'] is not None else '',v['acquired_at'] if v else '',v['quality'] if v else ''))
                        # Analyzer-controlled identity text must remain text in Excel.
                        output=["'"+v if isinstance(v,str) and v.startswith(('=','+','@','\t','\r')) else v for v in output]
                        writer.writerow(output);count+=1
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return count


def history_series(paths,session,number=1,limit=50000):
    chosen=selected_sessions(paths,session)
    if not chosen:return dict(points=[],unit='',name='',limited=False)
    row=chosen[0];parameter=next((p for p in json.loads(row['parameters']) if p['number']==number),None)
    if not parameter:return dict(points=[],unit='',name='',limited=False)
    points=[]
    with closing(read_connection(row['path'])) as db:
        for frame in frame_rows(db,session):
            if frame['quality']!='GOOD':points.append((frame['timestamp'],None));continue
            value=db.execute('SELECT acquired_at,value FROM recording_values WHERE frame_id=? AND register_number=?',(frame['id'],number)).fetchone()
            if value:points.append((value['acquired_at'],float(value['value']) if value['value'] is not None else None))
            if len(points)>limit:break
    return dict(points=points[:limit],unit=parameter['unit'],name=parameter['name'],limited=len(points)>limit,session=session)
