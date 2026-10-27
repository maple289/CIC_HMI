"""Excluded trend choices migrate without changing prior session data."""
from dataclasses import asdict
import csv,json
import pytest
from prevex_hmi.logging_db.recordings import recording_parameters,normalize_selections,EXCLUDED_RECORDING_PARAMETERS,sessions,export_csv,history_series
from prevex_hmi.devices.configuration import load_settings,save_settings
from prevex_hmi.gui.profile_library import library_config
from prevex_hmi.gui.window import MainWindow
from test_recording_sessions import recorder,sample,stamp
from test_monitoring import app


@pytest.mark.parametrize('profile,expected',[
    ('LEL 670 Series',{1,9,15,11}),('LEL 700 Series',{1,9,15,11,29,30}),
    ('BTU',{1,9,10,11,33}),('FID',{1,9,10,33,11,12})])
def test_only_requested_changing_measurements_are_choices(app,tmp_path,profile,expected):
    config=library_config(profile);settings=load_settings(tmp_path/'settings.json');settings['devices']=[asdict(config)]
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    try:
        group=w.trend_window.recording_parameters
        assert set(group.checkboxes)==expected and not set(group.checkboxes)&EXCLUDED_RECORDING_PARAMETERS
        group.select_all.click();assert set(group.selected_numbers())==expected
    finally:w.close();app.processEvents()


def test_saved_old_choices_are_trimmed_and_empty_is_preserved(tmp_path):
    path=tmp_path/'settings.json';settings=load_settings(path)
    old={'LEL 670 Series':[1,2,38,39,9,24,15,23,42,11,50],'LEL 700 Series':[2,38,39,24]}
    settings['recording']={'mode':'manual','interval':1,'parameters_by_profile':old}
    save_settings(path,settings);loaded=load_settings(path)
    assert loaded['recording']['parameters_by_profile']=={'LEL 670 Series':[1,9,15,11],'LEL 700 Series':[]}
    assert normalize_selections(old)==loaded['recording']['parameters_by_profile']


def test_status_is_metadata_without_a_status_recording_channel(recorder):
    r,now=recorder;data=sample();r.configure('manual',1,{'LEL 670 Series':[1,2,38,9]});r.start();r.tick(data,received=0)
    assert [p['number'] for p in r.parameters]==[1,9]
    assert r.store.db.execute('SELECT status,quality,status_timestamp FROM recording_frames').fetchone()==(data['raw'][2],'GOOD',stamp())
    assert {row[0] for row in r.store.db.execute('SELECT register_number FROM recording_values')}=={1,9}


def test_old_peak_session_remains_viewable_and_exportable(recorder,tmp_path):
    r,now=recorder;r.configure('manual',1,{'LEL 670 Series':[1]});r.start();r.tick(sample(),received=0);session=r.session
    # Replay a pre-exclusion archived session without using the new chooser.
    with r.store.db:
        parameters=r.parameters+[dict(number=38,name='PEAK HI',unit='%LFL')]
        r.store.db.execute('UPDATE recording_sessions SET parameters=? WHERE id=?',(json.dumps(parameters),session))
        frame=r.store.db.execute('SELECT id FROM recording_frames').fetchone()[0]
        r.store.db.execute('INSERT INTO recording_values VALUES (?,?,?,?,?,?,?)',(frame,session,38,stamp(),'33.5','%LFL','GOOD'))
    assert history_series([r.path],session,38)['points']==[(stamp(),33.5)]
    destination=tmp_path/'archive.csv';assert export_csv([r.path],destination,session=session)==1
    with destination.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    assert any('PEAK HI [38]' in name and value=='33.5' for name,value in rows[0].items())
