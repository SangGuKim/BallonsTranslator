from copy import deepcopy
from typing import Dict, List, Tuple

import cv2
import numpy as np

from ballontranslator.utils.proj_imgtrans import ProjImgTrans
from ballontranslator.utils.textblock import TextBlock, examine_textblk, sort_regions

from .base import DEVICE_SELECTOR, register_textdetectors
from .ctd import CTDModel
from .detector_ctbd import RTDetrV2TextDetector


CTD_ONNX_PATH = 'data/models/comictextdetector.pt.onnx'
CTD_TORCH_PATH = 'data/models/comictextdetector.pt'


def _box_match_score(source_box: List[int], layout_box: List[int]) -> Tuple[bool, float, float]:
    """Score whether a CTBD layout box belongs to a CTD text block.

    >>> _box_match_score([10, 10, 20, 20], [5, 5, 30, 30])
    (True, 1.0, 0.16)
    """

    sx1, sy1, sx2, sy2 = source_box
    lx1, ly1, lx2, ly2 = layout_box
    intersection = max(0, min(sx2, lx2) - max(sx1, lx1)) * max(
        0, min(sy2, ly2) - max(sy1, ly1)
    )
    source_area = max(1, (sx2 - sx1) * (sy2 - sy1))
    layout_area = max(1, (lx2 - lx1) * (ly2 - ly1))
    coverage = intersection / source_area
    union = source_area + layout_area - intersection
    iou = intersection / max(1, union)
    center_x = (sx1 + sx2) / 2
    center_y = (sy1 + sy2) / 2
    center_inside = lx1 <= center_x <= lx2 and ly1 <= center_y <= ly2
    return center_inside, coverage, iou


def match_layout_blocks(
    source_blocks: List[TextBlock],
    layout_blocks: List[TextBlock],
    minimum_coverage: float = 0.1,
) -> Dict[int, int]:
    """Return one-to-one CTD-to-CTBD matches ordered by geometric confidence.

    >>> src = [TextBlock(xyxy=[10, 10, 20, 20])]
    >>> layout = [TextBlock(xyxy=[5, 5, 30, 30])]
    >>> match_layout_blocks(src, layout)
    {0: 0}
    """

    candidates = []
    for source_index, source in enumerate(source_blocks):
        for layout_index, layout in enumerate(layout_blocks):
            center_inside, coverage, iou = _box_match_score(source.xyxy, layout.xyxy)
            if not center_inside and coverage < minimum_coverage:
                continue
            candidates.append(
                (
                    int(center_inside),
                    coverage,
                    iou,
                    source_index,
                    layout_index,
                )
            )

    matches = {}
    used_layout_indexes = set()
    for _, _, _, source_index, layout_index in sorted(candidates, reverse=True):
        if source_index in matches or layout_index in used_layout_indexes:
            continue
        matches[source_index] = layout_index
        used_layout_indexes.add(layout_index)
    return matches


def split_bubble_blocks(
    blocks: List[TextBlock], layouts: List[TextBlock], width: int, height: int,
) -> List[TextBlock]:
    """Separate source lines supported by distinct CTBD speech bubbles.

    Ambiguous or uncovered lines keep their original block. Never synthesize
    source lines from layout boxes or change the independently generated mask.

    >>> split_bubble_blocks([], [], 100, 100)
    []
    """
    result = []
    bubble_layouts = [layout for layout in layouts if getattr(layout, 'bubble_xyxy', None) is not None]
    for block in blocks:
        if len(block.lines) < 2:
            result.append(block)
            continue
        groups = {}
        for line in block.lines:
            points = np.asarray(line)
            line_box = [*points.min(axis=0), *points.max(axis=0)]
            owners = set()
            for layout in bubble_layouts:
                inside, coverage, _ = _box_match_score(line_box, layout.xyxy)
                if inside and coverage >= 0.8:
                    owners.add(tuple(layout.bubble_xyxy))
            if len(owners) != 1:
                break
            groups.setdefault(owners.pop(), []).append(line)
        else:
            if len(groups) > 1:
                for lines in groups.values():
                    part = deepcopy(block)
                    part.lines = deepcopy(lines)
                    part._bounding_rect = None
                    examine_textblk(part, width, height, sort=True)
                    part.adjust_bbox()
                    part._detected_font_size = part.font_size
                    result.append(part)
                continue
        result.append(block)
    return result


def _is_line_continuation(first: TextBlock, second: TextBlock) -> bool:
    """Recognize nearby pieces of one axis-aligned source line.

    >>> a = TextBlock(xyxy=[10, 10, 40, 70], lines=[[]], src_is_vertical=True)
    >>> b = TextBlock(xyxy=[12, 90, 38, 130], lines=[[]], src_is_vertical=True)
    >>> _is_line_continuation(a, b)
    True
    """
    if len(first.lines) != 1 or len(second.lines) != 1:
        return False
    if abs(first.angle) > 10 or abs(second.angle) > 10:
        return False
    cross, along = (0, 1) if first.src_is_vertical else (1, 0)
    a, b = first.xyxy, second.xyxy
    thicknesses = (a[cross + 2] - a[cross], b[cross + 2] - b[cross])
    if min(thicknesses) <= 0 or max(thicknesses) / min(thicknesses) > 1.5:
        return False
    overlap = min(a[cross + 2], b[cross + 2]) - max(a[cross], b[cross])
    gap = max(a[along], b[along]) - min(a[along + 2], b[along + 2])
    return overlap >= 0.7 * max(thicknesses) and 0 <= gap <= 1.5 * max(thicknesses)


def merge_layout_fragments(
    blocks: List[TextBlock], layouts: List[TextBlock], width: int, height: int,
) -> List[TextBlock]:
    """Join nested fragments or one-line continuations within one CTBD text box.

    >>> merge_layout_fragments([], [], 100, 100)
    []
    """
    owners = {}
    for index, block in enumerate(blocks):
        candidates = []
        for layout_index, layout in enumerate(layouts):
            inside, coverage, iou = _box_match_score(block.xyxy, layout.xyxy)
            if inside and coverage >= 0.9:
                candidates.append((coverage, iou, layout_index))
        if candidates:
            owners[index] = max(candidates)[2]

    removed = set()
    for index in sorted(owners, key=lambda i: len(blocks[i].lines), reverse=True):
        if index in removed:
            continue
        block = blocks[index]
        joined = False
        for other_index, owner in owners.items():
            if other_index == index or other_index in removed or owner != owners[index]:
                continue
            other = blocks[other_index]
            if block.src_is_vertical != other.src_is_vertical or abs(block.angle - other.angle) > 10:
                continue
            sizes = (block._detected_font_size, other._detected_font_size)
            if min(sizes) <= 0:
                continue
            _, coverage, _ = _box_match_score(other.xyxy, block.xyxy)
            nested = coverage >= 0.9 and max(sizes) / min(sizes) <= 1.25
            # 장음으로 끊긴 한 줄은 크기 추정도 달라진다. 같은 텍스트
            # 사각형 안의 정렬된 단일 줄에만 완화된 크기 조건을 적용한다.
            continuation = (
                max(sizes) / min(sizes) <= 1.5
                and _is_line_continuation(block, other)
            )
            if not nested and not continuation:
                continue
            block.lines.extend(line for line in other.lines if line not in block.lines)
            removed.add(other_index)
            joined = True
        if joined:
            # Rebuild line geometry, but keep the dominant source size rather
            # than allowing short fragments to change the font calibration.
            size = block._detected_font_size
            examine_textblk(block, width, height, sort=True)
            block.adjust_bbox()
            block.font_size = size
            block._detected_font_size = size
    return [block for index, block in enumerate(blocks) if index not in removed]



def recover_bubble_punctuation(
    image: np.ndarray, mask: np.ndarray, sources: List[TextBlock],
    layouts: List[TextBlock], matches: Dict[int, int],
) -> None:
    """Add aligned dots and thin strokes inside supported white bubble text.

    Work on the original pixels, before mask dilation. Components touching the
    crop edge and dark/background-heavy crops are deliberately left alone.

    >>> recover_bubble_punctuation(np.zeros((8, 8, 3), np.uint8),
    ...                            np.zeros((8, 8), np.uint8), [], [], {})
    """
    height, width = mask.shape[:2]
    for source_index, layout_index in matches.items():
        source, layout = sources[source_index], layouts[layout_index]
        if getattr(layout, 'bubble_xyxy', None) is None or abs(source.angle) > 15:
            continue
        x1, y1, x2, y2 = map(int, layout.xyxy)
        bx1, by1, bx2, by2 = map(int, layout.bubble_xyxy)
        x1, y1 = max(0, x1, bx1), max(0, y1, by1)
        x2, y2 = min(width, x2, bx2), min(height, y2, by2)
        if x2 <= x1 or y2 <= y1:
            continue
        crop = image[y1:y2, x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
        if np.median(gray) < 220:
            continue
        threshold, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        if threshold > 200 or np.count_nonzero(binary) > binary.size * 0.3:
            continue
        _, labels, stats, centers = cv2.connectedComponentsWithStats(binary)
        local_mask = mask[y1:y2, x1:x2]
        size = float(source._detected_font_size)
        if size < 4:
            continue
        cross, along = (0, 1) if source.src_is_vertical else (1, 0)
        origin = np.asarray([x1, y1])
        candidates = []
        for label, (x, y, w, h, area) in enumerate(stats[1:], 1):
            if area < 3 or x == 0 or y == 0 or x + w >= x2 - x1 or y + h >= y2 - y1:
                continue
            dot = max(w, h) <= size * 0.4
            stroke = min(w, h) <= size * 0.25 and max(w, h) >= min(w, h) * 2.5
            if not dot and not stroke:
                continue
            center = centers[label] + origin
            if not any(abs(center[cross] - np.asarray(line)[:, cross].mean()) <= size * 0.4
                       for line in source.lines):
                continue
            component = labels[y:y + h, x:x + w] == label
            seeded = np.count_nonzero(local_mask[y:y + h, x:x + w][component]) >= area * 0.1
            start = (y + y1) if source.src_is_vertical else (x + x1)
            length = h if source.src_is_vertical else w
            candidates.append((label, center[cross], start, start + length, dot, seeded))
        # 점열은 기존 마스크와 떨어져 있어도 세 점 이상 정렬되면 복원한다.
        # 긴 획은 기존 마스크와 연결된 묶음만 허용해 테두리 오인을 줄인다.
        pending = set(range(len(candidates)))
        accepted = []
        while pending:
            group = [pending.pop()]
            for current in group:
                _, cx, start, end, _, _ = candidates[current]
                neighbors = [i for i in pending
                             if abs(candidates[i][1] - cx) <= size * 0.3
                             and max(candidates[i][2], start) - min(candidates[i][3], end) <= size * 1.5]
                group.extend(neighbors)
                pending.difference_update(neighbors)
            if any(candidates[i][5] for i in group) or sum(candidates[i][4] for i in group) >= 3:
                accepted.extend(candidates[i][0] for i in group)
        if accepted:
            local_mask[np.isin(labels, accepted)] = 255


def inset_box(box: List[int], inset_ratio: float) -> List[int]:
    """Inset a layout box while preserving at least one pixel per dimension.

    >>> inset_box([0, 0, 100, 200], 0.1)
    [10, 20, 90, 180]
    """

    x1, y1, x2, y2 = box
    inset_x = int((x2 - x1) * inset_ratio)
    inset_y = int((y2 - y1) * inset_ratio)
    return [
        min(x1 + inset_x, x2 - 1),
        min(y1 + inset_y, y2 - 1),
        max(x2 - inset_x, x1 + 1),
        max(y2 - inset_y, y1 + 1),
    ]


@register_textdetectors('ctd_ctbd')
class CTDCTBDTextDetector(RTDetrV2TextDetector):
    """Use CTD metadata and masks with CTBD text layout rectangles.

    >>> detector = CTDCTBDTextDetector()
    >>> detector.name
    'ctd_ctbd'
    """

    dependencies = ['torch', 'torchvision', 'einops', 'onnxruntime']

    download_file_list = [
        {
            'url': 'https://huggingface.co/dreMaz/mit_models/resolve/main/comictextdetector.pt',
            'files': 'data/models/comictextdetector.pt',
            'sha256_pre_calculated': '1f90fa60aeeb1eb82e2ac1167a66bf139a8a61b8780acd351ead55268540cccb',
        },
        {
            'url': 'https://huggingface.co/dreMaz/mit_models/resolve/main/comictextdetector.pt.onnx',
            'files': 'data/models/comictextdetector.pt.onnx',
            'sha256_pre_calculated': '1a86ace74961413cbd650002e7bb4dcec4980ffa21b2f19b86933372071d718f',
        },
        {
            'url': 'https://huggingface.co/ogkalu/comic-text-and-bubble-detector/resolve/main/detector.onnx',
            'files': 'data/models/CTBD/detector.onnx',
            'sha256_pre_calculated': '065744e91c0594ad8663aa8b870ce3fb27222942eded5a3cc388ce23421bd195',
        },
    ]

    params = {
        'detect_size': {
            'type': 'selector',
            'options': [896, 1024, 1152, 1280],
            'value': 1280,
            'display_name': 'CTD Detect Size',
        },
        'det_rearrange_max_batches': {
            'type': 'selector',
            'options': [1, 2, 4, 6, 8, 12, 16, 24, 32],
            'value': 4,
            'display_name': 'CTD Max Split Batch Size',
        },
        'preserve_source_font_size': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'Preserve Source Font Size',
            'description': 'Keep the detected source font size during automatic layout and stroke adjustment. Disable to use the existing automatic size adjustment.',
        },
        'calibrate_source_font_size': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'Calibrate Source Font Size',
            'description': 'Match source ink size to the selected CJK font glyphs. Enable Preserve Source Font Size to prevent later layout shrinking.',
        },
        'font size multiplier': 1.0,
        'font size max': -1,
        'font size min': -1,
        'mask dilate size': 3,
        'calibrate_character_extent': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'Match Source Character Area',
            'description': 'Match representative character ink bounding-box areas during font calibration. Disable to use only the source line cross-section.',
        },
        'square_character_area': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'Source: Squared Longest Side',
            'description': 'Measure source glyphs using their maximum squared longest side. Disable to use maximum ink bounding-box area.',
        },
        'translation_square_character_area': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'Translation: Squared Longest Side',
            'description': 'Measure rendered translated glyphs using their maximum squared longest side. Disable to use maximum ink bounding-box area.',
        },
        'recover_bubble_punctuation': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'Recover Bubble Dots and Dashes',
            'description': 'Recover aligned ellipsis dots and connected thin strokes inside detected text on white speech bubbles. Keep the original CTD mask elsewhere.',
        },
        'split_bubble_blocks': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'Separate Speech Bubbles',
            'description': 'Separate CTD source lines when distinct CTBD speech bubbles support every line unambiguously. Keep the complete CTD inpaint mask.',
        },
        'minimum_layout_coverage': {
            'value': 0.1,
            'type': 'line_editor',
            'description': 'Minimum CTD area covered by a CTBD text box.',
            'display_name': 'Minimum Layout Coverage',
        },
        'bubble_layout_inset': {
            'value': 0.1,
            'type': 'line_editor',
            'description': 'Inset ratio applied to CTBD bubble layout boxes.',
            'display_name': 'Bubble Layout Inset',
        },
        'confidence_threshold': {
            'value': 0.3,
            'type': 'line_editor',
            'description': 'Minimum CTBD detection score (0.0-1.0).',
            'display_name': 'CTBD Confidence Threshold',
        },
        'device': DEVICE_SELECTOR(),
        'slice_threshold_ratio': {
            'value': 3.5,
            'type': 'line_editor',
            'display_name': 'CTBD Slice Threshold Ratio',
        },
        'slice_target_ratio': {
            'value': 3.0,
            'type': 'line_editor',
            'display_name': 'CTBD Slice Target Ratio',
        },
        'slice_overlap_ratio': {
            'value': 0.2,
            'type': 'line_editor',
            'display_name': 'CTBD Slice Overlap Ratio',
        },
        'slice_min_height_ratio': {
            'value': 0.7,
            'type': 'line_editor',
            'display_name': 'CTBD Slice Minimum Height Ratio',
        },
        'slice_merge_iou': {
            'value': 0.2,
            'type': 'line_editor',
            'display_name': 'CTBD Slice Merge IoU',
        },
        'slice_duplicate_iou': {
            'value': 0.5,
            'type': 'line_editor',
            'display_name': 'CTBD Slice Duplicate IoU',
        },
        'slice_merge_y_dist': {
            'value': 0.1,
            'type': 'line_editor',
            'display_name': 'CTBD Slice Merge Y Distance',
        },
        'slice_containment_thresh': {
            'value': 0.85,
            'type': 'line_editor',
            'display_name': 'CTBD Slice Containment Threshold',
        },
        'detect_bubbles': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'CTBD Detect Bubbles',
        },
        'detect_text': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'CTBD Detect Text',
        },
        'merge_duplicates': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'CTBD Merge Duplicates',
        },
        'merge_duplicates_iou': {
            'value': 0.7,
            'type': 'line_editor',
            'display_name': 'CTBD Merge Duplicates IoU',
        },
        'remove_contained_text': {
            'value': True,
            'type': 'checkbox',
            'display_name': 'CTBD Remove Contained Text',
        },
        'containment_threshold': {
            'value': 0.8,
            'type': 'line_editor',
            'display_name': 'CTBD Containment Threshold',
        },
        'inpaint_mask_dilate': {
            'value': 0,
            'type': 'line_editor',
            'display_name': 'Unused CTBD Mask Dilate',
        },
        'mask_unification_method': {
            'value': 'none',
            'type': 'selector',
            'options': ['none'],
            'display_name': 'Unused CTBD Mask Method',
        },
        'description': (
            'CTD glyph masks and source font sizes with CTBD translation rectangles. '
            'Source font size preservation can be enabled or disabled in the detector settings.'
        ),
    }

    _load_model_keys = {'model', 'image_slicer', 'ctd_model'}

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.ctd_model = None

    @property
    def detect_size(self) -> int:
        return int(self.get_param_value('detect_size'))

    @property
    def text_region_filter(self) -> str:
        # CTBD는 OCR 대상이 아니라 배치 근거를 제공한다. 부모의 원문 선택
        # 필터로 말풍선 후보를 버리면 CTD 원문만 남아 편집 폭이 되돌아간다.
        return 'all'

    def _load_model(self):
        super()._load_model()
        model_path = CTD_ONNX_PATH if self.device == 'cpu' else CTD_TORCH_PATH
        self.ctd_model = CTDModel(
            model_path,
            detect_size=self.detect_size,
            device=self.device,
            det_rearrange_max_batches=int(
                self.get_param_value('det_rearrange_max_batches')
            ),
        )

    def _detect(
        self,
        img: np.ndarray,
        proj: ProjImgTrans = None,
    ) -> Tuple[np.ndarray, List[TextBlock]]:
        _, ctd_mask, ctd_blocks = self.ctd_model(img)
        _, ctbd_blocks = super()._detect(img, proj)
        if self.get_param_value('split_bubble_blocks'):
            ctd_blocks = split_bubble_blocks(
                ctd_blocks, ctbd_blocks, img.shape[1], img.shape[0],
            )
        ctd_blocks = merge_layout_fragments(
            ctd_blocks, ctbd_blocks, img.shape[1], img.shape[0],
        )

        font_size_multiplier = float(self.get_param_value('font size multiplier'))
        font_size_max = float(self.get_param_value('font size max'))
        font_size_min = float(self.get_param_value('font size min'))
        for block in ctd_blocks:
            font_size = block._detected_font_size * font_size_multiplier
            if font_size_max > 0:
                font_size = min(font_size_max, font_size)
            if font_size_min > 0:
                font_size = max(font_size_min, font_size)
            font_size = int(round(font_size))
            block.font_size = font_size
            block._detected_font_size = font_size

        matches = match_layout_blocks(
            ctd_blocks,
            ctbd_blocks,
            minimum_coverage=float(
                self.get_param_value('minimum_layout_coverage')
            ),
        )
        bubble_layout_count = 0
        bubble_layout_inset = float(self.get_param_value('bubble_layout_inset'))
        bubble_layout_inset = min(max(bubble_layout_inset, 0.0), 0.49)
        for source_index, layout_index in matches.items():
            layout_block = ctbd_blocks[layout_index]
            bubble_box = getattr(layout_block, 'bubble_xyxy', None)
            if bubble_box is not None:
                layout_box = inset_box(
                    list(bubble_box),
                    bubble_layout_inset,
                )
                bubble_layout_count += 1
            else:
                layout_box = list(layout_block.xyxy)
            # Keep OCR crops and source-line geometry independent of the
            # translation rectangle consumed by TextBlkItem.initTextBlock().
            x1, y1, x2, y2 = layout_box
            ctd_blocks[source_index]._bounding_rect = [x1, y1, x2 - x1, y2 - y1]

        if self.get_param_value('recover_bubble_punctuation'):
            recover_bubble_punctuation(img, ctd_mask, ctd_blocks, ctbd_blocks, matches)

        mask_dilate_size = int(self.get_param_value('mask dilate size'))
        if mask_dilate_size > 0:
            element = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (2 * mask_dilate_size + 1, 2 * mask_dilate_size + 1),
                (mask_dilate_size, mask_dilate_size),
            )
            ctd_mask = cv2.dilate(ctd_mask, element)

        self.logger.info(
            f'Hybrid CTD/CTBD detector matched {len(matches)} of '
            f'{len(ctd_blocks)} CTD text blocks and used '
            f'{bubble_layout_count} bubble layout boxes.'
        )
        return ctd_mask, sort_regions(ctd_blocks)
