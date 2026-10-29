"""Command-list scrolling without jumps during safety-driven focus changes."""
from PySide6.QtWidgets import QApplication,QScrollArea,QWidget


class CommandScrollArea(QScrollArea):
    def focusNextPrevChild(self,next):
        previous=QApplication.focusWidget()
        disabling_focus=previous is not None and not previous.isEnabled()
        # QScrollArea normally reveals each new focus target with a 50px
        # margin. Disabling a focused command walks through subsequent buttons
        # and can scroll the entire list to the bottom. Keep that safety-driven
        # focus walk stationary; normal keyboard navigation still reveals rows.
        changed=QWidget.focusNextPrevChild(self,next)
        if changed and not disabling_focus:
            focused=QApplication.focusWidget()
            if focused:self.ensureWidgetVisible(focused,0,0)
        return changed
