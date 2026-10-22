import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtWidgets import QApplication

from ballontranslator.ui.text_engine.editing.manager import SceneTextManager
from ballontranslator.ui.text_engine.item import TextBlkItem
from ballontranslator.utils.config import pcfg
from ballontranslator.utils.textblock import TextBlock


class SourceSizedLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_initial_item_uses_translation_rectangle(self):
        block = TextBlock(
            xyxy=[517, 873, 586, 1031],
            lines=[[[517, 873], [586, 873], [586, 1031], [517, 1031]]],
            _bounding_rect=[473, 857, 143, 200],
            det_model='ctd_ctbd', src_is_vertical=True,
        )
        block.fontformat.font_size = 28
        block.fontformat.font_family = 'Arial'
        block.fontformat.vertical = False
        block.translation = '맛있어 보인다, 맛있어 보인다'
        item = TextBlkItem(block, 0)
        try:
            self.assertAlmostEqual(item.geometry_controller.logical_rect().width(), 143)
            self.assertAlmostEqual(item.get_fontformat().font_size, 28)
            self.assertEqual(item.toPlainText(), block.translation)
        finally:
            item.deleteLater()
            self.app.processEvents()

    def test_automatic_layout_obeys_source_font_size_option(self):
        for value, enabled in ((True, True), (False, False), ({'value': True}, True), ({'value': False}, False)):
            with self.subTest(value=value):
                block = TextBlock(
                    xyxy=[50, 20, 80, 180],
                    lines=[[[50, 20], [80, 20], [80, 180], [50, 180]]],
                    _bounding_rect=[0, 0, 160, 200],
                    det_model='ctd_ctbd', src_is_vertical=True,
                )
                block.fontformat.font_size = 28
                block.fontformat.font_family = 'Arial'
                block.fontformat.vertical = False
                block.fontformat.alignment = 1
                item = TextBlkItem(block, 0)
                manager = SimpleNamespace(
                    imgtrans_proj=SimpleNamespace(img_array=np.full((200, 160, 3), 255, np.uint8)),
                    auto_textlayout_flag=True, pairwidget_list=[],
                )
                text = '아주 맛있어 보인다 ' * 12
                try:
                    with (
                        patch.object(pcfg.module, 'textdetector_params', {
                            'ctd_ctbd': {'preserve_source_font_size': value},
                        }),
                        patch.object(pcfg, 'let_autolayout_flag', True),
                        patch.object(pcfg, 'let_fntsize_flag', 0),
                        patch.object(pcfg.module, 'translate_source', '日本語'),
                        patch.object(pcfg.module, 'translate_target', '한국어'),
                    ):
                        result = SceneTextManager.layout_textblk(
                            manager, item, text=text,
                            mask=np.full((200, 160), 255, np.uint8),
                            bounding_rect=[0, 0, 160, 200], region_rect=[0, 0, 160, 200],
                        )
                    self.assertTrue(result)
                    if enabled:
                        self.assertAlmostEqual(item.get_fontformat().font_size, 28)
                    else:
                        self.assertLess(item.get_fontformat().font_size, 28)
                    self.assertEqual(''.join(item.toPlainText().split()), ''.join(text.split()))
                finally:
                    item.deleteLater()
                    self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
