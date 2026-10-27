"""Historical presentation tests use isolated SQLite and simulated snapshots."""
import csv,json,math
from datetime import datetime
import pytest
from PySide6.QtCore import QTimeZone
from prevex_hmi.gui.history_view import LocalTimeAxis,display_zone,friendly_time,session_label,HistoricalPlots
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.gui.parameter_editor import ParameterEditor
from prevex_hmi.devices.configuration import load_settings,default_devices
from prevex_hmi.logging_db.recordings import RecordingStore,sessions,history_series,export_csv
from test_monitoring import app,until
from test_recording_sessions import sample,stamp


@pytest.fixture
def history(app,tmp_path):
    settings=load_settings(tmp_path/'settings.json');w=MainWindow(settings,tmp_path/'settings.json',tmp_path,start_worker=False)
    store=RecordingStore(tmp_path/'simulation.sqlite3')
    def add(numbers,values=(0,1,2),start=0,gap=False):
        sid,parameters=store.start(sample(start),1,False,'manual',stamp(start),selected=numbers);seen={}
        for i,value in enumerate(values):
            second=start+i*2
            if gap and i==1:store.gap(sid,'OFFLINE',stamp(second-1))
            store.append(sid,sample(second,value=value),parameters,seen,stamp(second))
        store.end(sid,'Stopped by operator',stamp(start+len(values)*2));return sid
    yield w,store,add
    store.close();w.close();until(app,lambda:not w.record_jobs);app.processEvents()


def test_windows_default_explicit_zone_dst_and_readable_axis(app):
    assert display_zone().id()==QTimeZone.systemTimeZoneId()
    zone=display_zone('America/Toronto')
    assert friendly_time('2026-10-27T00:18:56.123+00:00',zone)=='Oct 26, 2026 — 8:18:56 PM'
    assert friendly_time('2026-01-27T00:18:56+00:00',zone)=='Jan 26, 2026 — 7:18:56 PM'
    axis=LocalTimeAxis(zone);axis.setRange(0,10)
    values=[datetime.fromisoformat(t).timestamp() for t in ('2026-10-27T00:18:56+00:00','2026-10-27T00:18:57+00:00')]
    assert axis.tickStrings(values,1,.1)==['20:18:56','20:18:57']
    midnight=[datetime.fromisoformat(t).timestamp() for t in ('2026-10-27T03:59:59+00:00','2026-10-27T04:00:00+00:00')]
    assert 'Oct 26' in axis.tickStrings(midnight,1,1)[0] and 'Oct 27' in axis.tickStrings(midnight,1,1)[1]
    repeated=[datetime.fromisoformat(t).timestamp() for t in ('2026-11-01T05:30:00+00:00','2026-11-01T06:30:00+00:00')]
    labels=axis.tickStrings(repeated,1,3600);assert labels[0]!=labels[1] and '-04:00' in labels[0] and '-05:00' in labels[1]


def test_local_labels_sort_summaries_preferences_and_utc_unchanged(app,history,tmp_path):
    w,store,add=history;old=add([1],start=0);new=add([1,9],start=20,gap=True)
    before='\n'.join(store.db.iterdump());t=w.trend_window
    t.timezone_choice.setCurrentIndex(t.timezone_choice.findData('America/Toronto'))
    rows=sessions(t.paths,summaries=True);t.show_sessions(list(reversed(rows)))
    assert t.session_choice.currentData()['id']==new
    label=t.session_choice.currentText()
    assert 'Oct 26, 2026 — 10:30:20 AM' in label and 'LEL 670 / SNR675' in label
    assert '| Simulation | 1 sec | 00:00:06 | 3 samples' in label and '+00:00' not in label and '.000' not in label
    instant=t.range_start.dateTime().toMSecsSinceEpoch()
    t.timezone_choice.setCurrentIndex(t.timezone_choice.findData('UTC'))
    assert t.range_start.dateTime().toMSecsSinceEpoch()==instant and '2:30:20 PM' in t.session_choice.currentText()
    assert load_settings(w.settings_path)['trend_timezone']=='UTC'
    assert '\n'.join(store.db.iterdump())==before
    destination=tmp_path/'utc.csv';export_csv(t.paths,destination,session=new)
    with destination.open(encoding='utf-8-sig',newline='') as f:export=list(csv.DictReader(f))
    assert export[0]['Session start UTC']==stamp(20) and export[0]['Capture timestamp UTC'].endswith('+00:00')


@pytest.mark.parametrize('numbers,groups',[([1],1),([9,11],1),([1,9,15],3)])
def test_saved_only_multiple_units_independent_selection_and_negative_range(app,history,numbers,groups):
    w,store,add=history;sid=add(numbers,values=(-10,-5,2));t=w.trend_window
    t.show_sessions(sessions(t.paths,summaries=True));original=t.recording_parameters.selected_numbers()
    assert set(t.history_parameters.checkboxes)==set(numbers)
    t.history_parameters.select_numbers(numbers);t.load_session()
    until(app,lambda:len(t.history_plots.curves)==len(numbers) and t.recorded_curve.getData()[0] is not None)
    assert len(t.history_plots.plots)==groups and t.recording_parameters.selected_numbers()==original
    if 1 in numbers:
        plot=t.history_plots.plots[0];low,high=plot.viewRange()[1]
        assert low<-10 and high>2 and plot.zero_line.value()==0
    if groups>1:
        first=t.history_plots.plots[0];first.setXRange(100,200,padding=0);app.processEvents()
        assert all(p.viewRange()[0]==pytest.approx(first.viewRange()[0]) for p in t.history_plots.plots)


@pytest.mark.parametrize('count',[1,2,3])
def test_sparse_markers_no_implied_line_and_gap_disconnection(app,history,count):
    w,store,add=history;sid=add([1],values=tuple(range(count)));t=w.trend_window
    data=history_series(t.paths,sid);t.draw_history([data]);curve=t.recorded_curve
    assert curve.opts['symbol']=='o' and len(curve.getData()[0])==count
    assert sum(curve.opts['connect'])==(0 if count<3 else 2)
    sparse=dict(data,points=[(stamp(0),-2),(stamp(1),-1),(stamp(2),0),(stamp(3),None),(stamp(4),1),(stamp(5),2),(stamp(6),3)])
    t.draw_history([sparse]);assert list(t.recorded_curve.opts['connect'])==[True,True,False,False,True,True,False]
    assert math.isnan(t.recorded_curve.getData()[1][3])


def test_historical_selection_invalidates_inflight_jobs_and_handles_empty(app,history):
    w,store,add=history;add([1,9]);t=w.trend_window;t.show_sessions(sessions(t.paths))
    jobs=[];w.record_job=lambda work,done,*args:jobs.append((work,done))
    t.load_session();work,done=jobs.pop();t.history_parameters.select_numbers([9]);done(work())
    assert t.recorded_curve.getData()[0] is None
    t.history_parameters.select_numbers([]);t.load_session();assert not jobs and 'Select at least' in t.session_note.text()


@pytest.mark.parametrize('key,raw',[('cal_time',2),('span_temperature',512),('warning',40*256),('danger',50*256)])
def test_visible_adjustment_step_buttons_and_bounds(app,key,raw):
    # Names and limits remain profile-defined; clicks change only local widgets.
    editor=ParameterEditor(default_devices()[0],key,raw)
    value=editor.value;current=value.value();editor.increase_button.click()
    assert value.value()==pytest.approx(min(value.maximum(),current+value.singleStep()))
    editor.decrease_button.click();assert value.value()==current
    value.setValue(value.minimum());assert not editor.decrease_button.isEnabled()
    value.setValue(value.maximum());assert not editor.increase_button.isEnabled()
    assert editor.increase_button.accessibleName()=='Increase' and editor.decrease_button.text()=='−'
    editor.close()


def test_no_unsaved_channels_empty_session_and_real_gap_markers(app,history):
    w,store,add=history;t=w.trend_window;sid=add([1,9],gap=True)
    with store.db:store.db.execute('DELETE FROM recording_values WHERE register_number=9')
    rows=sessions(t.paths,summaries=True);t.show_sessions(rows)
    assert set(t.history_parameters.checkboxes)=={1}
    t.load_session();until(app,lambda:t.recorded_curve.getData()[0] is not None)
    ys=t.recorded_curve.getData()[1];assert any(math.isnan(v) for v in ys)
    assert not any(t.recorded_curve.opts['connect'])  # one point before / two after gap
    empty,parameters=store.start(sample(20),1,False,'manual',stamp(20),selected=[9])
    t.show_sessions(sessions(t.paths,summaries=True))
    assert t.session_choice.currentData()['id']==sid  # refresh preserves selection
    t.session_choice.setCurrentIndex(t.session_choice.findData(next(r for r in sessions(t.paths,summaries=True) if r['id']==empty)))
    assert not t.history_parameters.checkboxes
