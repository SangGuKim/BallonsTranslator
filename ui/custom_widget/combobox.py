from typing import List, Callable

from qtpy.QtWidgets import QComboBox, QWidget
from qtpy.QtCore import Signal, Qt
from qtpy.QtGui import QDoubleValidator, QFontDatabase

from utils.shared import CONFIG_COMBOBOX_LONG, CONFIG_COMBOBOX_MIDEAN, CONFIG_COMBOBOX_SHORT, CONFIG_COMBOBOX_HEIGHT
from .push_button import NoBorderPushBtn


class ComboBox(QComboBox):

    # https://stackoverflow.com/questions/3241830/qt-how-to-disable-mouse-scrolling-of-qcombobox
    def __init__(self, parent: QWidget = None, scrollWidget: QWidget = None, options: List[str] = None) -> None:
        super().__init__(parent)
        self.scrollWidget = scrollWidget
        if options is not None:
            self.addItems(options)

    def setScrollWidget(self, scrollWidget: QWidget):
        self.scrollWidget = scrollWidget

    def wheelEvent(self, *args, **kwargs):
        if self.scrollWidget is None or self.hasFocus():
            return super().wheelEvent(*args, **kwargs)
        else:
            return self.scrollWidget.wheelEvent(*args, **kwargs)
        

class SmallComboBox(ComboBox):
    pass


class ConfigComboBox(ComboBox):

    def __init__(self, fix_size=True, scrollWidget: QWidget = None, *args, **kwargs) -> None:
        super().__init__(scrollWidget, *args, **kwargs)
        self.fix_size = fix_size
        self.adjustSize()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def addItems(self, texts: List[str]) -> None:
        super().addItems(texts)
        self.adjustSize()

    def adjustSize(self) -> None:
        super().adjustSize()
        width = self.minimumSizeHint().width()
        if width < CONFIG_COMBOBOX_SHORT:
            width = CONFIG_COMBOBOX_SHORT
        elif width < CONFIG_COMBOBOX_MIDEAN:
            width = CONFIG_COMBOBOX_MIDEAN
        else:
            width = CONFIG_COMBOBOX_LONG
        if self.fix_size:
            self.setFixedWidth(width)
        else:
            self.setMaximumWidth(width)


class ParamComboBox(ComboBox):
    paramwidget_edited = Signal(str, str)
    flushbtn_clicked = Signal()
    pathbtn_clicked = Signal()
    def __init__(self, param_key: str, options: List[str], size=CONFIG_COMBOBOX_SHORT, scrollWidget: QWidget = None, flush_btn: bool = False, path_selector: bool = False, *args, **kwargs) -> None:
        super().__init__(scrollWidget=scrollWidget, *args, **kwargs)
        self.param_key = param_key
        self.setFixedWidth(size)
        self.setFixedHeight(CONFIG_COMBOBOX_HEIGHT)
        options = [str(opt) for opt in options]
        self.addItems(options)
        self.currentTextChanged.connect(self.on_select_changed)
        
        if flush_btn:
            self.flush_btn = NoBorderPushBtn(self.tr('Flush'))
            self.flush_btn.clicked.connect(self.flushbtn_clicked)
        if path_selector:
            self.path_select_btn = NoBorderPushBtn(self.tr('Select Path'))
            self.path_select_btn.clicked.connect(self.pathbtn_clicked)

    def on_select_changed(self):
        self.paramwidget_edited.emit(self.param_key, self.currentText())


class SizeComboBox(QComboBox):
    
    param_changed = Signal(str, float)
    def __init__(self, val_range: List = None, param_name: str = '', parent=None, init_value=None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.param_name = param_name
        self.editTextChanged.connect(self.on_text_changed)
        self.activated.connect(self.on_current_index_changed)
        self.setEditable(True)
        self.min_val = val_range[0]
        self.max_val = val_range[1]
        validator = QDoubleValidator()
        if val_range is not None:
            validator.setTop(val_range[1])
            validator.setBottom(val_range[0])
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)

        self.setValidator(validator)
        self._value = 0
        if init_value is not None:
            self.setValue(init_value)

    def on_text_changed(self):
        if self.hasFocus():
            self.param_changed.emit(self.param_name, self.value())

    def on_current_index_changed(self):
        if self.hasFocus() or self.view().isVisible():
            self.param_changed.emit(self.param_name, self.value())

    def value(self) -> float:
        txt = self.currentText()
        try:
            val = float(txt)
            self._value = val
            return val
        except:
            return self._value

    def setValue(self, value: float):
        value = min(self.max_val, max(self.min_val, value))
        self.setCurrentText(str(round(value, 2)))

    def changeByDelta(self, delta: float, multiplier = 0.01):
        if isinstance(multiplier, Callable):
            multiplier = multiplier()
        self.setValue(self.value() + delta * multiplier)


class SmallSizeComboBox(SizeComboBox):
    pass


class FontWeightComboBox(QComboBox):
    """Combobox that lists available font weights for a given family.

    Emits param_changed('font_weight', <int 100-900>) when the user picks a weight.
    Display is intentionally compact – just the numeric weight value.
    """

    param_changed = Signal(str, int)

    # Standard CSS weights used as a fallback when QFontDatabase returns nothing
    _STANDARD_WEIGHTS = [100, 200, 300, 400, 500, 600, 700, 800, 900]

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._current_family: str = ''
        self.setFixedWidth(58)
        self.setToolTip("Font Weight")
        self.currentIndexChanged.connect(self._on_index_changed)
        self._populate_standard()

    # ------------------------------------------------------------------
    # public helpers
    # ------------------------------------------------------------------

    def update_for_family(self, family: str) -> None:
        """Re-populate items with the weights available for *family*."""
        if family == self._current_family:
            return
        self._current_family = family
        prev_weight = self.current_weight()

        self.blockSignals(True)
        self.clear()

        styles = QFontDatabase.styles(family)
        weights_seen: set = set()

        if styles:
            for style in styles:
                raw_w = QFontDatabase.weight(family, style)
                if raw_w < 0:
                    continue
                # Normalise to the nearest 100
                w = round(raw_w / 100) * 100
                w = max(100, min(900, w))
                if w not in weights_seen:
                    weights_seen.add(w)
            weights = sorted(weights_seen)
        else:
            weights = self._STANDARD_WEIGHTS

        for w in weights:
            self.addItem(str(w), userData=w)

        self.blockSignals(False)
        self.set_weight(prev_weight)

    def set_weight(self, weight: int) -> None:
        """Select the item whose userData is closest to *weight*."""
        if weight is None:
            weight = 400
        best_idx, best_diff = 0, 9999
        for i in range(self.count()):
            diff = abs((self.itemData(i) or 0) - weight)
            if diff < best_diff:
                best_diff, best_idx = diff, i
        self.blockSignals(True)
        self.setCurrentIndex(best_idx)
        self.blockSignals(False)

    def current_weight(self) -> int:
        data = self.itemData(self.currentIndex())
        return data if data is not None else 400

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _populate_standard(self) -> None:
        self.blockSignals(True)
        for w in self._STANDARD_WEIGHTS:
            self.addItem(str(w), userData=w)
        self.setCurrentIndex(3)  # 400 Regular
        self.blockSignals(False)

    def _on_index_changed(self) -> None:
        self.param_changed.emit('font_weight', self.current_weight())

    def wheelEvent(self, event):
        # Prevent accidental scroll-wheel changes
        event.ignore()