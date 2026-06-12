from typing import List, Union, Tuple

import numpy as np
from qtpy.QtWidgets import QGraphicsOpacityEffect, QLabel, QColorDialog, QMenu
from qtpy.QtCore import  Qt, QPropertyAnimation, QEasingCurve, Signal
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

    def mousePressEvent(self, event: QMouseEvent):
        btn = event.button()
        if btn == Qt.MouseButton.LeftButton:
            self.changingColor.emit()
            color = QColorDialog.getColor(self.color or QColor(255, 255, 255))
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
            for row in range(8):
                for col in range(8):
                    if (row + col) % 2 == 0:
                        x0 = round(col * width / 8)
                        y0 = round(row * height / 8)
                        x1 = round((col + 1) * width / 8)
                        y1 = round((row + 1) * height / 8)
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
            self.setStyleSheet("background-color: white;")

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
        rgba = f'rgba({r}, {g}, {b}, {a})'
        self.setStyleSheet("background-color: " + rgba)

    def rgb(self) -> List:
        color = self.color
        return (color.red(), color.green(), color.blue())

    def rgba(self) -> List:
        color = self.color
        return (color.red(), color.green(), color.blue(), color.alpha())
    

class SmallColorPickerLabel(ColorPickerLabel):
    pass



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
    

class ConfigClickableLabel(ClickableLabel):
    pass

    
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
