from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import time

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from prevex_hmi.communication.engine import BusEngine
from prevex_hmi.communication.protocol import Addressing
from prevex_hmi.devices.configuration import default_devices, load_settings, save_settings
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.gui.presentation import format_reading, measurement, severity
from prevex_hmi.gui.window import MainWindow
from prevex_hmi.gui.device_dialogs import DeviceEditor
from prevex_hmi.logging_db.store import Historian
from prevex_hmi.profiles import PROFILES
from prevex_hmi.simulator.bus import SimulatedBus


@pytest.fixture(scope="session")
def app():
    instance=QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    yield instance


def until(app,condition,timeout=6):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.processEvents()
        if condition(): return
        time.sleep(0.01)
    pytest.fail("Timed out waiting for asynchronous monitoring state")


def snapshot(quality="GOOD",family="LEL"):
    config=next(d for d in default_devices() if d.family == family)
    return {"config":asdict(config),"raw":{1:25600,2:0,3:100,4:128},"quality":quality,"age":1,"last_success":datetime.now(timezone.utc).isoformat(),"error":"","identification":"simulated"}


@pytest.mark.parametrize("quality",["OFFLINE","STALE","DISABLED"])
def test_old_reading_never_presented_as_current(quality):
    data=snapshot(quality)
    assert measurement(data)[0] is None
    assert format_reading(data) == "--"
    assert severity(data)[1] == quality


def test_fid_uses_live_fullscale_and_missing_context_stays_unknown():
    data=snapshot(family="FID")
    data["raw"][3]=1000
    assert measurement(data) == (Decimal("1000"),"PPM")
    data["config"]["units"]=None
    assert measurement(data)[0] is None


def test_settings_roundtrip_and_corruption_preserved(tmp_path):
    path=tmp_path/"settings.json"
    settings=load_settings(path)
    settings["devices"]=list(reversed(settings["devices"]))
    save_settings(path,settings)
    assert load_settings(path) == settings
    path.write_text("broken json",encoding="utf-8")
    with pytest.raises(ValueError): load_settings(path)
    assert path.read_text() == "broken json"


def test_edit_family_or_units_starts_independent_history_identity(app):
    original=default_devices()[0]
    editor=DeviceEditor(original)
    assert editor.config().id == original.id
    editor.family.setCurrentText("FID")
    assert editor.config().id != original.id
    editor.close()


def test_historian_quality_events_ranges_and_retention(tmp_path):
    db=Historian(tmp_path/"test.sqlite3")
    stamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    old=(datetime.now(timezone.utc)-timedelta(days=100)).isoformat(timespec="milliseconds")
    db.measurement(old,"device",1,99,"%LFL","GOOD",0)
    db.measurement(stamp,"device",1,12.5,"%LFL","GOOD",0)
    db.measurement(stamp,"other",1,25,"PPM","GOOD",0)
    db.measurement(stamp,"device",1,None,"","OFFLINE",0)
    db.event(old,"device","Initial alarm","GOOD")
    db.commit()
    rows=db.history("device",hours=24)
    assert len(rows) == 2 and rows[0][1] == 12.5 and rows[1][1] is None
    db.retain(90)
    assert len(db.history("device",hours=365*24)) == 2
    assert len(db.events()) == 1
    db.close()


def test_widgets_hide_stale_data_and_render_model_specific_values(app,tmp_path):
    settings=load_settings(tmp_path/"settings.json")
    window=MainWindow(settings,tmp_path/"settings.json",tmp_path,start_worker=False)
    bus=BusEngine(SimulatedBus(default_devices()))
    data=snapshot()
    window.update_data([data],bus.diagnostics())
    window.open_device(data["config"]["id"])
    assert "100.00" in window.detail_reading.text()
    assert window.gauge.state.reading == "100.00"
    data["quality"]="OFFLINE"
    window.update_data([data],bus.diagnostics())
    assert window.detail_reading.text().strip() == "--"
    assert window.gauge.state.reading == "--"
    assert window.gauge.state.fraction is None
    window.close()
    bus.close()


def test_threaded_monitoring_fault_history_and_clean_close(app,tmp_path):
    settings=load_settings(tmp_path/"settings.json")
    window=MainWindow(settings,tmp_path/"settings.json",tmp_path)
    window.show()
    try:
        until(app,lambda:len(window.snapshots)==4 and all(s["quality"] == "GOOD" for s in window.snapshots.values()))
        # A real Qt timer continues while worker-owned polling and DB I/O run.
        assert window.update_count >= 1
        window.worker.request("history","lel-1",24)
        until(app,lambda:bool(window.history_rows))
        window.worker.request("fault",1,"timeout")
        until(app,lambda:window.snapshots["lel-1"]["quality"] == "OFFLINE")
        assert window.gauge.state.reading == "--"
        assert any(s["quality"] == "GOOD" for id,s in window.snapshots.items() if id != "lel-1")
    finally:
        window.close()
        until(app,lambda:not window.worker.isRunning())
        app.processEvents()
    assert (tmp_path/"simulation.sqlite3").exists()


def test_selection_switches_all_process_views_and_clears_previous_values(app,tmp_path):
    settings=load_settings(tmp_path/"settings.json")
    window=MainWindow(settings,tmp_path/"settings.json",tmp_path,start_worker=False)
    bus=BusEngine(SimulatedBus(default_devices()))
    lel=snapshot()
    fid=snapshot(family="FID")
    window.update_data([lel,fid],bus.diagnostics())
    assert window.monitor_name.text() == lel["config"]["name"]
    assert window.gauge.state.unit == "%LFL"
    window.selected.setCurrentIndex(window.selected.findData("fid-3"))
    assert window.monitor_name.text() == fid["config"]["name"]
    assert window.gauge.state.unit == "PPM"
    assert window.detail_reading.text().endswith("PPM")
    assert all(c.currentData() == "fid-3" for c in (window.selected,window.trend_device,window.history_device,window.fault_device))
    assert json.loads((tmp_path/"settings.json").read_text())["selected_device"] == "fid-3"
    # Select a configured analyzer that has not replied: no FID value can linger.
    window.selected.setCurrentIndex(window.selected.findData("btu-2"))
    assert window.gauge.state.reading == "--"
    assert window.detail_reading.text() == "--"
    assert window.parameters.rowCount() == 0
    assert window.overview_curve.xData is None or len(window.overview_curve.xData) == 0
    window.close()
    bus.close()


def test_selected_events_are_filtered(app,tmp_path):
    settings=load_settings(tmp_path/"settings.json")
    window=MainWindow(settings,tmp_path/"settings.json",tmp_path,start_worker=False)
    window.update_events([("now","lel-1","Warning","GOOD"),("now","fid-3","Danger","GOOD")])
    assert window.event_table.rowCount() == 1
    assert window.event_table.item(0,1).text() == "lel-1"
    window.close()
