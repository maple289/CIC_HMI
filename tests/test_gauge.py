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


def test_lel_fault_scale_adapts_and_restores_without_clamping_numeric_value():
    snapshot=reading(value=-120)
    snapshot['raw'][2]=25;snapshot['raw'][4]=4
    fault=gauge_state(snapshot)
    assert fault.minimum==-100 and fault.maximum==100
    assert fault.value==pytest.approx(-120) and fault.range_note=='BELOW RANGE'
    snapshot['raw'][2]=0;snapshot['raw'][4]=0
    normal=gauge_state(snapshot)
    assert normal.minimum==-30 and normal.maximum==100
    assert normal.value==pytest.approx(-120)


def test_lel_fault_relay_adapts_but_negative_sign_or_stale_fault_does_not():
    snapshot=reading(value=-20)
    assert gauge_state(snapshot).minimum==-30
    snapshot['raw'][4]=4
    assert gauge_state(snapshot).minimum==-100
    snapshot['raw'][2]=25;snapshot['register_ages']={2:100,4:100}
    assert gauge_state(snapshot).minimum==-30


@pytest.mark.parametrize("family,maximum,value,fraction,unit",[("LEL",100,25,0.25,"%LFL"),("BTU",1000,250,0.25,"unit unverified"),("FID",1000,250,0.25,"PPM")])
def test_gauge_span_is_fullscale_not_raw_word_limit(family,maximum,value,fraction,unit):
    state=gauge_state(reading(family,value,maximum))
    assert state.maximum == maximum
    assert state.value == pytest.approx(value)
    assert state.fraction == pytest.approx((value+30)/(maximum+30))
    assert state.minimum == -30
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


@pytest.mark.parametrize("value,expected_fraction,note",[(-40,0,"BELOW RANGE"),(120,1,"ABOVE RANGE")])
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
    assert gauge_state(data).fraction == pytest.approx(80/230)
    data=reading("FID",25,100)
    data["config"]["units"]="METRIC"
    assert gauge_state(data).unit == "MG"


@pytest.mark.parametrize('value',[-30,-20,-1,0])
def test_negative_values_have_distinct_positions_and_do_not_invent_faults(value):
    state=gauge_state(reading(value=value))
    assert state.value == pytest.approx(value,abs=.004)
    assert state.fraction == pytest.approx((value+30)/130,abs=.0001)
    assert state.status == 'Normal'


def test_manual_display_override_and_fallback_do_not_change_fid_reading():
    data=reading('FID',25,100)
    data['config'].update(range_mode='manual',manual_maximum=200)
    state=gauge_state(data)
    assert state.maximum==200 and state.value==25
    assert state.range_source=='Manual display override'
    data['config']['range_mode']='auto'
    assert gauge_state(data).maximum==100
    data['raw'].pop(3)
    state=gauge_state(data)
    assert state.maximum==200 and state.value is None
    assert state.range_source=='Manual fallback'
