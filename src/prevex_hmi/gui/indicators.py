from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QHBoxLayout,QLabel,QScrollArea,QVBoxLayout,QWidget
from prevex_hmi.profiles import PROFILES,profile_for,relays_for,service_for
from prevex_hmi.devices.models import DeviceConfig
from prevex_hmi.registers.schema import decode_relays,decode_service


class IndicatorPanel(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName("indicatorPanel")
        self.family=None;self.labels={}
        self.root=QVBoxLayout(self);self.root.setContentsMargins(10,8,10,8)
        self.summary=QLabel("COMMUNICATION: disconnected | STATUS [2]: unavailable")
        self.root.addWidget(self.summary)
        self.rows=[]
        for title in ("STATUS [2]","RELAYS [4]","SERVICE [59]"):
            row=QHBoxLayout();heading=QLabel(title);heading.setFixedWidth(100);row.addWidget(heading)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFixedHeight(40);scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            content=QWidget();layout=QHBoxLayout(content);layout.setContentsMargins(0,0,0,0);layout.setSpacing(5)
            scroll.setWidget(content);row.addWidget(scroll);self.root.addLayout(row)
            self.rows.append(layout)

    def build(self,family,config=None):
        self.config=config
        profile=profile_for(config) if config else PROFILES[family]
        self.family=(family,profile.revision);self.labels={}
        for row in self.rows:
            while row.count():
                item=row.takeAt(0)
                if item.widget():item.widget().deleteLater()
        groups=[{code:name for code,name in profile.statuses.items()},dict(enumerate(relays_for(0,config) if config else decode_relays(0))),dict(enumerate(service_for(0,config) if config else decode_service(0,family))) if family!="FID" else {0:"Not documented for FID"}]
        for group,items in enumerate(groups):
            for key,text in items.items():
                label=QLabel(text);label.setMinimumWidth(max(90,self.fontMetrics().horizontalAdvance('off  '+text)+28));label.setAlignment(Qt.AlignCenter)
                self.rows[group].addWidget(label);self.labels[(group,key)]=(label,text)
            self.rows[group].addStretch()

    def update_snapshot(self,snapshot):
        if snapshot is None:
            self.summary.setText("COMMUNICATION: disconnected | STATUS [2]: unavailable")
            for label,text in self.labels.values():self.paint(label,text,None,"#8290a5")
            return
        family=snapshot["config"]["family"]
        config=DeviceConfig(**snapshot["config"])
        if self.family!=(family,profile_for(config).revision):self.build(family,config)
        good=snapshot["quality"]=="GOOD";raw=snapshot["raw"];code=raw.get(2)
        self.summary.setText(f"COMMUNICATION: {snapshot['quality']} | STATUS [2]: {profile_for(config).status(code) if good and code is not None else 'unavailable'} | One STATUS code at a time; RELAYS/SERVICE are independent bits")
        relays=list(relays_for(raw.get(4,0),config).values())
        service=list(service_for(raw.get(59,0),config).values()) if family!="FID" else []
        for (group,key),(label,text) in self.labels.items():
            valid=good and (2 if group==0 else 4 if group==1 else 59) in raw
            number=2 if group==0 else 4 if group==1 else 59
            valid=valid and snapshot.get('register_ages',{}).get(number,0) <= max(5,snapshot['config']['interval']*3)
            active=(code==key) if group==0 else relays[key] if group==1 else service[key] if service else False
            color="#39c6a4"
            if group==0 and key not in (0,4,5,6,7,11,12):color="#efb753" if key==1 else "#f27778"
            elif group==1:color="#f27778" if key in (1,2) else "#efb753" if key in (0,3) else "#39c6a4"
            elif group==2:color="#efb753"
            self.paint(label,text,active if valid else None,color)

    def paint(self,label,text,active,color):
        label.setText(f"{'ON' if active else 'off' if active is False else '--'}  {text}")
        label.setStyleSheet(f"QLabel {{padding:4px 8px;border-radius:5px;border:1px solid {color if active else '#536074'};color:{color if active else '#8d9aaf'};font-weight:{'bold' if active else 'normal'};}}")
