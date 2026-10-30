"""Font resolution and short-window density; no physical transports."""
from PySide6.QtGui import QFont,QFontInfo,QFontDatabase
from PySide6.QtCore import QPoint
from prevex_hmi.gui.fonts import configure_application_font,display_diagnostics
from test_command_result_layout import app,setup_window,flush


def test_resolved_ui_font_survives_both_stylesheets(app,tmp_path):
    original=QFont(app.font());family=configure_application_font(app)
    w,bus,_=setup_window(tmp_path,'LEL 670 Series')
    try:
        assert app.font().styleHint()==QFont.SansSerif
        assert family.casefold() not in ('times','times new roman','serif')
        for theme in ('light','dark'):
            w.settings['theme']=theme;w.apply_theme();w.show();flush(app)
            for widget in (w.connect_button,w.command_buttons[0x100].button,w.monitor_name,w.monitor_status):
                assert QFontInfo(widget.font()).family()==family
            diagnostics=display_diagnostics(app,w)
            assert diagnostics['ui_family']==family and diagnostics['heading_family']==family
            assert diagnostics['ui_pixel_size']==13
            assert diagnostics['device_pixel_ratio']==w.devicePixelRatioF()
    finally:w.close();bus.close();app.setFont(original);flush(app)


def test_missing_preferred_family_uses_available_sans_family(app,tmp_path,monkeypatch):
    original=QFont(app.font())
    for name in ('arial.ttf','DejaVuSans.ttf'):
        from pathlib import Path
        path=Path('C:/Windows/Fonts')/name
        if path.exists():QFontDatabase.addApplicationFont(str(path))
    families=QFontDatabase.families()
    remaining=[family for family in families if family.casefold()!='segoe ui']
    monkeypatch.setattr(QFontDatabase,'families',lambda:remaining)
    monkeypatch.setenv('WINDIR',str(tmp_path))
    try:
        selected=configure_application_font(app)
        assert app.font().styleHint()==QFont.SansSerif
        assert selected.casefold() not in ('times','times new roman','serif')
    finally:app.setFont(original)


def test_short_window_reclaims_gauge_space_without_changing_command_geometry(app,tmp_path):
    w,bus,_=setup_window(tmp_path,'LEL 670 Series');w.show()
    try:
        w.resize(1280,950);flush(app)
        assert not w.property('compactDisplay') and w.hero.minimumHeight()==340
        normal=w.gauge.height()
        w.resize(1280,660);flush(app)
        assert w.property('compactDisplay') and w.hero.minimumHeight()==230
        assert w.gauge.height()<normal and w.gauge.height()>=220
        assert w.command_buttons[0x100].height()==40
        def geometry():
            return [(b.mapTo(w,QPoint()).toTuple(),b.size().toTuple()) for b in dict.fromkeys(w.command_buttons.values())]
        before=geometry()
        for state in ('SENDING','SENT_UNVERIFIED','EFFECT_OBSERVED','UNKNOWN'):
            w.show_command_receipt(dict(id=state,code=0x100,state=state,reply_received=state!='SENDING',detail='Long detail. '*100))
            w.command_buttons[0x100].feedback(state!='UNKNOWN');flush(app)
            assert geometry()==before and w.property('compactDisplay')
        w.resize(1280,950);flush(app)
        assert not w.property('compactDisplay') and w.hero.minimumHeight()==340 and w.gauge.minimumHeight()==330
    finally:w.close();bus.close();flush(app)
