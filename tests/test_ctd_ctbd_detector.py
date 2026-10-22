import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from ballontranslator.modules.textdetector.detector_ctd_ctbd import (
    CTDCTBDTextDetector, merge_layout_fragments, split_bubble_blocks,
    recover_bubble_punctuation,
)
from ballontranslator.modules.textdetector.detector_ctbd import RTDetrV2TextDetector
from ballontranslator.utils.textblock import TextBlock


def make_block(box, size=35):
    x1, y1, x2, y2 = box
    return TextBlock(
        xyxy=list(box), lines=[[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]],
        src_is_vertical=True, _detected_font_size=size,
    )


class LayoutFragmentTests(unittest.TestCase):
    def test_nested_fragment_keeps_lines_and_source_size(self):
        main = make_block([1161, 609, 1281, 809])
        main.lines = [
            [[1239, 609], [1281, 609], [1281, 677], [1239, 677]],
            [[1203, 614], [1236, 614], [1236, 778], [1203, 778]],
            [[1161, 612], [1192, 612], [1192, 809], [1161, 809]],
        ]
        fragment = make_block([1241, 678, 1275, 745], 34)
        layout = make_block([1143, 586, 1280, 829])
        result = merge_layout_fragments([fragment, main], [layout], 1336, 2000)
        self.assertEqual(result, [main])
        self.assertEqual(len(main.lines), 4)
        self.assertEqual(main._detected_font_size, 35)
        self.assertEqual(main.font_size, 35)

    def test_separate_dialogue_is_not_merged(self):
        first = make_block([10, 10, 30, 70])
        second = make_block([40, 10, 60, 70])
        blocks = [first, second]
        self.assertEqual(merge_layout_fragments(
            blocks, [make_block([0, 0, 80, 80])], 100, 100,
        ), blocks)

    def test_real_page_line_continuations_keep_ocr_geometry(self) -> None:
        cases = (
            ([545, 236, 580, 288], 35, [547, 306, 575, 361], 28, [520, 213, 600, 401]),
            ([194, 1512, 241, 1736], 44, [200, 1780, 233, 1820], 33, [175, 1493, 260, 1842]),
            ([639, 1409, 673, 1473], 34, [639, 1480, 670, 1536], 31, [609, 1379, 697, 1579]),
        )
        for first_box, first_size, second_box, second_size, layout_box in cases:
            for vertical in (True, False):
                with self.subTest(box=first_box, vertical=vertical):
                    def orient(box: list[int]) -> list[int]:
                        return box if vertical else [box[1], box[0], box[3], box[2]]
                    first = make_block(orient(first_box), first_size)
                    second = make_block(orient(second_box), second_size)
                    first.src_is_vertical = second.src_is_vertical = vertical
                    lines = deepcopy(first.lines + second.lines)
                    blocks = merge_layout_fragments(
                        [first, second], [make_block(orient(layout_box))], 2000, 2000,
                    )
                    self.assertEqual(len(blocks), 1)
                    self.assertEqual(sorted(blocks[0].lines), sorted(lines))
                    self.assertEqual(blocks[0]._detected_font_size, first_size)
                    self.assertEqual(blocks[0].xyxy, orient([
                        min(first_box[0], second_box[0]), min(first_box[1], second_box[1]),
                        max(first_box[2], second_box[2]), max(first_box[3], second_box[3]),
                    ]))

    def test_continuations_require_alignment_proximity_and_same_text_box(self) -> None:
        for box in ([45, 80, 75, 120], [10, 150, 40, 190]):
            first, second = make_block([10, 10, 40, 70]), make_block(box)
            blocks = [first, second]
            self.assertEqual(merge_layout_fragments(
                blocks, [make_block([0, 0, 100, 200])], 200, 200,
            ), blocks)
        first, second = make_block([10, 10, 40, 70]), make_block([10, 90, 40, 130])
        layouts = [make_block([0, 0, 50, 80]), make_block([0, 85, 50, 140])]
        self.assertEqual(merge_layout_fragments([first, second], layouts, 200, 200), [first, second])

    def test_different_size_or_orientation_is_not_merged(self):
        for size, vertical, angle in ((15, True, 0), (35, False, 0), (35, True, 30)):
            with self.subTest(size=size, vertical=vertical, angle=angle):
                main = make_block([10, 10, 70, 70])
                fragment = make_block([20, 20, 30, 40], size)
                fragment.src_is_vertical = vertical
                fragment.angle = angle
                blocks = [main, fragment]
                self.assertEqual(merge_layout_fragments(
                    blocks, [make_block([0, 0, 80, 80])], 100, 100,
                ), blocks)


class PunctuationMaskTests(unittest.TestCase):
    def test_six_fully_missed_dots_are_recovered_in_both_directions(self) -> None:
        for vertical in (True, False):
            with self.subTest(vertical=vertical):
                image = np.full((200, 100, 3), 255, np.uint8)
                for y in range(55, 146, 18):
                    cv2.circle(image, (50, y), 2, (0, 0, 0), -1)
                # 별도 열의 점열과 검출 사각형을 가로지르는 테두리는 남긴다.
                for y in range(55, 146, 18):
                    cv2.circle(image, (25, y), 2, (0, 0, 0), -1)
                cv2.line(image, (20, 20), (20, 180), (0, 0, 0), 2)
                source = make_block([40, 25, 60, 45], 24)
                layout = make_block([10, 10, 90, 180])
                layout.bubble_xyxy = [0, 0, 100, 200]
                if not vertical:
                    image = image.transpose(1, 0, 2).copy()
                    for block in (source, layout):
                        a, b, c, d = block.xyxy
                        block.xyxy = [b, a, d, c]
                        block.lines = [np.asarray(line)[:, ::-1].tolist() for line in block.lines]
                    layout.bubble_xyxy = [0, 0, 200, 100]
                source.src_is_vertical = vertical
                mask = np.zeros(image.shape[:2], np.uint8)
                recover_bubble_punctuation(image, mask, [source], [layout], {0: 0})
                actual = mask if vertical else mask.T
                self.assertTrue(all(actual[y, 50] == 255 for y in range(55, 146, 18)))
                self.assertFalse(np.any(actual[:, :30]))

    def test_detector_setting_disables_dot_recovery(self) -> None:
        image = np.full((200, 100, 3), 255, np.uint8)
        for y in range(55, 146, 18):
            cv2.circle(image, (50, y), 2, (0, 0, 0), -1)
        layout = make_block([10, 10, 90, 180])
        layout.bubble_xyxy = [0, 0, 100, 200]
        for enabled in (True, False):
            source = make_block([40, 25, 60, 45], 24)
            detector = CTDCTBDTextDetector(**{
                'recover_bubble_punctuation': enabled, 'mask dilate size': 0,
            })
            detector.ctd_model = lambda img: (None, np.zeros(img.shape[:2], np.uint8), [source])
            with patch.object(RTDetrV2TextDetector, '_detect', return_value=(None, [layout])):
                mask, blocks = detector._detect(image)
            self.assertEqual(bool(np.any(mask)), enabled)
            self.assertEqual(len(blocks), 1)
            self.assertEqual(blocks[0].lines, source.lines)

    def test_seeded_long_dash_and_trailing_dot_are_completed(self) -> None:
        image = np.full((200, 100, 3), 255, np.uint8)
        cv2.line(image, (50, 40), (50, 140), (0, 0, 0), 2)
        cv2.circle(image, (50, 155), 2, (0, 0, 0), -1)
        mask = np.zeros(image.shape[:2], np.uint8)
        mask[40:60, 49:52] = 255
        before = mask.copy()
        source = make_block([40, 25, 60, 70], 24)
        layout = make_block([10, 10, 90, 180])
        layout.bubble_xyxy = [0, 0, 100, 200]
        recover_bubble_punctuation(image, mask, [source], [layout], {0: 0})
        self.assertEqual(mask[130, 50], 255)
        self.assertEqual(mask[155, 50], 255)
        self.assertTrue(np.all(mask[before > 0] == 255))

    def test_unseeded_dash_sparse_dots_and_dark_background_are_ignored(self) -> None:
        for dark in (True, False):
            image = np.full((200, 100, 3), 0 if dark else 255, np.uint8)
            color = (255, 255, 255) if dark else (0, 0, 0)
            cv2.line(image, (50, 40), (50, 100), color, 2)
            cv2.circle(image, (50, 155), 2, color, -1)
            source = make_block([40, 25, 60, 70], 24)
            layout = make_block([10, 10, 90, 180])
            layout.bubble_xyxy = [0, 0, 100, 200]
            mask = np.zeros(image.shape[:2], np.uint8)
            recover_bubble_punctuation(image, mask, [source], [layout], {0: 0})
            self.assertFalse(np.any(mask))


class BubbleSeparationTests(unittest.TestCase):
    def make_case(self) -> tuple[TextBlock, list[TextBlock]]:
        source = make_block([134, 1543, 266, 1855], 33.67)
        source.lines = [
            [[220, 1546], [252, 1543], [266, 1715], [234, 1718]],
            [[187, 1545], [223, 1543], [238, 1756], [202, 1759]],
            [[134, 1683], [167, 1681], [177, 1853], [144, 1855]],
        ]
        first = make_block([176, 1528, 273, 1768])
        first.bubble_xyxy = [154, 1498, 300, 1794]
        second = make_block([129, 1670, 185, 1860])
        second.bubble_xyxy = [117, 1640, 207, 1883]
        return source, [first, second]

    def test_009_lower_left_splits_without_losing_source_lines(self) -> None:
        source, layouts = self.make_case()
        original = deepcopy(source)
        result = split_bubble_blocks([source], layouts, 1336, 2000)
        self.assertEqual([len(b.lines) for b in result], [2, 1])
        self.assertEqual(sorted(line for b in result for line in b.lines), sorted(original.lines))
        self.assertEqual(source.lines, original.lines)
        self.assertEqual(result[0].xyxy, [187, 1543, 266, 1759])
        self.assertEqual(result[1].xyxy, [134, 1681, 177, 1855])
        self.assertIsNot(result[0].fontformat, result[1].fontformat)

    def test_missing_ambiguous_or_shared_bubble_keeps_source_block(self) -> None:
        for mode in ('missing', 'ambiguous', 'shared'):
            with self.subTest(mode=mode):
                source, layouts = self.make_case()
                if mode == 'missing':
                    layouts.pop()
                elif mode == 'shared':
                    layouts[1].bubble_xyxy = layouts[0].bubble_xyxy
                else:
                    extra = make_block([100, 1500, 300, 1900])
                    extra.bubble_xyxy = [90, 1490, 310, 1910]
                    layouts.append(extra)
                self.assertEqual(split_bubble_blocks([source], layouts, 1336, 2000), [source])

    def test_detect_preserves_complete_ctd_mask_and_option_disables_split(self) -> None:
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                source, layouts = self.make_case()
                mask = np.zeros((2000, 1336), np.uint8)
                mask[1543:1759, 187:266] = 255
                mask[1681:1855, 134:177] = 255
                detector = CTDCTBDTextDetector(**{
                    'split_bubble_blocks': enabled, 'mask dilate size': 0,
                })
                detector.ctd_model = lambda img: (None, mask.copy(), [source])
                with patch.object(RTDetrV2TextDetector, '_detect', return_value=(None, layouts)):
                    actual_mask, blocks = detector._detect(np.zeros((2000, 1336, 3), np.uint8))
                np.testing.assert_array_equal(actual_mask, mask)
                self.assertEqual(len(blocks), 2 if enabled else 1)
                if enabled:
                    self.assertTrue(all(b._bounding_rect is not None for b in blocks))


class TranslationRectangleTests(unittest.TestCase):
    def test_legacy_region_filter_cannot_discard_auxiliary_bubble_layout(self) -> None:
        for value in ('all', 'text_bubble', 'text_free', {'value': 'text_free'}):
            with self.subTest(value=value):
                source = make_block([40, 30, 70, 150], 28)
                original_lines = deepcopy(source.lines)
                detector = CTDCTBDTextDetector(text_region_filter=value)
                detector.model = object()
                detector.ctd_model = lambda img: (None, np.zeros(img.shape[:2], np.uint8), [source])
                detector.image_slicer = SimpleNamespace(process_slices_for_detection=lambda img, detect: (
                    np.array([[10, 10, 110, 190]]), np.array([[35, 25, 75, 155]]),
                ))
                # 부모의 실제 CTBD 블록 생성과 필터를 거쳐야 이 회귀를 잡는다.
                _, blocks = detector._detect(np.full((200, 120, 3), 255, np.uint8))
                self.assertEqual(blocks[0].bounding_rect(), [20, 28, 80, 144])
                self.assertEqual(blocks[0].lines, original_lines)
                self.assertEqual(blocks[0].xyxy, [40, 30, 70, 150])
                self.assertEqual(detector.text_region_filter, 'all')
                self.assertNotIn('text_region_filter', detector.params)

    def test_source_font_size_option_defaults_on_and_can_be_disabled(self):
        detector = CTDCTBDTextDetector()
        self.assertTrue(detector.get_param_value('preserve_source_font_size'))
        detector.updateParam('preserve_source_font_size', False)
        self.assertFalse(detector.get_param_value('preserve_source_font_size'))
        self.assertFalse(detector.all_model_loaded())

    def test_bubble_rectangle_preserves_ocr_lines_and_font_size(self):
        source = make_block([40, 30, 70, 150], 28)
        original_lines = deepcopy(source.lines)
        layout = make_block([35, 25, 75, 155])
        layout.bubble_xyxy = [10, 10, 110, 190]
        detector = CTDCTBDTextDetector()
        detector.ctd_model = lambda img: (None, np.zeros(img.shape[:2], np.uint8), [source])
        with patch.object(RTDetrV2TextDetector, '_detect', return_value=(None, [layout])):
            _, blocks = detector._detect(np.zeros((200, 120, 3), np.uint8))
        block = blocks[0]
        self.assertEqual(block.xyxy, [40, 30, 70, 150])
        self.assertEqual(block.lines, original_lines)
        self.assertEqual(block.bounding_rect(), [20, 28, 80, 144])
        self.assertEqual(block.font_size, 28)

    def test_unmatched_block_keeps_source_rectangle(self):
        source = make_block([40, 30, 70, 150], 28)
        detector = CTDCTBDTextDetector()
        detector.ctd_model = lambda img: (None, np.zeros(img.shape[:2], np.uint8), [source])
        with patch.object(RTDetrV2TextDetector, '_detect', return_value=(None, [])):
            _, blocks = detector._detect(np.zeros((200, 120, 3), np.uint8))
        self.assertEqual(blocks[0].bounding_rect(), [40, 30, 30, 120])


if __name__ == '__main__':
    unittest.main()
