"""Dump Qt font database information and custom font name records.

This diagnostic script keeps the main application untouched while using the
same Qt APIs that BallonsTranslator relies on for font listing and matching.

Example:
    >>> "name_id" in _name_id_label(1)
    False
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any


FONT_EXTS = {".ttf", ".otf", ".ttc", ".pfb"}
NAME_IDS = {
    1: "family",
    2: "subfamily",
    4: "full_name",
    6: "postscript_name",
    16: "typographic_family",
    17: "typographic_subfamily",
}
WINDOWS_LANGS = {
    0x0404: "zh-TW",
    0x0409: "en-US",
    0x0411: "ja-JP",
    0x0412: "ko-KR",
    0x0804: "zh-CN",
}
MAC_LANGS = {
    23: "ko-KR",
}
MAC_ENCODINGS = {
    3: ["x-mac-korean", "cp949", "euc_kr"],
}


def _name_id_label(name_id: int) -> str:
    return NAME_IDS.get(name_id, f"name_{name_id}")


def _decode_name(raw: bytes, platform_id: int, encoding_id: int) -> str:
    """Decode a TrueType/OpenType name table string.

    Example:
        >>> _decode_name(bytes.fromhex("b3 aa b4 ae"), 1, 3)
        '나눔'
    """
    encodings = []
    if platform_id in (0, 3):
        encodings.extend(["utf-16-be", "utf-8"])
    elif platform_id == 1:
        encodings.extend(MAC_ENCODINGS.get(encoding_id, []))
        encodings.extend(["mac_roman", "latin-1"])
    else:
        encodings.extend(["utf-8", "latin-1"])

    for encoding in encodings:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        text = text.replace("\x00", "").strip()
        if text:
            return text
    return raw.decode("latin-1", errors="replace").replace("\x00", "").strip()


def _language_label(platform_id: int, language_id: int) -> str:
    if platform_id == 1:
        return MAC_LANGS.get(language_id, f"0x{language_id:04x}")
    return WINDOWS_LANGS.get(language_id, f"0x{language_id:04x}")


def _read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def _read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">L", data, offset)[0]


def _sfnt_offsets(data: bytes) -> list[int]:
    if len(data) < 12:
        return []

    tag = data[:4]
    if tag == b"ttcf":
        if len(data) < 12:
            return []
        count = _read_u32(data, 8)
        offsets = []
        for index in range(count):
            pos = 12 + index * 4
            if pos + 4 <= len(data):
                offsets.append(_read_u32(data, pos))
        return offsets

    if tag in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        return [0]

    return []


def _table_offset(data: bytes, sfnt_offset: int, table_tag: bytes) -> tuple[int, int] | None:
    if sfnt_offset + 12 > len(data):
        return None
    num_tables = _read_u16(data, sfnt_offset + 4)
    table_dir = sfnt_offset + 12
    for index in range(num_tables):
        pos = table_dir + index * 16
        if pos + 16 > len(data):
            return None
        if data[pos : pos + 4] == table_tag:
            return _read_u32(data, pos + 8), _read_u32(data, pos + 12)
    return None


def parse_font_names(path: Path) -> list[dict[str, Any]]:
    data = path.read_bytes()
    fonts = []
    for face_index, sfnt_offset in enumerate(_sfnt_offsets(data)):
        table = _table_offset(data, sfnt_offset, b"name")
        if table is None:
            fonts.append({"face_index": face_index, "error": "name table not found", "names": []})
            continue

        name_offset, name_length = table
        if name_offset + min(name_length, 6) > len(data):
            fonts.append({"face_index": face_index, "error": "invalid name table", "names": []})
            continue

        count = _read_u16(data, name_offset + 2)
        string_offset = name_offset + _read_u16(data, name_offset + 4)
        names = []
        seen = set()
        for record_index in range(count):
            pos = name_offset + 6 + record_index * 12
            if pos + 12 > len(data):
                break
            platform_id = _read_u16(data, pos)
            encoding_id = _read_u16(data, pos + 2)
            language_id = _read_u16(data, pos + 4)
            name_id = _read_u16(data, pos + 6)
            length = _read_u16(data, pos + 8)
            offset = _read_u16(data, pos + 10)
            if name_id not in NAME_IDS:
                continue

            raw_start = string_offset + offset
            raw_end = raw_start + length
            if raw_end > len(data):
                continue
            value = _decode_name(data[raw_start:raw_end], platform_id, encoding_id)
            if not value:
                continue
            dedupe_key = (platform_id, encoding_id, language_id, name_id, value)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            names.append(
                {
                    "label": _name_id_label(name_id),
                    "name_id": name_id,
                    "value": value,
                    "platform_id": platform_id,
                    "encoding_id": encoding_id,
                    "language_id": language_id,
                    "language": _language_label(platform_id, language_id),
                }
            )

        fonts.append({"face_index": face_index, "names": names})
    return fonts


def summarize_name_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for record in records:
        label = record["label"]
        values = summary.setdefault(label, [])
        item = {
            "value": record["value"],
            "language": record["language"],
            "platform_id": record["platform_id"],
            "encoding_id": record["encoding_id"],
            "language_id": record["language_id"],
        }
        if item not in values:
            values.append(item)
    return summary


def iter_font_files(fonts_dir: Path) -> list[Path]:
    if not fonts_dir.exists():
        return []
    return sorted(path for path in fonts_dir.rglob("*") if path.suffix.lower() in FONT_EXTS)


def qt_family_info(qfont_db: Any, qfont_info_cls: Any, family: str) -> dict[str, Any]:
    styles = qfont_db.styles(family)
    style_entries = []
    for style in styles:
        qfont = qfont_db.font(family, style, 16)
        qfont_info = qfont_info_cls(qfont)
        style_entries.append(
            {
                "style": style,
                "weight": qfont_db.weight(family, style),
                "bold": qfont_db.bold(family, style),
                "italic": qfont_db.italic(family, style),
                "fixed_pitch": qfont_db.isFixedPitch(family, style),
                "scalable": qfont_db.isScalable(family, style),
                "smoothly_scalable": qfont_db.isSmoothlyScalable(family, style),
                "bitmap_scalable": qfont_db.isBitmapScalable(family, style),
                "qt_font_family": qfont.family(),
                "qt_font_style_name": qfont.styleName(),
                "matched_family": qfont_info.family(),
                "matched_style_name": qfont_info.styleName(),
                "matched_weight": qfont_info.weight(),
                "exact_match": qfont_info.exactMatch(),
            }
        )
    return {
        "family": family,
        "private": qfont_db.isPrivateFamily(family),
        "writing_systems": [int(getattr(ws, "value", ws)) for ws in qfont_db.writingSystems(family)],
        "styles": style_entries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump Qt and custom font metadata.")
    parser.add_argument("--qt-api", default="pyqt6", choices=["pyqt6", "pyside6", "pyqt5", "pyside2"])
    parser.add_argument("--fonts-dir", default="fonts", help="Directory containing application fonts.")
    parser.add_argument("--output", help="Write JSON output to this path instead of stdout.")
    parser.add_argument("--limit-system", type=int, default=0, help="Limit system family dump count; 0 means no limit.")
    parser.add_argument("--family-filter", help="Only include Qt families containing this case-insensitive text.")
    parser.add_argument("--no-system", action="store_true", help="Skip system font family details.")
    parser.add_argument("--no-custom", action="store_true", help="Skip loading and parsing custom fonts.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["QT_API"] = args.qt_api

    from qtpy import API, QT_VERSION
    from qtpy.QtGui import QFontDatabase, QFontInfo
    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    qfont_db = QFontDatabase

    system_families = sorted(qfont_db.families(), key=str.casefold)
    custom_fonts = []

    if not args.no_custom:
        for font_path in iter_font_files(Path(args.fonts_dir)):
            entry: dict[str, Any] = {"path": str(font_path), "qt_id": -1, "qt_families": [], "parsed_faces": []}
            try:
                entry["parsed_faces"] = parse_font_names(font_path)
            except Exception as exc:
                entry["parse_error"] = repr(exc)
            font_id = qfont_db.addApplicationFont(str(font_path))
            entry["qt_id"] = font_id
            if font_id >= 0:
                entry["qt_families"] = list(qfont_db.applicationFontFamilies(font_id))
            custom_fonts.append(entry)

    all_families = sorted(qfont_db.families(), key=str.casefold)
    custom_family_names = sorted(
        {family for item in custom_fonts for family in item.get("qt_families", [])},
        key=str.casefold,
    )
    custom_family_set = set(custom_family_names)
    system_family_set = set(system_families)

    def include_family(family: str) -> bool:
        return not args.family_filter or args.family_filter.casefold() in family.casefold()

    selected_system = [family for family in system_families if include_family(family)]
    if args.limit_system:
        selected_system = selected_system[: args.limit_system]

    selected_custom = [family for family in custom_family_names if include_family(family)]

    result = {
        "qt": {"api": API, "version": QT_VERSION},
        "counts": {
            "system_families_before_custom_load": len(system_families),
            "all_families_after_custom_load": len(all_families),
            "custom_font_files": len(custom_fonts),
            "custom_qt_families": len(custom_family_names),
            "custom_system_name_conflicts": len(custom_family_set & system_family_set),
        },
        "custom_system_name_conflicts": sorted(custom_family_set & system_family_set, key=str.casefold),
        "custom_fonts": [
            {
                **entry,
                "parsed_summary": [
                    {
                        "face_index": face.get("face_index"),
                        "error": face.get("error"),
                        "names": summarize_name_records(face.get("names", [])),
                    }
                    for face in entry.get("parsed_faces", [])
                ],
            }
            for entry in custom_fonts
        ],
        "qt_custom_families": [
            {**qt_family_info(qfont_db, QFontInfo, family), "source": "custom", "also_system": family in system_family_set}
            for family in selected_custom
        ],
        "qt_system_families": []
        if args.no_system
        else [
            {**qt_family_info(qfont_db, QFontInfo, family), "source": "system", "also_custom": family in custom_family_set}
            for family in selected_system
        ],
    }

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
