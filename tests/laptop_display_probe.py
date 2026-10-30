"""Full fault-layout rendering at native desktop scale times the UI preference."""
import json,sys,time
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src'),str(Path(__file__).resolve().parent)]
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication
from prevex_hmi.gui.fonts import configure_application_font,display_diagnostics
from test_command_result_layout import setup_window,flush


def run(folder,client_size=None):
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);configure_application_font(app)
    report=[]
    for theme in ('dark','light'):
        w,bus,snapshot=setup_window(folder/theme,'LEL 670 Series')
        try:
            w.settings['theme']=theme;w.apply_theme()
            w.users.create_user('operator','password8');w.session=w.users.authenticate('operator','password8')
            requests=[];w.worker=SimpleNamespace(isRunning=lambda:True,test_only=False,request=lambda *args:requests.append(args))
            snapshot['raw'].update({2:25,4:12,59:161,60:0});snapshot['register_ages'][60]=0
            snapshot['control']=dict(verified=True,pending=False,ambiguous=False)
            w.update_data(snapshot,bus.diagnostics());w.snapshot_received_at=time.monotonic();w.update_command_buttons()
            w.disconnect_button.setVisible(True)
            w.compatibility_notice.setText('Compatibility review required - see Technical Details')
            w.banner.setText('SIMULATION | Connected - identified analyzer | Commands require confirmation')
            w.identity_label.setText('Selected Profile: Auto Detect | Detected Analyzer: LEL 670 Series')
            w.gauge._set_state(replace(w.gauge.state,value=-99,reading='-99.00',minimum=-100,status='TC2 failed',color='#8290a5',status_color='#f27778'))
            if client_size:w.resize(*client_size);w.show()
            else:w.showMaximized()
            flush(app)
            viewport=w.monitor_scroll.viewport();cards=w.readout_groups['Gauges'];position=cards.mapTo(viewport,QPoint())
            first=cards.grid.itemAtPosition(0,0).widget();card_position=first.mapTo(viewport,QPoint())
            assert w.gauge.height()>=290
            assert 0<=card_position.y() and card_position.y()+first.height()<=viewport.height(),(card_position,first.size(),viewport.size())
            assert w.command_scroll.verticalScrollBar().maximum()==0
            assert not requests and w.fault_summary.text()=='Analyzer Fault Active'
            metrics=display_diagnostics(app,w)
            (folder/f'{theme}-metrics.json').write_text(json.dumps(metrics,indent=2))
            w.grab().save(str(folder/f'{theme}-fault.png'))
            assert metrics['ui_family']==metrics['raw_ui_family']=='PREVEX UI Regular'
            assert metrics['heading_family']=='PREVEX UI SemiBold' and metrics['command_family']=='PREVEX UI Bold'
            assert metrics['font_source']=='bundled'
            folder.mkdir(parents=True,exist_ok=True);w.grab().save(str(folder/f'{theme}-fault.png'))
            report.append(dict(theme=theme,**metrics,gauge=w.gauge.size().toTuple(),first_card_y=card_position.y(),first_card_height=first.height(),viewport_height=viewport.height(),command_scroll_max=w.command_scroll.verticalScrollBar().maximum()))
        finally:w.worker=None;w.close();bus.close();flush(app)
    (folder/'report.json').write_text(json.dumps(report,indent=2));return report


if __name__=='__main__':print(json.dumps(run(Path(sys.argv[1])),indent=2))
