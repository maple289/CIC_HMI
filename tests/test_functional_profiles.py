"""Family selection and firmware-independent capabilities; simulator/fake SDK only."""
from dataclasses import asdict,replace
import copy,json,os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from prevex_hmi.devices.configuration import default_devices
from dev_support import load_settings
from prevex_hmi.devices.identification import detect,parse_identity,resolve_profile,identity_key
from prevex_hmi.profiles import profile_for,commands_for,series_for
from prevex_hmi.profiles.parameters import definitions,encode
from prevex_hmi.gui.connection_dialog import AnalyzerChoice
from prevex_hmi.gui.connection_screen import ConnectionScreen
from prevex_hmi.gui.profile_library import PROFILE_CHOICES
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.validated_controls import validated_670,ValidatedControlGrant
from prevex_hmi.simulator.bus import SimulatedBus
from test_validated_commands import control


VERSIONS=('1.00','4.80','4.81','5.08','5.11','5.12','9.99','Unknown','garbled','')


def config_for(series,version='5.12'):
    d=next(d for d in default_devices() if d.family=={'650':'FID','690':'BTU'}.get(series,'LEL'))
    return replace(d,assembly='SNR705' if series=='700' else d.assembly,version=version,register_profile=series if series in ('670','700') else 'auto')


@pytest.mark.parametrize('series',['650','670','690','700'])
@pytest.mark.parametrize('version',VERSIONS)
def test_firmware_does_not_change_series_capabilities_or_identification(series,version):
    config=config_for(series,version);baseline=config_for(series)
    assert profile_for(config)==profile_for(baseline)
    assert definitions(config)==definitions(baseline)
    assert commands_for(config)==commands_for(baseline)
    assert series_for(config)==series
    sim=SimulatedBus([config]);bus=BusEngine(sim,sleep=lambda _:None)
    try:
        found=detect(bus,config.addressing)
        assert found.verified and found.family==config.family and found.model==config.assembly and not found.warning
        effective,warning,verified=resolve_profile(config,config.family,found)
        assert verified and not warning and series_for(effective)==series
        assert not sim.events
        if series=='670':assert validated_670(effective)
        else:assert not validated_670(effective)
    finally:bus.close()


@pytest.mark.parametrize('text',['TYPE FTAVER 4\xa781 SNR671','TYPE FTAVER ??? SNR671','PREVEX VER??? SNR675','BTU SNR692','FID VER??? SNR650'])
def test_missing_or_unusual_version_does_not_reject_reliable_model(text):
    identity=parse_identity(text)
    assert identity.verified and not identity.warning
    assert identity.version=='4.81' if '\xa7' in text else identity.version=='Unknown'


def test_real_model_and_family_conflicts_remain_rejected():
    assert not parse_identity('BTU VER1.00 SNR650').verified
    assert not parse_identity('LEL FID SNR671').verified
    identity=parse_identity('FID SNR650')
    _,warning,verified=resolve_profile(config_for('670'),'LEL',identity)
    assert 'MISMATCH' in warning and not verified


@pytest.mark.parametrize('series',['670','700'])
def test_old_selection_normalizes_without_losing_identity_or_recording_preferences(tmp_path,series):
    path=tmp_path/'settings.json';settings=load_settings(path);config=config_for(series,'4.81')
    settings.update(analyzer_selection=f'LEL {series} Series',devices=[asdict(config)],simulated_lel_revision='700' if series=='700' else 'legacy')
    settings['recording']={'mode':'manual','parameters_by_profile':{f'LEL {series} Series':[1,9,11]}}
    if series=='670':settings['devices'][0]['register_profile']='fta_4x'
    original=json.dumps(settings);path.write_text(original,encoding='utf-8')
    loaded=load_settings(path)
    assert loaded['analyzer_selection']=='LEL'
    assert loaded['devices'][0]=={**settings['devices'][0],'register_profile':series}
    assert loaded['connection']==settings['connection'] and loaded['recording']==settings['recording']
    assert path.read_text(encoding='utf-8')==original


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False);return app


@pytest.mark.parametrize('series',['670','700'])
def test_only_three_ui_families_preserve_series_and_identity_on_selection(app,tmp_path,series):
    settings=load_settings(tmp_path/'settings.json');config=config_for(series,'Unknown')
    settings.update(devices=[asdict(config)],analyzer_selection='Auto Detect',simulated_lel_revision='700' if series=='700' else 'legacy')
    assert PROFILE_CHOICES==('LEL','BTU','FID')
    panel=ConnectionScreen(settings)
    assert [panel.profile.itemText(i) for i in range(panel.profile.count())]==['Auto Detect','LEL','BTU','FID']
    panel.profile.setCurrentText('LEL');result=panel.preferences(settings)
    assert result['devices']==settings['devices'] and result['connection']==settings['connection']
    dialog=AnalyzerChoice(settings);dialog.types.setCurrentText('LEL')
    assert dialog.types.count()==4
    result=dialog.settings()
    assert result['devices'][0]==settings['devices'][0]
    assert result['simulated_lel_revision']==settings['simulated_lel_revision']
    dialog.close();panel.close()


@pytest.mark.parametrize('version',VERSIONS)
def test_documented_670_setting_bounds_do_not_depend_on_firmware(version):
    config=config_for('670',version)
    assert encode(config,'cal_time',4)==4
    assert encode(config,'warning',40)==10240
    with pytest.raises(ValueError):encode(config,'cal_time',5)
    with pytest.raises(PermissionError):encode(config,'failsafe',7,previous=7)


def test_series_specific_service_definitions_remain_distinct():
    lel=definitions(config_for('670'));new=definitions(config_for('700'))
    assert lel['span_temperature'].bounds==(105,140) and new['span_temperature'].bounds==(50,150)
    assert new['latches'].reason and new['warning_latch'].number==72
    assert definitions(config_for('650'))['span_voltage'].title=='SPAN VDC'
    assert definitions(config_for('690'))['warning'].title=='LO ALARM'
    for series in ('650','670','690','700'):assert definitions(config_for(series))['failsafe'].reason


def test_fake_hardware_commands_allow_unknown_informational_version(control):
    service,state,store=control
    service.config=replace(service.config,version='Unknown')
    service.execute(0x100,'admin',confirmed=True)
    assert len(state['writes'])==1 and service.receipt['reply_received']


def test_changed_firmware_text_keeps_stable_identity_but_serial_change_does_not():
    first=parse_identity('LEL VER5.12 SNR675 S/N UNIT1');later=parse_identity('LEL VER??? SNR675 S/N UNIT1')
    assert identity_key(first)==identity_key(later)
    grant=ValidatedControlGrant('COM7',9600,1,-1,'SNR675','5.12',first.text)
    grant.validate_identity(later)
    with pytest.raises(PermissionError):grant.validate_identity(parse_identity('LEL VER5.12 SNR675 S/N OTHER'))


def test_unlabeled_controller_identifiers_remain_part_of_fresh_identity():
    original=parse_identity('TYPE FTAVER 4\xa781 SNR671 01 593')
    same=parse_identity('TYPE FTAVER ??? SNR671 01 593')
    other=parse_identity('TYPE FTAVER 9.99 SNR671 01 594')
    assert identity_key(original)==identity_key(same)
    assert identity_key(original)!=identity_key(other)
    grant=ValidatedControlGrant('COM7',9600,1,-1,'SNR671','4.81',original.text)
    grant.validate_identity(same)
    with pytest.raises(PermissionError):grant.validate_identity(other)


@pytest.mark.parametrize('version',VERSIONS)
def test_dilution_scale_uses_range_not_firmware(version):
    config=replace(config_for('670',version),assembly='SNR674D',fullscale=200)
    assert profile_for(config).register(1).decode(25600,'LEL',config.context)[0]==200
    config=replace(config,fullscale=100)
    assert profile_for(config).register(1).decode(25600,'LEL',config.context)[0]==100


@pytest.mark.parametrize('series',['650','670','690','700'])
def test_worker_monitors_all_series_with_unknown_firmware_and_exports_identity(app,tmp_path,series):
    from dev_support import MonitoringWorker
    config=config_for(series,'Unknown');settings=load_settings(tmp_path/'settings.json')
    settings.update(devices=[asdict(config)],analyzer_selection=config.family,simulated_family=config.family,simulated_lel_revision='700' if series=='700' else 'legacy')
    worker=MonitoringWorker(settings,tmp_path);updates=[];errors=[]
    worker.updated.connect(lambda snapshot,diagnostics:(updates.append((snapshot,diagnostics)),worker.stop()))
    worker.failed.connect(errors.append);worker.run()
    assert not errors and updates
    snapshot,diagnostics=updates[0]
    assert snapshot['quality']=='GOOD' and snapshot['config']['assembly']==config.assembly
    assert diagnostics['identity']['version']=='Unknown' and diagnostics['identity']['series']==series


def test_700_unknown_firmware_read_failure_keeps_reliable_identity():
    config=config_for('700','7.01');sim=SimulatedBus([config]);original=sim.read
    def read(address,pdu,count):
        if pdu==39:raise TimeoutError('Firmware unavailable')
        return original(address,pdu,count)
    sim.read=read;bus=BusEngine(sim,sleep=lambda _:None)
    try:
        identity=detect(bus,config.addressing)
        assert identity.verified and identity.version=='Unknown' and identity.model=='SNR705'
    finally:bus.close()


def test_control_scope_ignores_firmware_only_but_not_endpoint_changes():
    first=ValidatedControlGrant('COM7',9600,1,-1,'SNR675','5.12','LEL VER5.12 SNR675 S/N UNIT1')
    second=replace(first,version='Unknown',identity_text='LEL VER??? SNR675 SNR675 S/N UNIT1')
    assert first.scope_key()==second.scope_key()
    assert first.scope_key()!=replace(second,address=2).scope_key()


@pytest.mark.parametrize('firmware',['Unknown','9.99'])
def test_diagnostic_export_keeps_informational_firmware_without_io(app,tmp_path,monkeypatch,firmware):
    from PySide6.QtWidgets import QFileDialog
    from dev_support import MainWindow
    path=tmp_path/'diagnostics.json';settings=load_settings(tmp_path/'settings.json')
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path)
    w.identity=dict(family='LEL',model='SNR675',version=firmware,verified=True)
    w.diagnostics=dict(identity=dict(series='670',version=firmware),traffic=[])
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(path),'JSON (*.json)'))
    try:
        w.export_diagnostics();report=json.loads(path.read_text(encoding='utf-8'))
        assert report['firmware']==firmware and report['identity']['model']=='SNR675'
        assert not report['connection_current'] and w.worker is None
    finally:w.close();app.processEvents()
