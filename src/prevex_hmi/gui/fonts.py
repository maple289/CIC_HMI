"""Choose one verified sans-serif UI family for native and packaged windows."""
import os
from pathlib import Path
from PySide6.QtGui import QFont,QFontDatabase,QFontInfo,QRawFont

FONT_DIR=Path(__file__).resolve().parents[1]/'assets'/'fonts'


def configure_application_font(app):
    loaded=[]
    for weight in ('Regular','SemiBold','Bold'):
        identifier=QFontDatabase.addApplicationFont(str(FONT_DIR/f'PrevexUI-{weight}.ttf'))
        loaded.append(identifier>=0)
    if all(loaded):
        font=QFont('PREVEX UI Regular',10);font.setStyleHint(QFont.SansSerif)
        symbols=QFontDatabase.addApplicationFont(str(FONT_DIR/'PrevexSymbols-Regular.ttf'))
        if symbols>=0:font.setFamilies(['PREVEX UI Regular','PREVEX Symbols'])
        if QRawFont.fromFont(font).familyName()=='PREVEX UI Regular':
            app.setFont(font);app.setProperty('uiFontFamily','PREVEX UI Regular');app.setProperty('fontSource','bundled')
            return 'PREVEX UI Regular'
    # Register all UI weights, matching visual tests. Never distribute Windows
    # fonts or assume that loading just the regular face supplies the others.
    folder=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    for name in ('segoeui.ttf','seguisb.ttf','segoeuib.ttf'):
        path=folder/name
        if path.is_file():QFontDatabase.addApplicationFont(str(path))
    available={name.casefold():name for name in QFontDatabase.families()}
    font=QFontDatabase.systemFont(QFontDatabase.GeneralFont)
    font.setPointSize(10);font.setStyleHint(QFont.SansSerif)
    for candidate in ('Segoe UI','Tahoma','Arial','DejaVu Sans','Liberation Sans'):
        family=available.get(candidate.casefold())
        if not family:continue
        proposed=QFont(family,10);proposed.setStyleHint(QFont.SansSerif)
        if QFontInfo(proposed).family().casefold()==family.casefold():
            font=proposed;break
    app.setFont(font)
    app.setProperty('uiFontFamily',QFontInfo(font).family());app.setProperty('fontSource','system fallback')
    return QFontInfo(app.font()).family()


def display_diagnostics(app,window):
    screen=window.screen();button=window.connect_button
    return dict(platform=app.platformName(),screen=screen.geometry().getRect(),available=screen.availableGeometry().getRect(),
                logical_dpi=round(screen.logicalDotsPerInch(),2),device_pixel_ratio=window.devicePixelRatioF(),
                ui_family=QFontInfo(button.font()).family(),ui_pixel_size=button.font().pixelSize(),
                heading_family=QFontInfo(window.monitor_name.font()).family(),compact=bool(window.property('compactDisplay')),
                command_family=QFontInfo(window.command_buttons[0x100].button.font()).family(),
                raw_ui_family=QRawFont.fromFont(button.font()).familyName(),font_source=app.property('fontSource'),launch_size=app.property('launchSize'),
                platform_options=os.environ.get('QT_QPA_PLATFORM',''),
                qt_scale_factor=os.environ.get('QT_SCALE_FACTOR',''),qt_screen_scale_factors=os.environ.get('QT_SCREEN_SCALE_FACTORS',''))
