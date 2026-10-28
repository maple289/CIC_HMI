from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import copy
import json
import os
import time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from prevex_hmi.devices.configuration import default_devices,load_settings,save_settings
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.gui.presentation import format_reading,measurement,severity
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.gui.connection_dialog import AnalyzerChoice
from prevex_hmi.profiles import PROFILES
from prevex_hmi.profiles.gauges import GAUGE_REGISTERS,gauges_for
from prevex_hmi.logging_db.store import Historian

@pytest.fixture(scope='session')
def app():
    instance=QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    yield instance

def until(app,condition,timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.processEvents()
        if condition():return
        time.sleep(.01)
    pytest.fail('Timed out waiting for asynchronous state')

def snapshot(quality='GOOD',family='LEL'):
    d=next(d for d in default_devices() if d.family==family)
    return dict(config=asdict(d),raw={1:25600,2:0,3:d.fullscale,4:128},quality=quality,age=0,last_success=datetime.now(timezone.utc).isoformat(),error='',identification='test')


def identify(window,config):
    """Deliver an explicit simulated identity for UI-only snapshot fixtures."""
    from prevex_hmi.profiles import profile_name
    window.identification_result(dict(config=asdict(config),family=config.family,model=config.assembly,version=config.version,verified=True,communication_ok=True,loaded_profile=profile_name(config),controls_verified=True,text='Simulated fixture identity'))

@pytest.mark.parametrize('quality',['OFFLINE','STALE','DISABLED'])
def test_old_reading_never_presented_as_current(quality):
    data=snapshot(quality)
    assert measurement(data)[0] is None and format_reading(data)=='--'
    assert severity(data)[1]==quality

def test_individual_register_staleness():
    data=snapshot();data['register_ages']={1:20}
    assert measurement(data)[0] is None

def test_configuration_migration_preserves_backup_and_reduces_to_one(tmp_path):
    path=tmp_path/'settings.json'
    old=dict(schema_version=1,mode='simulation',theme='dark',selected_device='fid-3',devices=[asdict(d) for d in default_devices()])
    path.write_text(json.dumps(old))
    settings=load_settings(path)
    assert settings['schema_version']==2 and len(settings['devices'])==1
    assert settings['devices'][0]['family']=='FID' and settings['analyzer_selection']=='Auto Detect'
    assert json.loads(path.with_suffix('.v1-backup.json').read_text())==old
    settings['devices'].append(asdict(default_devices()[0]))
    with pytest.raises(ValueError):save_settings(path,settings)

def test_settings_roundtrip_and_corruption_preserved(tmp_path):
    path=tmp_path/'settings.json';settings=load_settings(path)
    save_settings(path,settings);assert load_settings(path)==settings
    path.write_text('bad json')
    with pytest.raises(ValueError):load_settings(path)
    assert path.read_text()=='bad json'

def test_choice_has_five_options_and_preserves_manual_range(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json');dialog=AnalyzerChoice(settings)
    assert [dialog.types.itemText(i) for i in range(5)]==['Auto Detect','LEL 670 Series','LEL 700 Series','BTU','FID']
    dialog.range_mode.setCurrentText('manual');dialog.manual.setValue(250)
    dialog.logging_enabled.setChecked(False)
    result=dialog.settings();assert result['devices'][0]['manual_maximum']==250
    assert not result['devices'][0]['logging_enabled']
    dialog.close()


def test_chooser_clicks_select_matching_simulator_and_confirms_ok(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json')
    settings.update(analyzer_selection='LEL',simulated_family='FID')
    settings['devices']=[asdict(next(d for d in default_devices() if d.family=='FID'))]
    dialog=AnalyzerChoice(settings);dialog.show();app.processEvents()
    try:
        assert dialog.name.text()=='LEL - Process line 1'
        assert dialog.sim_family.currentText()=='LEL'
        assert not dialog.units.isVisible() and not dialog.fullscale.isVisible()
        assert dialog.assembly.text()=='SNR675'
        for family,index,prefix in [('FID',4,'SNR65'),('BTU',3,'SNR69'),('LEL',1,'SNR67'),('LEL',2,'SNR70')]:
            dialog.types.showPopup()
            app.processEvents()
            item=dialog.types.model().index(index,0)
            dialog.types.view().scrollTo(item);app.processEvents()
            QTest.mouseClick(dialog.types.view().viewport(),Qt.LeftButton,pos=dialog.types.view().visualRect(item).center())
            app.processEvents()
            assert dialog.sim_family.currentText()==family
            assert dialog.assembly.text().startswith(prefix)
            assert dialog.name.text().startswith(family)
            assert dialog.units.isVisible()==(family=='FID')
            assert dialog.fullscale.isVisible()==(family=='FID')
            assert not dialog.lel_revision.isVisible()
            result=dialog.settings()
            assert result['devices'][0]['family']==family and result['simulated_family']==family
        dialog.address.setValue(1);dialog.address_mode.setCurrentText('display_minus_one')
        assert dialog.address.value()==2
        assert DeviceConfig(**dialog.settings()['devices'][0]).addressing.packet_address==1
        dialog.address.setValue(1)
        assert dialog.address.value()==2
        buttons=dialog.findChild(QDialogButtonBox)
        assert buttons.button(QDialogButtonBox.Save) is None
        QTest.mouseClick(buttons.button(QDialogButtonBox.Ok),Qt.LeftButton)
        assert dialog.result()==QDialog.Accepted
    finally:dialog.close()


def test_chooser_preserves_custom_name_and_auto_detect_simulator_choice(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json');settings['devices'][0]['name']='My process'
    dialog=AnalyzerChoice(settings)
    try:
        dialog.sim_family.setCurrentText('FID')
        assert dialog.name.text()=='My process' and dialog.settings()['devices'][0]['family']=='FID'
        dialog.types.setCurrentIndex(3)
        assert dialog.name.text()=='My process' and dialog.sim_family.currentText()=='BTU'
        dialog.address_mode.setCurrentText('display_minus_one');dialog.address_mode.setCurrentText('direct');dialog.address.setValue(1)
        assert DeviceConfig(**dialog.settings()['devices'][0]).addressing.packet_address==1
    finally:dialog.close()

def test_historian_quality_events_retention_and_audit(tmp_path):
    db=Historian(tmp_path/'test.sqlite3')
    stamp=datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    old=(datetime.now(timezone.utc)-timedelta(days=100)).isoformat(timespec='milliseconds')
    db.measurement(old,'one',1,99,'%LFL','GOOD',0);db.measurement(stamp,'one',1,-20,'%LFL','GOOD',0)
    db.measurement(stamp,'one',1,None,'','OFFLINE',0);db.event(old,'one','Alarm','GOOD')
    db.command_audit('one','operator',0x300,'UNKNOWN','No retry');db.retain(90)
    assert len(db.history('one',24*365))==2 and db.history('one')[0][1]==-20
    assert len(db.events())==1 and db.audit_rows()[0][4]=='UNKNOWN';db.close()

@pytest.mark.parametrize('family',['LEL','BTU','FID'])
def test_detected_family_has_all_gauges_and_one_worker(app,tmp_path,family):
    settings=load_settings(tmp_path/'settings.json');settings['simulated_family']=family
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=True);w.show()
    try:
        until(app,lambda:w.snapshot is not None and w.snapshot['quality']=='GOOD')
        assert w.identity['family']==family and w.identity['controls_verified']
        assert len(w.worker.settings['devices'])==1
        numbers=gauges_for(DeviceConfig(**w.snapshot['config']))
        assert set(numbers)<=set(w.readouts)
        until(app,lambda:all(n in w.snapshot['raw'] for n in numbers))
        assert not any(b.isEnabled() for b in w.command_buttons.values())
        w.worker.request('reading',-20)
        until(app,lambda:w.gauge.state.value is not None and w.gauge.state.value<0)
        assert w.gauge.state.minimum==-30
    finally:
        w.close();until(app,lambda:not w.worker.isRunning());app.processEvents()

def test_test_connection_identifies_without_starting_controls(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json');settings['simulated_family']='FID'
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    w.begin('test')
    try:
        until(app,lambda:bool(w.identity) and not w.worker.isRunning())
        assert w.identity['family']=='FID' and w.identity['test_only']
        assert w.snapshot is None and not any(b.isEnabled() for b in w.command_buttons.values())
    finally:w.close()

def test_profile_switch_stops_invalidates_and_opens_only_new_device(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json');w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=True)
    try:
        until(app,lambda:w.snapshot is not None)
        previous=w.worker
        w.settings=copy.deepcopy(w.settings);w.settings['simulated_family']='BTU'
        w.begin('connect')
        assert w.snapshot is None and w.gauge.state.reading=='--'
        until(app,lambda:w.worker is not previous and w.snapshot is not None and w.snapshot['config']['family']=='BTU')
        assert not previous.isRunning() and w.identity['family']=='BTU'
        assert 15 not in w.readouts and 10 in w.readouts
    finally:
        w.close();until(app,lambda:not w.worker.isRunning());app.processEvents()

def test_mismatch_and_hardware_access_gate(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json');settings['analyzer_selection']='FID'
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=True)
    try:
        until(app,lambda:w.snapshot is not None)
        assert 'MISMATCH' in w.warning.text() and not w.identity['controls_verified']
        assert w.snapshot['config']['family']=='LEL'
        w.settings=copy.deepcopy(w.settings);w.settings['mode']='hardware';w.begin('connect')
        until(app,lambda:w.worker is not None and not w.worker.isRunning() and w.next_action is None and 'No port was opened' in w.warning.text())
        assert w.snapshot is None and 'No port was opened' in w.warning.text()
    finally:
        w.close();app.processEvents()

def test_communication_loss_clears_indicator_and_retains_events(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json');w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=True)
    try:
        until(app,lambda:w.snapshot is not None and w.snapshot['quality']=='GOOD')
        assert sum(not label.isHidden() for (group,_),(label,_) in w.indicators.labels.items() if group==0)==1
        assert all(not label.text().startswith('ON ') for label,_ in w.indicators.labels.values() if not label.isHidden())
        w.worker.request('fault','timeout')
        until(app,lambda:w.snapshot is not None and w.snapshot['quality']=='OFFLINE')
        # Display-only hold is independent of the red connection indicator.
        assert 'No Connection' in w.monitor_status.text()
        until(app,lambda:w.gauge.state.reading=='--')
        assert w.gauge.state.reading=='--' and w.gauge.state.fraction is None
        assert 'OFFLINE' in w.indicators.summary.text()
        assert all(label.isHidden() for label,_ in w.indicators.labels.values())
        assert all(row.isHidden() for row in w.indicators.row_widgets)
        assert not any(b.isEnabled() for b in w.command_buttons.values())
    finally:
        w.close();until(app,lambda:not w.worker.isRunning());app.processEvents()
