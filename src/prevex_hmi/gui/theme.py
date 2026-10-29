"""Presentation-only colors shared by widgets, painter output and plots."""
from PySide6.QtGui import QColor,QPalette

LIGHT=dict(background='#F2F4F7',panel='#FFFFFF',sidebar='#E4EAF0',text='#243447',secondary='#607185',accent='#177E89',border='#D3DBE3',normal='#22846D',warning='#CB8B28',danger='#C74D55')


def is_dark(widget):
    owner=widget
    while owner is not None:
        if hasattr(owner,'settings'):return owner.settings.get('theme','dark')=='dark'
        owner=owner.parentWidget()
    return True


def display_color(color,dark):
    if dark:return color
    return {'#39c6a4':LIGHT['normal'],'#39c66c':LIGHT['normal'],'#f27778':LIGHT['danger'],
            '#ed575d':LIGHT['danger'],'#efb753':'#95651B','#e7b55e':'#95651B',
            '#69a7ed':'#286C9E','#45cbb0':LIGHT['accent'],'#8290a5':LIGHT['secondary'],
            '#adbbcf':LIGHT['secondary'],'#5a9fcf':'#397CA4','#e484d4':'#92528C',
            '#fa9365':'#AA582E','#a6ce64':'#5D782B'}.get(color.lower(),color)


def apply_palette(widget,dark):
    palette=widget.palette()
    values={QPalette.Window:'#0d1625' if dark else LIGHT['background'],QPalette.Base:'#182538' if dark else LIGHT['panel'],
            QPalette.AlternateBase:'#0d1625' if dark else '#F5F7FA',QPalette.Text:'#e7edf7' if dark else LIGHT['text'],
            QPalette.WindowText:'#e7edf7' if dark else LIGHT['text'],QPalette.Button:'#182538' if dark else '#E8EEF3',
            QPalette.ButtonText:'#e7edf7' if dark else LIGHT['text'],QPalette.Highlight:'#245a69' if dark else '#CDE5E4',
            QPalette.HighlightedText:'#ffffff' if dark else '#164E55',QPalette.ToolTipBase:'#182538' if dark else '#ffffff',
            QPalette.ToolTipText:'#e7edf7' if dark else LIGHT['text']}
    for role,color in values.items():palette.setColor(role,QColor(color))
    for role in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText):palette.setColor(QPalette.Disabled,role,QColor('#7f8ba0' if dark else '#778697'))
    widget.setPalette(palette)


def semantic_style(widget,color,extra=''):
    widget.setProperty('themeColor',color);widget.setProperty('themeExtra',extra)
    tone=display_color(color,is_dark(widget));widget.setStyleSheet(f"color:{tone};{extra.replace('{tone}',tone)}")


def refresh_semantics(root,dark):
    from PySide6.QtWidgets import QLabel
    for label in root.findChildren(QLabel):
        color=label.property('themeColor')
        if color:
            tone=display_color(color,dark);extra=(label.property('themeExtra') or '').replace('{tone}',tone)
            label.setStyleSheet(f'color:{tone};{extra}')


def style_plot(plot,dark):
    import pyqtgraph as pg
    text='#adbbcf' if dark else LIGHT['secondary'];border='#40516a' if dark else LIGHT['border']
    plot.setBackground('#111c2b' if dark else LIGHT['panel'])
    for name in ('left','bottom','right','top'):
        axis=plot.getAxis(name);axis.setPen(pg.mkPen(border));axis.setTextPen(pg.mkPen(text))
        axis.setLabel(axis.labelText,units=axis.labelUnits,**{'color':text})
    for curve in plot.listDataItems():
        pen=pg.mkPen(curve.opts.get('pen'))
        # Remember original colors so switching back restores the dark theme.
        if not hasattr(curve,'theme_pen'):curve.theme_pen=pen
        pen=pg.mkPen(curve.theme_pen);pen.setColor(QColor(display_color(pen.color().name(),dark)));curve.setPen(pen)
        if curve.opts.get('symbol'):
            curve.setSymbolBrush(pen.color());curve.setSymbolPen(pen.color())
    if hasattr(plot,'zero_line'):
        zero='#efb753' if dark else LIGHT['accent'];plot.zero_line.setPen(pg.mkPen(zero,width=2))
        if plot.zero_line.label:plot.zero_line.label.setColor(zero)
    if plot.plotItem.legend:
        for sample,label in plot.plotItem.legend.items:label.setText(label.text,color=text)


def stylesheet(dark):
    bg,panel,text=('#0d1625','#182538','#e7edf7') if dark else (LIGHT['background'],LIGHT['panel'],LIGHT['text'])
    border='#40516a' if dark else LIGHT['border'];secondary='#adbbcf' if dark else LIGHT['secondary']
    base=f"""
    QWidget {{background:{bg};color:{text};font-family:'Segoe UI';font-size:13px;}}
    QLabel#brand {{font-size:24px;font-weight:bold;}} QLabel#heading {{font-size:23px;font-weight:600;}}
    QLabel#digitalValue {{font-size:21px;font-weight:600;}}
    QFrame#panel,QFrame#readout,QFrame#indicatorPanel {{background:{panel};border:1px solid {border};border-radius:7px;}}
    QFrame#readout QLabel,QFrame#panel QLabel {{background:transparent;}}
    QPushButton,QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox,QDateTimeEdit {{background:{panel};border:1px solid {'#526780' if dark else border};border-radius:5px;padding:7px;}}
    QPushButton:hover {{border-color:{'#44cab0' if dark else LIGHT['accent']};}}
    QPushButton:disabled {{color:{'#7f8ba0' if dark else '#778697'};border-color:{'#36435a' if dark else '#DCE2E8'};}}
    QListWidget,QTableWidget {{background:{panel};alternate-background-color:{bg};border:0;}}
    QListWidget::item {{padding:14px 8px;}} QListWidget::item:selected {{background:#245a69;color:white;}}
    QHeaderView::section {{background:{panel};color:{text};padding:7px;border:0;}} QScrollArea {{border:0;}}
    QListWidget#navigation {{background:{'#182538' if dark else LIGHT['sidebar']};border:0;border-radius:8px;outline:0;}}
    QListWidget#navigation::item {{padding:12px 5px;margin:2px 3px;border:1px solid transparent;border-radius:7px;color:{secondary};font-size:12px;}}
    QListWidget#navigation::item:hover {{background:{'#22364A' if dark else '#D8E2EA'};color:{text};}}
    QListWidget#navigation::item:pressed {{background:{'#285363' if dark else '#BED8DC'};}}
    QListWidget#navigation::item:selected {{background:{'#245a69' if dark else '#CDE5E4'};border:1px solid {'#398F8D' if dark else '#8BBABB'};color:{'#79DFCF' if dark else '#135D65'};font-weight:600;}}
    QListWidget#navigation::item:selected:hover {{background:{'#2B6875' if dark else '#BEDDDE'};}}
    QListWidget#navigation::item:selected:pressed {{background:{'#1A4654' if dark else '#AFCFD2'};}}
    """
    if dark:return base+"""
    QLabel#banner {background:#e7b55e;color:#251c10;padding:9px;font-weight:bold;}
    QLabel#warning {background:#763d2e;color:#ffe3c2;padding:9px;}
    QPushButton#industrialCommand {color:#f1f5fa;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #52647a,stop:1 #283648);border-top:2px solid #8291a4;border-left:2px solid #697c93;border-right:2px solid #121e2b;border-bottom:3px solid #0b1624;border-radius:6px;font-weight:bold;}
    QPushButton#industrialCommand:pressed {background:#233244;border-top:3px solid #101c29;border-left:2px solid #101c29;border-bottom:1px solid #667991;padding-top:9px;}
    QPushButton#industrialCommand:disabled {color:#788595;background:#26313f;border:1px solid #3c4859;}
    """
    return base+f"""
    QLabel#banner {{background:#E4EDEF;color:#35565F;border:1px solid #CDDDE1;border-radius:6px;padding:6px 9px;font-weight:600;}}
    QLabel#warning {{background:#FFF0DB;color:#805019;border:1px solid #DEC29A;border-radius:6px;padding:9px;}}
    QWidget#analyzerHero {{background:white;border:1px solid {border};border-radius:8px;}}
    QWidget#analyzerHero QWidget,QWidget#analyzerHero QLabel {{background:transparent;}}
    QFrame#readout QLabel#parameterLabel {{color:{secondary};}}
    QFrame#readout QLabel#digitalValue {{color:{text};}}
    QPushButton:hover {{background:#EDF3F5;}}
    QPushButton:pressed {{background:#DAE7EA;border-color:{LIGHT['accent']};}}
    QPushButton:disabled,QToolButton:disabled {{background:#EEF1F4;color:#778697;}}
    QPushButton#industrialCommand {{color:{text};background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #EDF2F6,stop:1 #D5DFE8);border-top:2px solid #FFFFFF;border-left:1px solid #C1CDD8;border-right:1px solid #ADBDCA;border-bottom:3px solid #A7B8C7;border-radius:6px;font-weight:600;}}
    QPushButton#industrialCommand:hover {{background:#E0ECEF;border-color:#83A9AE;}}
    QPushButton#industrialCommand:pressed {{background:#C7D7E1;border-top:3px solid #A3B5C4;border-left:1px solid #A3B5C4;border-bottom:1px solid #EDF3F7;padding-top:9px;}}
    QPushButton#industrialCommand:disabled {{color:#778697;background:#E7EDF2;border:1px solid #D4DDE5;}}
    QToolButton {{background:#F1F5F8;border:1px solid {border};border-radius:5px;padding:5px;color:{text};}}
    QToolButton:hover {{background:#DCE9EC;border-color:#8FAEB4;}}
    QToolButton:pressed {{background:#CDDFE3;}}
    QGroupBox {{border:1px solid {border};border-radius:7px;margin-top:12px;padding:12px 8px 8px;}}
    QGroupBox::title {{subcontrol-origin:margin;left:10px;padding:0 4px;color:{secondary};}}
    QTabWidget::pane {{border:1px solid {border};border-radius:5px;background:white;}}
    QTabBar::tab {{background:#E4EAF0;color:{secondary};padding:8px 12px;border:1px solid {border};}}
    QTabBar::tab:selected {{background:white;color:{LIGHT['accent']};border-bottom:2px solid {LIGHT['accent']};}}
    QHeaderView::section {{background:#E9EEF3;color:{secondary};border-bottom:1px solid {border};}}
    QTableWidget {{gridline-color:#E1E6EC;selection-background-color:#CDE5E4;selection-color:#164E55;}}
    QTableWidget::item:selected,QListWidget::item:selected {{background:#CDE5E4;color:#164E55;}}
    QMenu {{background:white;border:1px solid {border};padding:4px;}}
    QMenu::item {{padding:7px 14px;}} QMenu::item:selected {{background:#DDECEE;color:#135D65;}}
    QToolTip {{background:white;color:{text};border:1px solid {border};padding:5px;}}
    QCheckBox,QRadioButton {{spacing:7px;}}
    QCheckBox::indicator {{width:16px;height:16px;}}
    QScrollBar:vertical {{background:#E8EDF2;width:12px;margin:0;}} QScrollBar::handle:vertical {{background:#B3C1CD;min-height:24px;border-radius:5px;}}
    QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
    """
