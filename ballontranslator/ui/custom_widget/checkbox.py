import sys

from qtpy.QtWidgets import QCheckBox
from qtpy.QtCore import Qt
from qtpy.QtGui import QMouseEvent

class QFontChecker(QCheckBox):
    BASE_MIN_WIDTH = 63 if sys.platform == 'darwin' else 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.BASE_MIN_WIDTH:
            self.setMinimumWidth(self.BASE_MIN_WIDTH)
        self.resetStyleSheet()

    def resetStyleSheet(self):
        self.setStyleSheet("")

class AlignmentChecker(QCheckBox):
    BASE_MIN_WIDTH = 33 if sys.platform == 'darwin' else 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.BASE_MIN_WIDTH:
            self.setMinimumWidth(self.BASE_MIN_WIDTH)
        self.resetStyleSheet()

    def resetStyleSheet(self):
        self.setStyleSheet("")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.checkState() == Qt.CheckState.Checked:
            return event.accept()
        return super().mousePressEvent(event)
