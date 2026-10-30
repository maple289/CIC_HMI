import copy,json,hashlib
from pathlib import Path
import pytest
from PySide6.QtGui import QRawFont,QTextLayout
from prevex_hmi.gui.display import choose_size,apply_launch_size,saved_size
from prevex_hmi.gui.fonts import FONT_DIR,configure_application_font
from prevex_hmi.devices.configuration import load_settings,validate_settings
from test_command_result_layout import app,setup_window,flush


@pytest.mark.parametrize('metrics,expected',[((1920,1080,150),85),((1920,1080,125),100),((1920,1080,100),100),((2560,1440,125),100),((3840,2160,150),100),(None,100)])
def test_automatic_size_uses_physical_screen_and_windows_scale(metrics,expected):
    assert choose_size('auto',metrics)==expected
    for value in (75,85,100):assert choose_size(value,metrics)==value


def test_scale_applied_once_and_manual_preference_overrides_external(monkeypatch):
    monkeypatch.delenv('QT_SCALE_FACTOR',raising=False)
    result=apply_launch_size('auto',metrics=(1920,1080,150))
    assert result['percent']==85 and result['source']=='automatic'
    assert __import__('os').environ['QT_SCALE_FACTOR']=='0.85'  # Qt already applies Windows' 1.5.
    monkeypatch.setenv('QT_SCALE_FACTOR','1.5')
    assert apply_launch_size('auto',metrics=(1920,1080,150))['source']=='environment'
    assert __import__('os').environ['QT_SCALE_FACTOR']=='1.5'
    assert apply_launch_size(100,metrics=(1920,1080,150))['percent']==100
    assert __import__('os').environ['QT_SCALE_FACTOR']=='1.0'


@pytest.mark.parametrize('value',['auto',75,85,100])
def test_display_preference_roundtrip_without_changing_analyzer(tmp_path,value):
    path=tmp_path/'settings.json';settings=load_settings(path);original=copy.deepcopy(settings)
    settings['ui_scale']=value;validate_settings(settings);path.write_text(json.dumps(settings))
    assert saved_size(path)==value
    loaded=load_settings(path);loaded.pop('ui_scale');assert loaded==original


@pytest.mark.parametrize('value',[True,False,0,150,85.0,'85',{},None])
def test_invalid_size_is_rejected(tmp_path,value):
    settings=load_settings(tmp_path/'settings.json');settings['ui_scale']=value
    with pytest.raises(ValueError,match='interface size'):validate_settings(settings)


def test_bundled_regular_semibold_and_bold_fonts_are_pinned_and_resolve(app):
    manifest=json.loads((FONT_DIR/'SOURCE.json').read_text())
    for name,info in manifest['files'].items():assert hashlib.sha256((FONT_DIR/name).read_bytes()).hexdigest()==info['sha256']
    assert b'SIL OPEN FONT LICENSE' in (FONT_DIR/'OFL.txt').read_bytes()
    assert configure_application_font(app)=='PREVEX UI Regular' and app.property('fontSource')=='bundled'
    font=app.font()
    for weight in (400,600,700):
        font.setWeight(type(font.weight())(weight));raw=QRawFont.fromFont(font)
        assert raw.familyName()=='PREVEX UI Regular' and all(raw.glyphIndexesForString('HMI 0123 Aa'))
    layout=QTextLayout('HMI ● ✓',font);layout.beginLayout();layout.createLine();layout.endLayout()
    assert all(all(run.glyphIndexes()) for run in layout.glyphRuns())
    assert 'PREVEX Symbols' in {run.rawFont().familyName() for run in layout.glyphRuns()}


def test_display_save_and_cancel_do_not_restart_monitoring_or_dispatch_commands(app,tmp_path,monkeypatch):
    w,bus,snapshot=setup_window(tmp_path,'LEL 670 Series');requests=[]
    monkeypatch.setattr(w,'request',lambda *args:requests.append(args));source=copy.deepcopy(snapshot)
    try:
        monkeypatch.setattr('prevex_hmi.gui.display.size_dialog',lambda *args:85)
        w.display_settings();assert w.settings['ui_scale']==85 and saved_size(w.settings_path)==85
        assert not w.closing and w.snapshot==source and not requests
        before=w.settings_path.read_bytes()
        monkeypatch.setattr('prevex_hmi.gui.display.size_dialog',lambda *args:None)
        w.display_settings();assert w.settings_path.read_bytes()==before and not requests
    finally:w.close();bus.close();flush(app)
