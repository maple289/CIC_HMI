"""Replay real-controller observations; automated tests never open COM4."""
from dataclasses import asdict,replace
import os,struct,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from prevex_hmi.devices.configuration import load_settings,default_devices
from prevex_hmi.devices.identification import parse_identity,resolve_profile
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.communication.hardware_session import ReadOnlyControllerGrant
from prevex_hmi.communication.protocol import frame,validate_read
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.profiles import profile_for,commands_for
from prevex_hmi.gui.presentation import measurement

IDENTITY=b'TYPE FTAVER 4\xa781 SNR671'.ljust(32,b' ')
RAW={1:32769,2:25,3:100,4:4,5:10240,6:12800,7:15360,9:63548,11:0,15:0,23:815,24:246,28:1,29:2047,30:512,38:0,39:32769,42:1226,43:15360,50:27136,51:11577,52:14624,53:9548,54:17996,55:8224,56:512,59:161}


def settings_for(path):
    settings=load_settings(path)
    settings.update(mode='hardware',analyzer_selection='Auto Detect')
    settings['connection'].update(port='COM4',baud=9600)
    settings['devices']=[asdict(replace(default_devices()[0],assembly='SNR671',version='4.81',interval=.5))]
    return settings


def test_fta_identity_is_lel_without_claiming_verified_version():
    identity=parse_identity(IDENTITY.decode('latin-1'))
    assert identity.family=='LEL' and identity.model=='SNR671' and identity.version=='4.81'
    assert identity.legacy_format and identity.warning and not identity.verified
    config,warning,controls=resolve_profile(default_devices()[0],'Auto Detect',identity)
    assert config.register_profile=='fta_4x' and warning and not controls
    assert profile_for(config).revision=='fta_4x' and not commands_for(config)
    for number in (8,40,57,60,62,1281):
        with pytest.raises((ValueError,PermissionError)):validate_read(profile_for(config),number,1)
    assert parse_identity('TYPE FTAVER 4\xa781 SNR671 BTU').family is None


def test_fault_word_uses_current_lcd_but_never_clamps_normal_negative_measurements():
    config=replace(default_devices()[0],assembly='SNR671',version='4.81',register_profile='fta_4x')
    snapshot=dict(config=asdict(config),raw=dict(RAW),quality='GOOD')
    assert measurement(snapshot,1)[0]==-99
    snapshot['register_ages']={51:100}
    assert measurement(snapshot,1)[0] is None
    snapshot['register_ages']={};snapshot['raw'][51]=0
    assert measurement(snapshot,1)[0] is None
    snapshot['raw'][2]=0;snapshot['raw'][4]=0
    assert float(measurement(snapshot,1)[0])==pytest.approx(-127.99609375)


@pytest.mark.parametrize('field,value',[('port','COM5'),('baud',19200),('identification_page','alternate')])
def test_grant_rejects_unapproved_connection_before_opening(tmp_path,field,value):
    settings=settings_for(tmp_path/'settings.json');settings['connection'][field]=value
    with pytest.raises(PermissionError):ReadOnlyControllerGrant().validate(settings,DeviceConfig(**settings['devices'][0]))


@pytest.mark.parametrize('operator_commands',[False,True])
def test_hardware_gui_replays_real_signals_and_blocks_injection_and_commands(tmp_path,monkeypatch,operator_commands):
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    class Replay:
        physical=True
        def __init__(self,*args,**kwargs):
            assert args[0]=='COM4' and kwargs['baud']==9600
            self.trace=lambda *_:None;self.calls=[];self.closed=False
        def read(self,address,pdu,count):
            assert address==1
            self.calls.append((address,pdu,count))
            self.trace(True,frame(struct.pack('>BBHH',address,3,pdu,count)))
            raw=dict(RAW)
            raw.update({257+i//2:int.from_bytes(IDENTITY[i:i+2],'big') for i in range(0,32,2)})
            values=[raw.get(n,0) for n in range(pdu+1,pdu+1+count)]
            self.trace(False,frame(bytes((address,3,count*2))+struct.pack(f'>{count}H',*values)))
            return values
        def close(self):self.closed=True
    instances=[]
    def factory(*args,**kwargs):
        result=Replay(*args,**kwargs);instances.append(result);return result
    monkeypatch.setattr('prevex_hmi.gui.window.require_available_port',lambda _:None)
    monkeypatch.setattr('prevex_hmi.communication.serial_transport.ReadOnlySerialTransport',factory)
    monkeypatch.setattr('prevex_hmi.communication.serial_transport.ControllerBenchTransport',factory)
    settings=settings_for(tmp_path/'settings.json')
    w=MainWindow(settings,tmp_path/'settings.json',tmp_path,hardware_grant=ReadOnlyControllerGrant(operator_commands=operator_commands));w.show()
    def wait(condition):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            app.processEvents()
            if condition():return
            time.sleep(.01)
        pytest.fail('Timed out waiting for replay worker')
    try:
        wait(lambda:w.snapshot is not None and all(n in w.snapshot['raw'] for n in RAW))
        assert w.snapshot['source']=='hardware' and w.snapshot['instrument_quality']=='INSTRUMENT_FAULT'
        assert w.snapshot['config']['register_profile']=='fta_4x'
        assert 'Connection Established' in w.monitor_status.text() and '-99 %LFL' in w.controller_display.text()
        assert measurement(w.snapshot,5)[0]==40 and measurement(w.snapshot,6)[0]==50
        assert measurement(w.snapshot,50)[0]==106
        assert measurement(w.snapshot,1)[0]==-99 and w.gauge.state.reading=='-99.00'
        assert w.gauge.state.minimum==-100 and 'LCD51' in w.readout_names[1].text()
        assert all(not b.isEnabled() for b in w.command_buttons.values())
        if operator_commands:
            w.users.create_user('admin','bench-test-password')
            w.session=w.users.authenticate('admin','bench-test-password');w.update_command_buttons()
            assert {code for code,button in w.command_buttons.items() if button.isEnabled()}=={0x100,0x200}
            w.show_command_receipt(dict(code=0x100,state='NO_STATE_CHANGE',reply_received=True,before=dict(status=25,relays=4,service=161),after=dict(status=25,relays=4,service=161)))
            assert 'Controller replied' in w.command_proof.text() and 'Reply received: YES' in w.command_proof.text()
            assert 'STATUS: 25 → 25' in w.command_proof.text()
        assert all(not b.isEnabled() for b in w.simulation_controls)
        assert (tmp_path/'hardware.sqlite3').exists() and not (tmp_path/'simulation.sqlite3').exists()
        w.worker.request('reading',42)
        wait(lambda:'Simulation injection' in w.command_message.text() or 'Simulation injection' in w.statusBar().currentMessage())
        assert w.snapshot['raw'][1]==32769
        assert len(instances)==1 and all(pdu+1 not in (8,40,57,60,62) for _,pdu,_ in instances[0].calls)
    finally:
        w.close();wait(lambda:not w.worker.isRunning());app.processEvents()
    assert instances[0].closed
