import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from qtpy.QtCore import QCoreApplication, QEvent
from qtpy.QtGui import QFontDatabase
from qtpy.QtTest import QSignalSpy
from qtpy.QtWidgets import QApplication

from ballontranslator.ui.run_pipeline_dialog import RunPipelineDialog
from ballontranslator.ui.text_engine.item import TextBlkItem
from ballontranslator.ui.text_engine.pipeline_formatting import (
    FontSizeRecalculationThread, recalculate_existing_font_size,
)
from ballontranslator.utils.config import ModuleConfig
from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.textblock import TextBlock


class FontSizeRecalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.family = None
        for p in (Path('fonts/KoPubWorld Batang Medium.ttf'), Path(os.environ['WINDIR']) / 'Fonts/malgun.ttf'):
            if p.is_file():
                families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(p.resolve())))
                if families:
                    cls.family = families[0]
                    break

    def make_case(self) -> tuple[np.ndarray, TextBlock]:
        if not self.family:
            self.skipTest('CJK font required')
        image = np.full((200, 100, 3), 255, np.uint8)
        for y in (20, 60, 100, 140):
            cv2.rectangle(image, (40, y), (58, y + 27), (0, 0, 0), -1)
        block = TextBlock(
            xyxy=[30, 10, 70, 180], lines=[[[30, 10], [70, 10], [70, 180], [30, 180]]],
            _bounding_rect=[10, 5, 80, 190], angle=8, det_model='ctd_ctbd',
            src_is_vertical=True, _detected_font_size=99,
            text='原文', translation='맛있어 보인다',
        )
        block.font_family = self.family
        block.font_weight = 500
        block.font_size = 99
        return image, block

    def test_rebases_on_scan_retains_font_translation_and_geometry(self) -> None:
        image, block = self.make_case()
        before = deepcopy(block)
        result = recalculate_existing_font_size(image, block, ModuleConfig())
        self.assertIsNotNone(result)
        self.assertLess(result.font_size, 40)
        self.assertEqual(result.font_size, int(result.font_size))
        self.assertEqual(result.font_family, before.font_family)
        self.assertEqual(result.font_weight, before.font_weight)
        self.assertEqual(result.text, before.text)
        self.assertEqual(result.translation, before.translation)
        self.assertEqual(result.xyxy, before.xyxy)
        self.assertEqual(result.lines, before.lines)
        self.assertEqual(result._bounding_rect, before._bounding_rect)
        self.assertEqual(result.angle, before.angle)
        self.assertEqual(result.rich_text, '')
        self.assertEqual(block.font_size, 99)
        self.assertEqual(block.rich_text, before.rich_text)
        again = recalculate_existing_font_size(image, result, ModuleConfig())
        self.assertEqual(again.font_size, result.font_size)
        self.assertEqual(again._detected_font_size, result._detected_font_size)

    def test_rich_text_is_recalculated_without_changing_source_on_failure(self) -> None:
        image, block = self.make_case()
        block.rich_text = '<p><b>맛있어 보인다</b></p>'
        original = block.rich_text
        result = recalculate_existing_font_size(image, block, ModuleConfig())
        self.assertIsNotNone(result)
        self.assertEqual(result.rich_text, '')
        self.assertLess(result.font_size, block.font_size)
        self.assertEqual(block.rich_text, original)
        image.fill(255)
        self.assertIsNone(recalculate_existing_font_size(image, block, ModuleConfig()))
        self.assertEqual(block.rich_text, original)

    def test_local_rich_text_is_protected_but_equivalent_spans_are_allowed(self) -> None:
        cases = (
            ('<p><b>맛있어</b> 보인다</p>', True),
            ('<p><span style="font-size:12pt">맛있어</span> 보인다</p>', True),
            ('<p><span style="color:#ff0000">맛있어</span> 보인다</p>', True),
            ('<p><span>맛있어</span><span> 보인다</span></p>', False),
            ('<p><b>맛있어 보인다</b></p>', False),
            ('<p>서로 다른 내용</p>', True),
        )
        for html, protected in cases:
            with self.subTest(html=html):
                image, block = self.make_case()
                block.rich_text = html
                result = recalculate_existing_font_size(image, block, ModuleConfig())
                if protected:
                    self.assertIsNone(result)
                else:
                    self.assertIsNotNone(result)
                    self.assertEqual(result.rich_text, '')
                self.assertEqual(block.rich_text, html)
                self.assertEqual(block.font_size, 99)

    def test_authored_blocks_skip_measurement_and_remain_unchanged(self) -> None:
        from ballontranslator.utils.text_effects import TextEffectStack, StrokeEffect
        from ballontranslator.utils.fontformat import TextTransformStack, BendTextTransform

        for kind in ('effect', 'transform', 'slant', 'opacity'):
            with self.subTest(kind=kind):
                image, block = self.make_case()
                block.rich_text = '<p><b>맞춘 글자</b></p>'
                if kind == 'effect':
                    block.fontformat.text_effects = TextEffectStack(effects=(StrokeEffect(width=0.1),))
                elif kind == 'transform':
                    block.fontformat.text_transform = TextTransformStack((BendTextTransform(0.5),))
                elif kind == 'slant':
                    block.fontformat.glyph_slant_angle = 10
                else:
                    block.fontformat.text_effects = TextEffectStack(overall_opacity=0.5)
                before = deepcopy(block.to_dict())
                with patch('ballontranslator.utils.font_size_estimation.estimate_source_ink_size') as measure:
                    self.assertIsNone(recalculate_existing_font_size(image, block, ModuleConfig()))
                    measure.assert_not_called()
                self.assertEqual(block.to_dict(), before)

    def test_area_mode_rebases_both_source_and_target_with_saved_metric(self) -> None:
        image, block = self.make_case()
        for squared in (False, True):
            settings = ModuleConfig(textdetector_params={'ctd_ctbd': {
                'square_character_area': {'value': squared},
            }})
            result = recalculate_existing_font_size(image, block, settings)
            self.assertIsNotNone(result)
            self.assertTrue(result._source_font_size_uses_ink_area)
            self.assertEqual(result._source_font_size_uses_squared_area, squared)
            expected = 28 if squared else np.sqrt(19 * 28)
            self.assertAlmostEqual(result._detected_font_size, expected)
        default = recalculate_existing_font_size(image, block, ModuleConfig())
        self.assertTrue(default._source_font_size_uses_squared_area)

    def test_source_and_translation_area_modes_are_independent(self) -> None:
        from qtpy.QtGui import QFont
        from ballontranslator.ui.text_engine.font_family import qfont_with_family
        from ballontranslator.ui.text_engine.pipeline_formatting import _rendered_glyph_ink_sizes
        from ballontranslator.utils.fontformat import px2pt, font_weight_to_qt
        from qtpy import QT6
        image, block = self.make_case()
        for source_square in (False, True):
            results = []
            for target_square in (False, True):
                settings = ModuleConfig(textdetector_params={'ctd_ctbd': {
                    'square_character_area': {'value': source_square},
                    'translation_square_character_area': {'value': target_square},
                }})
                result = recalculate_existing_font_size(image, block, settings)
                self.assertIsNotNone(result)
                self.assertEqual(result._source_font_size_uses_squared_area, source_square)
                font = qfont_with_family(QFont(), result.font_family)
                font.setPointSizeF(px2pt(result.font_size))
                font.setWeight(QFont.Weight(font_weight_to_qt(result.font_weight, qt6=QT6)))
                measured = max(_rendered_glyph_ink_sizes(
                    font, list(dict.fromkeys(result.translation.replace(' ', ''))),
                    square_metric=target_square,
                ))
                self.assertGreaterEqual(measured, result._detected_font_size)
                results.append(result)
            self.assertEqual(results[0]._detected_font_size, results[1]._detected_font_size)
            self.assertGreaterEqual(results[0].font_size, results[1].font_size)

    def test_recalculated_item_keeps_the_existing_translation_width(self) -> None:
        image, block = self.make_case()
        block.fontformat.vertical = False
        result = recalculate_existing_font_size(image, block, ModuleConfig())
        item = TextBlkItem(result, 0)
        try:
            self.assertEqual(item.geometry_controller.logical_rect().width(), 80)
            self.assertEqual(item.toPlainText(), block.translation)
            self.assertEqual(item.fontformat.font_family, block.font_family)
        finally:
            item.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_worker_missing_original_and_cancellation_do_not_modify_live_blocks(self) -> None:
        _, block = self.make_case()
        worker = FontSizeRecalculationThread()
        spy = QSignalSpy(worker.processing_finished)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(worker, 'start'):
                worker.start_processing(directory, {'missing.png': [block]}, ModuleConfig())
            worker.run()
            changes, skipped, failures = spy[0]
            self.assertFalse(changes)
            self.assertEqual(skipped, 1)
            self.assertEqual(failures, ('missing.png',))
            with patch.object(worker, 'start'):
                worker.start_processing(directory, {'missing.png': [block]}, ModuleConfig())
            worker.request_stop()
            worker.run()
            self.assertFalse(spy[1][0])
        self.assertEqual(block.font_size, 99)
        self.assertFalse(block.rich_text)
        worker.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_vertical_scan_is_measured_outside_horizontal_translation_box(self) -> None:
        image, block = self.make_case()
        normal = recalculate_existing_font_size(image, block, ModuleConfig())
        block.fontformat.vertical = False
        block._bounding_rect = [0, 0, 100, 15]
        result = recalculate_existing_font_size(image, block, ModuleConfig())
        self.assertEqual(result.font_size, normal.font_size)
        self.assertEqual(result._bounding_rect, [0, 0, 100, 15])
        self.assertFalse(result.vertical)
        self.assertTrue(result.src_is_vertical)
        self.assertEqual(result.lines, block.lines)

    def test_shared_source_lines_use_each_split_box_without_changing_geometry(self) -> None:
        from ballontranslator.ui.text_engine.pipeline_formatting import _shared_source_line_indices

        _, first = self.make_case()
        image = np.full((300, 200, 3), 255, np.uint8)
        for y in (20, 60, 100, 140):
            cv2.rectangle(image, (20, y), (39, y + 19), (0, 0, 0), -1)
        for y in (20, 80, 140, 200):
            cv2.rectangle(image, (110, y), (149, y + 39), (0, 0, 0), -1)
        first.lines = [[[10, 10], [50, 10], [50, 180], [10, 180]],
                       [[100, 10], [160, 10], [160, 280], [100, 280]]]
        first._bounding_rect = [10, 10, 40, 170]
        second = deepcopy(first)
        second._bounding_rect = [100, 10, 60, 270]
        before = deepcopy(first.lines)
        self.assertEqual(_shared_source_line_indices([first, second]), {0, 1})
        self.assertFalse(_shared_source_line_indices([first]))
        unrestricted = recalculate_existing_font_size(image, first, ModuleConfig())
        limited = recalculate_existing_font_size(image, first, ModuleConfig(), restrict_to_box=True)
        self.assertEqual(unrestricted._detected_font_size, 40)
        self.assertEqual(limited._detected_font_size, 20)
        self.assertEqual(limited.lines, before)
        self.assertEqual(limited._bounding_rect, first._bounding_rect)
        worker = FontSizeRecalculationThread()
        spy = QSignalSpy(worker.processing_finished)
        try:
            with tempfile.TemporaryDirectory() as directory:
                cv2.imwrite(str(Path(directory) / 'split.png'), image)
                with patch.object(worker, 'start'):
                    worker.start_processing(directory, {'split.png': [first, second]}, ModuleConfig())
                worker.run()
            changes, skipped, failures = spy[0]
            self.assertEqual([result._detected_font_size for _, result in changes], [20, 40])
            self.assertEqual(skipped, 0)
            self.assertFalse(failures)
            self.assertEqual(first.lines, before)
            self.assertEqual(second.lines, before)
            self.assertEqual(first.font_size, 99)
        finally:
            worker.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_split_box_outside_original_does_not_fall_back_to_other_text(self) -> None:
        image, block = self.make_case()
        block._bounding_rect = [150, 150, 20, 20]
        self.assertIsNone(recalculate_existing_font_size(
            image, block, ModuleConfig(), restrict_to_box=True,
        ))
        self.assertEqual(block.font_size, 99)

    def test_recalculation_saves_checkpoint_before_start_and_aborts_on_save_failure(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import Mock
        from ballontranslator.ui.mainwindow import MainWindow

        events = []
        project = Mock()
        project.is_empty = False
        project.pages = {'01.png': []}
        project.save.side_effect = lambda: events.append('saved')
        project.backup.side_effect = lambda: events.append('snapshot')
        worker = Mock()
        worker.isRunning.return_value = False
        worker.start_processing.side_effect = lambda *args: events.append('started') or True
        owner = SimpleNamespace(
            imgtrans_proj=project, font_size_recalculation_thread=worker,
            module_manager=SimpleNamespace(imgtrans_thread=Mock()),
            auto_tate_chu_yoko_thread=Mock(), st_manager=Mock(),
            font_size_recalculation_progress=Mock(), tr=lambda text: text,
        )
        owner.module_manager.imgtrans_thread.isRunning.return_value = False
        owner.auto_tate_chu_yoko_thread.isRunning.return_value = False
        MainWindow.recalculate_project_font_sizes(owner, ['01.png'])
        self.assertEqual(events, ['saved', 'snapshot', 'started'])
        events.clear()
        project.save.side_effect = OSError('backup unavailable')
        with patch('ballontranslator.ui.mainwindow.create_error_dialog') as error:
            MainWindow.recalculate_project_font_sizes(owner, ['01.png'])
        self.assertFalse(events)
        error.assert_called_once()
        self.assertEqual(worker.start_processing.call_count, 1)

    def test_progress_escape_requests_stop_without_allowing_project_switch(self) -> None:
        from ballontranslator.ui.mainwindow import _FontSizeRecalculationProgressBox
        dialog = _FontSizeRecalculationProgressBox('Font Size', True)
        spy = QSignalSpy(dialog.stop_clicked)
        dialog.show()
        try:
            dialog.reject()
            self.assertTrue(dialog.isVisible())
            self.assertEqual(len(spy), 1)
        finally:
            dialog.hide()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_unmeasurable_block_is_not_changed(self) -> None:
        image, block = self.make_case()
        image.fill(255)
        self.assertIsNone(recalculate_existing_font_size(image, block, ModuleConfig()))
        self.assertEqual(block.font_size, 99)
        self.assertFalse(block.rich_text)
        image, manual = self.make_case()
        manual.det_model = None
        self.assertIsNone(recalculate_existing_font_size(image, manual, ModuleConfig()))
        self.assertEqual(manual.font_size, 99)

    def test_worker_only_processes_selected_pages_and_keeps_live_blocks_untouched(self) -> None:
        image, block = self.make_case()
        worker = FontSizeRecalculationThread()
        spy = QSignalSpy(worker.processing_finished)
        with tempfile.TemporaryDirectory() as directory:
            cv2.imwrite(str(Path(directory) / 'second.png'), image)
            self.assertTrue(worker.start_processing(directory, {'second.png': [block]}, ModuleConfig()))
            if not len(spy):
                self.assertTrue(spy.wait(10000))
            self.assertTrue(worker.wait(10000))
        changes, skipped, failures = spy[0]
        self.assertEqual(len(changes), 1)
        self.assertEqual(skipped, 0)
        self.assertFalse(failures)
        self.assertIs(changes[0][0], block)
        self.assertLess(changes[0][1].font_size, 40)
        self.assertEqual(block.font_size, 99)
        self.assertFalse(block.rich_text)
        worker.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_range_dialog_chooses_only_requested_pages(self) -> None:
        project = ProjImgTrans()
        project.pages = {f'{i:03}.png': [] for i in range(1, 6)}
        project._image_info = {name: {'finish_code': 0} for name in project.pages}
        with patch('ballontranslator.ui.run_pipeline_dialog.save_config'):
            dialog = RunPipelineDialog(project=project)
            try:
                dialog.workflow_selector.setCurrentIndex(2)
                dialog.font_size_range.range_end.setValue(4)
                dialog.font_size_range.range_start.setValue(2)
                self.assertEqual(dialog.selected_pages(), ['002.png', '003.png', '004.png'])
                dialog._finish_font_size()
                self.assertEqual(dialog.result(), RunPipelineDialog.FONT_SIZE)
            finally:
                dialog.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
