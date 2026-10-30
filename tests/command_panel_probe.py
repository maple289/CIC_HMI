"""Subprocess-only Qt screen/command-layout probe; no serial transports."""
import copy,json,sys,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parent)]
from PySide6.QtCore import QPoint,Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QAbstractSlider
from test_command_result_layout import setup_window,flush
from prevex_hmi.gui.profile_library import PROFILE_CHOICES


def run(folder):
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    from prevex_hmi.gui.fonts import configure_application_font
    configure_application_font(app)
    screen=app.primaryScreen();results=[]
    def check(condition,detail):
        if not condition:raise AssertionError(detail)
    for profile in PROFILE_CHOICES:
        data=folder/profile.replace(' ','-');data.mkdir(parents=True,exist_ok=True)
        w,bus,snapshot=setup_window(data,profile)
        w.users.create_user('operator','password8');w.session=w.users.authenticate('operator','password8')
        sent=[];w.worker=SimpleNamespace(isRunning=lambda:True,test_only=False,request=lambda *message:sent.append(message))
        w.snapshot['raw'][60]=0;w.snapshot['raw'][27]=0;w.snapshot['register_ages'].update({60:0,27:0})
        def ready():
            w.snapshot_received_at=time.monotonic()
            w.command_dispatching=False;w.queued_command_id=None
            w.snapshot['control']=dict(verified=True,pending=False,ambiguous=False)
            w.update_command_buttons();flush(app)
        def geometry():
            return [(id(b),b.mapTo(w,QPoint()).toTuple(),b.size().toTuple(),b.button.size().toTuple(),b.led.mapTo(w,QPoint()).toTuple()) for b in dict.fromkeys(w.command_buttons.values())]
        try:
            w.show();flush(app)
            for theme in ('dark','light'):
                w.settings['theme']=theme;w.apply_theme();ready()
                available=screen.availableGeometry()
                w.showNormal();w.resize(max(1100,min(1280,available.width()-40)),max(600,min(900,available.height()-70)));flush(app)
                windowed_size=None;windowed_geometry=None
                for mode in ('windowed','maximized','restored'):
                    if mode=='maximized':w.showMaximized();flush(app)
                    elif mode=='restored':w.showNormal();flush(app)
                    ready();bar=w.command_scroll.verticalScrollBar();bar.setValue(0);flush(app)
                    viewport=w.command_scroll.viewport();header=w.role_label.mapTo(w,QPoint());panel=w.command_panel.mapTo(w,QPoint())
                    check(w.height()<=available.height(),('window larger than work area',w.size(),available))
                    check(w.command_scroll.horizontalScrollBar().maximum()==0,'Horizontal command clipping')
                    baseline=geometry();offset=bar.value();size=w.size();left_offset=w.monitor_scroll.verticalScrollBar().value()
                    if mode=='windowed':windowed_size=size;windowed_geometry=baseline
                    elif mode=='restored':check(size==windowed_size and baseline==windowed_geometry,'Restored window did not recover button geometry')
                    button=w.command_buttons[0x100].button;check(button.isEnabled(),('ACK disabled',profile))
                    QTest.mousePress(button,Qt.LeftButton);flush(app);check(geometry()==baseline,'Mouse-down changed geometry')
                    with patch('prevex_hmi.gui.window.confirm_command',return_value=True):QTest.mouseRelease(button,Qt.LeftButton)
                    flush(app)
                    check(sent and sent[-1][0:2]==('command',0x100),'Confirmed UI request missing')
                    check(bar.value()==offset and geometry()==baseline,('Focus-disable jump',profile,theme,mode,offset,bar.value()))
                    for index,state in enumerate(('SENT_UNVERIFIED','EFFECT_OBSERVED','NOT_VERIFIED','UNKNOWN','REJECTED')):
                        w.show_command_receipt(dict(id=f'{theme}-{mode}-{index}',code=0x100,state=state,reply_received=state not in ('UNKNOWN','REJECTED'),detail='Long simulated command feedback. '*100))
                        w.command_message.setText('Long simulated STATUS explanation. '*150)
                        w.statusBar().showMessage('Long simulated status-bar feedback. '*100)
                        for b in dict.fromkeys(w.command_buttons.values()):b.setEnabled(index%2==0)
                        flush(app)
                        check(w.size()==size and geometry()==baseline and bar.value()==offset,('Feedback changed geometry',state))
                    for b in dict.fromkeys(w.command_buttons.values()):b.reset()
                    flush(app);check(geometry()==baseline,'LED expiry changed geometry')
                    ready();check(geometry()==baseline and bar.value()==offset,'Unlock changed geometry')
                    if bar.maximum():
                        bar.triggerAction(QAbstractSlider.SliderToMaximum);flush(app)
                        last=w.command_buttons[0xF00];point=last.mapTo(viewport,QPoint())
                        check(point.y()>=0 and point.y()+last.height()<=viewport.height(),'CAL LOCK not reachable')
                        check(header==w.role_label.mapTo(w,QPoint()) and panel==w.command_panel.mapTo(w,QPoint()),'Header moved with scrollbar')
                        bar.setValue(0);target=[b.button for b in dict.fromkeys(w.command_buttons.values()) if b.isEnabled()][-1]
                        w.command_buttons[0x100].button.setFocus(Qt.TabFocusReason);flush(app)
                        reached=False
                        for _ in range(12):
                            if target.hasFocus():reached=True;break
                            QTest.keyClick(QApplication.focusWidget(),Qt.Key_Tab);flush(app)
                        position=target.mapTo(viewport,QPoint())
                        check(reached and position.y()>=0 and position.y()+target.height()<=viewport.height(),('Keyboard navigation cannot reveal lower commands',profile,theme,mode,position,target.text(),bar.value()))
                    else:
                        for b in dict.fromkeys(w.command_buttons.values()):
                            point=b.mapTo(viewport,QPoint());check(0<=point.y() and point.y()+b.height()<=viewport.height(),'Button cropped without scrollbar')
                    check(w.monitor_scroll.verticalScrollBar().value()==left_offset,'Command list scrolled main measurements')
                    bar.setValue(0);ready();w.grab().save(str(data/f'{theme}-{mode}.png'))
                    results.append(dict(profile=profile,theme=theme,mode=mode,window=w.size().toTuple(),rows_height=w.command_scroll.widget().height(),viewport_height=viewport.height(),scroll_max=bar.maximum(),stable=True))
            # Exercise the real three-second timer once per physical screen.
            if profile==PROFILE_CHOICES[0]:
                before=geometry();w.command_buttons[0x100].feedback(True)
                check(w.command_buttons[0x100].timer.interval()==3000,'LED duration changed')
                QTest.qWait(3100);flush(app)
                check(not w.command_buttons[0x100].timer.isActive() and geometry()==before,'Timed LED expiry moved buttons')
        finally:
            w.worker=None;w.close();bus.close();flush(app)
            deadline=time.monotonic()+5
            while w.recording_worker.isRunning() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    return dict(physical_access=False,screen=screen.geometry().getRect(),dpr=screen.devicePixelRatio(),cases=results)


if __name__=='__main__':
    directory=Path(sys.argv[1]);directory.mkdir(parents=True,exist_ok=True)
    result=run(directory);(directory/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps(dict(cases=len(result['cases']),screen=result['screen'],dpr=result['dpr'],physical_access=False)))
