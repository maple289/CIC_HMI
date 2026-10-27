"""Live-setpoint zones and one lock row; only synthetic data/transports."""
import copy
import os
from dataclasses import asdict,replace
from types import SimpleNamespace
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication,QMessageBox
from prevex_hmi.devices.configuration import default_devices,load_settings
from prevex_hmi.gui.gauge import gauge_state,CircularGauge
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.profiles import profile_for
from test_validated_commands import control
from test_identification_commands import controller


def sample(value=10,series='670',warning=25,danger=50):
    config=replace(default_devices()[0],assembly='SNR705' if series=='700' else 'SNR675',version='7.01' if series=='700' else '5.12',register_profile=series)
    p=profile_for(config)
    raw={n:p.register(n).encode(v,'LEL',config.context) for n,v in ((1,value),(5,warning),(6,danger))}
    raw.update({2:0,3:100,4:0,60:0})
    return dict(config=asdict(config),raw=raw,quality='GOOD',age=0,register_ages={n:0 for n in raw},control=dict(verified=True))


@pytest.fixture
def app():
    result=QApplication.instance() or QApplication([]);result.setQuitOnLastWindowClosed(False)
    return result


@pytest.mark.parametrize('series',['670','700'])
@pytest.mark.parametrize('value,color',[(-30,'#8290a5'),(-1,'#8290a5'),(0,'#39c6a4'),(24,'#39c6a4'),(25,'#efb753'),(49,'#efb753'),(50,'#f27778'),(120,'#f27778')])
def test_lel_indicator_uses_live_zone_boundaries_not_status(series,value,color):
    state=gauge_state(sample(value,series))
    assert state.color==color and state.status=='Normal'
    assert state.value==pytest.approx(value,abs=.004)
    assert state.negative_color=='#8290a5'
    assert state.markers==( ('W',25.,'#efb753'),('D',50.,'#f27778') )


def test_threshold_changes_and_actual_fault_status_are_independent():
    data=sample(35,warning=25,danger=50);original=copy.deepcopy(data)
    assert gauge_state(data).color=='#efb753' and data==original
    data['raw'][5]=40*256;data['raw'][6]=55*256;data['raw'][2]=25
    state=gauge_state(data)
    assert state.color=='#39c6a4' and state.status_color=='#f27778'
    assert state.status=='TC2 failed' and '40' in state.thresholds and '55' in state.thresholds
    assert state.minimum==-100


@pytest.mark.parametrize('invalid',['missing','stale','reversed','equal','negative','below_min','above_max','outside_scale','offline'])
def test_unverified_setpoints_never_show_positive_green_or_assumed_bands(invalid):
    data=sample()
    if invalid=='missing':del data['raw'][5]
    elif invalid=='stale':data['register_ages'][6]=30
    elif invalid=='reversed':data['raw'][5]=55*256
    elif invalid=='equal':data['raw'][5]=data['raw'][6]
    elif invalid=='negative':data['raw'][5]=(-5*256)&65535
    elif invalid=='below_min':data['raw'][5]=4*256
    elif invalid=='above_max':data['raw'][6]=61*256
    elif invalid=='outside_scale':data['config'].update(range_mode='manual',manual_maximum=40)
    else:data['quality']='OFFLINE'
    state=gauge_state(data)
    assert state.color=='#8290a5' and state.bands==() and state.markers==()
    assert 'unverified' in state.thresholds.lower()


def test_legacy_dilution_alarm_conversion_uses_its_profile():
    data=sample();data['config']=asdict(default_devices()[3]);data['raw'].update({1:3200,3:200,5:4000,6:6400})
    state=gauge_state(data)
    assert state.value==25 and state.markers[0][1]==31.25 and state.markers[1][1]==50
    assert state.color=='#39c6a4'


def test_short_hold_is_stale_gray_then_expires_without_mutating_input(app,monkeypatch):
    import prevex_hmi.gui.gauge as module
    now=[100.];monkeypatch.setattr(module.time,'monotonic',lambda:now[0])
    gauge=CircularGauge();data=sample(10);gauge.set_snapshot(data)
    assert gauge.state.color=='#39c6a4'
    lost=copy.deepcopy(data);lost['quality']='OFFLINE';now[0]+=1;gauge.set_snapshot(lost)
    assert gauge.state.value==10 and gauge.held and gauge.state.color=='#8290a5'
    assert gauge.state.bands==() and gauge.state.markers==() and 'unverified' in gauge.state.thresholds
    assert lost['quality']=='OFFLINE'
    now[0]+=4;gauge.expire();assert gauge.state.value is None and gauge.state.reading=='--'
    assert gauge.state.color==gauge.state.status_color=='#8290a5'
    gauge.set_snapshot(sample(0));assert gauge.state.value==0 and not gauge.held
    gauge.close()


def test_old_numeric_sample_does_not_flash_green_without_a_prior_hold(app):
    gauge=CircularGauge();data=sample(10);data['register_ages'][1]=4.5
    gauge.set_snapshot(data)
    assert gauge.state.value is None and gauge.state.reading=='--'
    assert gauge.state.color==gauge.state.status_color=='#8290a5'
    gauge.close()


@pytest.fixture
def window(app,tmp_path):
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path,start_worker=False)
    w.users.close();w.users=SimpleNamespace(resolve=lambda _:('operator','Operator'),close=lambda:None)
    w.worker=SimpleNamespace(isRunning=lambda:True,test_only=False)
    w.snapshot=sample();w.update_command_buttons()
    yield w
    w.worker=None;w.close();app.processEvents()


@pytest.mark.parametrize('lock,caption,code,hardware',[(0,'LOCK CAL',0xF00,'unlocked'),(1,'LOCK CAL',0xF00,'LOCKED'),(2,'UNLOCK CAL',0x1000,'unlocked'),(3,'UNLOCK CAL',0x1000,'LOCKED')])
def test_one_dynamic_row_decodes_software_and_hardware_separately(window,lock,caption,code,hardware):
    w=window;w.snapshot['raw'][60]=lock;w.update_command_buttons()
    assert w.command_buttons[0xF00] is w.command_buttons[0x1000]
    button=w.command_buttons[code]
    assert button.button.text()==caption and not button.button.icon().isNull()
    assert w.lock_command_code==code and button.isEnabled()
    assert w.hardware_lock_label.text()==f'Hardware lock: {hardware}'
    if lock&1:assert not w.command_buttons[0x300].isEnabled()


@pytest.mark.parametrize('condition',['missing','stale','invalid','offline','700','viewer'])
def test_unknown_or_unsupported_lock_state_disables_action(window,condition):
    w=window
    if condition=='missing':del w.snapshot['raw'][60]
    elif condition=='stale':w.snapshot['register_ages'][60]=30
    elif condition=='invalid':w.snapshot['raw'][60]=65535
    elif condition=='offline':w.snapshot['quality']='OFFLINE'
    elif condition=='700':w.snapshot=sample(series='700')
    else:w.users.resolve=lambda _:('viewer','Viewer')
    w.update_command_buttons()
    assert not w.command_buttons[0xF00].isEnabled()
    if condition!='viewer':assert w.lock_command_code is None


def test_action_switch_preserves_button_and_acknowledgment_led(window,app):
    w=window;w.show();app.processEvents();button=w.command_buttons[0xF00]
    position=button.mapTo(w,QPoint());led_position=button.led.mapTo(w,QPoint())
    w.show_command_receipt(dict(id='lock',code=0xF00,state='VERIFIED',reply_received=True))
    w.snapshot['raw'][60]=2;w.update_command_buttons();app.processEvents()
    assert button.button.text()=='UNLOCK CAL' and '#39c66c' in button.led.styleSheet()
    assert button.mapTo(w,QPoint())==position and button.led.mapTo(w,QPoint())==led_position
    w.show_command_receipt(dict(id='unlock',code=0x1000,state='REJECTED',reply_received=False))
    assert '#ed575d' in button.led.styleSheet()


def test_acknowledgment_alone_does_not_toggle_lock_action(window):
    w=window
    w.show_command_receipt(dict(id='lock',code=0xF00,state='PENDING',reply_received=True))
    w.update_command_buttons()
    assert w.command_buttons[0xF00].button.text()=='LOCK CAL'
    assert w.lock_command_code==0xF00


def test_dynamic_click_dispatches_only_current_confirmed_action(window,monkeypatch):
    w=window;sent=[];monkeypatch.setattr(w,'request',lambda *args:sent.append(args))
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    w.snapshot['raw'][60]=2;w.update_command_buttons();w.command_buttons[0xF00].button.click()
    assert sent==[('command',0x1000,w.session,True)]
    assert not w.command_buttons[0xF00].isEnabled()


def test_lock_change_during_confirmation_requires_review(window,monkeypatch):
    w=window;sent=[];monkeypatch.setattr(w,'request',lambda *args:sent.append(args))
    def confirm(*args):w.snapshot['raw'][60]=2;return QMessageBox.Yes
    monkeypatch.setattr(QMessageBox,'question',confirm);w.send_command(0xF00)
    assert not sent and w.lock_command_code==0x1000


def test_simulator_lock_commands_publish_actual_verified_readback(controller):
    service,token,clock,sim,store,users=controller
    for code,expected in ((0xF00,2),(0x1000,0)):
        service.execute(code,token,confirmed=True)
        assert service.receipt['state']=='VERIFIED'
        assert service.receipt['lock_readback']==expected and service.receipt['lock_register']==60


def test_fake_physical_lock_readback_preserves_hardware_bit(control):
    service,state,store=control;state['lock']=1
    for code,expected in ((0xF00,3),(0x1000,1)):
        service.execute(code,'admin',confirmed=True)
        assert service.receipt['state']=='VERIFIED' and service.receipt['lock_readback']==expected
        assert state['lock']==expected


def test_fake_physical_acknowledgment_without_changed_lock_is_observed_then_failed(control):
    service,state,store=control;original=service.bus.validated_operating_command
    now=[0.0];service.clock=lambda:now[0]
    def ignored(code):original(code);state['lock']=0
    service.bus.validated_operating_command=ignored
    service.execute(0xF00,'admin',confirmed=True)
    assert service.receipt['reply_received'] and service.receipt['state']=='VERIFYING_LOCK'
    pending=service.pending;now[0]=pending.timeout-.001
    service.observe(dict(raw={60:0},quality='GOOD',register_ages={60:0}))
    assert service.receipt['state']=='VERIFYING_LOCK' and service.pending is pending
    now[0]=pending.timeout
    service.observe(dict(raw={60:0},quality='GOOD',register_ages={60:0}))
    assert service.receipt['state']=='FAILED' and service.pending is None
    assert service.receipt['lock_readback']==0
    assert len(state['writes'])==1


@pytest.mark.parametrize('code,before,after',[(0xF00,0,2),(0xF00,1,3),(0x1000,2,0),(0x1000,3,1)])
def test_delayed_lock_change_uses_fresh_readback_and_never_resends(control,code,before,after):
    service,state,store=control;state['lock']=before
    original=service.bus.validated_operating_command
    def delayed(word):original(word);state['lock']=before
    service.bus.validated_operating_command=delayed
    service.execute(code,'admin',confirmed=True)
    assert service.receipt['state']=='VERIFYING_LOCK' and service.pending
    pending=service.pending;service.clock=lambda:pending.started+1
    # An older cached word claiming the desired state is not execution evidence.
    service.observe(dict(raw={60:after,2:25},quality='GOOD',register_ages={60:2}))
    assert service.pending and service.receipt['state']=='VERIFYING_LOCK'
    service.clock=lambda:pending.started+2
    service.observe(dict(raw={60:before},quality='GOOD',register_ages={60:0}))
    assert service.pending
    service.clock=lambda:pending.started+3
    service.observe(dict(raw={60:after,2:25},quality='GOOD',register_ages={60:0}))
    assert not service.pending and service.receipt['state']=='VERIFIED'
    assert service.receipt['lock_readback']==after and len(state['writes'])==1
    assert store.audit_rows()[0][4]=='VERIFIED'


@pytest.mark.parametrize('condition',['offline','stale','no_timestamp','invalid'])
def test_inconclusive_lock_verification_is_unknown_without_retries(control,condition):
    service,state,store=control;original=service.bus.validated_operating_command
    service.clock=lambda:0.0  # Exact-origin clock avoids host-uptime cancellation at the deadline.
    def delayed(code):original(code);state['lock']=0
    service.bus.validated_operating_command=delayed
    service.execute(0xF00,'admin',confirmed=True)
    pending=service.pending;service.clock=lambda:pending.started+pending.timeout
    snapshot=dict(raw={60:0},quality='GOOD',register_ages={60:0})
    if condition=='offline':snapshot['quality']='OFFLINE'
    elif condition=='stale':snapshot['register_ages'][60]=pending.timeout+1
    elif condition=='no_timestamp':snapshot['register_ages']={}
    else:snapshot['raw'][60]=0x2020
    service.observe(snapshot)
    assert service.pending is None and service.ambiguous and service.receipt['state']=='UNKNOWN'
    assert len(state['writes'])==1


def test_lock_pending_ui_identifies_register_verification_and_disables_duplicates(window):
    w=window;w.snapshot['control'].update(pending=True,pending_kind='lock')
    w.update_command_buttons()
    assert 'CAL LOCK [60]' in w.command_message.text() and not w.command_buttons[0xF00].isEnabled()
    w.show_command_receipt(dict(id='pending-lock',code=0xF00,state='VERIFYING_LOCK',reply_received=True))
    assert 'verifying CAL LOCK [60]' in w.command_proof.text()
