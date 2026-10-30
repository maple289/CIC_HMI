"""Explicit operator confirmation, exercised with Qt and the simulated bus only."""
from dataclasses import asdict
from types import SimpleNamespace
import time

import pytest
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QWidget
from prevex_hmi.communication.commands import CommandController
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.gui.command_confirmation import COMMAND_NAMES,CommandConfirmation,command_effect,confirm_command
from prevex_hmi.logging_db.store import Historian
from test_command_result_layout import app,flush,setup_window
from prevex_hmi.gui.profile_library import PROFILE_CHOICES,library_config


@pytest.mark.parametrize('code',COMMAND_NAMES)
@pytest.mark.parametrize('theme',['dark','light'])
def test_compact_confirmation_copy_and_explicit_activation(app,tmp_path,code,theme):
    w,bus,_=setup_window(tmp_path,'LEL 670 Series');w.settings['theme']=theme;w.apply_theme();w.show();flush(app)
    d=CommandConfirmation(w,code,asdict(w.config),fault='Analyzer fault active: TC2 failed.')
    try:
        d.show();flush(app)
        assert d.windowTitle()=='Confirm Command'
        assert d.message.text()==f'Execute {COMMAND_NAMES[code]} on the connected analyzer?'
        assert w.config.assembly in d.analyzer.text()
        assert d.effect.text()==command_effect(code)
        if code in (0x300,0x400,0x500):assert d.effect.text()=='This command will start analyzer calibration.'
        assert d.confirm_button.text()=='Confirm' and d.cancel_button.text()=='Cancel'
        assert d.focusWidget() is d.cancel_button
        assert all(not b.autoDefault() and not b.isDefault() for b in (d.confirm_button,d.cancel_button))
        text=' '.join(label.text() for label in (d.message,d.analyzer,d.effect,d.fault))
        assert not any(term in text.lower() for term in ('modbus','0x','register','firmware','status [','relays','baud','verification'))
        assert d.width()<=440 and d.height()<330
        assert (d.frameGeometry().center()-w.frameGeometry().center()).manhattanLength()<8
        for target in (d.cancel_button,d.confirm_button):
            target.setFocus();flush(app)
            for key in (Qt.Key_Return,Qt.Key_Enter):
                QTest.keyClick(target,key);flush(app)
                assert d.isVisible() and not d.confirmed
        QTest.mouseClick(d.confirm_button,Qt.LeftButton);flush(app)
        assert d.result()==QDialog.Accepted and d.confirmed and not d.isVisible()
    finally:d.close();w.close();bus.close();flush(app)


@pytest.mark.parametrize('action',['confirm','cancel','close','escape','enter_cancel','programmatic_accept'])
def test_confirmation_wrapper_requires_explicit_confirm(app,action):
    parent=QWidget();parent.show();errors=[]
    def answer():
        try:
            d=QApplication.activeModalWidget();assert isinstance(d,CommandConfirmation)
            if action=='confirm':QTest.mouseClick(d.confirm_button,Qt.LeftButton)
            elif action=='cancel':QTest.mouseClick(d.cancel_button,Qt.LeftButton)
            elif action=='close':d.close()
            elif action=='escape':QTest.keyClick(d,Qt.Key_Escape)
            elif action=='programmatic_accept':d.accept()
            else:
                QTest.keyClick(d,Qt.Key_Return);assert d.isVisible() and not d.confirmed
                QTest.mouseClick(d.cancel_button,Qt.LeftButton)
        except Exception as exc:
            errors.append(exc)
            if QApplication.activeModalWidget():QApplication.activeModalWidget().reject()
    try:
        QTimer.singleShot(0,answer)
        assert confirm_command(parent,0x100,asdict(default_devices()[0])) is (action=='confirm')
        assert not errors
    finally:parent.close();flush(app)


@pytest.mark.parametrize('name',PROFILE_CHOICES)
def test_profile_target_and_deliberate_keyboard_activation(app,name):
    parent=QWidget();parent.show();config=library_config(name)
    d=CommandConfirmation(parent,0x100,asdict(config))
    try:
        d.show();flush(app)
        assert name in d.analyzer.text() and config.assembly in d.analyzer.text()
        d.confirm_button.setFocus();QTest.keyClick(d.confirm_button,Qt.Key_Space);flush(app)
        assert d.confirmed and d.result()==QDialog.Accepted
    finally:d.close();parent.close();flush(app)


@pytest.mark.parametrize('code',COMMAND_NAMES)
@pytest.mark.parametrize('action',['confirm','cancel','close','enter_cancel'])
def test_all_commands_dispatch_only_after_confirm_and_retain_simulator_audit(app,tmp_path,code,action):
    w,bus,_=setup_window(tmp_path,'LEL 670 Series');requests=[];errors=[]
    w.worker=SimpleNamespace(isRunning=lambda:True,test_only=False,request=lambda *args:requests.append(args))
    store=Historian(tmp_path/'confirmation-audit.sqlite3')
    try:
        w.users.create_user('operator','password8');w.session=w.users.authenticate('operator','password8')
        w.snapshot['control']=dict(verified=True,pending=False,ambiguous=False)
        lock=2 if code==0x1000 else 0
        w.snapshot['raw'].update({2:0,60:lock});w.snapshot['register_ages'][60]=0
        bus.transport.devices[w.config.address].raw.update({2:0,60:lock})
        w.snapshot_received_at=time.monotonic();w.update_command_buttons();w.show();flush(app)
        assert w.command_buttons[code].isEnabled()
        def answer():
            try:
                d=QApplication.activeModalWidget();assert isinstance(d,CommandConfirmation)
                if action=='confirm':QTest.mouseClick(d.confirm_button,Qt.LeftButton)
                elif action=='cancel':QTest.mouseClick(d.cancel_button,Qt.LeftButton)
                elif action=='close':d.close()
                else:
                    QTest.keyClick(d,Qt.Key_Return);assert not requests and not d.confirmed and d.isVisible()
                    QTest.mouseClick(d.cancel_button,Qt.LeftButton)
            except Exception as exc:
                errors.append(exc)
                if QApplication.activeModalWidget():QApplication.activeModalWidget().reject()
        QTimer.singleShot(0,answer);w.send_command(code)
        assert not errors
        assert not bus.transport.events
        if action!='confirm':
            assert not requests and not store.audit_rows();return
        assert len(requests)==1
        name,sent_code,token,confirmed,request_id=requests[0]
        assert name=='command' and sent_code==code and confirmed is True
        bus.sleep=lambda _:None
        controller=CommandController(bus,w.config,store,w.users,identity_verified=True)
        controller.request_id=request_id;controller.execute(code,token,confirmed=confirmed)
        assert len([event for event in bus.transport.events if event.get('code')==code])==1
        assert controller.receipt['reply_received'] and controller.receipt['code']==code
        assert any(row[3]==code for row in store.audit_rows())
        w.show_command_receipt(controller.receipt)
        assert 'Reply received: YES' in w.command_proof.text() and 'Modbus acknowledgment' in w.command_proof.text()
    finally:
        store.close();w.worker=None;w.close();bus.close();flush(app)
