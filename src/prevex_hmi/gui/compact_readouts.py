"""Consistent compact digital cards that reflow with the available width."""
from PySide6.QtCore import QSize,Qt
from PySide6.QtWidgets import QGridLayout,QLayout,QSizePolicy,QWidget


class CompactReadouts(QWidget):
    card_width=200
    gap=8

    def __init__(self,parent=None):
        super().__init__(parent)
        self.cards=[];self.columns=0
        self.grid=QGridLayout(self)
        self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(self.gap)
        self.grid.setAlignment(Qt.AlignTop|Qt.AlignLeft)
        self.grid.setSizeConstraint(QLayout.SetNoConstraint)
        policy=QSizePolicy(QSizePolicy.Ignored,QSizePolicy.Minimum)
        policy.setHeightForWidth(True);self.setSizePolicy(policy)
        self.setMinimumWidth(self.card_width)

    def clear_cards(self):
        while self.grid.count():self.grid.takeAt(0)
        for card in self.cards:card.hide();card.deleteLater()
        self.cards=[];self.columns=0;self.setMinimumHeight(0);self.updateGeometry()

    def add_card(self,card):
        card.setFixedWidth(self.card_width)
        card.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Preferred)
        self.cards.append(card);self.columns=0;self.reflow()

    def column_count(self,width):
        return max(1,min(len(self.cards) or 1,(width+self.gap)//(self.card_width+self.gap)))

    def heightForWidth(self,width):
        columns=self.column_count(width);heights=[]
        for start in range(0,len(self.cards),columns):
            row=[]
            for card in self.cards[start:start+columns]:
                margins=card.contentsMargins()
                wrapped=card.layout().heightForWidth(self.card_width-margins.left()-margins.right())
                row.append(max(card.minimumSizeHint().height(),wrapped+margins.top()+margins.bottom() if wrapped>=0 else card.sizeHint().height()))
            heights.append(max(row))
        return sum(heights)+self.gap*max(0,len(heights)-1)

    def sizeHint(self):return QSize(self.card_width,self.heightForWidth(self.width()))
    def minimumSizeHint(self):return QSize(self.card_width,0)

    def reflow(self):
        columns=self.column_count(self.width())
        if columns==self.columns:return
        self.columns=columns
        while self.grid.count():self.grid.takeAt(0)
        for index,card in enumerate(self.cards):self.grid.addWidget(card,index//columns,index%columns)
        self.refresh_height()

    def refresh_height(self):
        height=self.heightForWidth(self.width())
        if height==self.minimumHeight():return
        self.setMinimumHeight(height)
        self.updateGeometry()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()
