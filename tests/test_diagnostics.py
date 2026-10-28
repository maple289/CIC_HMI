"""Exercise live Qt navigation/refresh in a bounded subprocess.

An event-loop stall must fail rather than hang the entire pytest process.
"""
from pathlib import Path
import os
import subprocess
import sys


def test_diagnostics_refresh_does_not_starve_navigation_or_timers(tmp_path):
    code=r'''
import sys,time,json
from pathlib import Path
from dataclasses import asdict
from PySide6.QtCore import QTimer,Qt,QEventLoop
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from prevex_hmi.devices.configuration import load_settings
from prevex_hmi.devices.models import DeviceConfig,DeviceState,utc_now
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.simulator.bus import SimulatedBus
from prevex_hmi.communication.engine import BusEngine
app=QApplication([])
app.setQuitOnLastWindowClosed(False)
font=QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
if font>=0:app.setFont(QFont(QFontDatabase.applicationFontFamilies(font)[0],10))
folder=Path(sys.argv[1]);settings=load_settings(folder/'settings.json')
w=MainWindow(settings,folder/'settings.json',folder,start_worker=False)
w.resize(1100,780);w.show();app.processEvents()
config=DeviceConfig(**settings['devices'][0])
transport=SimulatedBus([config]);bus=BusEngine(transport)
device=transport.devices[1];device.update(time.monotonic())
state=DeviceState(config,raw=device.raw.copy(),online=True,last_success=time.monotonic(),last_success_utc=utc_now())
data=state.snapshot(time.monotonic());diagnostics=bus.diagnostics()
w.identification_result(dict(config=data['config'],family=config.family,model=config.assembly,version=config.version,verified=True,communication_ok=True,loaded_profile='LEL 700 Series'))
updates=[];beats=[]
def refresh():
    frame=len(updates)
    diagnostics['traffic']=[dict(time=str(frame+i),direction='RX',address=1,register=1,hex='01 03 FE '+'12 34 '*127) for i in range(100)]
    w.update_data(data,diagnostics);updates.append(time.monotonic())
refresh()
QTest.mouseClick(w.navigation.viewport(),Qt.LeftButton,pos=w.navigation.visualItemRect(w.navigation.item(2)).center())
assert w.pages.currentIndex()==4
timer=QTimer();timer.timeout.connect(refresh);timer.start(40)
heartbeat=QTimer();heartbeat.timeout.connect(lambda:beats.append(time.monotonic()));heartbeat.start(20)
loop=QEventLoop();QTimer.singleShot(2500,loop.quit);loop.exec()
timer.stop();heartbeat.stop()
gap=max((b-a for a,b in zip(beats,beats[1:])),default=99)
assert len(updates)>=20 and len(beats)>=20 and gap<1.5,(len(updates),len(beats),gap)
assert w.traffic.rowCount()==100
QTest.mouseClick(w.navigation.viewport(),Qt.LeftButton,pos=w.navigation.visualItemRect(w.navigation.item(0)).center())
assert w.pages.currentIndex()==0
w.invalidate();assert w.traffic.rowCount()==0
w.update_data(data,diagnostics);assert w.traffic.rowCount()==100
print(json.dumps(dict(updates=len(updates),heartbeat_gap=gap)))
bus.close();w.close()
'''
    environment=os.environ.copy()
    environment['QT_QPA_PLATFORM']='offscreen'
    environment['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path)],env=environment,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
