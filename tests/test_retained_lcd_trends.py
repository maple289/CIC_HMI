"""Display-only holds replay real LCD blanking without opening a serial port."""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import copy,math,os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication
from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.devices.configuration import default_devices,load_settings
from prevex_hmi.gui.gauge import CircularGauge
from prevex_hmi.gui.presentation import measurement
from prevex_hmi.gui.trend_display import DisplayTrend
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.simulator.bus import SimulatedBus


@pytest.fixture
def app():
    result=QApplication.instance() or QApplication([]);result.setQuitOnLastWindowClosed(False)
    return result


def snapshot(seconds=0,text=b'-99 %LFL  ',quality='GOOD'):
    config=replace(default_devices()[0],assembly='SNR671',version='4.81',register_profile='fta_4x')
    raw={1:0x8001,2:20,3:100,4:12,5:40*256,6:50*256,60:0}
    raw.update({51+i//2:int.from_bytes(text[i:i+2],'big') for i in range(0,10,2)})
    return dict(config=asdict(config),raw=raw,register_ages={n:0 for n in raw},age=0,
                last_success=(datetime(2026,10,25,tzinfo=timezone.utc)+timedelta(seconds=seconds)).isoformat(),
                quality=quality,error='',source='hardware',reading_source='controller_lcd_fault')


@pytest.mark.parametrize('lcd_text',[b'          ',b'TC2 FAIL  '])
def test_blank_hold_survives_fresh_replies_but_not_stopped_communication(app,monkeypatch,lcd_text):
    now=[100.0];monkeypatch.setattr('prevex_hmi.gui.gauge.time',SimpleNamespace(monotonic=lambda:now[0]))
    gauge=CircularGauge();gauge.set_snapshot(snapshot())
    try:
        for second in range(2,62,2):
            now[0]=100+second;blank=snapshot(second,lcd_text)
            gauge.set_snapshot(blank);gauge.expire()
            assert gauge.state.value==-99 and gauge.lcd_hold and gauge.held
            assert gauge.blank_since==102 and gauge.display_quality=='RETAINED_STALE'
            assert measurement(blank)[0] is None
        now[0]=166.1;gauge.expire()
        assert gauge.state.value is None and not gauge.lcd_hold
    finally:gauge.close()


@pytest.mark.parametrize('failure',['offline','stale_lcd','profile_change','no_first_value'])
def test_blank_retention_does_not_bypass_quality_or_scope(app,monkeypatch,failure):
    now=[100.0];monkeypatch.setattr('prevex_hmi.gui.gauge.time',SimpleNamespace(monotonic=lambda:now[0]))
    gauge=CircularGauge()
    try:
        if failure!='no_first_value':gauge.set_snapshot(snapshot())
        now[0]=110;blank=snapshot(10,b'          ')
        if failure=='offline':blank['quality']='OFFLINE'
        if failure=='stale_lcd':blank['register_ages'][51]=10
        if failure=='profile_change':blank['config']['id']='different-instrument'
        gauge.set_snapshot(blank)
        assert gauge.state.value is None and not gauge.held
    finally:gauge.close()


def test_zero_retention_and_fresh_numeric_recovery(app,monkeypatch):
    now=[100.0];monkeypatch.setattr('prevex_hmi.gui.gauge.time',SimpleNamespace(monotonic=lambda:now[0]))
    gauge=CircularGauge()
    try:
        gauge.set_snapshot(snapshot(text=b'0 %LFL    '))
        now[0]=102;gauge.set_snapshot(snapshot(2,b'          '))
        assert gauge.state.value==0 and gauge.lcd_hold
        now[0]=110;gauge.set_snapshot(snapshot(10,b'-98 %LFL  '))
        assert gauge.state.value==-98 and not gauge.held and gauge.blank_since is None
    finally:gauge.close()


def test_held_trend_segments_and_real_gaps_are_distinct():
    trend=DisplayTrend();trend.append(1,0);trend.append(2,None,0);trend.append(8,None,0);trend.append(9,12)
    solid,held=trend.curves()
    assert not solid[0] and [p.held for p in trend.points]==[False,True,True,False]
    assert held[1][-2:]==[0,12]  # Hold until the new sample's timestamp, then its step.
    trend.append(10,None);trend.append(11,13);trend.append(12,14)
    solid,held=trend.curves()
    assert solid[0][-2:]==[11,12]  # No connector bridges the genuine missing sample.
    assert 10 not in held[0] and 11 not in held[0]
    trend.clear();assert not trend.points


def test_window_holds_readout_and_trace_without_mutating_measurements(app,tmp_path,monkeypatch):
    now=[100.0]
    clock=SimpleNamespace(monotonic=lambda:now[0],time=lambda:1700000000+now[0])
    monkeypatch.setattr('prevex_hmi.gui.gauge.time',clock);monkeypatch.setattr('prevex_hmi.gui.window.time',clock)
    w=MainWindow(load_settings(tmp_path/'settings.json'),tmp_path/'settings.json',tmp_path,start_worker=False)
    bus=BusEngine(SimulatedBus([default_devices()[0]]));diagnostics=bus.diagnostics()
    try:
        w.update_data(snapshot(),diagnostics)
        now[0]=102;blank=snapshot(2,b'          ');original=copy.deepcopy(blank)
        w.update_data(blank,diagnostics)
        assert blank==original and measurement(blank)[0] is None
        assert math.isnan(w.series[-1][1])  # Raw observations remain missing.
        assert w.display_trend.points[-1].held and w.display_trend.points[-1].value==-99
        assert w.readouts[1][0].text()=='-99.00 %LFL'
        assert 'Numeric reading missing since' in w.overview_hold_note.text()
        assert w.overview_held_curve.getData()[0] is not None
        now[0]=103;w.update_data(snapshot(3,b'          '),diagnostics)
        assert w.blank_started_wall==1700000102  # First-missing time is not renewed.
        now[0]=120;w.update_data(snapshot(20,b'-98 %LFL  '),diagnostics)
        assert not w.display_trend.points[-1].held and w.readouts[1][0].text()=='-98.00 %LFL'
        assert w.blank_started_wall is None
        w.invalidate();assert not w.display_trend.points and not w.series
    finally:w.close();bus.close();app.processEvents()
