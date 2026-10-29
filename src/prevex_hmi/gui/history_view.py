"""Presentation-only historical channel selection and timezone formatting."""
from datetime import datetime
import math
from PySide6.QtCore import QDateTime,QTimeZone,Signal,QLocale
from PySide6.QtWidgets import QVBoxLayout,QHBoxLayout,QCheckBox,QPushButton,QScrollArea,QWidget,QMenu,QWidgetAction,QLabel
import pyqtgraph as pg
import numpy as np


def display_zone(key='system'):
    zone=QTimeZone.systemTimeZone() if key=='system' else QTimeZone(key.encode())
    return zone if zone.isValid() else QTimeZone.systemTimeZone()


def local_datetime(stamp,zone):
    return QDateTime.fromMSecsSinceEpoch(round(datetime.fromisoformat(stamp).timestamp()*1000),zone)


def friendly_time(stamp,zone):
    if not stamp:return 'Active / unfinished'
    return QLocale(QLocale.English,QLocale.UnitedStates).toString(local_datetime(stamp,zone),'MMM d, yyyy — h:mm:ss AP')


def session_label(row,zone):
    import json
    config=json.loads(row['config'])
    profile=row['profile'].replace(' Series','')
    text=f"{friendly_time(row['started_at'],zone)} | {profile} / {config['assembly']} | {row['source'].title()} | {row['interval_seconds']} sec"
    end=row['ended_at'] or row.get('last_sample_at')
    if end:
        seconds=max(0,int((datetime.fromisoformat(end)-datetime.fromisoformat(row['started_at'])).total_seconds()))
        hours,rest=divmod(seconds,3600);minutes,seconds=divmod(rest,60)
        text+=f' | {hours:02}:{minutes:02}:{seconds:02}'
    if 'sample_count' in row:text+=f" | {row['sample_count']} samples"
    if not row['ended_at']:text+=' | active / unfinished'
    return text


class LocalTimeAxis(pg.DateAxisItem):
    def __init__(self,zone=None,**kwargs):
        self.zone=zone or display_zone();super().__init__(**kwargs)

    def tickStrings(self,values,scale,spacing):
        dates=[QDateTime.fromMSecsSinceEpoch(round(v*1000),self.zone) if math.isfinite(v) else QDateTime() for v in values]
        span=self.range[1]-self.range[0]
        cross_day=len({d.date().toJulianDay() for d in dates if d.isValid()})>1
        fmt='MMM d\nHH:mm:ss' if span>=86400 or cross_day else 'HH:mm:ss'
        # Fall-back DST hours have identical wall time; show offsets only there.
        offsets={}
        for d in dates:offsets.setdefault(d.toString(fmt),set()).add(d.offsetFromUtc())
        if any(len(v)>1 for v in offsets.values()):fmt+=' ttt'
        seen=set();labels=[]
        for d in dates:
            label=d.toString(fmt) if d.isValid() else ''
            labels.append(label if label not in seen else '');seen.add(label)
        return labels


class HistoricalParameters(QWidget):
    changed=Signal()

    def __init__(self):
        super().__init__();self.checkboxes={};box=QHBoxLayout(self);box.setContentsMargins(0,0,0,0)
        box.addWidget(QLabel('Historical parameters'))
        self.button=QPushButton('Choose parameters');self.menu=QMenu(self.button);self.button.setMenu(self.menu);box.addWidget(self.button,1)

    def set_parameters(self,parameters):
        self.menu.clear();self.checkboxes={};row=QHBoxLayout();controls=QWidget();controls.setLayout(row)
        for text,checked in (('Select All',True),('Clear All',False)):
            button=QPushButton(text);button.clicked.connect(lambda _,v=checked:self.select_numbers(list(self.checkboxes) if v else []));row.addWidget(button)
        action=QWidgetAction(self.menu);action.setDefaultWidget(controls);self.menu.addAction(action)
        for i,p in enumerate(parameters):
            c=QCheckBox(f"{p['name']} [{p['number']}] ({p['unit']})");c.setChecked(i==0)
            c.setContentsMargins(10,6,10,6);c.toggled.connect(self.selection_changed);self.checkboxes[p['number']]=c
            action=QWidgetAction(self.menu);action.setDefaultWidget(c);self.menu.addAction(action)
        self.update_summary();self.button.setEnabled(bool(parameters))

    def update_summary(self):
        selected=[c.text() for c in self.checkboxes.values() if c.isChecked()]
        self.button.setText(f'Choose parameters ({len(selected)} selected)');self.button.setToolTip('\n'.join(selected) or 'No saved parameters selected')

    def selection_changed(self):self.update_summary();self.changed.emit()

    def selected_numbers(self):return [n for n,c in self.checkboxes.items() if c.isChecked()]

    def select_numbers(self,numbers):
        for n,c in self.checkboxes.items():c.blockSignals(True);c.setChecked(n in numbers);c.blockSignals(False)
        self.selection_changed()


class HistoricalPlots(QScrollArea):
    def __init__(self):
        super().__init__();self.setWidgetResizable(True)
        self.content=QWidget();self.box=QVBoxLayout(self.content);self.setWidget(self.content)
        self.plots=[];self.curves=[];self.data=[];self.dark=True

    def set_theme(self,dark):
        from .theme import style_plot
        self.dark=dark
        for plot in self.plots:style_plot(plot,dark)

    def render(self,data,zone):
        self.data=data
        while self.box.count():
            w=self.box.takeAt(0).widget()
            if w:w.hide();w.deleteLater()
        self.plots=[];self.curves=[];groups={}
        for series in data:groups.setdefault(series['unit'],[]).append(series)
        if not groups:groups['']=[]
        colors=('#69a7ed','#45cbb0','#e7b55e','#e484d4','#fa9365','#a6ce64')
        for unit,series in groups.items():
            plot=pg.PlotWidget(axisItems={'bottom':LocalTimeAxis(zone)},background='#111c2b');plot.setMinimumHeight(215)
            plot.showGrid(x=True,y=True,alpha=.15);plot.setLabel('left',unit or 'Value');plot.setLabel('bottom',f"Time ({bytes(zone.id()).decode()})")
            plot.addLegend(offset=(8,8));plot.zero_line=pg.InfiniteLine(pos=0,angle=0,pen=pg.mkPen('#efb753',width=2),label='0',labelOpts={'position':.95,'color':'#efb753'})
            if unit in ('%LFL','%LEL'):plot.addItem(plot.zero_line)
            finite=[]
            for i,s in enumerate(series):
                xs=np.array([datetime.fromisoformat(t).timestamp() for t,v in s['points']]);ys=np.array([v if v is not None else np.nan for t,v in s['points']])
                # Connect only runs with at least three real observations. Always
                # draw markers; NaN gap markers break both sparse and dense runs.
                connect=np.zeros(len(ys),dtype=bool);start=0
                for end in range(len(ys)+1):
                    if end==len(ys) or not np.isfinite(ys[end]):
                        if end-start>=3:connect[start:end-1]=True
                        start=end+1
                color=colors[i%len(colors)]
                curve=plot.plot(xs,ys,pen=pg.mkPen(color,width=2),symbol='o',symbolSize=6,symbolBrush=color,symbolPen=color,connect=connect,name=s['name'])
                self.curves.append(curve);finite.extend(ys[np.isfinite(ys)])
            if finite:
                low,high=min(finite),max(finite)
                if unit in ('%LFL','%LEL'):low=min(0,low);high=max(0,high)
                margin=max((high-low)*.08,abs(high)*.01,.01);plot.setYRange(low-margin,high+margin,padding=0)
            self.box.addWidget(plot,1);self.plots.append(plot)
            if len(self.plots)>1:plot.setXLink(self.plots[0])
        all_times=[datetime.fromisoformat(t).timestamp() for s in data for t,v in s['points'] if v is not None]
        if all_times:
            low,high=min(all_times),max(all_times);margin=max((high-low)*.03,1)
            self.plots[0].setXRange(low-margin,high+margin,padding=0)
        if not self.curves:self.curves.append(self.plots[0].plot())
        self.set_theme(self.dark)
