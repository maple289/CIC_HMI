"""DPI-aware, font-independent sidebar line icons."""
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QColor,QIcon,QPainter,QPainterPath,QPen,QPixmap
from PySide6.QtWidgets import QListWidget,QStyledItemDelegate,QStyle,QStyleOptionViewItem


class NavigationDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        option=QStyleOptionViewItem(option)
        if index.row()==self.parent().pressed_row:option.state|=QStyle.State_Sunken
        super().paint(painter,option,index)


class NavigationList(QListWidget):
    """Keep existing list navigation; expose a visible mouse-down state."""
    def __init__(self):
        super().__init__();self.pressed_row=-1;self.setItemDelegate(NavigationDelegate(self))

    def mousePressEvent(self,event):
        self.pressed_row=self.indexAt(event.position().toPoint()).row()
        super().mousePressEvent(event);self.viewport().update()

    def mouseReleaseEvent(self,event):
        self.pressed_row=-1;super().mouseReleaseEvent(event);self.viewport().update()

    def leaveEvent(self,event):
        self.pressed_row=-1;super().leaveEvent(event);self.viewport().update()


def navigation_icon(kind,dark):
    icon=QIcon()
    for mode,color in ((QIcon.Normal,'#adbbcf' if dark else '#607185'),(QIcon.Selected,'#79DFCF' if dark else '#135D65')):
        for scale in (1,2,3):
            image=QPixmap(20*scale,20*scale);image.setDevicePixelRatio(scale);image.fill(Qt.transparent)
            painter=QPainter(image);painter.setRenderHint(QPainter.Antialiasing);painter.setPen(QPen(QColor(color),1.6,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            if kind=='Monitor':
                painter.drawArc(QRectF(2,3,16,16),30*16,120*16);painter.drawLine(QPointF(3,15),QPointF(5,15));painter.drawLine(QPointF(15,15),QPointF(17,15));painter.drawLine(QPointF(10,11),QPointF(14,7));painter.drawEllipse(QPointF(10,11),1.5,1.5)
            elif kind=='Service':
                path=QPainterPath(QPointF(12,2));path.cubicTo(8,1,6,5,8,8);path.lineTo(2,14);path.cubicTo(0,17,3,20,6,17);path.lineTo(12,11);path.cubicTo(16,13,20,9,18,5);path.lineTo(15,8);path.lineTo(12,5);path.closeSubpath();painter.drawPath(path)
            else:
                path=QPainterPath(QPointF(1,11));path.lineTo(5,11);path.lineTo(8,4);path.lineTo(11,17);path.lineTo(14,8);path.lineTo(16,11);path.lineTo(19,11);painter.drawPath(path)
            painter.end();icon.addPixmap(image,mode)
    return icon
