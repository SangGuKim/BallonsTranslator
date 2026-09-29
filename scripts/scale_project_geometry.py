from __future__ import annotations

import argparse
import copy
import json
import os
import os.path as osp
import re
import shutil
from datetime import datetime
from typing import Any, Iterable


FONT_SIZE_PT_PATTERN = re.compile(r"(font-size\s*:\s*)(-?\d+(?:\.\d+)?)(\s*pt)", re.IGNORECASE)


def parse_pair(value: str, name: str) -> tuple[float, float]:
    """Parse a comma-separated pair.

    >>> parse_pair("2,3.5", "scale")
    (2.0, 3.5)
    """
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"{name} must be formatted as X,Y.")
    try:
        x_value = float(parts[0])
        y_value = float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{name} must contain numbers.") from exc
    return x_value, y_value


def parse_offset(value: str) -> tuple[float, float]:
    """Parse an offset pair.

    >>> parse_offset("-12,24")
    (-12.0, 24.0)
    """
    return parse_pair(value, "offset")


def parse_scale_pair(value: str) -> tuple[float, float]:
    """Parse a scale pair.

    >>> parse_scale_pair("1.5,2")
    (1.5, 2.0)
    """
    x_scale, y_scale = parse_pair(value, "scale")
    if x_scale <= 0 or y_scale <= 0:
        raise argparse.ArgumentTypeError("scale values must be positive.")
    return x_scale, y_scale


def resolve_project_json(path: str) -> str:
    if osp.isfile(path):
        return path
    if not osp.isdir(path):
        raise FileNotFoundError(path)
    project_name = "imgtrans_" + osp.basename(osp.abspath(path)) + ".json"
    return osp.join(path, project_name)


def transform_point(point: Iterable[Any], sx: float, sy: float, dx: float, dy: float) -> list[int]:
    x_value, y_value = point
    return [int(round(float(x_value) * sx + dx)), int(round(float(y_value) * sy + dy))]


def transform_xyxy(value: Any, sx: float, sy: float, dx: float, dy: float) -> Any:
    if not isinstance(value, list) or len(value) != 4:
        return value
    x1, y1 = transform_point(value[:2], sx, sy, dx, dy)
    x2, y2 = transform_point(value[2:], sx, sy, dx, dy)
    return [x1, y1, x2, y2]


def transform_rect(value: Any, sx: float, sy: float, dx: float, dy: float) -> Any:
    if not isinstance(value, list) or len(value) != 4:
        return value
    x_value, y_value = transform_point(value[:2], sx, sy, dx, dy)
    width = int(round(float(value[2]) * sx))
    height = int(round(float(value[3]) * sy))
    return [x_value, y_value, width, height]


def transform_polygon_list(value: Any, sx: float, sy: float, dx: float, dy: float) -> Any:
    if not isinstance(value, list):
        return value
    transformed_lines = []
    for line in value:
        if not isinstance(line, list):
            transformed_lines.append(line)
            continue
        transformed_line = []
        for point in line:
            if isinstance(point, list) and len(point) >= 2:
                transformed_line.append(transform_point(point[:2], sx, sy, dx, dy))
            else:
                transformed_line.append(point)
        transformed_lines.append(transformed_line)
    return transformed_lines


def scale_number(value: Any, scale: float) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        scaled = float(value) * scale
        if isinstance(value, int):
            return int(round(scaled))
        return scaled
    return value


def format_scaled_float(value: float) -> str:
    """Format a scaled CSS number without noisy trailing zeroes.

    >>> format_scaled_float(24.0)
    '24'
    >>> format_scaled_float(12.34567)
    '12.3457'
    """
    return f"{value:.4f}".rstrip("0").rstrip(".")


def scale_rich_text_font_sizes(html: str, font_scale: float) -> str:
    """Scale Qt HTML font-size declarations stored in rich_text.

    >>> scale_rich_text_font_sizes("font-size:12pt;", 2)
    'font-size:24pt;'
    """
    def replace(match: re.Match[str]) -> str:
        point_size = float(match.group(2))
        if point_size <= 0:
            return match.group(0)
        scaled = format_scaled_float(point_size * font_scale)
        return match.group(1) + scaled + match.group(3)

    return FONT_SIZE_PT_PATTERN.sub(replace, html)


def is_positive_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value > 0


def transform_block(
    block: dict[str, Any],
    sx: float,
    sy: float,
    dx: float,
    dy: float,
    font_scale: float,
    scale_rich_text: bool,
) -> dict[str, Any]:
    updated = copy.deepcopy(block)
    updated["xyxy"] = transform_xyxy(updated.get("xyxy"), sx, sy, dx, dy)
    updated["lines"] = transform_polygon_list(updated.get("lines"), sx, sy, dx, dy)

    if updated.get("_bounding_rect") is not None:
        updated["_bounding_rect"] = transform_rect(updated.get("_bounding_rect"), sx, sy, dx, dy)

    if is_positive_number(updated.get("_detected_font_size")):
        updated["_detected_font_size"] = scale_number(updated["_detected_font_size"], font_scale)

    fontformat = updated.get("fontformat")
    if isinstance(fontformat, dict):
        fontformat["font_size"] = scale_number(fontformat.get("font_size"), font_scale)
        if fontformat.get("line_spacing_type") == 1:
            fontformat["line_spacing"] = scale_number(fontformat.get("line_spacing"), font_scale)

    if scale_rich_text and isinstance(updated.get("rich_text"), str):
        updated["rich_text"] = scale_rich_text_font_sizes(updated["rich_text"], font_scale)

    return updated


def transform_project(
    data: dict[str, Any],
    sx: float,
    sy: float,
    dx: float,
    dy: float,
    font_scale: float,
    scale_rich_text: bool = True,
) -> tuple[dict[str, Any], dict[str, int]]:
    updated = copy.deepcopy(data)
    stats = {"pages": 0, "blocks": 0}
    pages = updated.get("pages", {})
    if not isinstance(pages, dict):
        raise ValueError("Project JSON does not contain a valid pages object.")

    for page_name, block_list in pages.items():
        if not isinstance(block_list, list):
            continue
        stats["pages"] += 1
        stats["blocks"] += len(block_list)
        pages[page_name] = [
            transform_block(block, sx, sy, dx, dy, font_scale, scale_rich_text) if isinstance(block, dict) else block
            for block in block_list
        ]

    return updated, stats


def backup_path(json_path: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return json_path + f".{timestamp}.backup"


def write_project(json_path: str, data: dict[str, Any]) -> str:
    backup_target = backup_path(json_path)
    shutil.copy2(json_path, backup_target)
    tmp_path = json_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, json_path)
    return backup_target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scale BallonsTranslator project geometry with explicit scale and offset."
    )
    parser.add_argument("project", help="Project directory or project JSON path.")
    parser.add_argument("--scale", type=float, default=None, help="Uniform coordinate and font scale.")
    parser.add_argument("--scale-xy", type=parse_scale_pair, default=None, help="Coordinate scale as X,Y.")
    parser.add_argument("--offset", type=parse_offset, default=(0.0, 0.0), help="Coordinate offset as X,Y after scaling.")
    parser.add_argument("--font-scale", type=float, default=None, help="Font-related scalar. Required for non-uniform scale.")
    parser.add_argument("--no-rich-text", action="store_true", help="Do not scale font-size declarations inside rich_text HTML.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.scale is None and args.scale_xy is None:
        parser.error("one of --scale or --scale-xy is required.")
    if args.scale is not None and args.scale <= 0:
        parser.error("--scale must be positive.")
    if args.font_scale is not None and args.font_scale <= 0:
        parser.error("--font-scale must be positive.")

    if args.scale_xy is not None:
        sx, sy = args.scale_xy
    else:
        sx = sy = args.scale

    if args.font_scale is None:
        if sx != sy:
            parser.error("--font-scale is required when --scale-xy uses different X/Y values.")
        font_scale = sx
    else:
        font_scale = args.font_scale

    dx, dy = args.offset
    json_path = resolve_project_json(args.project)
    with open(json_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    updated, stats = transform_project(data, sx, sy, dx, dy, font_scale, scale_rich_text=not args.no_rich_text)

    print(f"project: {json_path}")
    print(f"pages: {stats['pages']}")
    print(f"blocks: {stats['blocks']}")
    print(f"scale: x={sx}, y={sy}, font={font_scale}")
    print(f"offset: x={dx}, y={dy}")
    print(f"rich_text_font_size: {'scaled' if not args.no_rich_text else 'unchanged'}")
    backup_target = write_project(json_path, updated)
    print(f"backup: {backup_target}")
    print("written: project JSON updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
