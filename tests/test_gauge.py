from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from prevex_hmi.devices.configuration import default_devices
from prevex_hmi.gui.gauge import gauge_state
from prevex_hmi.profiles import PROFILES


def reading(family="LEL",value=25,maximum=100,quality="GOOD"):
    device=next(d for d in default_devices() if d.family == family)
    if family == "FID":
        from dataclasses import replace
        device=replace(device,fullscale=maximum)
    r=PROFILES[family].registers
    raw={1:r[1].encode(value,family,device.context),2:0,3:maximum,5:r[5].encode(40,family,device.context),6:r[6].encode(50,family,device.context)}
    return {"config":asdict(device),"raw":raw,"quality":quality,"age":0,"last_success":datetime.now(timezone.utc).isoformat(),"error":"","identification":"test"}


@pytest.mark.parametrize("family,maximum,value,fraction,unit",[("LEL",100,25,0.25,"%LFL"),("BTU",1000,250,0.25,"unit unverified"),("FID",1000,250,0.25,"PPM")])
def test_gauge_span_is_fullscale_not_raw_word_limit(family,maximum,value,fraction,unit):
    state=gauge_state(reading(family,value,maximum))
    assert state.maximum == maximum
    assert state.value == pytest.approx(value)
    assert state.fraction == pytest.approx(fraction)
    assert state.unit == unit


def test_low_and_high_alarm_band_meanings_are_family_specific():
    lel=gauge_state(reading())
    btu=gauge_state(reading("BTU",25,1000))
    assert lel.bands[0][2] == "#39c6a4"
    assert lel.bands[1][2] == "#efb753"
    assert btu.bands[0][2] == "#efb753"
    assert btu.bands[1][2] == "#39c6a4"
    assert "Low alarm" in btu.thresholds


@pytest.mark.parametrize("quality",["OFFLINE","STALE","DISABLED"])
def test_unavailable_readings_hide_the_gauge_indicator(quality):
    state=gauge_state(reading(quality=quality))
    assert state.value is None and state.fraction is None
    assert state.reading == "--" and state.bands == ()


@pytest.mark.parametrize("value,expected_fraction,note",[(-5,0,"BELOW RANGE"),(120,1,"ABOVE RANGE")])
def test_out_of_range_clamps_marker_without_clamping_display(value,expected_fraction,note):
    state=gauge_state(reading(value=value))
    assert state.value == value
    assert state.fraction == expected_fraction
    assert state.range_note == note


def test_no_invented_alarm_bands_or_range():
    data=reading()
    data["raw"].pop(5)
    assert gauge_state(data).bands == ()
    data["raw"][3]=0
    assert gauge_state(data).maximum is None
    assert gauge_state(data).fraction is None
    assert gauge_state(None).reading == "--"


def test_legacy_dilution_span_and_fid_unit_changes():
    device=default_devices()[3]
    data=reading(value=50)
    data["config"]=asdict(device)
    data["raw"].update({1:6400,3:200})
    assert gauge_state(data).value == 50
    assert gauge_state(data).fraction == 0.25
    data=reading("FID",25,100)
    data["config"]["units"]="METRIC"
    assert gauge_state(data).unit == "MG"
