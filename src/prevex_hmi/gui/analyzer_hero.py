"""Responsive measurement and analyzer information; audit lives in Diagnostics."""
from PySide6.QtWidgets import QGridLayout,QLayout,QSizePolicy,QWidget
from PySide6.QtCore import Qt


class AnalyzerHero(QWidget):
    def __init__(self,gauge,information,parent=None):
        super().__init__(parent)
        self.gauge,self.information=gauge,information;self.setObjectName('analyzerHero');self.setAttribute(Qt.WA_StyledBackground,True)
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(12)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Minimum)
        self.grid.addWidget(gauge,0,0);self.grid.addWidget(information,0,1)
        self.grid.setColumnStretch(0,3);self.grid.setColumnStretch(1,2)
        self.setMinimumHeight(340)
