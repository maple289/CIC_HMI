"""Wall-clock Qt timing and transport scenarios, strictly simulated."""
from dataclasses import asdict
import time
import pytest
from prevex_hmi.devices.configuration import load_settings,default_devices
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.gui.worker import MonitoringWorker
from prevex_hmi.simulator.bus import SimulatedBus
from test_monitoring import app,until


@pytest.mark.parametrize('code',[0x100,0x200])
@pytest.mark.parametrize('scenario',['normal','resettable','persistent','delayed','no_response','communication_loss'])
def test_short_command_release_is_independent_of_effect_and_led(app,tmp_path,monkeypatch,code,scenario):
    writes=[];replies=[];active=[None]
    class ScenarioBus(SimulatedBus):
        def read(self,address,pdu,count):
            words=super().read(address,pdu,count)
            status,relays=(0,128) if scenario=='normal' else (1,9) if scenario=='resettable' else (25,12)
            if scenario=='resettable' and writes:status,relays=(0,0) if code==0x200 else (1,1)
            for i in range(count):
                if pdu+1+i==2:words[i]=status
                elif pdu+1+i==4:words[i]=relays
                elif pdu+1+i==59:words[i]=0
            return words
        def command(self,*args,**kwargs):
            writes.append(time.monotonic())
            if scenario=='delayed':time.sleep(.6)
            value=super().command(*args,**kwargs)
            if scenario=='no_response':raise TimeoutError('Injected lost acknowledgment after a single write')
            replies.append(time.monotonic());return value
    def factory(devices):active[0]=ScenarioBus(devices);return active[0]
    monkeypatch.setattr('prevex_hmi.gui.worker.SimulatedBus',factory)
    monkeypatch.setattr('prevex_hmi.gui.window.confirm_command',lambda *a,**kw:True)
    settings=load_settings(tmp_path/'settings.json');settings.update(analyzer_selection='LEL 670 Series',simulated_lel_revision='legacy',devices=[asdict(default_devices()[0])]);settings['devices'][0]['interval']=.25
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=True);w.show()
    try:
        until(app,lambda:w.profile_current and w.snapshot and 60 in w.snapshot['raw'])
        w.users.create_user('operator','password8');w.session=w.users.authenticate('operator','password8');w.update_command_buttons()
        button=w.command_buttons[code];assert button.isEnabled();button.button.click()
        for _ in range(5):button.button.click()  # Disabled UI must not enqueue repeats.
        until(app,lambda:bool(writes))
        if scenario=='no_response':
            until(app,lambda:w.snapshot['control'].get('ambiguous'))
            assert not any(b.isEnabled() for b in w.command_buttons.values()) and not replies
            assert len(writes)==1;return
        until(app,lambda:bool(replies))
        if scenario=='communication_loss':
            w.request('fault','timeout');until(app,lambda:not w.profile_current)
            assert not any(b.isEnabled() for b in w.command_buttons.values()) and len(writes)==1;return
        until(app,lambda:button.isEnabled(),timeout=3)
        assert time.monotonic()-replies[0]<1.8
        assert button.timer.isActive() and button.timer.interval()==3000
        assert not w.snapshot['control']['pending'] and not w.snapshot['control']['temporary_busy']
        if scenario!='resettable':assert w.snapshot['control']['effect_pending']
        assert len(writes)==1
        stages=[r['stage'] for r in w.command_timing.events if r.get('request_id')==w.snapshot['control']['receipt']['id']]
        assert all(stage in stages for stage in ('BUTTON_CLICKED','CONFIRMATION_ACCEPTED','QUEUED','DEQUEUED','TRANSMISSION_STARTED','RESPONSE_RECEIVED','LED_ACTIVATED','VERIFICATION_STARTED','UI_LOCK_RELEASED','BUTTON_ENABLED'))
    finally:
        w.close();until(app,lambda:not w.worker.isRunning() and not w.recording_worker.isRunning() and not w.record_jobs)


def test_operator_queue_priority_does_not_drop_fifo_or_bypass_execution(tmp_path):
    settings=load_settings(tmp_path/'settings.json');worker=MonitoringWorker(settings,tmp_path)
    worker.request('history',24);worker.request('inspect',9)
    worker.request('command',0x100,'untrusted-token',True);worker.request('command',0x200,'untrusted-token',True)
    messages=[worker.messages.get_nowait()[2] for _ in range(4)]
    assert [m[0] for m in messages]==['command','command','history','inspect']
    assert [m[1] for m in messages[:2]]==[0x100,0x200] and not worker.isRunning()
