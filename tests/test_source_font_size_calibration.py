import os
import unittest
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path

import cv2
import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from qtpy.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QPainter
from qtpy.QtWidgets import QApplication

from ballontranslator.ui.text_engine.pipeline_formatting import (
    apply_source_font_size_calibration, preserve_source_font_size,
)
from ballontranslator.ui.text_engine.font_family import qfont_with_family
from ballontranslator.ui.misc import pixmap2ndarray
from ballontranslator.utils.config import ModuleConfig
from ballontranslator.utils.font_size_estimation import (
    estimate_source_ink_size, glyph_ink_areas,
)
from ballontranslator.utils.fontformat import px2pt
from ballontranslator.utils.textblock import TextBlock


def source_case(vertical=True, light_text=False):
    image = np.full((120, 60, 3), 0 if light_text else 255, np.uint8)
    color = (255, 255, 255) if light_text else (0, 0, 0)
    for y in (20, 45, 70, 95):
        cv2.rectangle(image, (20, y), (37, y + 14), color, -1)
    points = [[10, 10], [50, 10], [50, 115], [10, 115]]
    if not vertical:
        image = image.transpose(1, 0, 2).copy()
        points = [[10, 10], [115, 10], [115, 50], [10, 50]]
    return image, TextBlock(lines=[points], src_is_vertical=vertical, _detected_font_size=40)


class SourceInkTests(unittest.TestCase):
    def test_separate_strokes_and_inverted_ink_use_line_cross_section(self):
        for vertical in (True, False):
            for light_text in (True, False):
                with self.subTest(vertical=vertical, light_text=light_text):
                    image, block = source_case(vertical, light_text)
                    self.assertAlmostEqual(estimate_source_ink_size(image, block), 18, delta=2)

    def test_detector_option_controls_source_measurement(self):
        from ballontranslator.modules.textdetector.detector_ctd import ComicTextDetector

        for enabled in (True, False):
            with self.subTest(enabled=enabled), patch.object(
                ComicTextDetector, 'params', deepcopy(ComicTextDetector.params),
            ):
                image, block = source_case()
                original_lines = deepcopy(block.lines)
                detector = ComicTextDetector(calibrate_source_font_size=enabled)
                detector.model = lambda img: (None, np.zeros(img.shape[:2], np.uint8), [block])
                _, blocks = detector.detect(image)
                expected = 18 if enabled else 40
                self.assertAlmostEqual(blocks[0]._detected_font_size, expected, delta=2)
                self.assertEqual(blocks[0].lines, original_lines)

    def test_character_extent_accounts_for_tall_glyphs_without_counting_strokes(self) -> None:
        image = np.full((200, 60, 3), 255, np.uint8)
        for y in (15, 55, 95, 135):
            cv2.rectangle(image, (20, y), (37, y + 5), (0, 0, 0), -1)
            cv2.rectangle(image, (20, y + 8), (37, y + 27), (0, 0, 0), -1)
        block = TextBlock(lines=[[[10, 10], [50, 10], [50, 180], [10, 180]]],
                          src_is_vertical=True, _detected_font_size=40)
        for vertical in (True, False):
            with self.subTest(vertical=vertical):
                self.assertAlmostEqual(estimate_source_ink_size(image, block), 18, delta=1)
                self.assertAlmostEqual(estimate_source_ink_size(image, block, True), 28, delta=1)
                image = image.transpose(1, 0, 2).copy()
                block.lines = [np.asarray(line)[:, ::-1].tolist() for line in block.lines]
                block.lines[0] = [block.lines[0][i] for i in (0, 3, 2, 1)]
                block.src_is_vertical = False

    def test_hybrid_detection_records_the_measurement_basis(self) -> None:
        from ballontranslator.modules.textdetector.detector_ctd_ctbd import CTDCTBDTextDetector
        for extent in (True, False):
            image, block = source_case()
            detector = CTDCTBDTextDetector(calibrate_character_extent=extent)
            with patch.object(CTDCTBDTextDetector, 'all_model_loaded', return_value=True), patch.object(
                CTDCTBDTextDetector, '_detect', return_value=(np.zeros(image.shape[:2], np.uint8), [block]),
            ):
                _, blocks = detector.detect(image)
            self.assertEqual(blocks[0]._source_font_size_uses_character_extent, extent)
            self.assertEqual(blocks[0]._source_font_size_uses_ink_area, extent)
            self.assertEqual(blocks[0]._source_font_size_uses_squared_area, extent)

    def test_short_near_square_ink_uses_larger_dimension_in_both_orientations(self) -> None:
        for vertical in (True, False):
            for inverted in (True, False):
                with self.subTest(vertical=vertical, inverted=inverted):
                    image = np.full((80, 80, 3), 0 if inverted else 255, np.uint8)
                    color = (255, 255, 255) if inverted else (0, 0, 0)
                    # 떨어진 두 획을 하나의 글자 모양으로 평가한다.
                    cv2.rectangle(image, (22, 20), (28, 59), color, -1)
                    cv2.rectangle(image, (37, 25), (55, 55), color, -1)
                    block = TextBlock(lines=[[[10, 10], [70, 10], [70, 70], [10, 70]]],
                                      src_is_vertical=vertical, _detected_font_size=60)
                    self.assertAlmostEqual(estimate_source_ink_size(image, block, True), 40, delta=1)
                    self.assertIsNone(estimate_source_ink_size(image, block, False))

    def test_dense_single_glyph_and_small_boundary_fragments(self) -> None:
        for vertical in (True, False):
            for inverted in (True, False):
                for dense in (True, False):
                    with self.subTest(vertical=vertical, inverted=inverted, dense=dense):
                        image = np.full((80, 80, 3), 255, np.uint8)
                        if dense:
                            cv2.rectangle(image, (14, 14), (65, 65), (0, 0, 0), -1)
                            expected = 52
                        else:
                            cv2.rectangle(image, (25, 25), (54, 54), (0, 0, 0), -1)
                            cv2.line(image, (10, 10), (16, 10), (0, 0, 0), 2)
                            cv2.line(image, (65, 70), (70, 70), (0, 0, 0), 2)
                            cv2.rectangle(image, (68, 11), (69, 11), (0, 0, 0), -1)
                            expected = 30
                        if inverted:
                            image = 255 - image
                        block = TextBlock(lines=[[[10, 10], [70, 10], [70, 70], [10, 70]]],
                                          src_is_vertical=vertical, text='あ')
                        for rect in (None, (5, 5, 70, 70)):
                            self.assertAlmostEqual(estimate_source_ink_size(
                                image, block, True, area_metric=True, square_metric=True,
                                measurement_rect=rect,
                            ), expected, delta=1)

    def test_measurement_box_masks_pixels_outside_rotated_source_line(self) -> None:
        image = np.full((150, 150, 3), 255, np.uint8)
        cv2.rectangle(image, (55, 35), (74, 54), (0, 0, 0), -1)
        cv2.rectangle(image, (55, 80), (89, 114), (0, 0, 0), -1)
        block = TextBlock(lines=[[[40, 10], [100, 20], [80, 135], [20, 125]]],
                          src_is_vertical=True, text='文字')
        unrestricted = estimate_source_ink_size(image, block, True, area_metric=True, square_metric=True)
        limited = estimate_source_ink_size(image, block, True, area_metric=True, square_metric=True,
                                          measurement_rect=(40, 25, 45, 40))
        self.assertIsNotNone(limited)
        self.assertLess(limited, unrestricted)
        self.assertLess(limited, 27)

    def test_square_rotated_detector_region_does_not_merge_two_page_aligned_glyphs(self) -> None:
        image = np.full((170, 170, 3), 255, np.uint8)
        cv2.rectangle(image, (55, 40), (94, 79), (0, 0, 0), -1)
        cv2.rectangle(image, (60, 95), (94, 126), (0, 0, 0), -1)
        points = [[75, 10], [145, 80], [75, 150], [5, 80]]
        for vertical in (True, False):
            with self.subTest(vertical=vertical):
                block = TextBlock(lines=[points], src_is_vertical=vertical, text='んつ')
                measured = estimate_source_ink_size(image, block, True, area_metric=True,
                                                    square_metric=True)
                self.assertAlmostEqual(measured, 40, delta=3)
            image = image.transpose(1, 0, 2).copy()
            points = [[y, x] for x, y in points]
            points = [points[i] for i in (0, 3, 2, 1)]

    def test_short_elongated_ink_and_dots_do_not_define_character_size(self) -> None:
        block = TextBlock(lines=[[[10, 10], [70, 10], [70, 70], [10, 70]]],
                          src_is_vertical=True, _detected_font_size=60)
        for mode in ('dash', 'vertical_dash', 'dots', 'isolated_dot', 'diagonal'):
            with self.subTest(mode=mode):
                image = np.full((80, 80, 3), 255, np.uint8)
                if mode == 'dash':
                    cv2.rectangle(image, (20, 38), (59, 42), (0, 0, 0), -1)
                elif mode == 'vertical_dash':
                    cv2.rectangle(image, (38, 20), (42, 59), (0, 0, 0), -1)
                elif mode == 'dots':
                    for x in (22, 37, 52):
                        cv2.circle(image, (x, 40), 2, (0, 0, 0), -1)
                elif mode == 'isolated_dot':
                    cv2.rectangle(image, (38, 38), (42, 42), (0, 0, 0), -1)
                else:
                    cv2.line(image, (20, 20), (59, 59), (0, 0, 0), 1)
                self.assertIsNone(estimate_source_ink_size(image, block, True))

    def test_narrow_fragment_and_nominal_average_do_not_shrink_valid_lines(self) -> None:
        image = np.full((200, 200, 3), 255, np.uint8)
        lines = []
        for x in (10, 60, 110):
            lines.append([[x, 10], [x + 40, 10], [x + 40, 180], [x, 180]])
            for y in (20, 60, 100, 140):
                cv2.rectangle(image, (x + 6, y), (x + 33, y + 27), (0, 0, 0), -1)
        fragment = [[170, 10], [182, 10], [182, 180], [170, 180]]
        for y in (30, 60, 90):
            cv2.circle(image, (176, y), 2, (0, 0, 0), -1)
        for vertical in (True, False):
            if not vertical:
                image = image.transpose(1, 0, 2).copy()
                lines = [[[p[1], p[0]] for p in line] for line in lines]
                lines = [[line[i] for i in (0, 3, 2, 1)] for line in lines]
                fragment = [[p[1], p[0]] for p in fragment]
                fragment = [fragment[i] for i in (0, 3, 2, 1)]
            normal = TextBlock(lines=deepcopy(lines), src_is_vertical=vertical, _detected_font_size=40)
            mixed = TextBlock(lines=deepcopy(lines) + [fragment], src_is_vertical=vertical,
                              _detected_font_size=33)
            self.assertAlmostEqual(estimate_source_ink_size(image, normal, True), 28, delta=1)
            self.assertAlmostEqual(estimate_source_ink_size(image, mixed, True), 28, delta=1)

    def test_calibration_applies_detector_multiplier_once(self) -> None:
        from ballontranslator.modules.textdetector.detector_ctd import ComicTextDetector
        image, block = source_case()
        with patch.object(ComicTextDetector, 'params', deepcopy(ComicTextDetector.params)):
            detector = ComicTextDetector(**{'calibrate_source_font_size': True, 'font size multiplier': 1.5})
            detector.model = lambda img: (None, np.zeros(img.shape[:2], np.uint8), [block])
            _, blocks = detector.detect(image)
        self.assertAlmostEqual(blocks[0]._detected_font_size, 27, delta=1)

    def test_one_valid_glyph_in_long_crop_uses_longer_side_and_ignores_dot(self) -> None:
        image = np.full((200, 80, 3), 255, np.uint8)
        cv2.rectangle(image, (25, 25), (44, 52), (0, 0, 0), -1)
        cv2.circle(image, (34, 100), 2, (0, 0, 0), -1)
        block = TextBlock(lines=[[[15, 10], [55, 10], [55, 180], [15, 180]]],
                          src_is_vertical=True, _detected_font_size=40, text=['は…'])
        for vertical in (True, False):
            self.assertAlmostEqual(estimate_source_ink_size(image, block, True), 28, delta=1)
            image = image.transpose(1, 0, 2).copy()
            block.lines = [np.asarray(line)[:, ::-1].tolist() for line in block.lines]
            block.lines[0] = [block.lines[0][i] for i in (0, 3, 2, 1)]
            block.src_is_vertical = False

    def test_flat_strokes_and_known_punctuation_only_text_are_excluded(self) -> None:
        block = TextBlock(lines=[[[15, 10], [55, 10], [55, 180], [15, 180]]],
                          src_is_vertical=True, _detected_font_size=40)
        image = np.full((200, 80, 3), 255, np.uint8)
        for y in (25, 70, 120):
            cv2.rectangle(image, (25, y), (44, y + 3), (0, 0, 0), -1)
        self.assertIsNone(estimate_source_ink_size(image, block, True))
        for text in ('……', '......', 'ー', '!?'):
            block.text = [text]
            image.fill(255)
            cv2.rectangle(image, (25, 25), (44, 52), (0, 0, 0), -1)
            self.assertIsNone(estimate_source_ink_size(image, block, True))

    def test_area_metric_uses_both_ink_dimensions(self) -> None:
        image = np.full((80, 80, 3), 255, np.uint8)
        cv2.rectangle(image, (22, 20), (28, 59), (0, 0, 0), -1)
        cv2.rectangle(image, (37, 25), (55, 55), (0, 0, 0), -1)
        block = TextBlock(lines=[[[10, 10], [70, 10], [70, 70], [10, 70]]],
                          src_is_vertical=True)
        self.assertAlmostEqual(estimate_source_ink_size(image, block, area_metric=True),
                               np.sqrt(34 * 40), delta=1)

    def test_area_measurement_keeps_letters_separated_by_small_gaps(self) -> None:
        image = np.full((160, 70, 3), 255, np.uint8)
        for y in (20, 50, 80):
            cv2.rectangle(image, (20, y), (47, y + 27), (0, 0, 0), -1)
        block = TextBlock(lines=[[[10, 10], [55, 10], [55, 140], [10, 140]]],
                          src_is_vertical=True)
        self.assertAlmostEqual(estimate_source_ink_size(image, block, area_metric=True), 28, delta=1)

    def test_area_uses_large_glyphs_without_small_kana_or_thin_punctuation(self) -> None:
        for vertical in (True, False):
            image = np.full((190, 70, 3), 255, np.uint8)
            for x, y, width, height in ((20, 15, 28, 29), (23, 55, 23, 18),
                                        (20, 90, 27, 26), (30, 130, 5, 18)):
                cv2.rectangle(image, (x, y), (x + width - 1, y + height - 1), (0, 0, 0), -1)
            points = [[10, 5], [60, 5], [60, 180], [10, 180]]
            if not vertical:
                image = image.transpose(1, 0, 2).copy()
                points = [[5, 10], [180, 10], [180, 60], [5, 60]]
            block = TextBlock(lines=[points], src_is_vertical=vertical)
            self.assertAlmostEqual(estimate_source_ink_size(image, block, area_metric=True),
                                   np.sqrt(28 * 29), delta=0.1)

    def test_area_maximum_keeps_large_glyph_without_statistical_trimming(self) -> None:
        image = np.full((340, 80, 3), 255, np.uint8)
        for y in (10, 50, 90, 130, 170, 210):
            cv2.rectangle(image, (20, y), (39, y + 19), (0, 0, 0), -1)
        cv2.rectangle(image, (20, 260), (51, 289), (0, 0, 0), -1)
        block = TextBlock(lines=[[[5, 0], [70, 0], [70, 330], [5, 330]]], src_is_vertical=True)
        self.assertAlmostEqual(estimate_source_ink_size(image, block, area_metric=True), np.sqrt(32 * 30))
        self.assertEqual(estimate_source_ink_size(image, block, area_metric=True, square_metric=True), 32)
        self.assertEqual(glyph_ink_areas(32, 30), (960, 1024))

    def test_crop_border_and_clipped_dash_do_not_inflate_glyph_area(self) -> None:
        image = np.full((120, 60, 3), 255, np.uint8)
        cv2.rectangle(image, (51, 0), (59, 18), (0, 0, 0), -1)
        cv2.rectangle(image, (20, 10), (44, 33), (0, 0, 0), -1)
        cv2.rectangle(image, (20, 43), (49, 72), (0, 0, 0), -1)
        cv2.rectangle(image, (34, 76), (36, 119), (0, 0, 0), -1)
        for vertical in (True, False):
            for square in (True, False):
                with self.subTest(vertical=vertical, square=square):
                    sample = image if vertical else image.transpose(1, 0, 2).copy()
                    height, width = sample.shape[:2]
                    block = TextBlock(
                        lines=[[[0, 0], [width - 1, 0],
                                [width - 1, height - 1], [0, height - 1]]],
                        src_is_vertical=vertical,
                    )
                    self.assertAlmostEqual(estimate_source_ink_size(
                        sample, block, area_metric=True, square_metric=square,
                    ), 30, delta=0.5)

    def test_blank_crop_keeps_detector_estimate(self):
        image, block = source_case()
        image.fill(255)
        self.assertIsNone(estimate_source_ink_size(image, block))
        self.assertEqual(block._detected_font_size, 40)


class GlyphCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.family = None
        # Windows offscreen Qt does not populate the system font database.
        candidates = (
            Path(__file__).resolve().parents[1] / 'fonts' / 'KoPubWorld Batang Medium.ttf',
            Path(os.environ.get('WINDIR', '/nonexistent')) / 'Fonts' / 'malgun.ttf',
        )
        for path in candidates:
            if path.is_file():
                index = QFontDatabase.addApplicationFont(str(path))
                families = QFontDatabase.applicationFontFamilies(index)
                if families:
                    cls.family = families[0]
                    break

    def test_visible_glyph_size_matches_source_and_repeated_pass_is_stable(self):
        if self.family is None:
            self.skipTest('A CJK font is required for visible glyph calibration')
        for detector in ('ctd', 'ysgyolo', 'ysg_ctd', 'ctd_ctbd'):
            for vertical in (True, False):
                with self.subTest(detector=detector, vertical=vertical):
                    settings = ModuleConfig(textdetector_params={detector: {
                        'calibrate_source_font_size': {'value': True},
                        'calibrate_character_extent': False,
                        'preserve_source_font_size': {'value': True},
                    }})
                    block = TextBlock(det_model=detector, src_is_vertical=vertical,
                                      _detected_font_size=28, translation='가나다라마바사')
                    block.fontformat.font_family = self.family
                    block.fontformat.font_size = 28
                    self.assertTrue(apply_source_font_size_calibration(block, settings))
                    size = block.font_size
                    font = qfont_with_family(QFont(), block.fontformat.font_family)
                    font.setPointSizeF(px2pt(size))
                    metrics = QFontMetricsF(font)
                    values = []
                    for char in block.translation:
                        bounds = metrics.tightBoundingRect(char)
                        values.append(bounds.width() if vertical else bounds.height())
                    self.assertAlmostEqual(float(np.median(values)), 28, delta=2)
                    self.assertTrue(apply_source_font_size_calibration(block, settings))
                    self.assertEqual(block.font_size, size)
                    self.assertEqual(block._detected_font_size, 28)
                    self.assertTrue(preserve_source_font_size(block, settings))

    def test_character_extent_matches_both_glyph_dimensions(self) -> None:
        if self.family is None:
            self.skipTest('A CJK font is required for visible glyph calibration')
        settings = ModuleConfig(textdetector_params={'ctd_ctbd': {
            'calibrate_character_extent': {'value': True},
        }})
        block = TextBlock(det_model='ctd_ctbd', src_is_vertical=True,
                          _detected_font_size=28, translation='맛있어 보인다',
                          _source_font_size_uses_character_extent=True)
        block.fontformat.font_family = self.family
        self.assertTrue(apply_source_font_size_calibration(block, settings))
        size = block.font_size
        font = qfont_with_family(QFont(), self.family)
        font.setPointSizeF(px2pt(size))
        metrics = QFontMetricsF(font)
        extents = [max(metrics.tightBoundingRect(c).width(), metrics.tightBoundingRect(c).height())
                   for c in dict.fromkeys(block.translation) if not c.isspace()]
        self.assertAlmostEqual(float(np.median(extents)), 28, delta=2)
        apply_source_font_size_calibration(block, settings)
        self.assertEqual(block.font_size, size)

    def test_older_project_keeps_cross_section_and_new_measurement_round_trips(self) -> None:
        if self.family is None:
            self.skipTest('A CJK font is required for visible glyph calibration')
        settings = ModuleConfig(textdetector_params={'ctd_ctbd': {'calibrate_character_extent': True}})
        old = TextBlock(det_model='ctd_ctbd', _detected_font_size=24,
                        translation='맛있어 보인다')
        old.font_family = self.family
        apply_source_font_size_calibration(old, settings)
        expected = old.font_size
        restored = TextBlock(**old.to_dict(deep_copy=True))
        self.assertFalse(restored._source_font_size_uses_character_extent)
        apply_source_font_size_calibration(restored, settings)
        self.assertEqual(restored.font_size, expected)
        old._source_font_size_uses_character_extent = True
        restored = TextBlock(**old.to_dict(deep_copy=True))
        self.assertTrue(restored._source_font_size_uses_character_extent)
        with patch('ballontranslator.utils.textblock.LOGGER.warning') as warning:
            malformed = TextBlock(_source_font_size_uses_character_extent='false')
        self.assertFalse(malformed._source_font_size_uses_character_extent)
        warning.assert_called_once()

    def test_target_area_matches_source_and_survives_reload(self) -> None:
        if self.family is None:
            self.skipTest('A CJK font is required')
        block = TextBlock(det_model='ctd_ctbd', translation='어렵게 학교 왔는데 따분하지 않아',
                          _detected_font_size=30, _source_font_size_uses_character_extent=True,
                          _source_font_size_uses_ink_area=True)
        block.font_family = self.family
        self.assertTrue(apply_source_font_size_calibration(block, ModuleConfig()))
        font = qfont_with_family(QFont(), self.family)
        font.setPointSizeF(px2pt(block.font_size))
        metrics = QFontMetricsF(font)
        # 별도의 흰 바탕에 그려 Qt 추정 경계가 아닌 최종 잉크 크기를 검증한다.
        extents = []
        for char in dict.fromkeys(block.translation):
            if char.isspace():
                continue
            image = QImage(140, 140, QImage.Format.Format_RGBA8888)
            image.fill(QColor('white'))
            painter = QPainter(image)
            painter.setFont(font)
            painter.setPen(QColor('black'))
            painter.drawText(30, 90, char)
            painter.end()
            pixels = pixmap2ndarray(image)
            ys, xs = np.nonzero(pixels[:, :, :3].mean(axis=2) < 128)
            extents.append(np.sqrt((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)))
        measured = max(extents)
        self.assertGreaterEqual(measured, 30)
        self.assertLess(measured, 32)
        expected = block.font_size
        restored = TextBlock(**block.to_dict(deep_copy=True))
        self.assertTrue(restored._source_font_size_uses_ink_area)
        apply_source_font_size_calibration(restored, ModuleConfig())
        self.assertEqual(restored.font_size, expected)
        with patch('ballontranslator.utils.textblock.LOGGER.warning') as warning:
            malformed = TextBlock(_source_font_size_uses_ink_area='false')
        self.assertFalse(malformed._source_font_size_uses_ink_area)
        warning.assert_called_once()

    def test_squared_area_matches_rendered_longest_side_and_survives_reload(self) -> None:
        if self.family is None:
            self.skipTest('A CJK font is required')
        from ballontranslator.ui.text_engine.pipeline_formatting import _rendered_glyph_ink_sizes
        block = TextBlock(det_model='ctd_ctbd', translation='알았어', _detected_font_size=25,
                          _source_font_size_uses_ink_area=True,
                          _source_font_size_uses_squared_area=True)
        block.font_family = self.family
        self.assertTrue(apply_source_font_size_calibration(block, ModuleConfig()))
        font = qfont_with_family(QFont(), self.family)
        font.setPointSizeF(px2pt(block.font_size))
        rectangles = _rendered_glyph_ink_sizes(font, list(block.translation))
        squares = _rendered_glyph_ink_sizes(font, list(block.translation), square_metric=True)
        self.assertTrue(all(square >= rectangle for square, rectangle in zip(squares, rectangles)))
        self.assertGreaterEqual(max(squares), 25)
        self.assertLess(max(squares), 27)
        restored = TextBlock(**block.to_dict(deep_copy=True))
        self.assertTrue(restored._source_font_size_uses_squared_area)
        apply_source_font_size_calibration(restored, ModuleConfig())
        self.assertEqual(restored.font_size, block.font_size)
        with patch('ballontranslator.utils.textblock.LOGGER.warning') as warning:
            malformed = TextBlock(_source_font_size_uses_squared_area='false')
        self.assertFalse(malformed._source_font_size_uses_squared_area)
        warning.assert_called_once()

    def test_disabled_option_preserves_existing_font_size(self):
        for detector in ('ctd', 'ysgyolo', 'ysg_ctd', 'ctd_ctbd'):
            settings = ModuleConfig(textdetector_params={detector: {
                'calibrate_source_font_size': False, 'preserve_source_font_size': False,
            }})
            block = TextBlock(det_model=detector, _detected_font_size=28, translation='한글')
            before = deepcopy(block.fontformat)
            self.assertFalse(apply_source_font_size_calibration(block, settings))
            self.assertEqual(block.fontformat, before)
            self.assertFalse(preserve_source_font_size(block, settings))

    def test_latin_translation_and_authored_rich_text_are_unchanged(self):
        settings = ModuleConfig()
        for translation, rich_text in (('Hello', ''), ('한글', '<p>한글</p>')):
            block = TextBlock(det_model='ctd_ctbd', _detected_font_size=28,
                              translation=translation, rich_text=rich_text)
            self.assertFalse(apply_source_font_size_calibration(block, settings))

    def test_font_size_limits_are_applied_after_calibration(self):
        if self.family is None:
            self.skipTest('A CJK font is required for visible glyph calibration')
        settings = ModuleConfig(textdetector_params={'ctd_ctbd': {'font size max': 20}})
        block = TextBlock(det_model='ctd_ctbd', _detected_font_size=28, translation='한글')
        block.fontformat.font_family = self.family
        self.assertTrue(apply_source_font_size_calibration(block, settings))
        self.assertLessEqual(block.font_size, 20)


if __name__ == '__main__':
    unittest.main()
