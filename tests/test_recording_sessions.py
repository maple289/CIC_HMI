"""Recording correctness with deterministic acquired samples; no serial access."""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import copy,csv,json,sqlite3
import pytest
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.gui.presentation import measurement
from prevex_hmi.logging_db import recordings
from prevex_hmi.logging_db.recordings import RecordingStore,recording_parameters,sessions,export_csv,history_series
from prevex_hmi.logging_db.recorder import Recorder
from prevex_hmi.logging_db.store import MonitoringHistorian
from prevex_hmi.profiles import profile_for
from prevex_hmi.simulator.bus import SimulatedBus

BASE=datetime(2026,10,26,14,30,tzinfo=timezone.utc)

def stamp(seconds=0):return (BASE+timedelta(seconds=seconds)).isoformat(timespec='milliseconds')

def sample(seconds=0,kind='670',value=-10):
    config=next(d for d in default_devices() if d.family==('LEL' if kind in ('670','700') else kind))
    if kind=='700':config=replace(config,assembly='SNR705',version='7.01')
    sim=SimulatedBus([config]);target=sim.devices[config.addressing.packet_address];target.update(seconds)
    raw=target.raw.copy();raw[1]=profile_for(config).register(1).encode(value,config.family,config.context)
    return dict(config=asdict(config),raw=raw,quality='GOOD',age=0,last_success=stamp(seconds),source='simulation',identity={'text':'test analyzer','serial':'test1'},instrument_quality='GOOD',register_ages={n:0 for n in raw},register_timestamps={n:stamp(seconds) for n in raw})

@pytest.fixture
def recorder(tmp_path,monkeypatch):
    now=[0.0];monkeypatch.setattr(recordings,'utc_now',lambda:stamp(now[0]))
    recorder=Recorder(tmp_path,clock=lambda:now[0])
    yield recorder,now
    recorder.close()

def rows(recorder,table):return recorder.store.db.execute('SELECT * FROM '+table).fetchall()

def test_manual_default_separate_sessions_and_frozen_elapsed(recorder):
    r,now=recorder;r.tick(sample(),received=0)
    assert r.session is None and not (r.data_path/'simulation.sqlite3').exists()
    r.start();r.tick(sample(),received=0);first=r.session
    now[0]=3;r.stop();assert r.status()['elapsed']==3
    now[0]=20;assert r.status()['elapsed']==3
    r.start();r.tick(sample(20),received=20);assert r.session!=first
    assert len(rows(r,'recording_sessions'))==2
    metadata=sessions([r.path]);assert metadata[0]['interval_seconds']==1 and metadata[0]['mode']=='manual'

@pytest.mark.parametrize('interval',[1,2,5,10])
def test_intervals_and_no_cached_duplicates(recorder,interval):
    r,now=recorder;r.options('manual',interval,True);r.start();snapshot=sample();r.tick(snapshot,received=0)
    initial=len(rows(r,'recording_values'))
    now[0]=interval-.1;r.tick(sample(now[0]),received=now[0]);assert len(rows(r,'recording_values'))==initial
    now[0]=interval;r.tick(snapshot,received=now[0]);assert len(rows(r,'recording_values'))==initial
    now[0]=interval*2;r.tick(sample(now[0]),received=now[0]);assert len(rows(r,'recording_values'))==initial+2
    assert {row[2] for row in rows(r,'recording_values')}=={1,2}

@pytest.mark.parametrize('mode',['manual','automatic'])
def test_loss_pause_resume_no_values_in_gap(recorder,mode):
    r,now=recorder;r.options(mode,1,False)
    if mode=='manual':r.start()
    r.tick(sample(),received=0);session=r.session;initial=len(rows(r,'recording_values'))
    now[0]=2;bad=sample(2);bad['quality']='OFFLINE';r.tick(bad,received=2)
    now[0]=3;r.tick(bad,received=3)
    assert r.session==session and r.status()['state'].startswith('Paused')
    assert len(rows(r,'recording_values'))==initial
    assert [row[3] for row in rows(r,'recording_frames')].count('OFFLINE')==1
    now[0]=4;r.tick(sample(4),received=4)
    assert r.session==session and r.status()['state']=='Recording'
    assert 'RESUMED' in [row[3] for row in rows(r,'recording_frames')]
    history=history_series([r.path],session)
    assert history['points'][0][1]==-10 and any(v is None for t,v in history['points'])

def test_silent_worker_staleness_creates_one_gap(recorder):
    r,now=recorder;r.options('automatic',1,False);snapshot=sample();r.tick(snapshot,received=0)
    now[0]=7;r.tick(snapshot,received=0);now[0]=9;r.tick(snapshot,received=0)
    assert [row[3] for row in rows(r,'recording_frames')].count('OFFLINE')==1

@pytest.mark.parametrize('mode',['manual','automatic'])
def test_profile_switch_never_combines_sessions(recorder,mode):
    r,now=recorder;r.options(mode,1,False)
    if mode=='manual':r.start()
    r.tick(sample(),received=0);first=r.session
    now[0]=2;r.tick(sample(2,'700'),received=2)
    if mode=='manual':assert r.session is None and not r.armed;r.start();r.tick(sample(2,'700'),received=2)
    assert r.session!=first
    metadata=sessions([r.path]);assert {s['profile'] for s in metadata}=={'LEL 670 Series','LEL 700 Series'}
    assert next(s for s in metadata if s['id']==first)['end_reason']=='Analyzer identity/profile changed'

@pytest.mark.parametrize('kind',['670','700','BTU','FID'])
def test_correct_names_units_conversions_and_negative_values(recorder,kind):
    r,now=recorder;snapshot=sample(kind=kind);config=recordings.DeviceConfig(**snapshot['config'])
    r.start();r.tick(snapshot,received=0)
    params=recording_parameters(config);metadata=json.loads(sessions([r.path])[0]['parameters'])
    assert metadata==params and {1,9,11}<={p['number'] for p in params}
    assert not {2,23,24,38,39,42,50}&{p['number'] for p in params}
    assert {r[2] for r in rows(r,'recording_values')}=={p['number'] for p in params}
    for row in rows(r,'recording_values'):
        value,unit=measurement(snapshot,row[2]);assert row[4]==str(value) and row[5]==unit
    assert float(next(row for row in rows(r,'recording_values') if row[2]==1)[4])<0

def test_per_register_timestamps_and_sparse_ancillary_samples(recorder):
    r,now=recorder;r.start();snapshot=sample();snapshot['register_timestamps'][9]=stamp(-2)
    r.tick(snapshot,received=0);now[0]=1
    next_sample=copy.deepcopy(snapshot);next_sample['register_timestamps'][1]=stamp(1);next_sample['register_timestamps'][2]=stamp(1)
    r.tick(next_sample,received=1)
    values=rows(r,'recording_values')
    assert len([row for row in values if row[2]==9])==1
    assert next(row for row in values if row[2]==9)[3]==stamp(-2)
    assert len([row for row in values if row[2]==1])==2

def test_lcd_hold_never_becomes_new_acquisition(recorder):
    from test_hardware_monitoring import RAW
    r,now=recorder;data=sample();config=recordings.DeviceConfig(**data['config'])
    config=replace(config,assembly='SNR671',version='4.81',register_profile='fta_4x');data['config']=asdict(config);data['raw']=dict(RAW)
    data['register_timestamps']={n:stamp() for n in RAW};data['register_ages']={n:0 for n in RAW}
    r.options('manual',1,True);r.start();r.tick(data,received=0)
    assert next(row for row in rows(r,'recording_values') if row[2]==1)[4]=='-99'
    now[0]=2;cached=copy.deepcopy(data);cached['register_timestamps'][1]=stamp(2);cached['register_timestamps'][2]=stamp(2)
    r.tick(cached,received=2)
    assert len([row for row in rows(r,'recording_values') if row[2]==1])==1
    now[0]=3;blank=copy.deepcopy(cached)
    for n in range(51,56):blank['raw'][n]=0x2020;blank['register_timestamps'][n]=stamp(3)
    r.tick(blank,received=3)
    values=[row for row in rows(r,'recording_values') if row[2]==1]
    assert len(values)==2 and values[-1][4] is None and values[-1][6]=='UNAVAILABLE'

def test_recording_export_bom_crlf_negative_blanks_and_metadata(recorder,tmp_path):
    r,now=recorder;r.start();data=sample();data['identity']['text']='=test identity, with comma';r.tick(data,received=0);first=r.session
    now[0]=1;bad=sample(1);bad['identity']=data['identity'].copy();bad['quality']='OFFLINE';r.tick(bad,received=1);r.stop()
    path=tmp_path/'test.csv';count=export_csv([r.path],path,session=first)
    assert count==2 and path.read_bytes().startswith(b'\xef\xbb\xbf') and b'\r\n' in path.read_bytes()
    with path.open(encoding='utf-8-sig',newline='') as f:output=list(csv.DictReader(f))
    column=next(k for k in output[0] if 'READING [1]' in k and 'acquired' not in k and 'quality' not in k)
    assert float(output[0][column])==-10 and output[1][column]==''
    assert output[0][column+' acquired UTC']==stamp()
    assert output[0]['Analyzer identification'].startswith("'=test")
    assert output[1]['Communication quality']=='OFFLINE' and output[1]['STATUS']==''
    assert output[0]['Session']==first and output[0]['Session end UTC']==stamp(1)

def test_export_date_range_cross_profile_columns_and_no_truncation(recorder,tmp_path):
    r,now=recorder;r.start();r.tick(sample(),received=0);first=r.session;r.stop()
    now[0]=5;r.start();r.tick(sample(5,'FID'),received=5);r.stop()
    path=tmp_path/'range.csv';assert export_csv([r.path],path,start=stamp(4),end=stamp(6))==1
    assert export_csv([r.path],path)==2
    with path.open(encoding='utf-8-sig',newline='') as f:reader=csv.reader(f);headers=next(reader)
    assert any('LEL 670 Series:' in h for h in headers) and any('FID:' in h and '(PPM)' in h for h in headers)
    with r.store.db:
        for i in range(5010):
            frame=r.store.db.execute('INSERT INTO recording_frames(session_id,timestamp,quality,status) VALUES (?,?,?,?)',(first,stamp(i+10),'GOOD',0)).lastrowid
            r.store.db.execute('INSERT INTO recording_values VALUES (?,?,?,?,?,?,?)',(frame,first,1,stamp(i+10),'-1','%LFL','GOOD'))
    assert export_csv([r.path],path,session=first)==5011

def test_export_failure_preserves_destination_and_database(recorder,tmp_path,monkeypatch):
    r,now=recorder;r.start();r.tick(sample(),received=0);path=tmp_path/'existing.csv';path.write_text('preserve')
    class Writer:
        def writerow(self,row):raise OSError('Disk full')
    monkeypatch.setattr(recordings.csv,'writer',lambda *_:Writer())
    with pytest.raises(OSError):export_csv([r.path],path)
    assert path.read_text()=='preserve' and not list(tmp_path.glob('*.tmp'))
    now[0]=1;r.tick(sample(1),received=1);assert r.session and len(rows(r,'recording_frames'))==2

def test_retention_does_not_delete_recording_sessions(recorder):
    from prevex_hmi.logging_db.store import Historian
    r,now=recorder;r.start();r.tick(sample(),received=0);r.stop()
    db=Historian(r.path);db.retain(1);db.close();assert len(rows(r,'recording_sessions'))==1

def test_history_storage_failure_fails_audits_closed_without_raising_logging(tmp_path):
    warnings=[]
    def factory(path):raise sqlite3.OperationalError('Disk full')
    db=MonitoringHistorian(tmp_path/'test.sqlite3',warnings.append,factory=factory)
    db.measurement('anything');db.event('anything');db.commit();assert db.history('id')==[] and warnings
    with pytest.raises(PermissionError):db.command_audit('anything')
    db.close()

def test_shutdown_closes_session_but_unfinished_session_is_queryable(recorder):
    r,now=recorder;r.start();r.tick(sample(),received=0);session=r.session
    # Read-only queries can inspect an unfinished session without mutating it.
    assert sessions([r.path])[0]['ended_at'] is None
    r.finish('Application shutdown');assert sessions([r.path])[0]['end_reason']=='Application shutdown'
    assert history_series([r.path],session)['points']


def test_stopped_automatic_recording_stays_disarmed_when_interval_changes(recorder):
    r,now=recorder;r.options('automatic',1,False);r.tick(sample(),received=0);r.stop()
    r.options('automatic',5,True);now[0]=1;r.tick(sample(1),received=1)
    assert r.session is None and not r.armed
    r.start();r.tick(sample(1),received=1);assert r.session and r.interval==5
