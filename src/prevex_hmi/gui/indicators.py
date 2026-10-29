"""One compact active-indicator strip; preserve status/relay/service sources."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QHBoxLayout,QLabel,QScrollArea,QWidget
from prevex_hmi.profiles import PROFILES,profile_for,relays_for,service_for
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.registers.schema import decode_relays,decode_service


def presentation(group,key,text):
    """Priority is independent of color: Danger is an alarm, not a fault."""
    if group==0:
        if key==1:return 1,'#efb753','Alarm'
        if key==2:return 1,'#f27778','Alarm'
        if key in (0,4,5,6,7,11,12):return 3,'#39c6a4','Operating state'
        return 0,'#f27778','Instrument condition'
    if group==1:
        if text=='Fault':return 0,'#f27778','Fault relay'
        if text=='Air/fuel cutoff':return 0,'#f27778','Safety interlock'
        if text in ('Warning / low','Danger / high','Horn'):
            return 1,'#f27778' if text=='Danger / high' else '#efb753','Alarm relay'
        if text=='Service Needed':return 2,'#efb753','Service advisory'
        return 3,'#39c6a4','Operating relay'
    return 2,'#efb753','Service advisory'


class IndicatorPanel(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('indicatorPanel')
        self.family=None;self.labels={};self.active_order=[];self.dark=True;self.last_snapshot=None
        root=QHBoxLayout(self);root.setContentsMargins(6,3,6,3)
        # Retain diagnostic text for existing consumers, without a visible row.
        self.summary=QLabel('COMMUNICATION: disconnected | STATUS [2]: unavailable',self);self.summary.hide()
        self.scroll=QScrollArea();self.scroll.setFrameShape(QFrame.NoFrame);self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content=QWidget();self.row=QHBoxLayout(self.content);self.row.setContentsMargins(0,0,0,0);self.row.setSpacing(5)
        self.scroll.setWidget(self.content);root.addWidget(self.scroll)
        self.setFixedHeight(50);self.row_widgets=[self.content]

    def build(self,family,config=None):
        self.config=config;profile=profile_for(config) if config else PROFILES[family]
        self.family=(family,profile.revision)
        while self.row.count():self.row.takeAt(0)
        for label,text in self.labels.values():label.hide();label.deleteLater()
        self.labels={};self.active_order=[]
        groups=[profile.statuses,dict(enumerate(relays_for(0,config) if config else decode_relays(0))),dict(enumerate(service_for(0,config) if config else decode_service(0,family))) if family!='FID' else {}]
        for group,items in enumerate(groups):
            for key,text in items.items():
                label=QLabel(text,self.content);label.setAlignment(Qt.AlignCenter)
                label.hide();self.labels[(group,key)]=(label,text)
        self.row.addStretch();self.content.hide()

    def update_snapshot(self,snapshot):
        self.last_snapshot=snapshot
        if snapshot is None:
            self.summary.setText('COMMUNICATION: disconnected | STATUS [2]: unavailable')
            for label,text in self.labels.values():label.hide()
            self.active_order=[];self.content.hide();self.hide();return
        config=DeviceConfig(**snapshot['config']);family=config.family;profile=profile_for(config)
        if self.family!=(family,profile.revision):self.build(family,config)
        good=snapshot['quality']=='GOOD';raw=snapshot['raw'];ages=snapshot.get('register_ages',{});limit=max(5,config.interval*3);code=raw.get(2)
        self.summary.setText(f"COMMUNICATION: {snapshot['quality']} | STATUS [2]: {profile.status(code) if good and ages.get(2,0)<=limit and code is not None else 'unavailable'}")
        relays=list(relays_for(raw.get(4,0),config).values());service=list(service_for(raw.get(59,0),config).values()) if family!='FID' else []
        active=[]
        for (group,key),(label,text) in self.labels.items():
            number=(2,4,59)[group];valid=good and number in raw and ages.get(number,0)<=limit
            on=code==key if group==0 else relays[key] if group==1 else service[key] if service else False
            label.setVisible(bool(valid and on))
            if not valid or not on:continue
            priority,color,meaning=presentation(group,key,text)
            from .theme import display_color
            color=display_color(color,self.dark)
            source=('STATUS','RELAYS','SERVICE')[group]
            label.setToolTip(f'{source} [{number}]: {text} — {meaning}');label.setAccessibleName(f'{source}: {text}')
            label.setStyleSheet(f'QLabel {{padding:3px 8px;border-radius:5px;border:1px solid {color};color:{color};font-weight:bold;}}')
            active.append((priority,group,key,label))
        previous=set(self.active_order)
        active.sort(key=lambda item:item[:3]);self.active_order=[(g,k) for _,g,k,_ in active]
        while self.row.count():self.row.takeAt(0)
        previous_priority=None
        for priority,group,key,label in active:
            if previous_priority is not None and priority!=previous_priority:self.row.addSpacing(8)
            self.row.addWidget(label);previous_priority=priority
        self.row.addStretch();self.content.setVisible(bool(active))
        self.setVisible(bool(active))
        if any(priority==0 and (group,key) not in previous for priority,group,key,label in active):self.scroll.horizontalScrollBar().setValue(0)

    def set_theme(self,dark):
        self.dark=dark;self.update_snapshot(self.last_snapshot)
