from typing import List, Union, Tuple

import numpy as np
from qtpy.QtWidgets import QGraphicsOpacityEffect, QLabel, QColorDialog, QMenu
from qtpy.QtCore import  Qt, QEvent, QPropertyAnimation, QEasingCurve, Signal
from qtpy.QtGui import QMouseEvent, QWheelEvent, QColor, QPixmap, QPainter


from ballontranslator.utils.shared import CONFIG_FONTSIZE_CONTENT
from ballontranslator.utils import shared
from ballontranslator.utils.config import pcfg
from ..misc import DARKFILL_ACTIVE, LIGHTFILL_ACTIVE


def _icon_fill_color(fill_attr: str) -> QColor:
    return QColor(fill_attr.split('"')[1])


class FadeLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # https://stackoverflow.com/questions/57828052/qpropertyanimation-not-working-with-window-opacity
        effect = QGraphicsOpacityEffect(self, opacity=1.0)
        self.setGraphicsEffect(effect)
        self.fadeAnimation = QPropertyAnimation(
            self,
            propertyName=b"opacity",
            targetObject=effect,
            duration=1200,
            startValue=1.0,
            endValue=0.,
        )
        self.fadeAnimation.setEasingCurve(QEasingCurve.Type.InQuint)
        self.fadeAnimation.finished.connect(self.hide)
        self.setHidden(True)
        self.gv = None

    def startFadeAnimation(self):
        self.show()
        self.fadeAnimation.stop()
        self.fadeAnimation.start()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.gv is not None:
            self.gv.wheelEvent(event)
        return super().wheelEvent(event)


class ColorPickerLabel(QLabel):
    colorChanged = Signal(bool)
    apply_color = Signal(str, tuple)
    changingColor = Signal()
    def __init__(self, parent=None, param_name='', *args, **kwargs):
        super().__init__(parent=parent, *args, **kwargs)
        self.color: QColor = None
        self.param_name = param_name
        self.mixed = False

    def _style_selector(self) -> str:
        '''
        Scope for this widget's own stylesheet. A selector-less rule such as
        "background-color: black" cascades into every descendant *and* into the
        QToolTip Qt spawns for the widget, which would repaint the tooltip in
        the swatch colour and hide its text.
        '''
        name = self.objectName()
        return f'#{name}' if name else type(self).__name__

    def _set_background(self, css_color: str):
        self.setStyleSheet(f'{self._style_selector()} {{ background-color: {css_color}; }}')

    def mousePressEvent(self, event: QMouseEvent):
        btn = event.button()
        if btn == Qt.MouseButton.LeftButton:
            self.changingColor.emit()
            initial_color = self.color if self.color is not None else QColor(255, 255, 255)
            color = QColorDialog.getColor(initial_color, self.window())
            is_valid = color.isValid()
            if is_valid:
                self.setPickerColor(color)
            self.colorChanged.emit(is_valid)
        elif btn == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            apply_act = menu.addAction(self.tr("Apply Color"))
            rst = menu.exec(event.globalPosition().toPoint())
            if rst == apply_act and self.color is not None:
                self.apply_color.emit(self.param_name, self.rgb())

    def setMixed(self, mixed: bool):
        self.mixed = mixed
        if mixed:
            self.color = QColor(255, 255, 255)
            size = self.size()
            width = max(size.width(), 24)
            height = max(size.height(), 24)
            pixmap = QPixmap(width, height)
            pixmap.fill(QColor(255, 255, 255))
            painter = QPainter(pixmap)
            fill_attr = DARKFILL_ACTIVE if pcfg.darkmode else LIGHTFILL_ACTIVE
            mixed_color = _icon_fill_color(fill_attr)
            cells = 6
            for row in range(cells):
                for col in range(cells):
                    if (row + col) % 2 == 0:
                        x0 = round(col * width / cells)
                        y0 = round(row * height / cells)
                        x1 = round((col + 1) * width / cells)
                        y1 = round((row + 1) * height / cells)
                        painter.fillRect(
                            x0,
                            y0,
                            max(1, x1 - x0),
                            max(1, y1 - y0),
                            mixed_color,
                        )
            painter.end()
            self.setPixmap(pixmap)
            self.setScaledContents(True)
            self._set_background('white')

    def setPickerColor(self, color: Union[QColor, List, Tuple]):
        self.mixed = False
        self.setPixmap(QPixmap())
        self.setScaledContents(False)
        if not isinstance(color, QColor):
            if isinstance(color, np.ndarray):
                color = np.round(color).astype(np.uint8).tolist()
            color = QColor(*color)
        self.color = color
        r, g, b, a = color.getRgb()
        self._set_background(f'rgba({r}, {g}, {b}, {a})')

    def rgb(self) -> List:
        color = self.color
        return (color.red(), color.green(), color.blue())

    def rgba(self) -> List:
        color = self.color
        return (color.red(), color.green(), color.blue(), color.alpha())
    

class SmallColorPickerLabel(ColorPickerLabel):
    pass


class NestedColorPickerLabel(ColorPickerLabel):
    '''
    Stroke color swatch that hosts the fill color swatch inside it, so the
    outline/fill pair reads as one glyph instead of two unlabelled squares.

    The inner swatch is a child widget, which means Qt routes a click on it to
    the inner picker and a click on the surrounding margin to this one. No
    manual hit testing is involved, and both swatches keep the plain
    ColorPickerLabel API their signal handlers already rely on.
    '''

    # Fraction of the leftover horizontal space placed left of the inner
    # swatch. Both swatches are square, so 0.5 centres it; drop it below 0.5 to
    # bias the inner square towards the left.
    INNER_LEFT_RATIO = 0.5

    def __init__(self, parent=None, param_name='', inner_param_name='', *args, **kwargs):
        super().__init__(parent=parent, param_name=param_name, *args, **kwargs)
        self.setObjectName('NestedStrokeColorPicker')
        self.inner = ColorPickerLabel(self, param_name=inner_param_name)
        self.inner.setObjectName('NestedFillColorPicker')
        self.setProperty('innerHover', False)
        self.inner.installEventFilter(self)

    def eventFilter(self, watched, event):
        # Qt keeps a parent in the :hover state while the cursor is over one of
        # its children, so hovering the inner square would light up both borders
        # and read as if both swatches were selected. Track the inner swatch and
        # let the stylesheet drop this one's highlight while it is hovered.
        if watched is self.inner:
            etype = event.type()
            if etype == QEvent.Type.Enter:
                self._set_inner_hover(True)
            elif etype == QEvent.Type.Leave:
                self._set_inner_hover(False)
        return super().eventFilter(watched, event)

    def _set_inner_hover(self, hovering: bool):
        if bool(self.property('innerHover')) == hovering:
            return
        self.setProperty('innerHover', hovering)
        # A dynamic property only reaches the stylesheet after a re-polish.
        self.style().unpolish(self)
        self.style().polish(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_inner()

    def showEvent(self, event):
        super().showEvent(event)
        self._layout_inner()

    def _layout_inner(self):
        content = self.contentsRect()
        # The stylesheet pins the inner swatch with equal min/max, so prefer the
        # resolved minimum and only fall back before the style is polished.
        hint = self.inner.sizeHint()
        w = self.inner.minimumWidth() or hint.width()
        h = self.inner.minimumHeight() or hint.height()
        x = content.left() + round(max(0, content.width() - w) * self.INNER_LEFT_RATIO)
        y = content.top() + round(max(0, content.height() - h) / 2)
        self.inner.setGeometry(x, y, w, h)
        self.inner.raise_()



class ClickableLabel(QLabel):

    clicked = Signal()

    def __init__(self, text=None, parent=None, *args, **kwargs):
        super().__init__(parent=parent, *args, **kwargs)
        if text is not None:
            self.setText(text)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        return super().mousePressEvent(e)
    

class CheckableLabel(QLabel):

    checkStateChanged = Signal(bool)

    def __init__(self, checked_text: str, unchecked_text: str, default_checked: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checked_text = checked_text
        self.unchecked_text = unchecked_text
        self.checked = default_checked
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if default_checked:
            self.setText(checked_text)
        else:
            self.setText(unchecked_text)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self.checked)
            self.checkStateChanged.emit(self.checked)
        return super().mousePressEvent(e)

    def setChecked(self, checked: bool):
        self.checked = checked
        if checked:
            self.setText(self.checked_text)
        else:
            self.setText(self.unchecked_text)


class TextCheckerLabel(QLabel):
    checkStateChanged = Signal(bool)
    def __init__(self, text: str, checked: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setText(text)
        self.setCheckState(checked)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setCheckState(self, checked: bool):
        self.checked = checked
        if checked:
            self.setStyleSheet("QLabel { background-color: rgb(30, 147, 229); color: white; }")
        else:
            self.setStyleSheet("")

    def isChecked(self):
        return self.checked

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCheckState(not self.checked)
            self.checkStateChanged.emit(self.checked)


class ParamNameLabel(QLabel):
    def __init__(self, param_name: str, alignment = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        if alignment is None:
            self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self.setAlignment(alignment)

        font = self.font()
        font.setPointSizeF(CONFIG_FONTSIZE_CONTENT-2)
        self.setFont(font)
        self.setText(param_name)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


class SmallParamLabel(QLabel):
    def __init__(self, param_name: str, alignment = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        if alignment is None:
            self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            self.setAlignment(alignment)

        self.setText(param_name)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


class SizeControlLabel(QLabel):

    btn_released = Signal()
    size_ctrl_changed = Signal(int)

    def __init__(self, parent=None, direction=0, text='', alignment=None, transparent_bg=True):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        if text:
            self.setText(text)
        if direction == 0:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.cur_pos = 0
        self.direction = direction
        self.mouse_pressed = False
        if transparent_bg:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if alignment is not None:
            self.setAlignment(alignment)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.mouse_pressed = True
            if shared.FLAG_QT6:
                g_pos = e.globalPosition().toPoint()
            else:
                g_pos = e.globalPos()
            self.cur_pos = g_pos.x() if self.direction == 0 else g_pos.y()
        return super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.mouse_pressed = False
            self.btn_released.emit()
        return super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self.mouse_pressed:
            if shared.FLAG_QT6:
                g_pos = e.globalPosition().toPoint()
            else:
                g_pos = e.globalPos()
            if self.direction == 0:
                new_pos = g_pos.x()
                self.size_ctrl_changed.emit(new_pos - self.cur_pos)
            else:
                new_pos = g_pos.y()
                self.size_ctrl_changed.emit(self.cur_pos - new_pos)
            self.cur_pos = new_pos
        return super().mouseMoveEvent(e)
    

class SmallSizeControlLabel(SizeControlLabel):
    pass
