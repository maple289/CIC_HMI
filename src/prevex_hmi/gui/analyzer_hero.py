"""Responsive gauge, analyzer information and fixed-height command result."""
from PySide6.QtWidgets import QGridLayout,QLayout,QSizePolicy,QWidget


class AnalyzerHero(QWidget):
    def __init__(self,gauge,information,result,parent=None):
        super().__init__(parent)
        self.gauge,self.information,self.result=gauge,information,result
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(12)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Minimum)
        self.wide=None;self.reflow()

    def reflow(self):
        wide=self.width()>=900
        if wide==self.wide:return
        self.wide=wide
        while self.grid.count():self.grid.takeAt(0)
        for column in range(3):self.grid.setColumnStretch(column,0)
        self.grid.addWidget(self.gauge,0,0);self.grid.addWidget(self.information,0,1)
        self.result.setFixedHeight(360 if wide else 280)
        if wide:
            self.grid.addWidget(self.result,0,2)
            for column,stretch in enumerate((3,2,2)):self.grid.setColumnStretch(column,stretch)
        else:
            self.grid.addWidget(self.result,1,0,1,2)
            self.grid.setColumnStretch(0,3);self.grid.setColumnStretch(1,2)
        self.setMinimumHeight(360 if wide else 622);self.updateGeometry()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()
