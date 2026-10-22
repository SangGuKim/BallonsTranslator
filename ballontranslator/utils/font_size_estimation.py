"""Measure source lettering without coupling inference workers to Qt."""

from typing import List, Optional, Tuple
import unicodedata

import cv2
import numpy as np

from .textblock import TextBlock


def glyph_ink_areas(width: float, height: float) -> Tuple[float, float]:
    """Return bounding-box area and squared longest side for the same ink glyph.

    >>> glyph_ink_areas(16, 19)
    (304, 361)
    >>> glyph_ink_areas(20, 20)
    (400, 400)
    """
    return width * height, max(width, height) ** 2


def _separated_short_line_glyphs(
    labels: np.ndarray, stats: np.ndarray, transform: np.ndarray,
    vertical: bool, short: float,
) -> List[Tuple[float, float]]:
    """Recognize separated full-sized glyphs in a misleading square detector crop.

    >>> _separated_short_line_glyphs(np.zeros((2, 2), np.int32),
    ...     np.zeros((1, 5), np.int32), np.eye(3), True, 20)
    []
    """
    invertible, inverse = cv2.invert(transform)
    if not invertible:
        return []
    candidates = []
    ink_area = np.count_nonzero(labels)
    for label, (x, y, width, height, area) in enumerate(stats[1:], 1):
        if area < max(8, ink_area * 0.15):
            continue
        rows, columns = np.nonzero(labels[y:y + height, x:x + width] == label)
        if not len(rows):
            continue
        points = np.column_stack((columns + x, rows + y)).astype(np.float32)
        original = cv2.perspectiveTransform(points[None], inverse)[0]
        low, high = original.min(axis=0), original.max(axis=0)
        size = high - low + 1
        if min(size) < short * 0.3 or max(size) > min(size) * 1.8:
            continue
        candidates.append((low, high, size))
    if len(candidates) < 2:
        return []
    along, across = (1, 0) if vertical else (0, 1)
    candidates.sort(key=lambda candidate: candidate[0][along])
    for previous, current in zip(candidates, candidates[1:]):
        gap = current[0][along] - previous[1][along] - 1
        overlap = min(previous[1][across], current[1][across]) - max(
            previous[0][across], current[0][across],
        ) + 1
        # 단순한 떨어진 획이나 상하 부수를 여러 글자로 나누지 않는다.
        # 본문 크기의 성분이 진행 방향으로 충분히 떨어져 정렬돼야 한다.
        if (gap < min(previous[2][along], current[2][along]) * 0.25
                or overlap < min(previous[2][across], current[2][across]) * 0.5):
            return []
    return [(float(size[0]), float(size[1])) for _, _, size in candidates]


def estimate_source_ink_size(
    image: np.ndarray, block: TextBlock, character_extent: bool = False, *,
    area_metric: bool = False, square_metric: bool = False,
    measurement_rect: Optional[Tuple[float, float, float, float]] = None,
) -> Optional[float]:
    """Measure representative ink extent directly in original-image pixels.

    Measure line projections rather than connected components: separate
    strokes in one Japanese character must not be mistaken for small letters.
    Low contrast or unreliable crops retain the detector's existing estimate.
    Callers apply the user's multiplier separately; a block-wide nominal size
    must not rescale every line and propagate narrow-fragment errors.
    With character_extent, include representative glyph heights as well as
    widths; punctuation and unresolved runs do not provide height samples.
    area_metric takes the maximum per-glyph area without statistical trimming.
    Long-line area samples must be bounded inside the crop along the text flow;
    clipped letters, dash tails and border fragments cannot define glyph area
    or favor a closing operation that joins them to neighboring letters.
    Compute both bounding-box area and squared longest side; square_metric
    selects the latter. Return the square root to retain linear scaling.
    measurement_rect optionally restricts source pixels to a split block’s
    current page-space box (x, y, width, height), preserving line geometry.
    Short lines use the larger ink dimension only for near-square, sufficiently
    occupied shapes; thin strokes and dot chains cannot establish glyph size.

    >>> estimate_source_ink_size(np.full((20, 20, 3), 255, np.uint8), TextBlock()) is None
    True
    """
    character_extent = character_extent or area_metric
    source_text = block.get_text().strip()
    if source_text and not any(
        unicodedata.category(char)[0] in {'L', 'N'} and char not in 'ーｰ'
        for char in source_text
    ):
        return None
    # 분할된 블록만 사용자가 맞춘 박스 내부로 원본 픽셀을 제한한다.
    # 원문 사각형은 변형하지 않아 CTD의 기울기와 줄별 배율을 유지한다.
    origin = np.zeros(2, dtype=np.float32)
    coverage_source = None
    if measurement_rect is not None:
        rect = np.asarray(measurement_rect, dtype=np.float64)
        if rect.shape != (4,) or not np.isfinite(rect).all() or np.any(rect[2:] <= 0):
            return None
        left, top = np.maximum(0, np.floor(rect[:2])).astype(int)
        right, bottom = np.minimum(image.shape[1::-1], np.ceil(rect[:2] + rect[2:])).astype(int)
        if left >= right or top >= bottom:
            return None
        image = image[top:bottom, left:right]
        origin = np.asarray([left, top], dtype=np.float32)
        coverage_source = np.ones(image.shape[:2], dtype=np.uint8)
    estimates = []
    for line in block.lines:
        points = np.asarray(line, np.float32).reshape(4, 2)
        width = float((np.linalg.norm(points[1] - points[0]) + np.linalg.norm(points[2] - points[3])) / 2)
        height = float((np.linalg.norm(points[3] - points[0]) + np.linalg.norm(points[2] - points[1])) / 2)
        short, long = (width, height) if block.src_is_vertical else (height, width)
        short_line = long < short * 1.5
        if short < 4 or (short_line and not character_extent):
            continue
        w, h = max(2, round(width) + 1), max(2, round(height) + 1)
        target = np.asarray([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
        transform = cv2.getPerspectiveTransform(points - origin, target)
        coverage = None
        if coverage_source is not None:
            coverage = cv2.warpPerspective(
                coverage_source, transform, (w, h), flags=cv2.INTER_NEAREST,
                borderMode=cv2.BORDER_CONSTANT, borderValue=0,
            ).astype(bool)
            if not coverage.any():
                continue
        crop = cv2.warpPerspective(
            image, transform, (w, h), borderMode=cv2.BORDER_REPLICATE,
        )
        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
        samples = gray[coverage].reshape(-1, 1) if coverage is not None else gray
        if float(np.std(samples)) < 8:
            continue
        threshold, _ = cv2.threshold(samples, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        foreground = gray > threshold
        # 밀착된 한 글자는 절반 이상이 본문일 수 있다. 이때 극성은
        # 전체 면적 대신 crop 가장자리의 배경을 기준으로 정한다.
        background = (np.concatenate((foreground[0], foreground[-1],
                                     foreground[1:-1, 0], foreground[1:-1, -1]))
                      if short_line else foreground)
        if coverage is not None:
            if short_line:
                border_coverage = np.concatenate((coverage[0], coverage[-1],
                                                  coverage[1:-1, 0], coverage[1:-1, -1]))
                background = background[border_coverage]
            else:
                background = foreground[coverage]
            if not background.size:
                background = foreground[coverage]
        if np.mean(background) > 0.5:
            foreground = ~foreground
        if coverage is not None:
            foreground &= coverage
        if short_line:
            # 내부에 충분히 큰 본문이 있을 때만 작은 경계 조각을 버린다.
            # 내부 본문이 없거나 경계 획이 크면 잘린 글자일 수 있어 보존한다.
            _, labels, stats, _ = cv2.connectedComponentsWithStats(foreground.astype(np.uint8))
            # 보간 때문에 경계에서 한 픽셀 떨어진 테두리 조각도 포함한다.
            boundary = set(np.concatenate((labels[:2].ravel(), labels[-2:].ravel(),
                                           labels[:, :2].ravel(), labels[:, -2:].ravel()))) - {0}
            interior = [i for i in range(1, len(stats)) if i not in boundary
                        and min(stats[i, 2:4]) >= short * 0.35]
            if interior and boundary:
                main_area = max(stats[i, cv2.CC_STAT_AREA] for i in interior)
                edge_area = sum(stats[i, cv2.CC_STAT_AREA] for i in boundary)
                if main_area >= 4 * edge_area:
                    foreground[np.isin(labels, list(boundary))] = False
        fraction = (float(foreground.sum() / coverage.sum()) if coverage is not None
                    else float(np.mean(foreground)))
        if not 0.02 <= fraction <= (0.8 if short_line else 0.45):
            continue
        projection = foreground.sum(axis=0 if block.src_is_vertical else 1)
        active = np.flatnonzero(projection >= max(2, long * 0.02))
        if len(active) < 3:
            continue
        ink_size = float(active[-1] - active[0] + 1)
        if short_line:
            # 기울어진 정방형 검출 박스가 실제로는 세로/가로의 두 글자를
            # 담을 수 있다. 확실히 분리된 본문은 원본 축에서 각각 측정한다.
            labels[~foreground] = 0
            glyphs = _separated_short_line_glyphs(labels, stats, transform, block.src_is_vertical, short)
            if glyphs:
                for glyph_width, glyph_height in glyphs:
                    areas = glyph_ink_areas(glyph_width, glyph_height)
                    estimates.append(float(np.sqrt(areas[int(square_metric)])) if area_metric
                                     else max(glyph_width, glyph_height))
                continue
            # 짧은 대사는 줄의 종횡비가 아니라 실제 잉크 모양을 판단한다.
            # 한 글자의 떨어진 획은 합쳐서 보되, 가는 장음·점열은 제외한다.
            along_projection = foreground.sum(axis=1 if block.src_is_vertical else 0)
            along_active = np.flatnonzero(along_projection >= 2)
            if len(along_active) < 3:
                continue
            along_size = float(along_active[-1] - along_active[0] + 1)
            smaller, larger = min(ink_size, along_size), max(ink_size, along_size)
            density = np.count_nonzero(foreground) / (ink_size * along_size)
            if (larger > smaller * 1.5 or smaller < min(width, height) * 0.35
                    or density < 0.08):
                continue
            areas = glyph_ink_areas(ink_size, along_size)
            ink_size = float(np.sqrt(areas[int(square_metric)])) if area_metric else larger
        elif character_extent:
            # 짧게 떨어진 획을 먼저 이어서 「う」의 윗획 등을 별도 글자로
            # 세지 않는다. 점·장음은 글자 높이 표본에서 제외한다.
            along_projection = foreground.sum(axis=1 if block.src_is_vertical else 0)
            occupied = (along_projection >= 2).astype(np.uint8)
            gap = max(1, round(short * 0.1))
            closed = cv2.morphologyEx(
                occupied.reshape(1, -1), cv2.MORPH_CLOSE,
                np.ones((1, gap + 1), np.uint8),
            ).ravel()
            candidates = []
            for projection in (closed, occupied):
                edges = np.flatnonzero(np.diff(np.r_[0, projection, 0].astype(np.int8)))
                runs = edges[1::2] - edges[::2]
                valid_mask = (runs >= ink_size * 0.6) & (runs <= short * 1.4)
                if area_metric:
                    # 검출 경계까지 이어지는 표본은 잘린 글자·장음·테두리일
                    # 수 있다. 이런 표본으로 닫힘 연산의 분할을 선택하지 않는다.
                    valid_mask &= (edges[::2] > 0) & (edges[1::2] < len(projection))
                valid = runs[valid_mask]
                candidates.append((valid, runs, edges))
            # 닫힘 연산이 서로 다른 글자까지 붙였다면 원래 투영을 사용한다.
            glyph_spans, spans, edges = max(candidates, key=lambda candidate: len(candidate[0]))
            if area_metric:
                # 줄 전체 폭 대신 각 글자의 실제 폭을 사용한다. 느낌표의
                # 줄기처럼 높이만 정상인 가는 획은 면적 표본에서 제외한다.
                for start, end in zip(edges[::2], edges[1::2]):
                    if start == 0 or end == len(occupied):
                        continue
                    span = float(end - start)
                    if not ink_size * 0.6 <= span <= short * 1.4:
                        continue
                    glyph = foreground[start:end, :] if block.src_is_vertical else foreground[:, start:end]
                    across = np.flatnonzero(glyph.any(axis=0 if block.src_is_vertical else 1))
                    if len(across) < 3:
                        continue
                    cross = float(across[-1] - across[0] + 1)
                    if max(cross, span) > min(cross, span) * 1.8:
                        continue
                    areas = glyph_ink_areas(cross, span)
                    extent = float(np.sqrt(areas[int(square_metric)]))
                    if 0.35 <= extent / short <= 1.4:
                        estimates.append(extent)
                continue
            if len(glyph_spans) == 1:
                # 유효한 한 글자만 있어도 정방형에 가까우면 긴 변을 사용한다.
                span = float(glyph_spans[0])
                if max(ink_size, span) <= min(ink_size, span) * 1.5:
                    ink_size = max(ink_size, span)
            elif len(glyph_spans) >= 2:
                span = float(np.median(glyph_spans))
                ink_size = max(ink_size, span)
            elif len(spans) and np.max(spans) < ink_size * 0.4:
                # 행 전체가 납작한 획뿐이면 폭을 글자 크기로 간주하지 않는다.
                continue
        ratio = ink_size / short
        if 0.35 <= ratio <= (1.4 if character_extent else 1.05):
            estimates.append(ink_size)
    if not estimates:
        return None
    if area_metric:
        return max(estimates)
    values = np.asarray(estimates, dtype=np.float64)
    center = float(np.median(values))
    if len(values) >= 3:
        # 소표본에서 무작위 RANSAC을 돌리지 않는다. 점·장음의 형상 필터를
        # 통과한 표본도 중앙값과 MAD로 확인하며, MAD=0일 때도 작은 오차는 허용한다.
        deviations = np.abs(values - center)
        tolerance = max(2.0, center * 0.15, 3 * 1.4826 * float(np.median(deviations)))
        values = values[deviations <= tolerance]
    return float(np.median(values))
