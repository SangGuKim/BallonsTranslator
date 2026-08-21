import copy
from typing import Iterable, List, Union

from qtpy import QT6
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QToolTip,
    QVBoxLayout,
)
from qtpy.QtCore import QSignalBlocker, Signal, Qt
from qtpy.QtGui import (
    QActionGroup,
    QColor,
    QFocusEvent,
    QFont,
    QFontDatabase,
    QIcon,
    QKeyEvent,
    QPainter,
    QPen,
    QPixmap,
    QTextCursor,
)

from ballontranslator.utils import shared
from ballontranslator.utils import config as C
from ballontranslator.utils.config import save_text_styles
from ballontranslator.utils.fontformat import (
    FontFormat,
    FontWeight,
    LineSpacingType,
    pt2px,
    font_weight_from_qt,
)
from ...custom_widget import (
    AlignmentChecker,
    CheckableLabel,
    ColorPickerLabel,
    FontWeightComboBox as RegistryFontWeightComboBox,
    NestedColorPickerLabel,
    QFontChecker,
    SizeComboBox,
    SizeControlLabel,
    TextCheckerLabel,
    Widget,
)
from ..item import TextBlkItem, storage_font_family
from ..annotations import (
    DEFAULT_EMPHASIS_POSITION,
    EMPHASIS_GLYPHS,
    EMPHASIS_POSITIONS,
    EMPHASIS_STYLES,
    OLDSTYLE_NUMS,
    RubyValidationError,
)
from .advanced import TextAdvancedFormatPanel
from ..transforms.edit_session import TextTransformEditSession
from ..transforms.panel import TextTransformPanel
from .presets import TextStylePresetPanel
from .commands import handle_ffmt_change, restore_canvas_view_focus
from ... import shared_widget as SW
from ...misc import DARKFILL_ACTIVE, LIGHTFILL_ACTIVE, themed_icon_url

def _icon_fill_color(fill_attr: str) -> str:
    return fill_attr.split('"')[1]


def mixed_checkbox_style():
    icon_fill = DARKFILL_ACTIVE if C.pcfg.darkmode else LIGHTFILL_ACTIVE
    icon_color = _icon_fill_color(icon_fill)
    return f"""
QFontChecker {{
    max-width: 34px;
}}
QFontChecker::indicator:indeterminate {{
    width: 30px;
    height: 30px;
    border: 2px solid {icon_color};
    background-color: {icon_color};
}}
QFontChecker#FontBoldChecker::indicator:indeterminate {{
    image: url({themed_icon_url('fontfmt_bold_activate.svg')});
}}
QFontChecker#FontItalicChecker::indicator:indeterminate {{
    image: url({themed_icon_url('fontfmt_italic_activate.svg')});
}}
QFontChecker#FontUnderlineChecker::indicator:indeterminate {{
    image: url({themed_icon_url('fontfmt_underline_activate.svg')});
}}
QFontChecker#FontVerticalChecker::indicator:indeterminate {{
    image: url({themed_icon_url('fontfmt_vertical_activate.svg')});
}}
AlignmentChecker {{
    margin: 0px;
}}
AlignmentChecker::indicator:indeterminate {{
    height: 28px;
    width: 28px;
    border: 2px solid {icon_color};
    background-color: {icon_color};
}}
AlignmentChecker#AlignLeftChecker::indicator:indeterminate {{
    border-right: none;
    min-width: 36px;
    max-width: 36px;
    image: url({themed_icon_url('fontfmt_alignl_activate.svg')});
}}
AlignmentChecker#AlignCenterChecker::indicator:indeterminate {{
    border-right: none;
    border-left: none;
    min-width: 36px;
    max-width: 36px;
    image: url({themed_icon_url('fontfmt_alignc_activate.svg')});
}}
AlignmentChecker#AlignRightChecker::indicator:indeterminate {{
    border-left: none;
    min-width: 35px;
    max-width: 35px;
    image: url({themed_icon_url('fontfmt_alignr_activate.svg')});
}}
"""


def set_checker_mixed_style(checker):
    checker.setStyleSheet(mixed_checkbox_style())


def reset_checker_style(checker):
    if hasattr(checker, 'resetStyleSheet'):
        checker.resetStyleSheet()
    else:
        checker.setStyleSheet("")


COLOR_FIELDS = {'frgb', 'srgb', 'shadow_color', 'gradient_start_color', 'gradient_end_color'}


def _format_weight(font_format: FontFormat):
    weight = font_format.font_weight
    if weight is None:
        weight = 700 if font_format.bold else 400
    return int(weight)


def _format_bold(font_format: FontFormat):
    return bool(font_format.bold) or _format_weight(font_format) >= 700


def _color_tuple(value):
    if hasattr(value, 'tolist'):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        return value
    return tuple(int(round(float(channel))) for channel in value)


def format_values_equal(left, right):
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            return False
        return all(format_values_equal(lval, rval) for lval, rval in zip(left, right))
    return left == right


def format_field_equal(key: str, left_format: FontFormat, right_format: FontFormat):
    if key in COLOR_FIELDS:
        return _color_tuple(left_format[key]) == _color_tuple(right_format[key])
    if key == 'font_weight':
        return _format_weight(left_format) == _format_weight(right_format)
    if key == 'bold':
        return _format_bold(left_format) == _format_bold(right_format)
    return format_values_equal(left_format[key], right_format[key])


class LineEdit(QLineEdit):

    return_pressed_wochange = Signal()
    return_pressed = Signal()

    def __init__(self, content: str = None, parent = None):
        super().__init__(content, parent)
        self.textChanged.connect(self.on_text_changed)
        self._text_changed = False
        self.editingFinished.connect(self.on_editing_finished)
        # self.returnPressed.connect(self.on_return_pressed)

    def on_text_changed(self):
        self._text_changed = True

    def on_editing_finished(self):
        self._text_changed = False

    def focusOutEvent(self, e: QFocusEvent) -> None:
        self._text_changed = False
        return super().focusOutEvent(e)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        super().keyPressEvent(e)
        if e.key() == Qt.Key.Key_Return:
            self.return_pressed.emit()
            if not self._text_changed:
                self.return_pressed_wochange.emit()


class IncrementalBtn(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFixedSize(12, 12)


class AlignmentBtnGroup(QFrame):
    param_changed = Signal(str, int)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.alignLeftChecker = AlignmentChecker(self)
        self.alignLeftChecker.clicked.connect(self.alignBtnPressed)
        self.alignCenterChecker = AlignmentChecker(self)
        self.alignCenterChecker.clicked.connect(self.alignBtnPressed)
        self.alignRightChecker = AlignmentChecker(self)
        self.alignRightChecker.clicked.connect(self.alignBtnPressed)
        self.alignLeftChecker.setObjectName("AlignLeftChecker")
        self.alignRightChecker.setObjectName("AlignRightChecker")
        self.alignCenterChecker.setObjectName("AlignCenterChecker")

        hlayout = QHBoxLayout(self)
        hlayout.addWidget(self.alignLeftChecker)
        hlayout.addWidget(self.alignCenterChecker)
        hlayout.addWidget(self.alignRightChecker)
        hlayout.setSpacing(0)
        margins = hlayout.contentsMargins()
        hlayout.setContentsMargins(margins.left(), margins.top(), 0, margins.bottom())

    def _checkers(self):
        return [self.alignLeftChecker, self.alignCenterChecker, self.alignRightChecker]

    def setMixed(self):
        for checker in self._checkers():
            checker.blockSignals(True)
            checker.setTristate(True)
            checker.setCheckState(Qt.CheckState.PartiallyChecked)
            set_checker_mixed_style(checker)
            checker.blockSignals(False)
        hlayout.setContentsMargins(8, 8, 8, 8)

    def alignBtnPressed(self):
        for checker in self._checkers():
            checker.setTristate(False)
            reset_checker_style(checker)
        btn = self.sender()
        if btn == self.alignLeftChecker:
            self.alignLeftChecker.setChecked(True)
            self.alignCenterChecker.setChecked(False)
            self.alignRightChecker.setChecked(False)
            self.param_changed.emit('alignment', 0)
        elif btn == self.alignRightChecker:
            self.alignRightChecker.setChecked(True)
            self.alignCenterChecker.setChecked(False)
            self.alignLeftChecker.setChecked(False)
            self.param_changed.emit('alignment', 2)
        else:
            self.alignCenterChecker.setChecked(True)
            self.alignLeftChecker.setChecked(False)
            self.alignRightChecker.setChecked(False)
            self.param_changed.emit('alignment', 1)

    def setAlignment(self, alignment: int):
        for checker in self._checkers():
            checker.setTristate(False)
            reset_checker_style(checker)
        if alignment == 0:
            self.alignLeftChecker.setChecked(True)
            self.alignCenterChecker.setChecked(False)
            self.alignRightChecker.setChecked(False)
        elif alignment == 1:
            self.alignLeftChecker.setChecked(False)
            self.alignCenterChecker.setChecked(True)
            self.alignRightChecker.setChecked(False)
        else:
            self.alignLeftChecker.setChecked(False)
            self.alignCenterChecker.setChecked(False)
            self.alignRightChecker.setChecked(True)


class EmphasisToolButton(QToolButton):
    """Toggle emphasis and select its CSS-compatible mark and position."""

    emphasis_changed = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_style = 'filled dot'
        self._position = DEFAULT_EMPHASIS_POSITION
        self.setObjectName('FontEmphasisToolButton')
        self.setCheckable(True)
        self.setToolTip(self.tr('Emphasis Marks'))
        popup_modes = getattr(QToolButton, 'ToolButtonPopupMode', QToolButton)
        self.setPopupMode(popup_modes.MenuButtonPopup)

        menu = QMenu(self)
        menu.setObjectName('FontEmphasisMenu')
        section_font = menu.font()
        section_font.setBold(True)
        marks_header = menu.addAction(self.tr('Marks'))
        marks_header.setEnabled(False)
        marks_header.setFont(section_font)
        self._style_group = QActionGroup(self)
        self._style_group.setExclusive(True)
        self._style_actions = {}
        style_labels = (
            self.tr('Filled Dot'),
            self.tr('Open Dot'),
            self.tr('Filled Circle'),
            self.tr('Open Circle'),
            self.tr('Filled Double Circle'),
            self.tr('Open Double Circle'),
            self.tr('Filled Triangle'),
            self.tr('Open Triangle'),
            self.tr('Filled Sesame'),
            self.tr('Open Sesame'),
        )
        for label, style in zip(style_labels, EMPHASIS_STYLES[1:]):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setData(style)
            self._style_group.addAction(action)
            self._style_actions[style] = action
        self._style_group.triggered.connect(self._on_style_selected)

        position_header = menu.addAction(self.tr('Position'))
        position_header.setEnabled(False)
        position_header.setFont(section_font)
        self._position_group = QActionGroup(self)
        self._position_group.setExclusive(True)
        self._position_actions = {}
        position_labels = (
            self.tr('Over / Right'),
            self.tr('Under / Right'),
            self.tr('Over / Left'),
            self.tr('Under / Left'),
        )
        for label, position in zip(position_labels, EMPHASIS_POSITIONS):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setData(position)
            self._position_group.addAction(action)
            self._position_actions[position] = action

        self._position_group.triggered.connect(self._on_position_selected)
        menu.aboutToShow.connect(self._update_menu_icons)
        self.setMenu(menu)
        self._update_menu_icons()
        self._style_actions[self._selected_style].setChecked(True)
        self._position_actions[self._position].setChecked(True)
        self.clicked.connect(self._on_toggled)

    def values(self) -> tuple[str, str]:
        style = self._selected_style if self.isChecked() else 'none'
        return style, self._position

    def _update_menu_icons(self) -> None:
        icon_size = 24
        ratio = max(1.0, self.devicePixelRatioF())
        font = self.font()
        font.setPixelSize(20)
        color = self.palette().text().color()
        icon_key = (ratio, font.toString(), color.rgba())
        if icon_key == getattr(self, '_menu_icon_key', None):
            return
        self._menu_icon_key = icon_key
        for style, action in self._style_actions.items():
            pixmap = QPixmap(
                round(icon_size * ratio), round(icon_size * ratio)
            )
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(
                0, 0, icon_size, icon_size,
                Qt.AlignmentFlag.AlignCenter,
                EMPHASIS_GLYPHS[style],
            )
            painter.end()
            action.setIcon(QIcon(pixmap))

    def set_values(self, style: str, position: str) -> None:
        enabled = style in self._style_actions
        if enabled:
            self._selected_style = style
            self._style_actions[style].setChecked(True)
        if position in self._position_actions:
            self._position = position
            self._position_actions[position].setChecked(True)
        with QSignalBlocker(self):
            self.setChecked(enabled)
        self.update()

    def _on_toggled(self, _checked: bool) -> None:
        self.emphasis_changed.emit(*self.values())

    def _on_style_selected(self, action) -> None:
        self._selected_style = str(action.data())
        self.setChecked(True)
        self.update()
        self.emphasis_changed.emit(*self.values())

    def _on_position_selected(self, action) -> None:
        self._position = str(action.data())
        if self.isChecked():
            self.emphasis_changed.emit(*self.values())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        arrow_width = 11
        icon_width = max(1, self.width() - arrow_width)
        icon_rect = self.rect()
        icon_rect.setWidth(icon_width)
        if self.isChecked() and self.isEnabled():
            painter.fillRect(
                icon_rect.adjusted(2, 2, -2, -2), QColor(30, 147, 229)
            )
        if self.isEnabled() and (self.isChecked() or self.underMouse()):
            painter.setPen(QPen(QColor(30, 147, 229), 2))
            painter.drawRect(icon_rect.adjusted(1, 1, -1, -1))
        color = (
            QColor('white')
            if self.isChecked() and self.isEnabled()
            else self.palette().text().color()
        )
        if not self.isEnabled():
            color.setAlpha(110)
        painter.setPen(color)

        glyph_font = self.font()
        glyph_font.setPixelSize(16)
        mark_font = self.font()
        mark_font.setPixelSize(12)
        painter.setFont(mark_font)
        mark = EMPHASIS_GLYPHS[self._selected_style]
        mark_bounds = painter.fontMetrics().tightBoundingRect(mark)
        mark_x = round((icon_width - mark_bounds.width()) / 2 - mark_bounds.left())
        mark_y = self.height() - 3 - mark_bounds.bottom()
        painter.drawText(mark_x, mark_y, mark)

        glyph = 'あ'
        glyph_bottom = mark_y + mark_bounds.top() - 1
        painter.setFont(glyph_font)
        glyph_bounds = painter.fontMetrics().tightBoundingRect(glyph)
        available_height = max(1, glyph_bottom - 1)
        if glyph_bounds.height() > 0:
            fitted_size = round(
                glyph_font.pixelSize()
                * available_height
                / glyph_bounds.height()
            )
            glyph_font.setPixelSize(min(19, max(16, fitted_size)))
            painter.setFont(glyph_font)
            glyph_bounds = painter.fontMetrics().tightBoundingRect(glyph)
        glyph_x = round(
            (icon_width - glyph_bounds.width()) / 2 - glyph_bounds.left()
        )
        glyph_y = glyph_bottom - glyph_bounds.bottom()
        painter.drawText(glyph_x, glyph_y, glyph)

        separator = QColor(color)
        separator.setAlpha(90)
        painter.setPen(QPen(separator, 1))
        painter.drawLine(icon_width, 3, icon_width, self.height() - 4)
        painter.setPen(QPen(color, 1.2))
        arrow_x = self.width() - arrow_width // 2
        arrow_y = self.height() // 2
        painter.drawLine(arrow_x - 3, arrow_y - 1, arrow_x, arrow_y + 2)
        painter.drawLine(arrow_x, arrow_y + 2, arrow_x + 3, arrow_y - 1)


class FormatGroupBtn(QFrame):
    param_changed = Signal(str, object)
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.boldBtn = QFontChecker(self)
        self.boldBtn.setObjectName("FontBoldChecker")
        self.boldBtn.clicked.connect(self.setBold)
        self.italicBtn = QFontChecker(self)
        self.italicBtn.setObjectName("FontItalicChecker")
        self.italicBtn.clicked.connect(self.setItalic)
        self.underlineBtn = QFontChecker(self)
        self.underlineBtn.setObjectName("FontUnderlineChecker")
        self.underlineBtn.clicked.connect(self.setUnderline)
        self.emphasisBtn = EmphasisToolButton(self)
        hlayout = QHBoxLayout(self)
        hlayout.addWidget(self.boldBtn)
        hlayout.addWidget(self.italicBtn)
        hlayout.addWidget(self.underlineBtn)
        hlayout.addWidget(self.emphasisBtn)
        hlayout.setSpacing(0)

    def setMixed(self, btn: QFontChecker):
        btn.blockSignals(True)
        btn.setTristate(True)
        btn.setCheckState(Qt.CheckState.PartiallyChecked)
        btn.setProperty('mixed', True)
        set_checker_mixed_style(btn)
        btn.blockSignals(False)

    def clearMixed(self):
        for btn in (self.boldBtn, self.italicBtn, self.underlineBtn):
            btn.blockSignals(True)
            btn.setProperty('mixed', False)
            reset_checker_style(btn)
            btn.setTristate(False)
            btn.blockSignals(False)

    def setBold(self):
        self.clearMixed()
        self.param_changed.emit('font_weight', 700 if self.boldBtn.isChecked() else 400)

    def setItalic(self):
        self.clearMixed()
        self.param_changed.emit('italic', self.italicBtn.isChecked())

    def setUnderline(self):
        self.clearMixed()
        self.param_changed.emit('underline', self.underlineBtn.isChecked())


class FontSizeBox(QFrame):
    param_changed = Signal(str, float)
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.upBtn = IncrementalBtn(self)
        self.upBtn.setObjectName("FsizeIncrementUp")
        self.downBtn = IncrementalBtn(self)
        self.downBtn.setObjectName("FsizeIncrementDown")
        self.upBtn.clicked.connect(self.onUpBtnClicked)
        self.downBtn.clicked.connect(self.onDownBtnClicked)
        self.fcombobox = SizeComboBox([1, 1000], 'font_size', self)
        self.fcombobox.setObjectName("FontFormatSizeBox")
        self.fcombobox.addItems([
            "5", "5.5", "6.5", "7.5", "8", "9", "10", "10.5",
            "11", "12", "14", "16", "18", "20", '22', "26", "28",
            "36", "48", "56", "72", "93", "123", "163"
        ])
        self.fcombobox.param_changed.connect(self.param_changed)

        hlayout = QHBoxLayout(self)
        vlayout = QVBoxLayout()
        vlayout.addWidget(self.upBtn)
        vlayout.addWidget(self.downBtn)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(0)
        hlayout.addLayout(vlayout)
        hlayout.addWidget(self.fcombobox)
        hlayout.setSpacing(3)
        hlayout.setContentsMargins(0, 0, 0, 0)

    def getFontSize(self) -> str:
        return self.fcombobox.currentText()

    def onUpBtnClicked(self):
        raito = 1.25
        size = self.getFontSize()
        if not size.strip():
            self.param_changed.emit('rel_font_size', raito)
            return
        multi_size=False
        marker = ''
        if size.endswith(("+", "*")):
            marker = size[-1]
            size = size[:-1]
            multi_size=True
        size = float(size)
        newsize = int(round(size * raito))
        if newsize == size:
            newsize += 1
        newsize = min(1000, newsize)
        if newsize != size:
            if not multi_size:
                self.param_changed.emit('font_size', newsize)
                self.fcombobox.setCurrentText(str(newsize))
            else:
                self.param_changed.emit('rel_font_size', raito)
                self.fcombobox.setCurrentText(str(newsize) + marker)

    def onDownBtnClicked(self):
        raito = 0.75
        size = self.getFontSize()
        if not size.strip():
            self.param_changed.emit('rel_font_size', raito)
            return
        multi_size=False
        marker = ''
        if size.endswith(("+", "*")):
            marker = size[-1]
            size = size[:-1]
            multi_size=True
        size = float(size)
        newsize = int(round(size * raito))
        if newsize == size:
            newsize -= 1
        newsize = max(1, newsize)
        if newsize != size:
            if not multi_size:
                self.param_changed.emit('font_size', newsize)
                self.fcombobox.setCurrentText(str(newsize))
            else:
                self.param_changed.emit('rel_font_size', raito)
                self.fcombobox.setCurrentText(str(newsize) + marker)
    

class FontFamilyComboBox(QComboBox):
    def _change_font_size(self, ratio: float) -> None:
        size_text = self.getFontSize()
        multi_size = size_text.endswith('+')
        size = float(size_text[:-1] if multi_size else size_text)
        new_size = int(round(size * ratio))
        if new_size == size:
            new_size += 1 if ratio > 1 else -1
        new_size = min(1000, max(1, new_size))
        if new_size == size:
            return

        display_text = f'{new_size}+' if multi_size else str(new_size)
        with QSignalBlocker(self.fcombobox):
            self.fcombobox.setCurrentText(display_text)
        # The arrows are part of the editable size control. Keep focus on that
        # control so effects and the live text use the same unfocused layout.
        self.fcombobox.setFocus()
        self.param_changed.emit(
            'rel_font_size' if multi_size else 'font_size',
            ratio if multi_size else new_size,
        )

    def onUpBtnClicked(self) -> None:
        self._change_font_size(1.25)

    def onDownBtnClicked(self) -> None:
        self._change_font_size(0.75)


class FontWeightComboBox(QComboBox):
    param_changed = Signal(str, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        labels = {
            FontWeight.Thin: self.tr('Thin'),
            FontWeight.ExtraLight: self.tr('Extra Light'),
            FontWeight.Light: self.tr('Light'),
            FontWeight.Normal: self.tr('Normal'),
            FontWeight.Medium: self.tr('Medium'),
            FontWeight.DemiBold: self.tr('Demi Bold'),
            FontWeight.Bold: self.tr('Bold'),
            FontWeight.ExtraBold: self.tr('Extra Bold'),
            FontWeight.Black: self.tr('Black'),
        }
        for weight in FontWeight:
            self.addItem(labels[weight], int(weight))
        self.activated.connect(self._on_activated)
        self.set_weight(FontWeight.Normal)

    def _on_activated(self, index: int) -> None:
        self.param_changed.emit('font_weight', self.weight())

    def weight(self) -> FontWeight:
        return FontWeight(int(self.currentData()))

    def set_weight(self, weight: FontWeight) -> None:
        index = self.findData(int(FontWeight(weight)))
        if index >= 0:
            self.setCurrentIndex(index)


_FONT_WEIGHT_SUFFIXES = (
    ('extra light', FontWeight.ExtraLight),
    ('extra bold', FontWeight.ExtraBold),
    ('semi bold', FontWeight.DemiBold),
    ('demi bold', FontWeight.DemiBold),
    ('extralight', FontWeight.ExtraLight),
    ('extrabold', FontWeight.ExtraBold),
    ('semibold', FontWeight.DemiBold),
    ('demibold', FontWeight.DemiBold),
    ('regular', FontWeight.Normal),
    ('normal', FontWeight.Normal),
    ('medium', FontWeight.Medium),
    ('light', FontWeight.Light),
    ('black', FontWeight.Black),
    ('bold', FontWeight.Bold),
    ('thin', FontWeight.Thin),
)


def _split_weight_family_name(
    family: str,
) -> tuple[str, FontWeight] | tuple[None, None]:
    """Split a family only when it has a recognized final weight token.

    >>> _split_weight_family_name('Inter Display SemiBold')
    ('Inter Display', <FontWeight.DemiBold: 600>)
    >>> _split_weight_family_name('Blackadder ITC')
    (None, None)
    """
    folded = family.casefold()
    for suffix, weight in _FONT_WEIGHT_SUFFIXES:
        marker = f' {suffix}'
        if folded.endswith(marker):
            return family[:-len(marker)], weight
    return None, None


def _font_database() -> Union[type[QFontDatabase], QFontDatabase]:
    return QFontDatabase if QT6 else QFontDatabase()


def _family_weights(
    database: Union[type[QFontDatabase], QFontDatabase],
    family: str,
) -> set[FontWeight]:
    weights = set()
    for style in database.styles(family):
        weights.add(font_weight_from_qt(int(database.weight(family, style))))
    return weights


def _weight_family_aliases(
    font_families: Iterable[str],
) -> dict[str, tuple[str, FontWeight]]:
    """Return suffix aliases that resolve to a base family's same face."""
    families = list(font_families)
    by_folded_name = {family.casefold(): family for family in families}
    database = _font_database()
    weights_by_family = {}
    aliases = {}
    for alias in families:
        base_name, weight = _split_weight_family_name(alias)
        if base_name is None:
            continue
        base = by_folded_name.get(base_name.casefold())
        if base is None:
            continue
        if base not in weights_by_family:
            weights_by_family[base] = _family_weights(database, base)
        if alias not in weights_by_family:
            weights_by_family[alias] = _family_weights(database, alias)
        base_weights = weights_by_family[base]
        alias_weights = weights_by_family[alias]
        if (
            weight in base_weights
            and alias_weights == {weight}
        ):
            aliases[alias] = (base, weight)
    return aliases


class FontFamilyComboBox(QComboBox):
    param_changed = Signal(str, object)
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setEditable(True)
        self.view().setUniformItemSizes(True)
        self.currentIndexChanged.connect(self.on_fontfamily_changed)
        self.lineedit = lineedit = LineEdit(parent=self)
        lineedit.return_pressed.connect(self.on_return_pressed)
        lineedit.editingFinished.connect(self.apply_fontfamily)
        self.setLineEdit(lineedit)
        self.return_pressed = False
        self._using_font_entries = False
        self.weight_aliases = {}
        self.canonical_weight_aliases = {}
        self._weight_alias_source = None

    def _preview_font(self, family: str) -> QFont:
        font = QFont(self.view().font())
        font.setFamily(family)
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() + 4)
        elif font.pixelSize() > 0:
            font.setPixelSize(font.pixelSize() + 5)
        return font
        
    def apply_fontfamily(self) -> None:
        ffamily = self._current_storage_family()
        if ffamily:
            self.param_changed.emit('font_family', ffamily)

    def update_font_list(self, font_list: Iterable[str]) -> None:
        font_list = list(font_list)
        alias_source = frozenset(shared.FONT_FAMILIES or font_list)
        if alias_source != self._weight_alias_source:
            self.weight_aliases = _weight_family_aliases(alias_source)
            self._weight_alias_source = alias_source
        visible_families = set(font_list)
        self.canonical_weight_aliases = {
            alias: target
            for alias, target in self.weight_aliases.items()
            if target[0] in visible_families
        }
        font_list = [
            family
            for family in font_list
            if family not in self.canonical_weight_aliases
        ]
        if font_list == [self.itemText(i) for i in range(self.count())]:
            return
        self._using_font_entries = False
        self.currentIndexChanged.disconnect(self.on_fontfamily_changed)
        current_font = self._current_storage_family() or getattr(C.active_format, 'font_family', '')
        self.clear()
        for family in font_list:
            index = self.count()
            self.addItem(family)
            self.setItemData(index, self._preview_font(family), Qt.ItemDataRole.FontRole)
        self.set_displayed_font(current_font)
        self.currentIndexChanged.connect(self.on_fontfamily_changed)

    def set_displayed_font(self, font_family: str) -> None:
        """Show a family without adding a filtered font back to the popup."""
        index = self.findText(font_family)
        self.setCurrentIndex(index)
        if index < 0:
            self.setEditText(font_family)

    def update_font_entries(self, entries: Iterable[object]) -> None:
        """Update picker with registry entries.

        The visible text is localized ``display_family`` while the emitted value
        remains the storage-safe canonical family. Pseudo custom groups resolve
        to the selected face canonical for the active weight.
        """

        self._using_font_entries = True
        self.currentIndexChanged.disconnect(self.on_fontfamily_changed)
        current_font = self._current_storage_family() or getattr(C.active_format, 'font_family', '')
        self.clear()
        for entry in entries:
            index = self.count()
            self.addItem(entry.display_family, entry)
            preview_font = self._preview_font(entry.qt_family)
            if len(entry.weights) == 1:
                try:
                    preview_font.setWeight(QFont.Weight(int(entry.weights[0])))
                except (TypeError, ValueError):
                    preview_font.setWeight(int(entry.weights[0]))
            self.setItemData(index, preview_font, Qt.ItemDataRole.FontRole)
            details = [entry.source, f'qt: {entry.qt_family}']
            if entry.weights:
                details.append('weights: ' + ', '.join(str(weight) for weight in entry.weights))
            if entry.is_pseudo_group:
                details.append('stores selected face canonical')
            self.setItemData(index, '; '.join(details), Qt.ItemDataRole.ToolTipRole)
        self.set_current_family(current_font)
        self.currentIndexChanged.connect(self.on_fontfamily_changed)

    def set_current_family(self, family: str):
        if not family:
            self.setCurrentText('')
            return
        target_entry = None
        target_face = None
        target_weight = getattr(C.active_format, 'font_weight', None)
        if shared.FONT_REGISTRY is not None:
            resolved = shared.FONT_REGISTRY.resolve_family(family, target_weight)
            target_entry = resolved.entry
            target_face = resolved.face
        for index in range(self.count()):
            entry = self.itemData(index)
            if not hasattr(entry, 'canonical_family'):
                continue
            entry_families = {entry.canonical_family, entry.display_family, entry.qt_family}
            matches_face = target_face is not None and target_face in entry.faces
            matches_family = entry is target_entry or matches_face or family in entry_families
            matches_weight = (
                entry is target_entry
                or matches_face
                or target_weight is None
                or not entry.weights
                or int(target_weight) in {int(weight) for weight in entry.weights}
            )
            if matches_family and matches_weight:
                self.setCurrentIndex(index)
                self.lineEdit().setText(self.itemText(index))
                return
        self.set_displayed_font(family)

    def _current_storage_family(self):
        entry = self.itemData(self.currentIndex()) if self._using_font_entries else None
        if hasattr(entry, 'storage_family_for_weight'):
            weight = getattr(C.active_format, 'font_weight', None)
            return entry.storage_family_for_weight(weight)
        return self.currentText().strip()

    def current_entry(self):
        entry = self.itemData(self.currentIndex()) if self._using_font_entries else None
        return entry if hasattr(entry, 'weights') else None

    def canonical_family(
        self, font_family: str
    ) -> tuple[str, FontWeight | None]:
        return self.canonical_weight_aliases.get(
            font_family, (font_family, None)
        )

    def on_return_pressed(self):
        self.return_pressed = True
        self.apply_fontfamily()

    def on_fontfamily_changed(self):
        if self.return_pressed:
            self.return_pressed = False
        else:
            self.apply_fontfamily()


class FontFormatPanel(Widget):
    
    textblk_item: TextBlkItem = None
    textblk_items: List[TextBlkItem] = None
    text_cursor: QTextCursor = None
    global_format: FontFormat = None
    restoring_textblk: bool = False

    def __init__(self, app: QApplication, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.app = app

        self.vlayout = QVBoxLayout(self)
        self.vlayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.familybox = FontFamilyComboBox(parent=self)
        self.familybox.setContentsMargins(0, 0, 0, 0)
        self.familybox.setObjectName("FontFamilyBox")
        self.familybox.setToolTip(self.tr("Font Family"))
        self.familybox.param_changed.connect(self.on_param_changed)
        self.familybox.param_changed.connect(self._on_family_changed_for_weight)
        self.familybox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if shared.FONT_FAMILIES:
            self.familybox.update_font_list(
                shared.get_filtered_font_list(shared.FONT_FAMILIES)
            )

        self.fontsizebox = FontSizeBox(self)
        self.fontsizebox.setToolTip(self.tr("Font Size"))
        self.fontsizebox.setObjectName("FontSizeBox")
        self.fontsizebox.fcombobox.setToolTip(self.tr("Change font size"))
        self.fontsizebox.param_changed.connect(self.on_param_changed)

        self.fontWeightCombo = RegistryFontWeightComboBox(self)
        self.fontWeightCombo.setToolTip(self.tr("Font Weight"))
        self.fontWeightCombo.param_changed.connect(self.on_font_weight_changed)
        self.fontWeightBox = self.fontWeightCombo
        self.group_font_faces = True
        
        self.lineSpacingLabel = SizeControlLabel(self, direction=1, transparent_bg=False)
        self.lineSpacingLabel.setObjectName("lineSpacingLabel")
        self.lineSpacingLabel.size_ctrl_changed.connect(self.onLineSpacingCtrlChanged)
        self.lineSpacingLabel.btn_released.connect(lambda : self.on_param_changed('line_spacing', self.lineSpacingBox.value()))

        self.lineSpacingBox = SizeComboBox([0, 100], 'line_spacing', self)
        self.lineSpacingBox.setObjectName("CompactFormatComboBox")
        self.lineSpacingBox.setObjectName("FontFormatSizeBox")
        self.lineSpacingBox.addItems(["1.0", "1.1", "1.2"])
        self.lineSpacingBox.setToolTip(self.tr("Change line spacing"))
        self.lineSpacingBox.setFixedWidth(48)
        self.lineSpacingBox.param_changed.connect(self.on_param_changed)

        linesp_hlayout = QHBoxLayout()
        linesp_hlayout.addWidget(self.lineSpacingLabel)
        linesp_hlayout.addWidget(self.lineSpacingBox)
        linesp_hlayout.setSpacing(7)
        
        # One nested swatch: the outer rectangle is the stroke color, the inner
        # square is the font color. Qt routes clicks to whichever of the two the
        # cursor is over, so both keep the plain ColorPickerLabel behaviour.
        self.strokeColorPicker = NestedColorPickerLabel(
            self, param_name='srgb', inner_param_name='frgb'
        )
        self.colorPicker = self.strokeColorPicker.inner
        self.colorPicker = ColorPickerLabel(self, param_name='frgb')
        self.colorPicker.setObjectName('FontFormatColorPicker')
        self.colorPicker.setToolTip(self.tr("Change font color"))
        self.colorPicker.changingColor.connect(self.changingColor)
        self.colorPicker.colorChanged.connect(self.onColorLabelChanged)
        self.colorPicker.apply_color.connect(self.on_apply_color)

        self.alignBtnGroup = AlignmentBtnGroup(self)
        self.alignBtnGroup.param_changed.connect(self.on_param_changed)

        self.formatBtnGroup = FormatGroupBtn(self)
        self.formatBtnGroup.param_changed.connect(self.on_format_btn_changed)

        self.verticalChecker = QFontChecker(self)
        self.verticalChecker.setObjectName("FontVerticalChecker")
        self.verticalChecker.clicked.connect(lambda : self.on_param_changed('vertical', self.verticalChecker.isChecked()))

        self._tate_chu_yoko_tooltip = self.tr(
            'Combine the selected text into one upright vertical cell'
        )
        self.tateChuYokoChecker = QFontChecker(self)
        self.tateChuYokoChecker.setObjectName("FontTateChuYokoChecker")
        self.tateChuYokoChecker.setToolTip(self._tate_chu_yoko_tooltip)
        self.tateChuYokoChecker.clicked.connect(
            self.on_tate_chu_yoko_changed
        )
        self.romanAlignmentChecker = QFontChecker(self)
        self.romanAlignmentChecker.setObjectName(
            'FontRomanAlignmentChecker'
        )
        self.romanAlignmentChecker.setToolTip(
            self.tr('Standard Vertical Roman Alignment')
        )
        self.romanAlignmentChecker.clicked.connect(
            lambda checked: self.on_param_changed(
                'standard_vertical_roman_alignment', checked
            )
        )

        self.strokeWidthBox = SizeComboBox([0, 10], 'stroke_width', self)
        self.strokeWidthBox.setObjectName("CompactFormatComboBox")
        self.strokeWidthBox.setObjectName("FontFormatSizeBox")
        self.strokeWidthBox.addItems(["0.1"])
        self.strokeWidthBox.setToolTip(self.tr("Change stroke width"))
        self.strokeWidthBox.setFixedWidth(48)
        self.strokeWidthBox.param_changed.connect(self.on_param_changed)

        self.fontStrokeLabel = SizeControlLabel(self, 0, self.tr("Stroke"))
        self.fontStrokeLabel.setObjectName("fontStrokeLabel")
        self.fontStrokeLabel.size_ctrl_changed.connect(self.strokeWidthBox.changeByDelta)
        self.fontStrokeLabel.btn_released.connect(lambda : self.on_param_changed('stroke_width', self.strokeWidthBox.value()))
        
        self.strokeColorPicker = ColorPickerLabel(self, param_name='srgb')
        self.strokeColorPicker.setObjectName('FontFormatColorPicker')
        self.strokeColorPicker.setToolTip(self.tr("Change stroke color"))
        self.strokeColorPicker.changingColor.connect(self.changingColor)
        self.strokeColorPicker.colorChanged.connect(self.onColorLabelChanged)
        self.strokeColorPicker.apply_color.connect(self.on_apply_color)

        stroke_hlayout = QHBoxLayout()
        stroke_hlayout.addWidget(self.fontStrokeLabel)
        stroke_hlayout.addWidget(self.strokeWidthBox)
        stroke_hlayout.setSpacing(shared.WIDGET_SPACING_CLOSE)

        self.letterSpacingBox = SizeComboBox([0, 10], "letter_spacing", self)
        self.letterSpacingBox.setObjectName("CompactFormatComboBox")
        stroke_hlayout.addWidget(self.strokeColorPicker)
        stroke_hlayout.setSpacing(7)

        self.letterSpacingBox = SizeComboBox([0, 10], "letter_spacing", self)
        self.letterSpacingBox.setObjectName("FontFormatSizeBox")
        self.letterSpacingBox.addItems(["0.0"])
        self.letterSpacingBox.setToolTip(self.tr("Change letter spacing"))
        self.letterSpacingBox.setFixedWidth(48)
        self.letterSpacingBox.param_changed.connect(self.on_param_changed)

        self.letterSpacingLabel = SizeControlLabel(self, direction=0, transparent_bg=False)
        self.letterSpacingLabel.setObjectName("letterSpacingLabel")
        self.letterSpacingLabel.size_ctrl_changed.connect(self.letterSpacingBox.changeByDelta)
        self.letterSpacingLabel.btn_released.connect(lambda : self.on_param_changed('letter_spacing', self.letterSpacingBox.value()))

        lettersp_hlayout = QHBoxLayout()
        lettersp_hlayout.addWidget(self.letterSpacingLabel)
        lettersp_hlayout.addWidget(self.letterSpacingBox)
        lettersp_hlayout.setSpacing(7)

        self.angleBox = SizeComboBox([-180, 180], "angle", self)
        self.angleBox.setObjectName("CompactFormatComboBox")
        self.angleBox.addItems(["0", "90", "180", "-90"])
        self.angleBox.setToolTip(self.tr("Angle"))
        self.angleBox.setFixedWidth(48)
        self.angleBox.param_changed.connect(self.on_param_changed)

        self.angleLabel = SizeControlLabel(self, direction=0, transparent_bg=False)
        self.angleLabel.setObjectName("fontAngleLabel")
        self.angleLabel.setToolTip(self.tr("Angle"))
        self.angleLabel.size_ctrl_changed.connect(self.onAngleCtrlChanged)
        self.angleLabel.btn_released.connect(lambda : self.on_param_changed('angle', self.angleBox.value()))

        angle_hlayout = QHBoxLayout()
        angle_hlayout.addWidget(self.angleLabel)
        angle_hlayout.addWidget(self.angleBox)
        angle_hlayout.setSpacing(shared.WIDGET_SPACING_CLOSE)
        
        self.global_fontfmt_str = self.tr("Global Font Format")
        self.textstyle_panel = TextStylePresetPanel(
            self.global_fontfmt_str,
            config_name='show_text_style_preset',
            config_expand_name='expand_tstyle_panel'
        )
        self.textstyle_panel.active_text_style_label_changed.connect(self.on_active_textstyle_label_changed)
        self.textstyle_panel.active_stylename_edited.connect(self.on_active_stylename_edited)

        self.textadvancedfmt_panel = TextAdvancedFormatPanel(
            self.tr('Advanced Text Format'),
            config_name='text_advanced_format_panel',
            config_expand_name='expand_tadvanced_panel',
            on_format_changed=self.on_param_changed
        )
        self.formatBtnGroup.emphasisBtn.emphasis_changed.connect(
            self.on_emphasis_changed
        )
        self.textadvancedfmt_panel.ruby_apply_requested.connect(
            self.on_ruby_apply_requested
        )
        self.textadvancedfmt_panel.ligature_axis_changed.connect(
            self.on_ligature_axis_changed
        )
        self.textadvancedfmt_panel.ruby_remove_requested.connect(
            self.on_ruby_remove_requested
        )
        self.texttransform_panel = TextTransformPanel(
            self.tr('Text Transform'),
            config_name='text_transform_panel',
            config_expand_name='expand_ttransform_panel',
        )
        self.text_transform_session = TextTransformEditSession(
            self,
            self.texttransform_panel,
        )
        color_label = self.textadvancedfmt_panel.shadow_group.color_label
        color_label.changingColor.connect(self.changingColor)
        color_label.colorChanged.connect(self.onColorLabelChanged)
        color_label.apply_color.connect(self.on_apply_color)

        color_label = self.textadvancedfmt_panel.gradient_group.start_picker
        color_label.changingColor.connect(self.changingColor)
        color_label.colorChanged.connect(self.onColorLabelChanged)
        color_label.apply_color.connect(self.on_apply_color)
        
        color_label = self.textadvancedfmt_panel.gradient_group.end_picker
        color_label.changingColor.connect(self.changingColor)
        color_label.colorChanged.connect(self.onColorLabelChanged)
        color_label.apply_color.connect(self.on_apply_color)
        
        self.foldTextBtn = CheckableLabel(self.tr("Unfold"), self.tr("Fold"), False)
        self.sourceBtn = TextCheckerLabel(self.tr("Source"))
        self.transBtn = TextCheckerLabel(self.tr("Translation"))
        for label in (self.foldTextBtn, self.sourceBtn, self.transBtn):
            label.setObjectName("FontFormatActionLabel")

        FONTFORMAT_SPACING = 5

        vl0 = QVBoxLayout()
        vl0.addWidget(self.textstyle_panel.view_widget)
        vl0.addWidget(self.textadvancedfmt_panel.view_widget)
        vl0.addWidget(self.texttransform_panel.view_widget)
        vl0.setSpacing(0)
        vl0.setContentsMargins(0, 0, 0, 0)
        hl1 = QHBoxLayout()
        font_selector_layout = QHBoxLayout()
        font_selector_layout.addWidget(self.familybox, 1)
        font_selector_layout.addWidget(self.fontWeightBox)
        font_selector_layout.setSpacing(7)
        font_selector_layout.setContentsMargins(0, 0, 0, 0)
        hl1.addLayout(font_selector_layout, 1)
        hl1.addWidget(self.fontsizebox)
        hl1.setSpacing(4)
        hl1.setContentsMargins(0, 11, 0, 0)
        hl2 = QHBoxLayout()
        hl2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl2.addWidget(self.strokeColorPicker)
        hl2.addWidget(self.alignBtnGroup)
        hl2.addWidget(self.formatBtnGroup)
        vertical_layout = QHBoxLayout()
        vertical_layout.addWidget(self.verticalChecker)
        vertical_layout.addWidget(self.tateChuYokoChecker)
        vertical_layout.addWidget(self.romanAlignmentChecker)
        vertical_layout.setSpacing(0)
        vertical_layout.setContentsMargins(0, 0, 0, 0)
        hl2.addLayout(vertical_layout)
        hl2.setSpacing(FONTFORMAT_SPACING)
        hl2.setContentsMargins(0, 0, 0, 0)
        hl3 = QHBoxLayout()
        hl3.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl3.addLayout(stroke_hlayout)
        hl3.addLayout(lettersp_hlayout)
        hl3.addLayout(linesp_hlayout)
        hl3.addLayout(angle_hlayout)
        hl3.setContentsMargins(3, 0, 3, 0)
        hl3.setSpacing(8)
        hl3.setSpacing(12)
        hl4 = QHBoxLayout()
        hl4.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl4.addWidget(self.foldTextBtn)
        hl4.addWidget(self.sourceBtn)
        hl4.addWidget(self.transBtn)
        hl4.setStretch(0, 1)
        hl4.setStretch(1, 1)
        hl4.setStretch(2, 1)
        hl4.setContentsMargins(0, 11, 0, 0)
        hl4.setSpacing(0)

        self.vlayout.addLayout(vl0)
        self.vlayout.addLayout(hl1)
        self.vlayout.addLayout(hl2)
        self.vlayout.addLayout(hl3)
        self.vlayout.addLayout(hl4)
        self.vlayout.setContentsMargins(0, 0, 6, 0)
        self.vlayout.setSpacing(0)

        self.focusOnColorDialog = False
        self.textblk_items = []
        self.mixed_fields = set()
        C.active_format = self.global_format

    def global_mode(self):
        return id(C.active_format) == id(self.global_format)

    def preset_mode(self):
        preset_format = self.active_text_style_format()
        return preset_format is not None and id(C.active_format) == id(preset_format)

    def multi_block_mode(self):
        return bool(self.textblk_items)

    def rich_text_mode(self):
        return self.textblk_item is not None and self.textblk_item.isEditing()

    def effective_global_format(self):
        active_format = self.active_text_style_format()
        if active_format is not None:
            return active_format
        return self.global_format
    
    def active_text_style_label(self):
        return self.textstyle_panel.active_text_style_label

    def active_text_style_format(self):
        af = self.active_text_style_label()
        if af is not None:
            return af.fontfmt
        else:
            return None

    def on_param_changed(self, param_name: str, value):
        func = handle_ffmt_change.get(param_name)
        func_kwargs = {}
        if param_name in {'font_size', 'rel_font_size'}:
            func_kwargs['clip_size'] = True
        if self.preset_mode():
            self.update_active_preset_param(param_name, value)
        elif self.multi_block_mode():
            func(param_name, value, C.active_format, is_global=False, blkitems=self.textblk_items, set_focus=True, **func_kwargs)
            self.refresh_multi_block_format()
        elif self.global_mode():
            func(param_name, value, self.global_format, is_global=True, **func_kwargs)
            self.update_text_style_label()
        else:
            func(param_name, value, C.active_format, is_global=False, blkitems=self.textblk_item, set_focus=True, **func_kwargs)
            if self.rich_text_mode():
                self.update_rich_text_cursor_format(self.textblk_item)

    def update_active_preset_param(self, param_name: str, value):
        active_text_style_label = self.active_text_style_label()
        if active_text_style_label is None:
            return
        if param_name == 'rel_font_size':
            active_text_style_label.fontfmt.font_size *= value
        elif hasattr(active_text_style_label.fontfmt, param_name):
            active_text_style_label.fontfmt[param_name] = value
        else:
            print(f'undefined param name: {param_name}')
            return
        if param_name == 'font_weight':
            active_text_style_label.fontfmt.bold = int(value) >= 700
        active_text_style_label.updatePreview()
        save_text_styles()

    def on_format_btn_changed(self, param_name: str, value):
        if param_name == 'font_weight':
            self.on_font_weight_changed(param_name, self._nearest_available_weight(value))
        else:
            self.on_param_changed(param_name, value)

    def on_font_weight_changed(self, param_name: str, weight: int):
        weight = self._nearest_available_weight(weight)
        self._sync_weight_controls(weight)
        canonical_family, _ = self.familybox.canonical_family(
            C.active_format.font_family
        )
        if canonical_family != C.active_format.font_family:
            with QSignalBlocker(self.familybox):
                self.familybox.set_displayed_font(canonical_family)
            self.on_param_changed('font_family', canonical_family)
        storage_family = self._pseudo_group_storage_family(weight)
        if storage_family and storage_family != C.active_format.font_family:
            self.on_param_changed('font_family', storage_family)
        self.on_param_changed('font_weight', FontWeight(weight))

    def _nearest_available_weight(self, weight: int) -> int:
        weights = [self.fontWeightCombo.itemData(index) for index in range(self.fontWeightCombo.count())]
        weights = [int(item) for item in weights if item is not None]
        if not weights:
            return int(weight)
        return min(weights, key=lambda item: (abs(item - int(weight)), -item))

    def _sync_weight_controls(self, weight: int, update_active: bool = True):
        is_bold = weight >= 700
        if update_active:
            C.active_format.bold = is_bold
        self.fontWeightCombo.blockSignals(True)
        self.fontWeightCombo.set_weight(weight)
        self.fontWeightCombo.blockSignals(False)
        self.formatBtnGroup.boldBtn.blockSignals(True)
        self.formatBtnGroup.boldBtn.setChecked(is_bold)
        self.formatBtnGroup.boldBtn.blockSignals(False)

    def _pseudo_group_storage_family(self, weight: int) -> str:
        entry = self.familybox.current_entry()
        if entry is None or not getattr(entry, 'is_pseudo_group', False):
            return ''
        return entry.storage_family_for_weight(weight)

    def _refresh_weight_combo(self, font_format: FontFormat = None):
        font_format = font_format or C.active_format
        entry = self.familybox.current_entry()
        weights = entry.weights if entry is not None else []
        weight = font_format.font_weight
        if weight is None:
            weight = 700 if font_format.bold else 400
        self.fontWeightCombo.update_weights(weights, weight)
        self._sync_weight_controls(self.fontWeightCombo.current_weight(), update_active=False)

    def _on_family_changed_for_weight(self, param_name: str, family: str):
        if param_name == 'font_family':
            self._refresh_weight_combo(C.active_format)
            weight = self.fontWeightCombo.current_weight()
            active_weight = C.active_format.font_weight if C.active_format.font_weight is not None else (700 if C.active_format.bold else 400)
            if weight != active_weight:
                self._sync_weight_controls(weight)
                self.on_param_changed('font_weight', weight)

    def set_font_grouping_mode(self, group_font_faces: bool):
        self.group_font_faces = group_font_faces
        self.fontWeightCombo.setVisible(group_font_faces)

    def on_font_family_changed(
        self, param_name: str, font_family: str
    ) -> None:
        canonical_family, inferred_weight = (
            self.familybox.canonical_family(font_family)
        )
        if canonical_family != font_family:
            with QSignalBlocker(self.familybox):
                self.familybox.set_displayed_font(canonical_family)
        self.on_param_changed(param_name, canonical_family)
        if inferred_weight is not None:
            self.fontWeightBox.set_weight(inferred_weight)
            self.on_param_changed('font_weight', inferred_weight)

    def toggle_bold(self) -> None:
        current_weight = FontWeight(C.active_format.font_weight)
        weight = (
            FontWeight.Normal
            if current_weight >= FontWeight.DemiBold
            else FontWeight.Bold
        )
        self._apply_font_weight(weight)

    def _apply_font_weight(self, weight: FontWeight) -> None:
        font_family = self.familybox.currentText()
        canonical_family, _ = self.familybox.canonical_family(font_family)
        if canonical_family != font_family:
            with QSignalBlocker(self.familybox):
                self.familybox.set_displayed_font(canonical_family)
            self.on_param_changed('font_family', canonical_family)
        self.fontWeightBox.set_weight(weight)
        self.on_param_changed('font_weight', weight)

    def on_emphasis_changed(self, style: str, position: str) -> None:
        if self.textblk_item is not None:
            items = [self.textblk_item]
        else:
            items = SW.canvas.selected_text_items()
        for item in items:
            item.setEmphasis(style, position)
        if items:
            restore_canvas_view_focus()

    def on_ligature_axis_changed(self, axis: str, state: str) -> None:
        if self.global_mode():
            attribute = (
                'oldstyle_nums'
                if axis == OLDSTYLE_NUMS
                else f'ligature_{axis}'
            )
            setattr(self.global_format, attribute, state)
            self.update_text_style_label()
        if self.textblk_item is not None:
            items = [self.textblk_item]
        else:
            items = SW.canvas.selected_text_items()
        for item in items:
            if axis == OLDSTYLE_NUMS:
                item.setOldstyleNums(state)
            else:
                item.setLigatureAxis(axis, state)
        if items:
            restore_canvas_view_focus()

    def on_tate_chu_yoko_changed(self, enabled: bool) -> None:
        if self.textblk_item is not None:
            items = [self.textblk_item]
        else:
            items = SW.canvas.selected_text_items()
        try:
            for item in items:
                item.setTateChuYoko(enabled)
        except RubyValidationError as error:
            if str(error) == 'Tate-chu-yoko cannot overlap Ruby':
                message = self.tr('Tate-chu-yoko cannot overlap Ruby.')
            else:
                message = self.tr(
                    'Unable to apply Tate-chu-yoko to this selection.'
                )
            current = (
                self.textblk_item.tate_chu_yoko_enabled()
                if self.textblk_item is not None else False
            )
            self.set_tate_chu_yoko_enabled(current)
            self.tateChuYokoChecker.setToolTip(message)
            QToolTip.showText(
                self.tateChuYokoChecker.mapToGlobal(
                    self.tateChuYokoChecker.rect().bottomLeft()
                ),
                message,
                self.tateChuYokoChecker,
            )
            return
        self.tateChuYokoChecker.setToolTip(self._tate_chu_yoko_tooltip)
        if items:
            restore_canvas_view_focus()

    def _restore_ruby_edit_focus(self, item: TextBlkItem) -> None:
        if item.isEditing():
            SW.canvas.gv.setFocus()
            item.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            restore_canvas_view_focus()

    def on_ruby_apply_requested(
        self, ruby_type: str, text: str, position: str
    ) -> None:
        item = self.textblk_item
        if item is None:
            self.textadvancedfmt_panel.ruby_group.set_error(
                self.tr('Select base text to apply Ruby.')
            )
            return
        try:
            item.setRuby(ruby_type, text, position)
        except RubyValidationError as error:
            messages = {
                'Select non-empty base text before applying Ruby': self.tr(
                    'Select base text to apply Ruby.'
                ),
                'Ruby text cannot be empty': self.tr(
                    'Ruby text cannot be empty.'
                ),
                'Mono Ruby needs one whitespace-separated reading per base grapheme': self.tr(
                    'Mono Ruby needs one whitespace-separated reading per base grapheme.'
                ),
                'Ruby cannot partially overlap an existing container': self.tr(
                    'Ruby cannot partially overlap an existing container.'
                ),
                'Ruby cannot overlap Tate-chu-yoko': self.tr(
                    'Ruby cannot overlap Tate-chu-yoko.'
                ),
                'Ruby base text cannot contain paragraph or forced line breaks': self.tr(
                    'Ruby base text cannot contain paragraph or forced line breaks.'
                ),
            }
            self.textadvancedfmt_panel.ruby_group.set_error(
                messages.get(
                    str(error),
                    self.tr('Unable to apply Ruby to this selection.'),
                )
            )
            self._restore_ruby_edit_focus(item)
            return
        self.textadvancedfmt_panel.set_ruby_state(*item.ruby_editor_values())
        self._restore_ruby_edit_focus(item)

    def on_ruby_remove_requested(self) -> None:
        item = self.textblk_item
        if item is None:
            return
        item.removeRuby()
        self.textadvancedfmt_panel.set_ruby_state(*item.ruby_editor_values())
        self._restore_ruby_edit_focus(item)

    def resolve_text_transform_edits_for_save(self):
        self.text_transform_session.resolve_for_save()

    def resolve_text_transform_edits_for_history_change(self):
        self.text_transform_session.resolve_for_history_change()

    def resolve_text_transform_edits_for_page_change(self):
        self.text_transform_session.resolve_for_page_change()

    def cancel_text_transform_edits_for_scene_change(self):
        self.text_transform_session.cancel_for_scene_change()

    def update_text_style_label(self):
        if self.global_mode():
            active_text_style_label = self.active_text_style_label()
            if active_text_style_label is not None:
                active_text_style_label.update_style(self.global_format)

    def changingColor(self):
        self.focusOnColorDialog = True

    def onColorLabelChanged(self, is_valid=True):
        self.focusOnColorDialog = False
        if is_valid:
            sender: ColorPickerLabel = self.sender()
            rgb = sender.rgb()
            self.on_param_changed(sender.param_name, rgb)

    def on_apply_color(self, param_name, rgb):
        self.on_param_changed(param_name, rgb)

    def onLineSpacingCtrlChanged(self, delta: int):
        if C.active_format.line_spacing_type == LineSpacingType.Distance:
            mul = 0.1
        else:
            mul = 0.01
        self.lineSpacingBox.setValue(self.lineSpacingBox.value() + delta * mul)

    def onAngleCtrlChanged(self, delta: int) -> None:
        self.angleBox.setValue(round(self.angleBox.value()) + delta)

    def sync_inline_format(
        self,
        font_format: FontFormat,
        multi_size: bool = False,
        *,
        preserve_focused_editors: bool = True,
    ) -> None:
        C.active_format = font_format
        font_size = round(font_format.font_size, 1)
        if int(font_size) == font_size:
            font_size = str(int(font_size))
        else:
            font_size = f'{font_size:.1f}'
        if multi_size:
            font_size += "+"

        if not preserve_focused_editors or not self.familybox.hasFocus():
            with QSignalBlocker(self.familybox):
                self.familybox.set_displayed_font(font_format.font_family)
        if (
            not preserve_focused_editors
            or not self.fontsizebox.fcombobox.hasFocus()
        ):
            with QSignalBlocker(self.fontsizebox.fcombobox):
                self.fontsizebox.fcombobox.setCurrentText(font_size)
        if not preserve_focused_editors or not self.fontWeightBox.hasFocus():
            with QSignalBlocker(self.fontWeightBox):
                self.fontWeightBox.set_weight(font_format.font_weight)
        foreground = tuple(font_format.foreground_color())
        if (
            (not preserve_focused_editors or not self.focusOnColorDialog)
            and (
                self.colorPicker.color is None
                or self.colorPicker.rgb() != foreground
            )
        ):
            self.colorPicker.setPickerColor(foreground)
        if not preserve_focused_editors or not self.lineSpacingBox.hasFocus():
            with QSignalBlocker(self.lineSpacingBox):
                self.lineSpacingBox.setValue(font_format.line_spacing)
        if not preserve_focused_editors or not self.letterSpacingBox.hasFocus():
            with QSignalBlocker(self.letterSpacingBox):
                self.letterSpacingBox.setValue(font_format.letter_spacing)
        self.formatBtnGroup.underlineBtn.setChecked(font_format.underline)
        self.formatBtnGroup.italicBtn.setChecked(font_format.italic)
        self.textadvancedfmt_panel.set_line_spacing_type(
            font_format.line_spacing_type
        )
        if self.textblk_item is None:
            self.formatBtnGroup.emphasisBtn.set_values(
                'none', 'over right'
            )
            self.set_tate_chu_yoko_enabled(False)
            self.textadvancedfmt_panel.set_ruby_state(
                'group', '', 'over', False,
            )
        else:
            self.formatBtnGroup.emphasisBtn.set_values(
                *self.textblk_item.emphasis_values()
            )
            self.set_tate_chu_yoko_enabled(
                self.textblk_item.tate_chu_yoko_enabled()
            )
            self.textadvancedfmt_panel.set_ruby_state(
                *self.textblk_item.ruby_editor_values()
            )
        for axis in self.textadvancedfmt_panel.ligature_comboboxes:
            if axis == OLDSTYLE_NUMS:
                value = (
                    font_format.oldstyle_nums
                    if self.textblk_item is None
                    else self.textblk_item.oldstyle_nums_value()
                )
            else:
                value = (
                    getattr(font_format, f'ligature_{axis}')
                    if self.textblk_item is None
                    else self.textblk_item.ligature_axis_value(axis)
                )
            self.textadvancedfmt_panel.set_ligature_axis(
                axis,
                value,
            )

    def set_active_format(
        self,
        font_format: FontFormat,
        size_marker: str = '',
        *,
        update_transform_panel: bool = True,
    ) -> None:
        C.active_format = font_format
        self.familybox.blockSignals(True)
        font_size = round(font_format.font_size, 1)
        if int(font_size) == font_size:
            font_size = str(int(font_size))
        else:
            font_size = f'{font_size:.1f}'
        if size_marker:
            font_size += size_marker
        self.fontsizebox.fcombobox.setCurrentText(font_size)
        self.familybox.set_current_family(font_format.font_family)
        self._refresh_weight_combo(font_format)
        self.colorPicker.setPickerColor(font_format.foreground_color())
        self.strokeColorPicker.setPickerColor(font_format.stroke_color())
        self.strokeWidthBox.setValue(font_format.stroke_width)
        self.lineSpacingBox.setValue(font_format.line_spacing)
        self.letterSpacingBox.setValue(font_format.letter_spacing)
        self.angleBox.setValue(0 if self.textblk_item is None else self.textblk_item.angle)
        self.verticalChecker.setTristate(False)
        reset_checker_style(self.verticalChecker)
        self.verticalChecker.setChecked(font_format.vertical)
        weight = font_format.font_weight if font_format.font_weight is not None else (700 if font_format.bold else 400)
        self._sync_weight_controls(weight, update_active=False)
        self.formatBtnGroup.clearMixed()
        self.formatBtnGroup.boldBtn.setChecked(weight >= 700)
        self.formatBtnGroup.underlineBtn.setChecked(font_format.underline)
        self.formatBtnGroup.italicBtn.setChecked(font_format.italic)
        self.sync_inline_format(
            font_format,
            bool(size_marker),
            preserve_focused_editors=False,
        )
        self.strokeColorPicker.setPickerColor(font_format.stroke_color())
        self.strokeWidthBox.setValue(font_format.stroke_width)
        self.verticalChecker.setChecked(font_format.vertical)
        self.romanAlignmentChecker.setChecked(
            font_format.standard_vertical_roman_alignment
        )
        self.alignBtnGroup.setAlignment(font_format.alignment)
        self.textadvancedfmt_panel.set_active_format(font_format)
        if update_transform_panel:
            self.texttransform_panel.set_active_format(font_format)

    def set_mixed_fields(self, mixed_fields):
        self.mixed_fields = set(mixed_fields)
        self.textadvancedfmt_panel.set_mixed_fields(self.mixed_fields)
        mixed_size_boxes = {
            'stroke_width': self.strokeWidthBox,
            'line_spacing': self.lineSpacingBox,
            'letter_spacing': self.letterSpacingBox,
        }
        if 'font_family' in self.mixed_fields:
            self.familybox.blockSignals(True)
            self.familybox.setCurrentText('')
            self.familybox.blockSignals(False)
        if 'font_size' in self.mixed_fields:
            if not self.fontsizebox.getFontSize().endswith('+'):
                self.fontsizebox.fcombobox.blockSignals(True)
                self.fontsizebox.fcombobox.setCurrentText('')
                self.fontsizebox.fcombobox.blockSignals(False)
        for field, box in mixed_size_boxes.items():
            if field in self.mixed_fields:
                box.blockSignals(True)
                box.setCurrentText('')
                box.blockSignals(False)
        if 'font_weight' in self.mixed_fields:
            self.fontWeightCombo.blockSignals(True)
            self.fontWeightCombo.setCurrentIndex(-1)
            self.fontWeightCombo.blockSignals(False)
        if 'bold' in self.mixed_fields:
            self.formatBtnGroup.setMixed(self.formatBtnGroup.boldBtn)
        if 'italic' in self.mixed_fields:
            self.formatBtnGroup.setMixed(self.formatBtnGroup.italicBtn)
        if 'underline' in self.mixed_fields:
            self.formatBtnGroup.setMixed(self.formatBtnGroup.underlineBtn)
        if 'frgb' in self.mixed_fields:
            self.colorPicker.setMixed(True)
        if 'srgb' in self.mixed_fields:
            self.strokeColorPicker.setMixed(True)
        if 'vertical' in self.mixed_fields:
            self.verticalChecker.blockSignals(True)
            self.verticalChecker.setTristate(True)
            self.verticalChecker.setCheckState(Qt.CheckState.PartiallyChecked)
            set_checker_mixed_style(self.verticalChecker)
            self.verticalChecker.blockSignals(False)
        if 'alignment' in self.mixed_fields:
            self.alignBtnGroup.setMixed()

    def update_text_style_arrow_buttons(self, has_text_selection: bool = False, mixed_selection: bool = False):
        preset_only = self.active_text_style_label() is not None and not has_text_selection
        apply_enabled = not preset_only
        update_enabled = not preset_only and not mixed_selection
        self.textstyle_panel.setArrowButtonsEnabled(apply_enabled, update_enabled)

    def aggregate_textblk_formats(self, textblk_items: List[TextBlkItem]):
        formats = [textblk_item.get_fontformat() for textblk_item in textblk_items]
        aggregate_format = formats[0]
        mixed_fields = set()
        for font_format in formats[1:]:
            for key in aggregate_format.annotations_set():
                if key.startswith('_') or not hasattr(font_format, key):
                    continue
                if not format_field_equal(key, aggregate_format, font_format):
                    mixed_fields.add(key)
        if 'font_size' in mixed_fields:
            aggregate_format.font_size = sum(font_format.font_size for font_format in formats) / len(formats)
        return aggregate_format, mixed_fields

    def refresh_multi_block_format(self):
        if not self.multi_block_mode():
            return
        aggregate_format, mixed_fields = self.aggregate_textblk_formats(self.textblk_items)
        size_marker = '+' if 'font_size' in mixed_fields else ''
        self.set_active_format(aggregate_format, size_marker=size_marker)
        self.set_mixed_fields(mixed_fields)
        self.update_text_style_arrow_buttons(has_text_selection=True, mixed_selection=bool(mixed_fields))

    def fontformat_from_char_format(self, char_format, base_format: FontFormat):
        font = char_format.font()
        brush = char_format.foreground()
        font_format = base_format.deepcopy()
        font_weight = int(font.weight())
        font_format.font_family = storage_font_family(font.family(), font_weight)
        font_format.font_weight = font_weight
        font_format.bold = font.bold()
        font_format.italic = font.italic()
        font_format.underline = font.underline()
        point_size = char_format.fontPointSize() or font.pointSizeF()
        if point_size > 0:
            font_format.font_size = pt2px(point_size)
        if brush.style() != Qt.BrushStyle.NoBrush:
            color = brush.color()
            font_format.frgb = [color.red(), color.green(), color.blue()]
        return font_format

    def selected_rich_text_formats(self, textblk_item: TextBlkItem):
        cursor = textblk_item.textCursor()
        if not cursor.hasSelection():
            return [self.fontformat_from_char_format(cursor.charFormat(), textblk_item.fontformat)]

        doc = textblk_item.document()
        sel_start = cursor.selectionStart()
        sel_end = cursor.selectionEnd()
        formats = []
        block = doc.firstBlock()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                frag_start = fragment.position()
                frag_end = frag_start + fragment.length()
                if max(frag_start, sel_start) < min(frag_end, sel_end):
                    formats.append(self.fontformat_from_char_format(fragment.charFormat(), textblk_item.fontformat))
                it += 1
            block = block.next()
        if not formats:
            formats.append(self.fontformat_from_char_format(cursor.charFormat(), textblk_item.fontformat))
        return formats

    def aggregate_rich_text_cursor_format(self, textblk_item: TextBlkItem):
        formats = self.selected_rich_text_formats(textblk_item)
        aggregate_format = formats[0]
        mixed_fields = set()
        for font_format in formats[1:]:
            for key in {'font_family', 'font_size', 'font_weight', 'frgb', 'bold', 'italic', 'underline'}:
                if not format_field_equal(key, aggregate_format, font_format):
                    mixed_fields.add(key)
        return aggregate_format, mixed_fields

    def update_rich_text_cursor_format(self, textblk_item: TextBlkItem = None):
        textblk_item = textblk_item or self.textblk_item
        if textblk_item is None or not textblk_item.isEditing():
            return
        if textblk_item is not self.textblk_item:
            return
        aggregate_format, mixed_fields = self.aggregate_rich_text_cursor_format(textblk_item)
        self.set_active_format(aggregate_format)
        self.set_mixed_fields(mixed_fields)
        self.update_text_style_arrow_buttons(has_text_selection=True, mixed_selection=bool(mixed_fields))
    def set_tate_chu_yoko_enabled(self, enabled: bool) -> None:
        self.tateChuYokoChecker.setChecked(enabled)
        self.tateChuYokoChecker.setToolTip(self._tate_chu_yoko_tooltip)

    def set_globalfmt_title(self):
        active_text_style_label = self.active_text_style_label()
        if active_text_style_label is None:
            self.set_formatpanel_title(self.global_fontfmt_str, highlight=True)
        else:
            title = self.global_fontfmt_str + ' - ' + active_text_style_label.fontfmt._style_name
            valid_title = self.textstyle_panel.elidedText(title)
            self.set_formatpanel_title(valid_title)

    def set_formatpanel_title(self, title: str, highlight: bool = False):
        self.textstyle_panel.setTitle(title)
        textlabel = self.textstyle_panel.view_widget.title_label.textlabel
        if highlight:
            textlabel.setStyleSheet("color: rgb(30, 147, 229);")
        else:
            textlabel.setStyleSheet("")


    def deactivate_style_label(self):
        if self.active_text_style_label() is not None:
            self.textstyle_panel.on_stylelabel_activated(False)


    def on_active_textstyle_label_changed(self):
        active_text_style_label = self.active_text_style_label()
        if self.textblk_item is None:
            if active_text_style_label is not None:
                self.set_active_format(active_text_style_label.fontfmt)
            else:
                self.set_active_format(self.global_format)
            self.set_globalfmt_title()
            self.update_text_style_arrow_buttons()

    def on_active_stylename_edited(self):
        if self.global_mode() or self.preset_mode():
            self.set_globalfmt_title()

    def set_textblk_item(self, textblk_item: TextBlkItem = None, multi_select:bool=False, multi_select_items: List[TextBlkItem] = None):
        # A selection transition is a transaction boundary for transform text.
        # Commit against the old target list before replacing it.
        self.text_transform_session.finish_pending_edits()
        if textblk_item is not None:
            transform_items = [textblk_item]
        elif multi_select:
            transform_items = list(multi_select_items) if multi_select_items else SW.canvas.selected_text_items()
        else:
            transform_items = []

        preserve_local_owner = False
        if textblk_item is None:
            focus_w = self.app.focusWidget()
            focus_on_fmtoptions = self.focusOnColorDialog or (
                focus_w is not None
                and (focus_w is self or self.isAncestorOf(focus_w))
            )
            preserve_local_owner = (
                not transform_items
                and self.textblk_item is not None
                and focus_on_fmtoptions
            )
            if preserve_local_owner:
                # Formatting focus can briefly clear the canvas selection; use
                # the retained local item when comparing effective owners.
                transform_items = [self.textblk_item]

        self.text_transform_session.replace_targets(transform_items)

        if textblk_item is None:
            if not preserve_local_owner:
                # Store the current text block's format before switching to global.
                # This existing owner switch must preserve the complete transform.
                if self.textblk_item is not None:
                    target_format = C.active_format
                    if self.textblk_item.isEditing():
                        uniform_format = self.textblk_item.uniform_document_fontformat()
                        if uniform_format is not None:
                            target_format = uniform_format
                    # Keep the TextBlock-owned object shared with its live
                    # layout; replacing it desynchronizes fill and effects.
                    letter_spacing = (
                        self.textblk_item.fontformat.letter_spacing
                    )
                    line_spacing = self.textblk_item.fontformat.line_spacing
                    line_spacing_type = (
                        self.textblk_item.fontformat.line_spacing_type
                    )
                    self.textblk_item.fontformat.merge(target_format)
                    self.textblk_item.fontformat.letter_spacing = (
                        letter_spacing
                    )
                    self.textblk_item.fontformat.line_spacing = line_spacing
                    self.textblk_item.fontformat.line_spacing_type = (
                        line_spacing_type
                    )
                self.textblk_item = None
                self.textblk_items = []
                # The transform panel is refreshed below via set_transform_items
                # whenever there are targets; skip the redundant update here.
                update_transform_panel = not transform_items
                if multi_select:
                    self.textblk_items = list(multi_select_items or [])
                    aggregate_format, mixed_fields = self.aggregate_textblk_formats(self.textblk_items)
                    size_marker = '+' if 'font_size' in mixed_fields else ''
                    self.set_active_format(
                        aggregate_format,
                        size_marker=size_marker,
                        update_transform_panel=update_transform_panel,
                    )
                    self.set_mixed_fields(mixed_fields)
                    self.set_formatpanel_title(self.multi_textblocks_title(self.textblk_items))
                    self.update_text_style_arrow_buttons(has_text_selection=True, mixed_selection=bool(mixed_fields))
                elif self.active_text_style_label() is not None:
                    self.set_active_format(
                        self.active_text_style_format(),
                        update_transform_panel=update_transform_panel,
                    )
                    self.set_mixed_fields(set())
                    self.set_globalfmt_title()
                    self.update_text_style_arrow_buttons()
                else:
                    self.set_active_format(
                        self.global_format,
                        update_transform_panel=update_transform_panel,
                    )
                    self.set_mixed_fields(set())
                    self.set_globalfmt_title()
                    self.update_text_style_arrow_buttons()
            if transform_items:
                self.texttransform_panel.set_transform_items(transform_items)
            
        else:
            if not self.restoring_textblk:
                blk_fmt = textblk_item.get_fontformat()
                self.textblk_item = textblk_item
                self.textblk_items = []
                size_marker = '*' if not textblk_item.isEditing() and textblk_item.isMultiFontSize() else ''
                self.set_active_format(
                    blk_fmt,
                    size_marker=size_marker,
                    update_transform_panel=not transform_items,
                )
                self.set_mixed_fields(set())
                self.texttransform_panel.set_transform_items(transform_items)
                self.set_formatpanel_title(f'TextBlock #{textblk_item.idx}')
                self.update_text_style_arrow_buttons(has_text_selection=True)
                if textblk_item.isEditing():
                    self.update_rich_text_cursor_format(textblk_item)

    def multi_textblocks_title(self, textblk_items: List[TextBlkItem] = None):
        if not textblk_items:
            return self.tr('Text Blocks')
        indexes = ', '.join(f'#{item.idx}' for item in textblk_items)
        title = self.tr('Text Blocks {indexes}').format(indexes=indexes)
        return self.textstyle_panel.elidedText(title)
