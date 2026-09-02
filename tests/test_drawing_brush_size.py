import os
import unittest


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtCore import Qt
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QAbstractSpinBox, QApplication

from ballontranslator.ui.drawingpanel import (
    InpaintPanel,
    PenConfigPanel,
    RectPanel,
)


class DrawingBrushSizeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_pen_size_can_be_typed_and_updates_the_slider(self) -> None:
        panel = PenConfigPanel()
        values = []
        panel.thicknessChanged.connect(values.append)
        panel.show()
        panel.thicknessSpinBox.setFocus()
        panel.thicknessSpinBox.selectAll()

        QTest.keyClicks(panel.thicknessSpinBox, '17')
        QTest.keyClick(panel.thicknessSpinBox, Qt.Key.Key_Return)

        self.assertEqual(panel.thicknessSpinBox.value(), 17)
        self.assertEqual(panel.thicknessSlider.value(), 17)
        self.assertIn(17, values)

    def test_inpaint_slider_and_numeric_input_stay_synchronized(self) -> None:
        panel = InpaintPanel()

        panel.thicknessSlider.setValue(23)
        self.assertEqual(panel.thicknessSpinBox.value(), 23)

        panel.thicknessSpinBox.setValue(9)
        self.assertEqual(panel.thicknessSlider.value(), 9)

    def test_numeric_editor_is_compact_and_has_no_stepper_buttons(self) -> None:
        panel = PenConfigPanel()
        button_symbols = getattr(
            QAbstractSpinBox,
            'ButtonSymbols',
            QAbstractSpinBox,
        )

        self.assertEqual(panel.thicknessSpinBox.width(), 60)
        self.assertEqual(
            panel.thicknessSpinBox.buttonSymbols(),
            button_symbols.NoButtons,
        )

    def test_box_dilate_can_be_typed_and_updates_the_slider(self) -> None:
        panel = RectPanel()
        panel.show()
        panel.dilateSpinBox.setFocus()
        panel.dilateSpinBox.selectAll()

        QTest.keyClicks(panel.dilateSpinBox, '17')
        QTest.keyClick(panel.dilateSpinBox, Qt.Key.Key_Return)

        self.assertEqual(panel.dilateSpinBox.value(), 17)
        self.assertEqual(panel.dilate_slider.value(), 17)
        self.assertFalse(panel.dilate_slider.show_hover_value)


if __name__ == '__main__':
    unittest.main()
