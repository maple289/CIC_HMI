"""Compact indicator ordering and provenance across supported profiles."""
from dataclasses import asdict
import copy
import pytest
from PySide6.QtWidgets import QLabel
from prevex_hmi.gui.indicators import IndicatorPanel,presentation
from prevex_hmi.gui.profile_library import library_config
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.devices.configuration import load_settings
from test_monitoring import app


@pytest.mark.parametrize('name',['LEL 670 Series','LEL 700 Series','BTU','FID'])
def test_faults_alarms_service_then_operation_one_row_with_individual_freshness(app,name):
    config=library_config(name);panel=IndicatorPanel();panel.resize(400,50);panel.show()
    data=dict(config=asdict(config),raw={2:26,4:0xffff,59:0xffff},quality='GOOD',register_ages={2:0,4:0,59:0})
    panel.update_snapshot(data);app.processEvents()
    priorities=[presentation(g,k,panel.labels[(g,k)][1])[0] for g,k in panel.active_order]
    assert priorities==sorted(priorities) and priorities[0]==0 and priorities[-1]==3
    assert panel.labels[panel.active_order[0]][1]=='Flameout'
    visible=[panel.labels[key][0] for key in panel.active_order]
    assert len({label.geometry().y() for label in visible})==1 and panel.height()==50
    assert panel.scroll.horizontalScrollBar().maximum()>0
    assert not panel.summary.isVisibleTo(panel)
    assert 'STATUS [2]' in panel.labels[(0,26)][0].toolTip()
    assert 'Fault relay' in next(l.toolTip() for (g,k),(l,t) in panel.labels.items() if g==1 and t=='Fault')
    if name=='FID':assert not any(g==2 for g,k in panel.active_order)
    data['register_ages'][4]=100;panel.update_snapshot(data)
    assert not any(g==1 for g,k in panel.active_order) and (0,26) in panel.active_order
    data['quality']='OFFLINE';panel.update_snapshot(data)
    assert not panel.active_order and all(l.isHidden() for l,t in panel.labels.values())
    panel.close()


def test_alarm_and_operating_meanings_are_preserved_and_new_fault_returns_left(app):
    config=library_config('LEL 700 Series');panel=IndicatorPanel();panel.resize(350,50);panel.show()
    data=dict(config=asdict(config),raw={2:2,4:0xffff & ~(1<<2) & ~(1<<10),59:0xffff},quality='GOOD')
    panel.update_snapshot(data);app.processEvents()
    assert presentation(0,2,'Danger')[2]=='Alarm' and presentation(0,11,'Warmup')[2]=='Operating state'
    assert presentation(1,9,'Service Needed')[2]=='Service advisory'
    panel.scroll.horizontalScrollBar().setValue(panel.scroll.horizontalScrollBar().maximum())
    assert panel.scroll.horizontalScrollBar().value()>0
    data['raw'][4]|=4;panel.update_snapshot(data);app.processEvents()
    assert panel.scroll.horizontalScrollBar().value()==0 and panel.active_order[0]==(1,2)
    fault=panel.labels[(1,2)][0];danger=panel.labels[(0,2)][0]
    assert fault.x()<danger.x() and 'Alarm' in danger.toolTip()
    panel.close()


def test_gauge_has_no_removed_copy_or_visible_status_summary(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json');w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    try:
        w.show();app.processEvents()
        texts=[label.text() for label in w.pages.widget(0).findChildren(QLabel) if label.isVisibleTo(w)]
        assert not any('One active analyzer.' in text or 'COMMUNICATION:' in text or 'Active indicators only' in text for text in texts)
        assert not w.indicators.summary.isVisibleTo(w)
    finally:w.close();app.processEvents()
