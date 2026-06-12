import sys

from qtpy.QtWidgets import QCheckBox
from qtpy.QtCore import Qt
from qtpy.QtGui import QMouseEvent

class QFontChecker(QCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if sys.platform == 'darwin':
            self.setStyleSheet("min-width: 45px")

class AlignmentChecker(QCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if sys.platform == 'darwin':
            self.setStyleSheet("min-width: 15px")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.checkState() == Qt.CheckState.Checked:
            return event.accept()
        return super().mousePressEvent(event)
