"""Simulated wall-clock command latency probe; never opens serial ports."""
import os,sys,time,json,argparse
from pathlib import Path
from unittest.mock import patch
os.environ['QT_QPA_PLATFORM']='offscreen';sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication,QMessageBox
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.devices.configuration import load_settings,default_devices
from prevex_hmi.simulator.bus import SimulatedBus
from prevex_hmi.communication.commands import CommandController
from dataclasses import asdict


def run(folder,code):
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False);events=[];origin=time.monotonic();started=[False]
    def mark(stage,**detail):
        if started[0]:events.append(dict(stage=stage,monotonic=time.monotonic(),**detail))
    class ProbeBus(SimulatedBus):
        def read(self,address,pdu,count):
            words=super().read(address,pdu,count)
            for i in range(count):
                n=pdu+1+i
                if n==2:words[i]=0
                elif n==4:words[i]=128
                elif n==59:words[i]=0
            return words
        def command(self,*args,**kwargs):
            mark('tx_started');result=super().command(*args,**kwargs);mark('response_received');return result
    record=CommandController.record;watch=CommandController.watch_effect
    def recorded(self,actor,c,result,detail):
        if result in ('NOT_VERIFIED','EFFECT_OBSERVED','UNKNOWN','FAILED'):mark('verification_completed',state=result)
        return record(self,actor,c,result,detail)
    def watching(self,*args,**kwargs):mark('verification_started');return watch(self,*args,**kwargs)
    folder.mkdir(parents=True,exist_ok=True);settings=load_settings(folder/'settings.json');settings.update(mode='simulation',analyzer_selection='LEL 670 Series',simulated_family='LEL',simulated_lel_revision='legacy',devices=[asdict(default_devices()[0])]);settings['devices'][0]['interval']=.25
    with patch('prevex_hmi.gui.worker.SimulatedBus',ProbeBus),patch.object(CommandController,'record',recorded),patch.object(CommandController,'watch_effect',watching),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):
        w=MainWindow(settings,folder/'settings.json',folder,start_worker=True);w.show()
        deadline=time.monotonic()+12
        while not (w.profile_current and w.snapshot and 60 in w.snapshot['raw']):
            app.processEvents();time.sleep(.005)
            if time.monotonic()>deadline:raise RuntimeError('Simulator startup timed out')
        if not w.users.has_users():w.users.create_user('probe','password8')
        w.session=w.users.authenticate('probe','password8');w.update_command_buttons()
        request=w.worker.request
        def queued(*args):mark('queued');return request(*args)
        w.worker.request=queued
        feedback=w.command_buttons[code].feedback
        def led(accepted):mark('led_activated',accepted=accepted);return feedback(accepted)
        w.command_buttons[code].feedback=led
        started[0]=True;origin=time.monotonic();mark('clicked');w.command_buttons[code].button.click()
        prior={c:False for c in w.command_buttons};released=False;done_at=None;deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            app.processEvents()
            for c,b in w.command_buttons.items():
                enabled=b.isEnabled()
                if enabled and not prior[c]:mark('button_enabled',code=c)
                prior[c]=enabled
            enabled=bool(w.command_buttons[0x100].isEnabled() and w.command_buttons[0x200].isEnabled())
            if enabled!=released:mark('global_lock_released' if enabled else 'global_lock_acquired');released=enabled
            if any(e['stage']=='verification_completed' for e in events):
                if done_at is None:done_at=time.monotonic()
                if time.monotonic()-done_at>.4:break
            time.sleep(.005)
        w.close();deadline=time.monotonic()+5
        while (w.worker.isRunning() or w.recording_worker.isRunning() or w.record_jobs) and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
    for e in events:e['elapsed_ms']=round((e.pop('monotonic')-origin)*1000,2)
    return dict(code=f'0x{code:04X}',mode='simulation',events=events,physical_access=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    results=[run(args.output.parent/f'{args.output.stem}-{code:x}',code) for code in (0x100,0x200)]
    args.output.write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
