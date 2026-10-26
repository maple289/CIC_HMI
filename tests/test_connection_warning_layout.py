"""Read-only identity replay and shared responsive-card geometry regressions."""
from dataclasses import asdict,replace
from pathlib import Path
import copy,os,struct,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtWidgets import QApplication,QLabel
from prevex_hmi.devices.configuration import default_devices,load_settings
from prevex_hmi.devices.identification import parse_identity
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.communication.protocol import frame
from prevex_hmi.profiles import profile_for
from prevex_hmi.simulator.bus import SimulatedBus
from prevex_hmi.communication.engine import BusEngine
from test_hardware_monitoring import IDENTITY,RAW


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    path=Path('C:/Windows/Fonts/segoeui.ttf')
    if path.exists():
        font=QFontDatabase.addApplicationFont(str(path))
        if font>=0:app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0],10))
    return app


def wait(app,condition):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        app.processEvents()
        if condition():return
        time.sleep(.01)
    pytest.fail('Timed out waiting for test-only worker')


@pytest.mark.parametrize('legacy',[True,False])
def test_admin_test_connection_does_not_change_profile_or_activate_commands(app,tmp_path,monkeypatch,legacy):
    payload=IDENTITY if legacy else b'PREVEX VER5.12 SNR675 2005'.ljust(32,b' ')
    calls=[];instances=[]
    class Replay:
        physical=True
        def __init__(self,*args,**kwargs):
            self.trace=lambda *_:None;self.closed=False;instances.append(self)
        def read(self,address,pdu,count):
            calls.append((address,pdu,count))
            self.trace(True,frame(struct.pack('>BBHH',address,3,pdu,count)))
            raw={**RAW,62:11}
            raw.update({257+i//2:int.from_bytes(payload[i:i+2],'big') for i in range(0,32,2)})
            words=[raw.get(n,0) for n in range(pdu+1,pdu+count+1)]
            self.trace(False,frame(bytes((address,3,count*2))+struct.pack(f'>{count}H',*words)))
            return words
        def close(self):self.closed=True
    monkeypatch.setattr('prevex_hmi.gui.window.require_available_port',lambda _:None)
    monkeypatch.setattr('prevex_hmi.communication.serial_transport.available_ports',lambda:['COM4'])
    monkeypatch.setattr('prevex_hmi.communication.serial_transport.ReadOnlySerialTransport',Replay)
    monkeypatch.setattr('prevex_hmi.communication.serial_transport.ControllerBenchTransport',lambda *a,**k:pytest.fail('Test Connection must remain read-only'))
    settings=load_settings(tmp_path/'settings.json');settings.update(mode='hardware',analyzer_selection='Auto Detect')
    settings['connection'].update(port='COM4',baud=9600)
    settings['devices']=[asdict(default_devices()[0])]
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    w.show()
    if not legacy:w.warning.setText('Previous compatibility warning');w.warning.show()
    try:
        results=[]
        for admin in (False,True):
            if admin:
                w.users.create_user('admin','test-identity-password')
                w.session=w.users.authenticate('admin','test-identity-password')
            w.begin('test');wait(app,lambda:bool(w.identity) and not w.worker.isRunning())
            wait(app,lambda:w.connection_test_dialog is not None and not w.test_in_progress)
            assert w.connection_test_dialog.isVisible()
            assert w.test_view_active and w.pages.currentWidget() is w.test_page
            assert w.navigation.isHidden() and w.disconnect_button.isHidden() and w.bench_button.isHidden()
            assert not w.gauge.isVisibleTo(w) and not w.indicators.isVisibleTo(w)
            assert all(not button.isVisibleTo(w) for button in w.command_buttons.values())
            assert w.connection_test_dialog.result_label.text()=='Connection test passed'
            assert 'COM4' in w.connection_test_dialog.details.text()
            assert ('SNR671' if legacy else 'SNR675') in w.connection_test_dialog.details.text()
            assert 'Monitoring is stopped' in w.connection_test_dialog.instructions.text()
            assert all(item.closed for item in instances)
            results.append(copy.deepcopy(w.identity))
            assert w.snapshot is None and not w.identity['controls_verified']
            assert not any(b.isEnabled() for b in w.command_buttons.values())
            assert 'Selected: Auto Detect' in w.identity_label.text()
            assert 'Detected: LEL 670 Series' in w.identity_label.text()
            assert 'Valid Modbus response' in w.identity_label.text()
            if legacy:
                assert '0xA7' in w.warning.text() and 'by explicit user instruction' in w.warning.text()
                assert 'Only explicitly authorized operator' not in w.warning.text()
                assert 'provisional; reported 4\xa781' in w.identity_label.text()
                assert w.identity['config']['register_profile']=='fta_4x'
            else:
                assert not w.warning.text() and w.warning.isHidden()
                assert w.identity['config']['register_profile']=='670'
        assert results[0]==results[1]
        assert all(item.closed for item in instances)
        if legacy:assert all(pdu+1 not in (8,60,62) for _,pdu,_ in calls)
    finally:w.close();app.processEvents()


@pytest.mark.parametrize('failure',['missing_port','worker_timeout'])
def test_connection_failure_has_explicit_result_without_controls(app,tmp_path,monkeypatch,failure):
    from prevex_hmi.gui.worker import MonitoringWorker
    settings=load_settings(tmp_path/'settings.json');settings['mode']='hardware';settings['connection']['port']='COM4'
    error='COM4 is no longer available' if failure=='missing_port' else 'Identification timed out; no valid Modbus response'
    def available(_):
        if failure=='missing_port':raise ValueError(error)
    class FailedCheck(MonitoringWorker):
        def run(self):self.failed.emit(error)
    monkeypatch.setattr('prevex_hmi.gui.window.require_available_port',available)
    monkeypatch.setattr('prevex_hmi.gui.window.MonitoringWorker',FailedCheck)
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    try:
        w.begin('test');wait(app,lambda:w.connection_test_dialog is not None)
        assert w.connection_test_dialog.result_label.text()=='Connection test failed'
        assert error in w.connection_test_dialog.details.text()
        assert not w.test_in_progress and w.snapshot is None
        assert not any(b.isEnabled() for b in w.command_buttons.values())
    finally:w.close();app.processEvents()


def test_unknown_identity_is_not_reported_as_identified_success(app,tmp_path):
    from prevex_hmi.gui.connection_result import ConnectionTestResult
    settings=load_settings(tmp_path/'settings.json')
    dialog=ConnectionTestResult(settings,dict(communication_ok=True,warning='Unknown analyzer identity'))
    try:
        assert 'identification unresolved' in dialog.result_label.text()
        assert 'Unknown analyzer identity' in dialog.details.text()
    finally:dialog.close()


@pytest.mark.parametrize('action',['Back','Connect and monitor'])
def test_focused_test_view_returns_without_stale_live_widgets(app,tmp_path,action):
    from PySide6.QtWidgets import QPushButton
    settings=load_settings(tmp_path/'settings.json')
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False);w.show()
    try:
        w.navigation.setCurrentRow(1 if action=='Back' else 0)
        w.begin('test')
        assert w.test_view_active and not w.gauge.isVisibleTo(w)
        wait(app,lambda:w.connection_test_dialog is not None and not w.test_in_progress)
        result=w.connection_test_dialog
        button=next(b for b in result.findChildren(QPushButton) if b.text()==action)
        button.click()
        wait(app,lambda:not w.test_view_active)
        assert w.navigation.isVisible() and w.connection_test_dialog is None
        if action=='Connect and monitor':
            wait(app,lambda:w.snapshot is not None and w.snapshot['quality']=='GOOD')
            assert w.gauge.isVisibleTo(w) and w.disconnect_button.isVisible()
        else:
            assert w.snapshot is None and w.pages.currentIndex()==1
            assert not w.worker.isRunning()
    finally:
        w.close()
        wait(app,lambda:not w.worker or not w.worker.isRunning());app.processEvents()


def test_legacy_warning_distinguishes_raw_separator_and_firmware_scope():
    raw=parse_identity('TYPE FTAVER 4\xa781 SNR671')
    assert raw.reported_version=='4\xa781' and raw.version=='4.81' and raw.version_provisional
    normal=parse_identity('TYPE FTAVER 4.81 SNR671')
    assert not normal.version_provisional and '0xA7' not in normal.warning
    assert '5.12+' in normal.warning and normal.verified and normal.compatibility_assumed
    modern=parse_identity('PREVEX VER5.12 SNR675 2005')
    assert not modern.warning and not modern.legacy_format


def test_profile_mismatch_keeps_genuine_firmware_details():
    from prevex_hmi.devices.identification import resolve_profile,Identification
    identity=parse_identity('TYPE FTAVER 4\xa781 SNR671')
    config,warning,controls=resolve_profile(default_devices()[0],'BTU',identity)
    assert 'MISMATCH' in warning and '0xA7' in warning and 'by explicit user instruction' in warning
    assert not controls and config.register_profile=='fta_4x'
    _,warning,controls=resolve_profile(default_devices()[0],'BTU',Identification('LEL','SNR673','5.12',verified=True))
    assert 'MISMATCH' in warning and 'Undocumented' in warning and not controls


@pytest.mark.parametrize('detail',['CRC error in identification reply','Identification timed out'])
def test_detection_errors_remain_visible(detail):
    from prevex_hmi.devices.identification import resolve_profile,Identification
    config,warning,controls=resolve_profile(default_devices()[0],'Auto Detect',Identification(warning=detail))
    assert config is None and detail in warning and not controls


@pytest.mark.parametrize('kind',['670','700','BTU','FID'])
def test_compact_cards_reflow_without_clipping_or_overlap(app,tmp_path,kind):
    family='LEL' if kind in ('670','700') else kind
    config=next(d for d in default_devices() if d.family==family)
    if kind=='700':config=replace(config,assembly='SNR705',version='7.01')
    settings=load_settings(tmp_path/'settings.json');settings['devices']=[asdict(config)]
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    sim=SimulatedBus([config]);sim.devices[config.addressing.packet_address].update(time.monotonic())
    bus=BusEngine(sim,sleep=lambda _:None)
    snapshot=dict(config=asdict(config),raw=sim.devices[config.addressing.packet_address].raw.copy(),quality='GOOD',register_ages={},age=0,last_success='2026-10-24T12:00:00+00:00',error='',control={})
    try:
        w.update_data(snapshot,bus.diagnostics());w.show();app.processEvents()
        container=w.readout_container;counts=[]
        for width in (1540,1100,1900,1100):
            w.resize(width,1020);app.processEvents();app.processEvents()
            cards=container.cards;counts.append(container.columns)
            assert container.columns==container.column_count(container.width())
            assert all(card.width()==200 for container in w.readout_groups.values() for card in container.cards)
            for group in w.readout_groups.values():
                cards=group.cards
                for i,card in enumerate(cards):
                    assert card.geometry().right()<group.width()
                    assert card.geometry().bottom()<group.height()
                    assert all(not card.geometry().intersects(other.geometry()) for other in cards[i+1:])
                    for label in card.findChildren(QLabel):
                        if label.isHidden():continue
                        assert label.x()>=0 and label.y()>=0
                        assert label.geometry().right()<card.width() and label.geometry().bottom()<card.height()
                        assert label.height()>=label.heightForWidth(label.width())
        assert counts[1]<counts[0]<=counts[2] and counts[3]==counts[1]
        assert all(not text.isHidden() for text in w.readout_names.values())
    finally:w.close();bus.close();app.processEvents()
