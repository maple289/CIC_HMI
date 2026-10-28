"""Command result geometry and safe browsing of the existing profile library."""
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import copy,os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtWidgets import QApplication,QDialog,QComboBox
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.devices.configuration import load_settings
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.gui.profile_library import PROFILE_CHOICES,library_config
from prevex_hmi.profiles import profile_for
from prevex_hmi.simulator.bus import SimulatedBus


@pytest.fixture
def app():
    result=QApplication.instance() or QApplication([]);result.setQuitOnLastWindowClosed(False)
    path=Path('C:/Windows/Fonts/segoeui.ttf')
    if path.exists():
        fid=QFontDatabase.addApplicationFont(str(path))
        if fid>=0:result.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0],10))
    return result


def flush(app):
    for _ in range(5):app.processEvents()


def setup_window(tmp_path,name):
    config=library_config(name);settings=load_settings(tmp_path/'settings.json')
    settings.update(analyzer_selection=name,simulated_family=config.family,devices=[asdict(config)])
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    sim=SimulatedBus([config]);bus=BusEngine(sim)
    snap=dict(config=asdict(config),raw=sim.devices[config.address].raw.copy(),quality='GOOD',
              age=0,register_ages={},last_success='2026-10-25T12:00:00+00:00',error='')
    w.update_data(snap,bus.diagnostics());w.monitor_model.setText(f'{config.assembly} / firmware{config.version}')
    return w,bus,snap


@pytest.mark.parametrize('name',PROFILE_CHOICES)
def test_command_buttons_and_leds_stay_anchored_during_results_and_alarm_changes(app,tmp_path,name):
    w,bus,snap=setup_window(tmp_path,name);w.show()
    try:
        for width in (1540,1100,1900):
            w.resize(width,1020);flush(app)
            w.command_scroll.ensureWidgetVisible(w.command_buttons[0x700]);flush(app)
            def geometry():
                return [(b.mapTo(w,QPoint()).toTuple(),b.size().toTuple(),b.led.mapTo(w,QPoint()).toTuple()) for b in w.command_buttons.values()]
            before=geometry();offset=w.command_scroll.verticalScrollBar().value()
            height=w.command_result_card.height()
            for sequence,state in enumerate(('SENDING','PENDING','STARTED','COMPLETED_OBSERVED','FAILED','UNKNOWN')):
                w.show_command_receipt(dict(id=str(sequence),code=0x700,state=state,reply_received=state!='SENDING',detail='Detailed execution status and validation result. '*70,before_status=20,status_after=0))
                w.command_message.setText('Additional controller result information. '*60)
                changing=copy.deepcopy(snap);changing['raw'].update({2:0 if sequence%2 else 20,4:0 if sequence%2 else 12,59:0 if sequence%2 else 161})
                w.indicators.update_snapshot(changing);flush(app)
                assert geometry()==before
                assert w.command_scroll.verticalScrollBar().value()==offset
                assert w.command_result_card.height()==height
            assert not w.command_result_card.isVisibleTo(w)
            assert not w.gauge.geometry().intersects(w.analyzer_info.geometry())
            assert w.last_command.isVisibleTo(w) and w.last_command.height()==56
            panel_position=w.indicators.mapTo(w,QPoint()).toTuple()
            w.monitor_scroll.verticalScrollBar().setValue(w.monitor_scroll.verticalScrollBar().maximum());flush(app)
            assert w.indicators.isVisibleTo(w) and w.indicators.mapTo(w,QPoint()).toTuple()==panel_position
            assert geometry()==before  # Only the readings scroll; alarms and commands stay pinned.
            w.monitor_scroll.verticalScrollBar().setValue(0);flush(app)
    finally:w.close();bus.close();flush(app)


def test_profile_dropdown_browses_without_reinterpreting_or_changing_connected_analyzer(app,tmp_path,monkeypatch):
    w,bus,snap=setup_window(tmp_path,'LEL 670 Series')
    requests=[];w.worker=SimpleNamespace(isRunning=lambda:True,test_only=False,request=lambda *args:requests.append(args))
    original=copy.deepcopy(w.settings)
    try:
        assert isinstance(w.profile_selector,QComboBox)
        assert [w.profile_selector.itemData(i) for i in range(1,5)]==list(PROFILE_CHOICES)
        for name in ('LEL 700 Series','BTU','FID'):
            w.profile_selector.setCurrentIndex(w.profile_selector.findData(name));flush(app)
            assert w.settings==original and w.snapshot==snap
            assert not w.read_setting_button.isEnabled()
            assert all(w.settings_table.item(i,3).text()=='--' and w.settings_table.item(i,4).text()=='--' for i in range(w.settings_table.rowCount()))
            assert 'Library preview' in w.profile_note.text()
            if name in ('BTU','FID'):assert 'Preliminary' in w.profile_note.text()
            w.settings_table.selectRow(0);w.read_setting();assert not requests
        captured=[]
        class CancelledChoice:
            def __init__(self,settings,parent):captured.append(settings)
            def exec(self):return QDialog.Rejected
        monkeypatch.setattr('prevex_hmi.gui.window.AnalyzerChoice',CancelledChoice)
        w.use_library_profile()
        assert captured[0]['analyzer_selection']=='FID' and w.settings==original and not requests
        from prevex_hmi.gui.connection_dialog import AnalyzerChoice
        monkeypatch.setattr('prevex_hmi.gui.window.AnalyzerChoice',AnalyzerChoice)
        monkeypatch.setattr(AnalyzerChoice,'exec',lambda self:QDialog.Accepted)
        started=[];w.worker=None
        monkeypatch.setattr(w,'start_worker',lambda **kwargs:started.append(copy.deepcopy(w.settings)))
        w.use_library_profile()
        assert started and started[0]['analyzer_selection']=='FID'
        assert started[0]['devices'][0]['family']=='FID' and started[0]['simulated_family']=='FID'
        assert w.snapshot is None  # Old readings invalidated before a new worker can start.
        # Restore a live matching source for the read-only inspection check.
        w.snapshot=snap;w.settings=original
        w.worker=SimpleNamespace(isRunning=lambda:True,test_only=False,request=lambda *args:requests.append(args))
        w.profile_selector.setCurrentIndex(0);flush(app)
        assert w.read_setting_button.isEnabled()
        w.settings_table.selectRow(0);w.read_setting();assert requests and requests[-1][0]=='inspect'
    finally:w.worker=None;w.close();bus.close();flush(app)
