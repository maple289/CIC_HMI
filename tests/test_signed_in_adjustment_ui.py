"""Role-based physical adjustment UI tested with cached data only, no port."""
from dataclasses import asdict,replace
from types import SimpleNamespace
import time
from PySide6.QtWidgets import QDialog,QMessageBox
from prevex_hmi.devices.configuration import default_devices,load_settings
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.gui.parameter_editor import ParameterEditor
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.simulator.bus import SimulatedBus
from prevex_hmi.profiles.common import COMMANDS
from test_monitoring import app


def test_guest_viewer_operator_admin_and_revoked_sessions(app,tmp_path,monkeypatch):
    settings=load_settings(tmp_path/'settings.json')
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    bus=BusEngine(SimulatedBus([default_devices()[0]]),sleep=lambda _:None)
    config=replace(default_devices()[0],assembly='SNR671',version='4.81',register_profile='fta_4x')
    raw={1:0,2:0,3:100,4:0,5:40*256,6:50*256,17:7,18:7,28:1,56:512,60:0}
    snapshot=dict(config=asdict(config),raw=raw,quality='GOOD',age=0,register_ages={n:0 for n in raw},last_success='2026-10-26T12:00:00+00:00',error='',source='hardware',control={'verified':True,'physical_commands':list(COMMANDS)})
    try:
        # This stand-in never opens a transport or handles a request.
        w.worker=SimpleNamespace(isRunning=lambda:True,test_only=False)
        w.settings['mode']='hardware'
        from test_monitoring import identify
        identify(w,config);w.update_data(snapshot,bus.diagnostics())
        assert not any(button.isEnabled() for button in w.parameter_menus.values())
        w.users.create_user('admin','test-password');admin=w.users.authenticate('admin','test-password')
        w.users.create_user('operator','test-password','Operator',session=admin)
        w.users.create_user('viewer','test-password','Viewer',session=admin)
        for role,expected in (('viewer',False),('operator',True),('admin',True)):
            w.session=w.users.authenticate(role,'test-password');w.snapshot_received_at=time.monotonic();w.update_command_buttons()
            assert all(button.isEnabled()==expected for button in w.parameter_menus.values())
            if expected:assert not w.parameter_access_reason('cal_time')
        operator=w.users.authenticate('operator','test-password');w.session=operator;w.update_command_buttons()
        w.users.logout(operator);w.update_command_buttons()
        assert not any(button.isEnabled() for button in w.parameter_menus.values())
        w.session=admin;w.snapshot_received_at=time.monotonic();w.update_command_buttons()
        editor=ParameterEditor(config,'cal_time',1,physical=True,parent=w)
        assert editor.save_button.isEnabled() and 'Real controller' in editor.access_note.text()
        captured=[]
        monkeypatch.setattr(ParameterEditor,'exec',lambda d:QDialog.Accepted)
        monkeypatch.setattr(ParameterEditor,'proposed',lambda d:2)
        monkeypatch.setattr(QMessageBox,'question',lambda *args:captured.append(args[2]) or QMessageBox.No)
        w.edit_parameter('cal_time')
        assert 'REAL CONTROLLER' in captured[0] and '4.81' in captured[0] and 'SAVE ALL' in captured[0]
        requests=[];w.worker.request=lambda *args:requests.append(args)
        monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
        w.snapshot_received_at=time.monotonic();w.edit_parameter('cal_time')
        assert requests==[('parameter','cal_time',2,1,admin,True)]
        assert w.command_dispatching and not any(button.isEnabled() for button in w.parameter_menus.values())
        assert 18 not in w.parameter_menus
    finally:w.worker=None;w.close();bus.close();app.processEvents()
