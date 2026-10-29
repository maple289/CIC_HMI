"""UI-only styling changes preserve navigation, measurement state and LED timing."""
import copy
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPalette,QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from prevex_hmi.gui.theme import LIGHT,display_color
from prevex_hmi.gui.profile_library import PROFILE_CHOICES
from prevex_hmi.gui.connection_dialog import AnalyzerChoice,LoginDialog
from test_command_result_layout import app,setup_window,flush


@pytest.mark.parametrize('profile',PROFILE_CHOICES)
def test_theme_roundtrip_preserves_measurements_navigation_and_feedback(app,tmp_path,profile):
    w,bus,snapshot=setup_window(tmp_path,profile);w.show()
    try:
        original=copy.deepcopy(w.gauge.state);source=copy.deepcopy(snapshot)
        button=w.command_buttons[0x100];button.feedback(True);button.timer.start(2400)
        w.show_command_receipt(dict(id='ui-only',code=0x100,state='SENT_UNVERIFIED',reply_received=True))
        result=w.last_command.text();receipt_key=w.last_receipt_key
        for theme in ('light','dark','light'):
            before=button.timer.remainingTime();w.settings['theme']=theme;w.apply_theme();flush(app)
            assert button.timer.isActive() and button.timer.remainingTime()<=before
            assert w.gauge.state==original and snapshot==source
            assert w.last_command.text()==result and w.last_receipt_key==receipt_key
            assert w.navigation.width()==122 and w.navigation.count()==3
            assert not any(b.text()=='View Command Audit' for b in w.findChildren(QPushButton))
            for i,name in enumerate(('Monitor','Service','Diagnostics')):
                item=w.navigation.item(i);assert item.text()==name and not item.icon().isNull()
                rect=w.navigation.visualItemRect(item)
                QTest.mouseClick(w.navigation.viewport(),Qt.LeftButton,pos=rect.center());flush(app)
                assert w.navigation.currentRow()==i
            w.show_diagnostics('Command audit');flush(app)
            assert w.audit_table.isVisibleTo(w) and w.command_proof.isVisibleTo(w)
            w.navigation.setCurrentRow(0)
        for width,height in ((1100,780),(1280,800),(1540,1020),(1920,1080)):
            w.resize(width,height);flush(app)
            assert w.navigation.horizontalScrollBar().maximum()==0
            for i in range(3):
                item=w.navigation.item(i);rect=w.navigation.visualItemRect(item)
                assert rect.left()>=0 and rect.right()<w.navigation.viewport().width()
                assert QFontMetrics(w.navigation.font()).horizontalAdvance(item.text())+32<rect.width()
            assert not w.gauge.geometry().intersects(w.analyzer_info.geometry())
    finally:w.close();bus.close();flush(app)


def test_light_dialogs_plots_faults_and_negative_gauge_keep_their_meaning(app,tmp_path):
    w,bus,snapshot=setup_window(tmp_path,'LEL 670 Series');w.show()
    try:
        fault=copy.deepcopy(snapshot);fault['raw'].update({1:0xFE00,2:25,4:4})
        w.update_data(fault,bus.diagnostics());before=copy.deepcopy(w.gauge.state)
        w.settings['theme']='light';w.apply_theme();flush(app)
        assert w.gauge.state==before and before.value<0 and before.markers
        assert w.fault_summary.text()=='Analyzer Fault Active' and LIGHT['danger'] in w.fault_summary.styleSheet()
        assert w.connection_established and LIGHT['normal'] in w.monitor_status.styleSheet()
        assert w.palette().color(QPalette.Window)==QColor(LIGHT['background'])
        data=[dict(unit='%LFL',name='Reading',points=[('2026-10-29T12:00:00+00:00',-2.),('2026-10-29T12:00:01+00:00',None),('2026-10-29T12:00:02+00:00',3.)]),
              dict(unit='degC',name='Temperature',points=[('2026-10-29T12:00:00+00:00',120.)])]
        w.trend_window.draw_history(data);plots=w.trend_window.history_plots
        assert len(plots.plots)==2 and plots.data==data
        for plot in plots.plots:assert plot.backgroundBrush().color()==QColor('#FFFFFF')
        w.settings['theme']='dark';w.apply_theme();flush(app)
        for plot in plots.plots:assert plot.backgroundBrush().color()==QColor('#111c2b')
        assert plots.data==data and w.gauge.state==before
        w.settings['theme']='light';w.apply_theme()
        for dialog in (AnalyzerChoice(w.settings,w),LoginDialog(w.users,w)):
            dialog.show();flush(app)
            assert dialog.palette().color(QPalette.WindowText)==QColor(LIGHT['text'])
            dialog.close()
    finally:w.close();bus.close();flush(app)


def test_light_semantic_text_contrast():
    def luminance(color):
        values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        return sum(weight*(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4) for weight,c in zip((.2126,.7152,.0722),values))
    for color in (LIGHT['text'],LIGHT['secondary'],LIGHT['accent'],LIGHT['normal'],LIGHT['danger'],display_color('#efb753',False)):
        assert 1.05/(luminance(color)+.05)>=4.5


@pytest.mark.parametrize('theme',['dark','light'])
def test_sidebar_hover_and_mouse_down_are_visibly_distinct(app,tmp_path,theme):
    w,bus,snapshot=setup_window(tmp_path,'LEL 670 Series');w.settings['theme']=theme;w.apply_theme();w.show();flush(app)
    try:
        nav=w.navigation;rect=nav.visualItemRect(nav.item(0));point=rect.bottomRight();point.setX(point.x()-10);point.setY(point.y()-10)
        def color():
            flush(app);image=nav.viewport().grab().toImage();dpr=image.devicePixelRatio()
            return image.pixelColor(round(point.x()*dpr),round(point.y()*dpr))
        QTest.mouseMove(nav.viewport(),nav.viewport().rect().bottomRight());normal=color()
        QTest.mouseMove(nav.viewport(),rect.center());hover=color()
        QTest.mousePress(nav.viewport(),Qt.LeftButton,pos=rect.center());pressed=color()
        QTest.mouseRelease(nav.viewport(),Qt.LeftButton,pos=rect.center());released=color()
        assert normal!=hover and pressed!=hover and released==hover
        assert nav.currentRow()==0
    finally:w.close();bus.close();flush(app)
