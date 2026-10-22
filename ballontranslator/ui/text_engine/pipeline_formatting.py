"""Final text-document formatting at page and project boundaries."""

import threading
from copy import copy, deepcopy
from pathlib import Path
from math import ceil, sqrt
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from qtpy import QT6
from qtpy.QtCore import QPointF, QThread, Signal
from qtpy.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)

from ballontranslator.utils.config import AutoTateChuYokoConfig, ModuleConfig
from ballontranslator.utils.fontformat import font_weight_to_qt, px2pt
from ballontranslator.utils.font_size_estimation import glyph_ink_areas
from ballontranslator.utils.message import create_error_dialog
from ballontranslator.utils.textblock import TextBlock
from ..misc import pixmap2ndarray
from .font_family import qfont_with_family
from .annotations import (
    apply_auto_text_combine_upright,
    apply_letter_spacing,
    apply_line_spacing,
    load_rich_text_html,
    to_rich_text_html,
)


def preserve_source_font_size(block: TextBlock, settings: ModuleConfig) -> bool:
    """Resolve supported detectors' font policy from saved or live settings.

    >>> preserve_source_font_size(TextBlock(det_model='ctd'), ModuleConfig())
    False
    >>> preserve_source_font_size(TextBlock(det_model='ctd_ctbd'), ModuleConfig())
    True
    """
    if block.det_model not in {'ctd', 'ysgyolo', 'ysg_ctd', 'ctd_ctbd'}:
        return False
    params = settings.textdetector_params.get(block.det_model) or {}
    value = params.get('preserve_source_font_size', block.det_model == 'ctd_ctbd')
    if isinstance(value, dict):
        value = value.get('value', True)
    return bool(value)


def _rendered_glyph_ink_sizes(
    font: QFont, characters: Sequence[str], *, square_metric: bool = False,
) -> List[float]:
    """Measure glyph bounding areas from raster alpha at the requested font size.

    Ignore alpha below half coverage, matching dark ink rather than faint
    antialiasing fringes. Each glyph is rendered separately to avoid joining
    neighboring glyphs; source punctuation is filtered by the source estimator.
    QImage rasterization is safe in the recalculation worker; no QPixmap is used.

    >>> _rendered_glyph_ink_sizes(QFont(), [])
    []
    """
    metrics = QFontMetricsF(font)
    sizes = []
    for char in characters:
        if not metrics.inFontUcs4(ord(char)):
            continue
        bounds = metrics.boundingRect(char).united(metrics.tightBoundingRect(char)).toAlignedRect()
        image = QImage(max(1, bounds.width() + 8), max(1, bounds.height() + 8),
                       QImage.Format.Format_RGBA8888)
        image.fill(0)
        # QFontMetrics and QPainter must use the same DPI even on scaled displays.
        dpi = round(metrics.fontDpi() / 0.0254)
        image.setDotsPerMeterX(dpi)
        image.setDotsPerMeterY(dpi)
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setFont(font)
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(QPointF(4 - bounds.left(), 4 - bounds.top()), char)
        finally:
            painter.end()
        pixels = pixmap2ndarray(image)
        rows, columns = np.nonzero(pixels[:, :, 3] >= 128)
        if len(rows):
            areas = glyph_ink_areas(float(columns.max() - columns.min() + 1),
                                    float(rows.max() - rows.min() + 1))
            sizes.append(sqrt(areas[int(square_metric)]))
    return sizes


def apply_source_font_size_calibration(
    block: TextBlock, settings: ModuleConfig, *, force: bool = False,
) -> bool:
    """Match detected source ink to representative translated CJK glyph ink.

    Derive every result from the detection baseline so repeating a pipeline
    formatting pass cannot compound the font-size correction. Authored rich
    text and non-CJK translations keep their explicit formatting.

    >>> apply_source_font_size_calibration(TextBlock(), ModuleConfig())
    False
    """
    if (not force and block.det_model not in {'ctd', 'ysgyolo', 'ysg_ctd', 'ctd_ctbd'}) or block.rich_text:
        return False
    params = settings.textdetector_params.get(block.det_model) or {}
    enabled = params.get('calibrate_source_font_size', block.det_model == 'ctd_ctbd')
    if isinstance(enabled, dict):
        enabled = enabled.get('value', False)
    # 원문의 저장된 측정 기준은 유지한다. 번역문은 별도 설정을 사용하되,
    # 설정이 없는 이전 프로젝트는 원문과 같은 기준을 적용한다.
    character_extent = block._source_font_size_uses_character_extent
    area_metric = block._source_font_size_uses_ink_area
    square_metric = params.get('translation_square_character_area',
                               block._source_font_size_uses_squared_area)
    if isinstance(square_metric, dict):
        square_metric = square_metric.get('value', block._source_font_size_uses_squared_area)
    square_metric = bool(square_metric)
    source_size = block._detected_font_size
    if (not force and not enabled) or source_size <= 0:
        return False
    characters = list(dict.fromkeys(
        char for char in block.translation
        if '\uac00' <= char <= '\ud7a3' or '\u4e00' <= char <= '\u9fff'
        or '\u3041' <= char <= '\u30fa'
    ))[:32]
    if not characters:
        return False
    font = qfont_with_family(QFont(), block.fontformat.font_family)
    font.setPointSizeF(px2pt(100))
    font.setWeight(QFont.Weight(font_weight_to_qt(block.fontformat.font_weight, qt6=QT6)))
    font.setItalic(block.fontformat.italic)
    if area_metric:
        sizes = _rendered_glyph_ink_sizes(font, characters, square_metric=square_metric)
        if not sizes:
            return False
        ink_size = max(sizes)
        if not 35 <= ink_size <= 130:
            return False
        size = ceil(source_size * 100 / ink_size)
        # 정수 출력 크기에서 다시 실측한다. 작은 글자의 힌팅은 선형이
        # 아니므로 큰 probe의 비율만으로 종료하지 않는다.
        for _ in range(3):
            font.setPointSizeF(px2pt(size))
            actual_sizes = _rendered_glyph_ink_sizes(font, characters, square_metric=square_metric)
            if not actual_sizes:
                return False
            actual = max(actual_sizes)
            if actual >= source_size:
                break
            size = max(size + 1, ceil(size * source_size / actual))
    else:
        metrics = QFontMetricsF(font)
        sizes = []
        for char in characters:
            if not metrics.inFontUcs4(ord(char)):
                continue
            bounds = metrics.tightBoundingRect(char)
            size = (max(bounds.width(), bounds.height()) if character_extent
                    else bounds.width() if block.src_is_vertical else bounds.height())
            if size > 0:
                sizes.append(size)
        if not sizes:
            return False
        ink_size = median(sizes)
        if not 35 <= ink_size <= 130:
            return False
        size = source_size * 100 / ink_size
        # Refine at the actual output size: small-font hinting is not perfectly
        # proportional to the large probe used for the initial estimate.
        font.setPointSizeF(px2pt(size))
        metrics = QFontMetricsF(font)
        actual_sizes = []
        for char in characters:
            if not metrics.inFontUcs4(ord(char)):
                continue
            bounds = metrics.tightBoundingRect(char)
            actual = (max(bounds.width(), bounds.height()) if character_extent
                      else bounds.width() if block.src_is_vertical else bounds.height())
            if actual > 0:
                actual_sizes.append(actual)
        if actual_sizes:
            size *= source_size / median(actual_sizes)
    # 최종 표시 크기만 올림한다. 명시적인 최대 크기는 그 뒤에 적용해
    # 소수점 제한값도 넘지 않으며, 반복 실행은 항상 원문 baseline에서 시작한다.
    size = ceil(size)
    for key, clamp in (('font size min', max), ('font size max', min)):
        limit = params.get(key, -1)
        if isinstance(limit, dict):
            limit = limit.get('value', -1)
        if float(limit) > 0:
            size = clamp(size, float(limit))
    block.font_size = size
    return True


def _load_text_block_document(block: TextBlock) -> QTextDocument:
    """Build a formatting document without constructing a scene item."""
    document = QTextDocument()
    font_format = block.fontformat
    font = qfont_with_family(
        document.defaultFont(),
        font_format.font_family,
    )
    font.setPointSizeF(font_format.size_pt)
    font.setWeight(QFont.Weight(font_weight_to_qt(
        font_format.font_weight,
        qt6=QT6,
    )))
    font.setItalic(font_format.italic)
    font.setUnderline(font_format.underline)
    document.setDefaultFont(font)

    if block.rich_text:
        load_rich_text_html(
            document,
            block.rich_text,
            letter_spacing_fallback=font_format.letter_spacing,
            vertical=font_format.vertical,
        )
        return document

    document.setPlainText(block.translation)
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    char_format = QTextCharFormat()
    char_format.setFont(font)
    char_format.setForeground(QColor(*font_format.foreground_color()))
    cursor.mergeCharFormat(char_format)
    cursor.mergeBlockCharFormat(char_format)
    apply_letter_spacing(
        cursor,
        font_format.letter_spacing,
        vertical=font_format.vertical,
    )
    apply_line_spacing(
        cursor,
        font_format.line_spacing,
        font_format.line_spacing_type,
    )
    return document


def apply_auto_tate_chu_yoko(
    blocks: Sequence[TextBlock],
    settings: AutoTateChuYokoConfig,
) -> int:
    """Replace automatic Tate-chu-yoko on finalized text blocks.

    Horizontal blocks have existing Tate-chu-yoko removed but receive no new
    runs. Return the number of blocks whose persisted rich text changed.

    >>> settings = AutoTateChuYokoConfig(enabled=True, max_length=2)
    >>> block = TextBlock(translation='12')
    >>> block.vertical = True
    >>> apply_auto_tate_chu_yoko([block], settings)
    1
    """
    if not settings.enabled:
        return 0
    allowed_characters = settings.allowed_characters()
    no_characters: frozenset[str] = frozenset()
    changed = 0
    for block in blocks:
        if not block.rich_text and not block.translation:
            continue
        if (
            not block.rich_text
            and (
                not block.vertical
                or not allowed_characters
                or not any(
                    character in allowed_characters
                    for character in block.translation
                )
            )
        ):
            continue
        document = _load_text_block_document(block)
        block_allowed_characters = (
            allowed_characters if block.vertical else no_characters
        )
        if not apply_auto_text_combine_upright(
            document,
            block_allowed_characters,
            settings.max_length,
        ):
            continue
        block.rich_text = to_rich_text_html(
            document,
            line_spacing_fallback=block.fontformat.line_spacing,
            line_spacing_type_fallback=block.fontformat.line_spacing_type,
        )
        changed += 1
    return changed


class AutoTateChuYokoThread(QThread):
    """Apply automatic Tate-chu-yoko to project documents off the UI thread.

    >>> issubclass(AutoTateChuYokoThread, QThread)
    True
    """

    progress_changed = Signal(int, str)
    processing_finished = Signal(int, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pages: List[Tuple[str, List[TextBlock]]] = []
        self._settings = AutoTateChuYokoConfig()
        self._stop_event = threading.Event()

    def start_processing(
        self,
        pages: Dict[str, List[TextBlock]],
        settings: AutoTateChuYokoConfig,
    ) -> bool:
        if self.isRunning():
            return False
        self._pages = list(pages.items())
        self._settings = settings.copy()
        self._stop_event.clear()
        self.start()
        return True

    def request_stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        changed_blocks: List[TextBlock] = []
        error: Optional[Exception] = None
        try:
            total_pages = len(self._pages)
            for page_index, (page_name, blocks) in enumerate(
                self._pages,
                start=1,
            ):
                for block in blocks:
                    if self._stop_event.is_set():
                        break
                    if apply_auto_tate_chu_yoko(
                        (block,),
                        self._settings,
                    ):
                        changed_blocks.append(block)
                if self._stop_event.is_set():
                    break
                self.progress_changed.emit(
                    round(page_index / total_pages * 100),
                    page_name,
                )
        except Exception as exception:
            error = exception

        self.processing_finished.emit(
            len(changed_blocks),
            tuple(changed_blocks),
        )
        if error is not None:
            create_error_dialog(
                error,
                self.tr('Failed to apply automatic Tate-chu-yoko.'),
                'AutoTateChuYokoApplyFailed',
            )


def _font_size_snapshot(block: TextBlock) -> TextBlock:
    # 원문·효과 마스크 배열은 읽지도 수정하지 않는다. 크기 계산에 필요한
    # 서식과 좌표만 복사해 큰 프로젝트의 이미지 배열 복제를 피한다.
    snapshot = copy(block)
    snapshot.fontformat = deepcopy(block.fontformat)
    snapshot.lines = deepcopy(block.lines)
    snapshot.xyxy = list(block.xyxy)
    snapshot._bounding_rect = list(block._bounding_rect) if block._bounding_rect is not None else None
    return snapshot


def _has_local_rich_text_formatting(block: TextBlock) -> bool:
    """Protect differing character formats while allowing uniform whole-text style.

    >>> _has_local_rich_text_formatting(TextBlock())
    False
    """
    if not block.rich_text:
        return False
    document = _load_text_block_document(block)
    # HTML의 태그 배치는 비교하지 않는다. 같은 서식의 여러 span은
    # 전체 서식과 같지만, 실제 구간별 서식이나 텍스트 차이는 보존한다.
    if document.toPlainText() != block.translation:
        return True
    reference = None
    paragraph = document.begin()
    while paragraph.isValid():
        fragments = paragraph.begin()
        while not fragments.atEnd():
            fragment = fragments.fragment()
            if fragment.isValid() and fragment.length():
                current = fragment.charFormat()
                if reference is None:
                    reference = current
                elif current != reference:
                    return True
            fragments += 1
        paragraph = paragraph.next()
    return False


def recalculate_existing_font_size(
    image: np.ndarray, block: TextBlock, settings: ModuleConfig, *,
    restrict_to_box: bool = False,
) -> Optional[TextBlock]:
    """Rebase size on original scan geometry using the block's current font.

    Return a staged copy; retain source text, translation and layout geometry.
    Local rich-text formatting, active effects and transforms retain authored
    sizing. Uniform rich text is cleared only after successful measurement.

    >>> recalculate_existing_font_size(None, TextBlock(), ModuleConfig()) is None
    True
    """
    from ballontranslator.utils.font_size_estimation import estimate_source_ink_size

    # 효과·변형은 사용자가 이미 맞춘 시각적 크기를 보존한다.
    if (not block.fontformat.text_effects.is_neutral()
            or not block.fontformat.text_transform.is_neutral()
            or _has_local_rich_text_formatting(block)):
        return None
    if image is None or not block.det_model or not block.lines or not block.translation.strip():
        return None
    work = copy(block)
    lines = np.asarray(work.lines, dtype=np.float32)
    if lines.ndim != 3 or lines.shape[1:] != (4, 2) or not np.isfinite(lines).all():
        return None
    if work.src_is_vertical is None:
        work.src_is_vertical = bool(
            np.linalg.norm(lines[:, 3] - lines[:, 0], axis=1).sum()
            > np.linalg.norm(lines[:, 1] - lines[:, 0], axis=1).sum()
        )
    # 이전 폰트 크기나 줄 폭 평균을 재사용하지 않고 원문 잉크를 바로 측정한다.
    params = settings.textdetector_params.get(block.det_model) or {}
    extent = params.get('calibrate_character_extent', True)
    if isinstance(extent, dict):
        extent = extent.get('value', True)
    square = params.get('square_character_area', True)
    if isinstance(square, dict):
        square = square.get('value', True)
    measured = estimate_source_ink_size(
        image, work, character_extent=bool(extent), area_metric=bool(extent),
        square_metric=bool(square),
        measurement_rect=tuple(block.bounding_rect()) if restrict_to_box else None,
    )
    if measured is None:
        return None
    multiplier = params.get('font size multiplier', 1.0)
    if isinstance(multiplier, dict):
        multiplier = multiplier.get('value', 1.0)
    multiplier = float(multiplier)
    if not np.isfinite(multiplier) or multiplier <= 0:
        raise ValueError('Font size multiplier must be positive and finite')
    result = _font_size_snapshot(block)
    result._detected_font_size = measured * multiplier
    result._source_font_size_uses_character_extent = bool(extent)
    result._source_font_size_uses_ink_area = bool(extent)
    result._source_font_size_uses_squared_area = bool(extent and square)
    result.rich_text = ''
    if not apply_source_font_size_calibration(result, settings, force=True):
        return None
    return result


def _shared_source_line_indices(blocks: Sequence[TextBlock]) -> set[int]:
    """Find split/copy siblings retaining the same detector line geometry.

    >>> _shared_source_line_indices([TextBlock(), TextBlock()])
    set()
    """
    owners: Dict[tuple, int] = {}
    shared: set[int] = set()
    for index, block in enumerate(blocks):
        try:
            lines = np.asarray(block.lines, dtype=np.float64)
        except (TypeError, ValueError):
            continue
        if lines.ndim != 3 or lines.shape[1:] != (4, 2) or not np.isfinite(lines).all():
            continue
        for line in lines:
            key = tuple(map(tuple, line))
            previous = owners.setdefault(key, index)
            if previous != index:
                shared.update((previous, index))
    return shared


class FontSizeRecalculationThread(QThread):
    """Measure a selected page snapshot without modifying the live project.

    >>> issubclass(FontSizeRecalculationThread, QThread)
    True
    """

    progress_changed = Signal(int, str)
    processing_finished = Signal(object, int, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pages: List[Tuple[str, List[Tuple[TextBlock, TextBlock]]]] = []
        self._directory = ''
        self._settings = ModuleConfig()
        self._stop_event = threading.Event()

    def start_processing(
        self, directory: str, pages: Dict[str, List[TextBlock]], settings: ModuleConfig,
    ) -> bool:
        if self.isRunning():
            return False
        self._directory = directory
        self._pages = [(name, [(block, _font_size_snapshot(block)) for block in blocks])
                       for name, blocks in pages.items()]
        self._settings = deepcopy(settings)
        self._stop_event.clear()
        self.start()
        return True

    def request_stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        from ballontranslator.utils.io_utils import imread
        from ballontranslator.utils.logger import logger

        changes = []
        skipped = 0
        failures = set()
        try:
            for index, (name, blocks) in enumerate(self._pages, 1):
                if self._stop_event.is_set():
                    break
                try:
                    image = imread(str(Path(self._directory) / name))
                    if image is None:
                        raise OSError('Cannot read original image')
                except Exception as error:
                    logger.warning('Font size recalculation failed for %s: %s', name, error)
                    failures.add(name)
                    skipped += len(blocks)
                    continue
                # 같은 원문 줄을 공유하는 분할 박스만 편집 영역을 신뢰한다.
                # 일반 박스는 번역 배치 위치와 무관하게 기존 CTD 영역을 쓴다.
                shared = _shared_source_line_indices([snapshot for _, snapshot in blocks])
                for block_index, (original, snapshot) in enumerate(blocks):
                    if self._stop_event.is_set():
                        break
                    try:
                        result = recalculate_existing_font_size(
                            image, snapshot, self._settings,
                            restrict_to_box=block_index in shared,
                        )
                        if result is None:
                            skipped += 1
                        else:
                            changes.append((original, result))
                    except Exception as error:
                        skipped += 1
                        failures.add(name)
                        logger.warning('Font size recalculation failed for %s: %s', name, error)
                self.progress_changed.emit(round(index / len(self._pages) * 100), name)
        finally:
            self._pages.clear()
            self.processing_finished.emit(tuple(changes), skipped, tuple(sorted(failures)))
