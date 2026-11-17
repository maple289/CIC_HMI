"""Production operator boundary; hardware tests use an in-memory FC03 adapter."""
from dataclasses import asdict,replace
from pathlib import Path
from types import SimpleNamespace
import copy,json,os,subprocess,sys
import pytest
from PySide6.QtWidgets import QPushButton,QComboBox
from prevex_hmi.devices.configuration import load_settings,save_settings,default_devices
from prevex_hmi.gui.window import MainWindow as OperatorWindow
from prevex_hmi.gui.worker import MonitoringWorker as OperatorWorker
from prevex_hmi.gui.connection_dialog import AnalyzerChoice
from prevex_hmi.simulator.bus import SimulatedBus
from prevex_hmi import runtime_policy
from test_monitoring import app,until


def close(app,w):
    w.close();until(app,lambda:not w.recording_worker.isRunning() and (not w.worker or not w.worker.isRunning()));app.processEvents()


def test_default_and_legacy_simulation_preferences_are_hardware_only_without_data_loss(app,tmp_path,monkeypatch):
    path=tmp_path/'settings.json';legacy=load_settings(path,allow_simulation=True)
    legacy['connection'].update(port='COM9',baud=9600,timeout=.7,parity='N',identification_page='alternate')
    legacy['devices'][0]['id']='preserved-id';legacy['recording']={'mode':'manual','interval':5};legacy['trend_timezone']='UTC'
    save_settings(path,legacy);db=tmp_path/'simulation.sqlite3';db.write_bytes(b'historical data must not change')
    expected=copy.deepcopy(legacy);expected['mode']='hardware'
    def forbidden(*a,**k):raise AssertionError('Startup must not open a physical port')
    monkeypatch.setattr('prevex_hmi.communication.serial_transport.ReadOnlySerialTransport.__init__',forbidden)
    result=load_settings(path);assert result==expected and json.loads(path.read_text(encoding='utf-8'))==expected
    assert db.read_bytes()==b'historical data must not change'
    w=OperatorWindow(result,path,tmp_path)
    try:
        assert w.worker is None and not w.profile_current and w.settings['mode']=='hardware'
        assert [w.connection_screen.profile.itemText(i) for i in range(4)]==['Auto Detect','LEL','BTU','FID']
        assert not hasattr(w.connection_screen,'mode')
        labels=[button.text().lower() for button in w.findChildren(QPushButton)]
        assert not any('simulat' in label or 'resume dynamic' in label for label in labels)
        assert not any(hasattr(w,n) for n in ('simulation_controls','fault_kind','forced_value','forced_status'))
        dialog=AnalyzerChoice(legacy)
        assert dialog.settings()['mode']=='hardware'
        assert not any(hasattr(dialog,n) for n in ('mode','sim_family','lel_revision','fullscale'))
        assert all('simulation' not in combo.itemText(i).lower() for combo in dialog.findChildren(QComboBox) for i in range(combo.count()))
        dialog.close()
    finally:close(app,w)
    assert load_settings(tmp_path/'new-install/settings.json')['mode']=='hardware'


def test_production_policy_cannot_enable_simulator_even_with_explicit_constructor_flag(app,tmp_path,monkeypatch):
    settings=load_settings(tmp_path/'settings.json',allow_simulation=True)
    monkeypatch.setattr(runtime_policy,'PRODUCTION',True)
    assert not runtime_policy.simulation_allowed(True)
    with pytest.raises(PermissionError):SimulatedBus([default_devices()[0]])
    with pytest.raises(ValueError):OperatorWorker(settings,tmp_path,simulation_authorized=True)
    w=OperatorWindow(settings,tmp_path/'settings.json',tmp_path,simulation_authorized=True)
    try:assert w.settings['mode']=='hardware' and not w.simulation_authorized and w.worker is None
    finally:close(app,w)


@pytest.mark.parametrize('family,assembly', [('LEL','SNR675'),('LEL','SNR705'),('BTU','SNR692'),('FID','SNR650')])
def test_hardware_pipeline_identity_readonly_inspection_and_traffic(app,tmp_path,monkeypatch,family,assembly):
    settings=load_settings(tmp_path/'settings.json');config=next(c for c in default_devices() if c.family==family)
    config=replace(config,assembly=assembly,version='7.01' if assembly=='SNR705' else config.version,address=1,interval=.25)
    settings.update(devices=[asdict(config)],analyzer_selection='Auto Detect');settings['connection'].update(port='COM9',baud=9600)
    monkeypatch.setattr('prevex_hmi.gui.serial_ports.list_ports.comports',lambda:[SimpleNamespace(device='COM9',description='Test adapter')])
    adapters=[]
    class ReadOnlyAdapter:
        physical=False  # In-memory test adapter; does not validate physical protocol applicability.
        def __init__(self,*a,**k):self.sim=SimulatedBus([config]);self.trace=lambda *a:None;self.calls=[];adapters.append(self)
        def read(self,address,pdu,count):
            self.calls.append((address,pdu,count));self.sim.trace=self.trace;return self.sim.read(address,pdu,count)
        def close(self):self.sim.close()
    monkeypatch.setattr('prevex_hmi.communication.serial_transport.ReadOnlySerialTransport',ReadOnlyAdapter)
    w=OperatorWindow(settings,tmp_path/'settings.json',tmp_path)
    try:
        assert w.worker is None
        w.connect_from_screen('connect')
        assert w.worker is not None,(w.connection_screen.note.text(),w.statusBar().currentMessage(),w.settings)
        until(app,lambda:w.snapshot is not None and w.connection_established,timeout=12)
        assert w.snapshot['source']=='hardware' and w.identity['model']==assembly
        assert w.inspect_button.text()=='Inspect register'
        w.inspect_register.setCurrentIndex(w.inspect_register.findData(18));w.inspect_button.click()
        until(app,lambda:w.inspection_result.text().startswith('Register 18:'),timeout=8)
        until(app,lambda:18 in w.snapshot['raw'])
        until(app,lambda:w.traffic.rowCount()>0)
        assert w.snapshot['raw'][18] in (0,4,7) and adapters[0].calls
        assert not adapters[0].sim.events  # No operating or setting writes.
    finally:close(app,w)


def test_protected_entry_rejects_old_simulator_flag_without_creating_operator_files(tmp_path):
    code="from prevex_hmi import runtime_policy;runtime_policy.PRODUCTION=True;from prevex_hmi.main import main;raise SystemExit(main())"
    env=os.environ.copy();env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    result=subprocess.run([sys.executable,'-c',code,'--smoke-test','--data-dir',str(tmp_path/'unused')],capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==2 and 'unrecognized arguments' in result.stderr
    assert not (tmp_path/'unused').exists()
