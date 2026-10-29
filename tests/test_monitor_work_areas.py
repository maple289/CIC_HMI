"""Operator layout and command effects use isolated snapshots; no serial port."""
from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace
import copy
import pytest
from prevex_hmi.communication.commands import CommandController
from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.gui.command_status import command_status
from prevex_hmi.gui.gauge import gauge_state
from prevex_hmi.gui.presentation import measurement,monitor_condition
from test_command_result_layout import setup_window,flush
from test_monitoring import app


def test_monitor_service_diagnostics_and_collapsed_details(app,tmp_path):
    w,bus,snap=setup_window(tmp_path,'LEL 670 Series');w.show();flush(app)
    try:
        assert [w.navigation.item(i).text() for i in range(w.navigation.count())]==['Monitor','Service','Diagnostics']
        assert w.navigation.width()==122 and not w.technical_details.isVisibleTo(w)
        snap=copy.deepcopy(snap);snap['source']='hardware';snap['raw'].update({1:2560,2:25,4:4,38:25600,39:0x8001})
        w.update_data(snap,bus.diagnostics());flush(app)
        assert w.fault_summary.text()=='Analyzer Fault Active'
        assert w.gauge.state.value==10 and w.gauge.state.color=='#39c6a4'
        assert w.connection_established and 'Established' in w.monitor_status.text()
        assert '0x8001' in w.diagnostics_technical.text() and not w.controller_display.isVisibleTo(w)
        w.technical_toggle.click();flush(app)
        assert w.controller_display.isVisibleTo(w) and w.navigation.currentRow()==0
        w.technical_toggle.click();w.navigation.setCurrentRow(1);flush(app)
        assert w.pages.currentIndex()==6 and w.readout_groups['Calibration parameters'].isVisibleTo(w)
        assert not w.readout_groups['Gauges'].isVisibleTo(w)
        w.navigation.setCurrentRow(0);w.show_diagnostics('Command audit');flush(app)
        assert w.navigation.currentRow()==2 and w.diagnostics_tabs.tabText(w.diagnostics_tabs.currentIndex())=='Command audit'
        assert w.command_proof.isVisibleTo(w) and w.audit_table.isVisibleTo(w)
        rows=[('2026-10-28','unit','operator',0x200,'UNKNOWN','No valid command acknowledgment received. Lost reply'),('2026-10-28','unit','operator',0x200,'NOT_VERIFIED','Acknowledgment received; no effect')]
        w.fill_command_audit(rows)
        assert 'No valid' in w.audit_table.item(0,4).text() and 'acknowledgment received' in w.audit_table.item(1,4).text()
        receipt=dict(id='original',code=0x200,state='SENT_UNVERIFIED',reply_received=True)
        w.show_command_receipt(receipt);w.parameter_feedback('fresh simulated FC03 readback verified')
        w.show_command_receipt(receipt)
        assert 'Setting change verified' in w.last_command.text()
        w.navigation.setCurrentRow(0);assert not w.command_proof.isVisibleTo(w)
        w.worker_error('Serial connection lost')
        assert w.operational_warning.isVisibleTo(w) and 'Serial connection lost' in w.operational_warning.text()
        assert not w.technical_details.isVisibleTo(w)
    finally:w.close();bus.close();flush(app)


def test_peak_low_conversion_preserved_pending_firmware_evidence():
    config=default_devices()[0]
    data=dict(config=asdict(config),raw={39:0x8001},quality='GOOD')
    assert measurement(data,39)==(Decimal('-127.99609375'),'%LFL')


@pytest.mark.parametrize('status,relays,quality,expected',[
    (0,0,'GOOD','Normal Operation'),(25,0,'GOOD','Analyzer Fault Active'),
    (0,4,'GOOD','Analyzer Fault Active'),(4,0,'GOOD','Calibration in Progress'),
    (0,0,'OFFLINE','Communication Lost'),(1,1,'GOOD','Process Alarm Active')])
def test_fault_summary_does_not_invalidate_measurements(status,relays,quality,expected):
    config=default_devices()[0]
    data=dict(config=asdict(config),raw={1:2560,2:status,3:100,4:relays,5:25*256,6:50*256},quality=quality,age=0)
    before=copy.deepcopy(data)
    assert monitor_condition(data)[1]==expected and data==before
    if quality=='GOOD':assert gauge_state(data).value==10 and gauge_state(data).color=='#39c6a4'
    else:assert measurement(data)[0] is None
    if relays==4:assert gauge_state(data).status=='Analyzer Fault Active'


def effect_controller(code=0x200,before=None):
    audit=[];now=[0.0];config=default_devices()[0]
    c=CommandController(SimpleNamespace(),config,SimpleNamespace(command_audit=lambda *row:audit.append(row)),None,clock=lambda:now[0])
    c.receipt=dict(id='test',code=code,state='SENT_UNVERIFIED',reply_received=True)
    c.watch_effect('operator',code,before or {2:25,4:4})
    return c,now,audit


def test_reset_normal_alone_and_cached_precommand_samples_are_not_proof():
    c,now,audit=effect_controller();now[0]=2
    c.observe(dict(raw={2:0,4:4},quality='GOOD',register_ages={2:0,4:0}))
    assert c.effect and not audit
    c.observe(dict(raw={2:0,4:0},quality='GOOD',register_ages={2:3,4:3}))
    assert c.effect and not audit
    c.observe(dict(raw={2:0,4:0},quality='GOOD',register_ages={2:0,4:0}))
    assert c.effect is None and c.receipt['state']=='EFFECT_OBSERVED'
    assert 'RELAYS 0004 -> 0000' in audit[-1][-1]


def test_acknowledged_timeout_is_distinct_from_missing_ack_and_later_normal():
    c,now,audit=effect_controller();now[0]=8
    c.observe(dict(raw={2:0,4:4},quality='GOOD',register_ages={2:0,4:0}))
    assert c.receipt['state']=='NOT_VERIFIED' and not c.ambiguous
    assert 'Acknowledgment received' in audit[-1][-1]
    c.observe(dict(raw={2:0,4:0},quality='GOOD',register_ages={2:0,4:0}))
    assert c.receipt['state']=='NOT_VERIFIED'
    c.receipt['reply_received']=False;c.record('operator',0x200,'UNKNOWN','Lost write reply')
    assert 'No valid command acknowledgment' in audit[-1][-1]


def test_acknowledge_horn_effect_and_communication_loss():
    c,now,audit=effect_controller(0x100,{2:25,4:12});now[0]=1
    c.observe(dict(raw={2:25,4:4},quality='GOOD',register_ages={2:0,4:0}))
    assert c.receipt['state']=='EFFECT_OBSERVED' and 'STATUS 25 -> 25' in audit[-1][-1]
    c,now,audit=effect_controller();c.observe(dict(raw={},quality='OFFLINE'))
    assert c.receipt['state']=='UNKNOWN' and c.ambiguous and c.effect is None


def test_service_effect_requires_fresh_documented_flags_and_deadline():
    c,now,audit=effect_controller(0x100,{2:25,4:4,59:0x21});now[0]=1
    c.observe(dict(raw={2:25,4:4,59:0},quality='GOOD',register_ages={2:0,4:0,59:2}))
    assert c.effect
    c.observe(dict(raw={2:25,4:4,59:0x20},quality='GOOD',register_ages={2:0,4:0,59:0}))
    assert c.receipt['state']=='EFFECT_OBSERVED'
    c,now,audit=effect_controller(0x100,{2:25,4:4,59:0x20});now[0]=1
    c.observe(dict(raw={2:25,4:4,59:0},quality='GOOD',register_ages={2:0,4:0,59:0}))
    assert c.effect  # CHK RDNG disappearing alone does not prove acknowledgment.
    c,now,audit=effect_controller();now[0]=9
    c.observe(dict(raw={2:0,4:0},quality='GOOD',register_ages={2:0,4:0}))
    assert c.receipt['state']=='NOT_VERIFIED'


def test_distinct_outcome_icons_and_labels():
    verified=command_status(dict(state='EFFECT_OBSERVED',reply_received=True))
    acknowledged=command_status(dict(state='SENT_UNVERIFIED',reply_received=True))
    missing=command_status(dict(state='UNKNOWN',reply_received=False))
    unverified=command_status(dict(state='NOT_VERIFIED',reply_received=True))
    assert len({verified[0],acknowledged[0],missing[0]})==3
    assert 'effect verified' in verified[1] and 'acknowledged' in acknowledged[1]
    assert 'No valid' in missing[1] and 'acknowledgment received' in unverified[1]


def test_effect_cannot_cross_analyzer_profiles():
    c,now,audit=effect_controller();now[0]=1
    other=asdict(c.config);other['id']='other'
    c.observe(dict(config=other,raw={2:0,4:0},quality='GOOD',register_ages={2:0,4:0}))
    assert c.receipt['state']=='UNKNOWN' and c.ambiguous and 'profile changed' in audit[-1][-1]


def test_new_command_ends_prior_observer_without_overwriting_its_receipt():
    c,now,audit=effect_controller();previous=c.receipt
    current=dict(id='new-command',code=0x100,state='CHECKING',reply_received=False)
    c.receipt=current;c.end_previous_effect()
    assert c.receipt is current and current['state']=='CHECKING'
    assert previous['state']=='NOT_VERIFIED' and c.effect is None
    assert audit[-1][2:4]==(0x200,'NOT_VERIFIED')
    now[0]=1;c.observe(dict(raw={2:0,4:0},quality='GOOD',register_ages={2:0,4:0}))
    assert previous['state']=='NOT_VERIFIED' and not c.ambiguous


def test_old_control_receipts_cannot_replay_led_or_unlock_queued_action(app,tmp_path):
    w,bus,snap=setup_window(tmp_path,'LEL 670 Series')
    try:
        old=dict(id='old',code=0x100,state='SENT_UNVERIFIED',reply_received=True)
        new=dict(id='new',code=0x200,state='SENDING',reply_received=False)
        button=w.command_buttons[0x100]
        w.show_command_receipt(old);assert button.timer.isActive();button.timer.stop()
        w.show_command_receipt(new);w.show_command_receipt(old)
        assert not button.timer.isActive()
        w.queued_command_id='new';w.command_dispatching=True
        w.command_control_update(dict(receipt=old,verified=True,transmitting=False))
        assert w.command_dispatching and w.queued_command_id=='new'
        assert not w.command_buttons[0x200].isEnabled() and not button.timer.isActive()
        w.command_control_update(dict(receipt={**new,'state':'REJECTED'},verified=True,transmitting=False))
        assert not w.command_dispatching and w.queued_command_id is None
    finally:w.close();bus.close();flush(app)


@pytest.mark.parametrize('condition',['stale','undocumented_status','missing_relays'])
def test_effect_deadline_without_fresh_verification_keeps_global_lock(condition):
    c,now,audit=effect_controller();now[0]=8
    snapshot=dict(raw={2:25,4:4},quality='GOOD',register_ages={2:0,4:0})
    if condition=='stale':snapshot['register_ages']={2:9,4:9}
    elif condition=='undocumented_status':snapshot['raw'][2]=0x2020
    else:del snapshot['raw'][4]
    c.observe(snapshot)
    assert c.ambiguous and c.effect is None and c.receipt['state']=='UNKNOWN'
    assert 'No fresh post-command' in audit[-1][-1]
