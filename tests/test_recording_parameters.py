"""Checkbox selection, persistence and immutable recording sessions. No hardware."""
from dataclasses import asdict
import copy,csv,json
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox,QFileDialog
from prevex_hmi.devices.configuration import load_settings,save_settings
from prevex_hmi.gui.profile_library import library_config
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.logging_db.recordings import recording_parameters,normalize_selections,sessions,export_csv
from test_recording_sessions import recorder,sample
from test_trend_window import window
from test_monitoring import app,until


@pytest.mark.parametrize('profile',['LEL 670 Series','LEL 700 Series','BTU','FID'])
def test_parameter_checkboxes_follow_profile_and_default_to_main(app,tmp_path,profile):
    settings=load_settings(tmp_path/'settings.json');config=library_config(profile);settings['devices']=[asdict(config)]
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    try:
        group=w.trend_window.recording_parameters
        assert group.title()=='Recording Parameters' and group.profile==profile
        expected=recording_parameters(config)
        assert list(group.checkboxes)==[p['number'] for p in expected]
        assert group.selected_numbers()==[1]
        assert all(p['name'] in group.checkboxes[p['number']].text() and (not p['unit'] or p['unit'] in group.checkboxes[p['number']].text()) for p in expected)
        assert w.trend_window.start_button.isEnabled()
        w.open_trend();w.trend_window.resize(1100,840);app.processEvents();app.processEvents()
        assert max(group.grid.getItemPosition(i)[1] for i in range(group.grid.count()))==2
        w.trend_window.resize(720,650);app.processEvents();app.processEvents()
        assert max(group.grid.getItemPosition(i)[1] for i in range(group.grid.count()))==1
    finally:w.close();app.processEvents()


def test_per_profile_selections_clear_all_and_relaunch(app,tmp_path):
    path=tmp_path/'settings.json';w=MainWindow(load_settings(path),path,tmp_path,start_worker=False)
    choices={'LEL 670 Series':[9,11],'LEL 700 Series':[],'BTU':[10,11,33],'FID':[1,12]}
    try:
        t=w.trend_window
        for profile,numbers in choices.items():
            t.set_analyzer(library_config(profile));group=t.recording_parameters
            group.clear_all.click();assert not t.start_button.isEnabled()
            group.select_all.click();assert len(group.selected_numbers())==len(group.checkboxes) and t.start_button.isEnabled()
            group.select_numbers(numbers);assert t.start_button.isEnabled()==bool(numbers)
        assert {k:set(v) for k,v in load_settings(path)['recording']['parameters_by_profile'].items()}=={k:set(v) for k,v in choices.items()}
    finally:w.close();app.processEvents()
    other=MainWindow(load_settings(path),path,tmp_path,start_worker=False)
    try:
        for profile,numbers in choices.items():
            other.trend_window.set_analyzer(library_config(profile))
            assert set(other.trend_window.recording_parameters.selected_numbers())==set(numbers)
            assert other.trend_window.start_button.isEnabled()==bool(numbers)
    finally:other.close();app.processEvents()


def test_select_before_start_no_dialogs_lock_until_stop_and_export_subset(app,window,tmp_path,monkeypatch):
    w=window;w.open_trend();t=w.trend_window;group=t.recording_parameters
    def forbidden(*args,**kwargs):raise AssertionError('Start Recording must not open a dialog')
    monkeypatch.setattr(QMessageBox,'question',forbidden)
    group.clear_all.click();assert not t.start_button.isEnabled()
    for number in (9,11):
        checkbox=group.checkboxes[number]
        QTest.mouseClick(checkbox,Qt.LeftButton,pos=QPoint(8,checkbox.height()//2))
    assert group.selected_numbers()==[9,11] and t.start_button.isEnabled()
    t.interval.setCurrentIndex(t.interval.findData(2));t.start_button.click()
    assert not group.isEnabled() and not t.interval.isEnabled() and not t.start_button.isEnabled()
    group.checkboxes[1].setChecked(True);t.interval.setCurrentIndex(t.interval.findData(10))
    assert not group.checkboxes[1].isChecked() and t.interval.currentData()==2
    until(app,lambda:w.recording_status['session'] is not None and w.recording_status['samples']>=1)
    session=w.recording_status['session'];row=next(r for r in sessions(t.paths) if r['id']==session)
    assert {p['number'] for p in json.loads(row['parameters'])}=={9,11} and row['interval_seconds']==2
    w.trend_window.close();w.open_trend();assert not group.isEnabled() and not t.interval.isEnabled()
    w.request('fault','timeout');until(app,lambda:w.recording_status['state'].startswith('Paused'),timeout=8)
    assert not group.isEnabled() and not t.interval.isEnabled()
    t.stop_button.click();assert not group.isEnabled()
    until(app,lambda:w.recording_status['session'] is None and not t.stop_pending)
    assert group.isEnabled() and t.interval.isEnabled() and t.start_button.isEnabled()
    assert set(group.selected_numbers())=={9,11}
    destination=tmp_path/'chosen.csv'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(destination),'CSV (*.csv)'))
    assert t.export_scope.currentIndex()==0
    t.export_button.click();until(app,lambda:destination.exists() and t.export_button.isEnabled())
    with destination.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    assert rows and any('BLOCK TEMP [9]' in name for name in rows[0]) and any('FLAME TEMP [11]' in name for name in rows[0])
    assert not any('FLAMMABILITY [1]' in name for name in rows[0]) and rows[0]['STATUS'] in ('0','1','2')


@pytest.mark.parametrize('chosen',[[],[8],[1,1],[True],['1']])
def test_backend_rejects_empty_invalid_selection_without_session(recorder,chosen):
    r,now=recorder
    with pytest.raises(ValueError):r.start_selected('manual',1,{'LEL 670 Series':chosen},sample(),'LEL 670 Series')
    assert r.session is None and not r.armed and r.store is None


def test_backend_freezes_parameters_interval_even_when_paused(recorder):
    r,now=recorder;r.start_selected('manual',2,{'LEL 670 Series':[9,11]},sample(),'LEL 670 Series');r.tick(sample(),received=0);session=r.session
    for paused in (False,True):
        if paused:
            now[0]=1;data=sample(1);data['quality']='OFFLINE';r.tick(data,received=1)
        with pytest.raises(ValueError):r.configure('manual',10,{'LEL 670 Series':[1]})
        assert r.session==session and r.interval==2 and {p['number'] for p in r.parameters}=={9,11}
    r.stop();r.configure('manual',5,{'LEL 670 Series':[1]});assert r.interval==5


def test_automatic_recording_uses_each_profile_selection(recorder):
    r,now=recorder;r.configure('automatic',1,{'LEL 670 Series':[9],'LEL 700 Series':[9,15]})
    r.tick(sample(),received=0);first=r.session;assert [p['number'] for p in r.parameters]==[9]
    now[0]=2;r.tick(sample(2,'700'),received=2)
    assert r.session!=first and {p['number'] for p in r.parameters}=={9,15}


def test_start_with_no_communication_checks_profile_on_first_snapshot(recorder):
    r,now=recorder;r.start_selected('manual',1,{'FID':[12]},None,'FID')
    r.tick(sample(),received=0)
    assert not r.armed and r.session is None and 'profile changed' in r.error


def test_old_preferences_default_to_main_without_changing_existing_sessions(app,tmp_path):
    path=tmp_path/'settings.json';settings=load_settings(path);settings['recording']={'mode':'manual','interval':5,'main_only':False};save_settings(path,settings)
    w=MainWindow(load_settings(path),path,tmp_path,start_worker=False)
    try:assert w.trend_window.recording_parameters.selected_numbers()==[1] and w.trend_window.interval.currentData()==5
    finally:w.close();app.processEvents()


@pytest.mark.parametrize('mapping',[{'FID':[8]},{'BTU':[True]},{'unknown':[1]},{'LEL 700 Series':[1,1]},{'FID':'1'},[]])
def test_invalid_saved_parameter_maps_are_rejected(tmp_path,mapping):
    settings=load_settings(tmp_path/'settings.json');settings['recording']={'parameters_by_profile':mapping}
    with pytest.raises(ValueError):save_settings(tmp_path/'settings.json',settings)


def test_fid_unit_change_refreshes_checkbox_units_without_losing_selection(app,tmp_path):
    from prevex_hmi.communication.engine import BusEngine
    from prevex_hmi.simulator.bus import SimulatedBus
    path=tmp_path/'settings.json';w=MainWindow(load_settings(path),path,tmp_path,start_worker=False)
    bus=BusEngine(SimulatedBus([library_config('FID')]),sleep=lambda _:None)
    try:
        data=sample(kind='FID');data['error']=''
        w.update_data(data,bus.diagnostics());group=w.trend_window.recording_parameters
        group.select_numbers([1,12]);assert '(PPM)' in group.checkboxes[1].text()
        data=copy.deepcopy(data);data['config']['units']='METRIC'
        w.update_data(data,bus.diagnostics())
        assert '(MG)' in group.checkboxes[1].text() and group.selected_numbers()==[1,12]
    finally:w.close();bus.close();app.processEvents()
