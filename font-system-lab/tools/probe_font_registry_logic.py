"""Probe the proposed BallonsTranslator font registry policy.

The output is intentionally compact: it shows the picker entries that would be
created by the proposed policy, plus warnings for names that need review.

Example:
    >>> choose_localized([{"language": "en-US", "value": "A"}], "ko-KR")
    'A'
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
from typing import Any

from dump_font_info import iter_font_files, parse_font_names


WEIGHT_BY_STYLE = {
    "thin": 100,
    "extralight": 200,
    "extra light": 200,
    "ultralight": 200,
    "ultra light": 200,
    "light": 300,
    "regular": 400,
    "normal": 400,
    "book": 400,
    "medium": 500,
    "extrabold": 800,
    "extra bold": 800,
    "ultrabold": 800,
    "ultra bold": 800,
    "demibold": 600,
    "demi bold": 600,
    "semibold": 600,
    "semi bold": 600,
    "bold": 700,
    "black": 900,
    "heavy": 900,
}
EXACT_WEIGHT_BY_STYLE = {
    "b": 700,
    "l": 300,
    "m": 500,
}
WINDOWS_LEGACY_RASTER_FAMILIES = {
    "Fixedsys",
    "MS Sans Serif",
    "MS Serif",
    "Small Fonts",
    "System",
    "Terminal",
}


def json_groups(raw: Any, section: str) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and section in raw:
        return raw.get(section, [])
    return raw.get("groups", raw if isinstance(raw, list) else [])


def load_system_alias_table(path: str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = json_groups(raw, "system_aliases")
    table = {}
    for group in groups:
        canonical = group["canonical"]
        aliases = [canonical, *group.get("aliases", [])]
        normalized_group = {
            "canonical": canonical,
            "display": group.get("display", canonical),
            "aliases": aliases,
            "note": group.get("note", ""),
        }
        for alias in aliases:
            table[normalize_key(alias)] = normalized_group
    return table


def load_custom_group_table(path: str | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    groups = json_groups(raw, "custom_groups")
    table = {}
    for group in groups:
        canonical = group["canonical"]
        display = group.get("display", canonical)
        members = group.get("members", [])
        normalized_group = {
            "canonical": canonical,
            "display": display,
            "members": members,
            "note": group.get("note", ""),
        }
        for member in members:
            member_names = [member["canonical"], *member.get("aliases", [])]
            for name in member_names:
                table[normalize_key(name)] = {**normalized_group, "member": member}
    return table


@dataclass
class FaceCandidate:
    file: str
    face_index: int
    canonical_family: str
    display_family: str
    style_name: str
    display_face: str
    weight: int | None
    qt_families: list[str]
    english_family: str | None = None
    localized_family: str | None = None
    postscript_name: str | None = None
    warnings: list[str] = field(default_factory=list)


def normalize_key(value: str) -> str:
    return " ".join(value.casefold().split())


def simplify_style(value: str | None) -> str:
    if not value:
        return "Regular"
    return value.strip() or "Regular"


def records_by_label(face: dict[str, Any], label: str) -> list[dict[str, Any]]:
    return [record for record in face.get("names", []) if record.get("label") == label]


def choose_english(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        if record.get("language") == "en-US" and record.get("value"):
            return record["value"]
    for record in records:
        value = record.get("value")
        if value and value.isascii():
            return value
    return None


def choose_localized(records: list[dict[str, Any]], locale: str) -> str | None:
    for record in records:
        if record.get("language") == locale and record.get("value"):
            return record["value"]
    language_prefix = locale.split("-", 1)[0]
    for record in records:
        language = str(record.get("language", ""))
        if language.startswith(language_prefix) and record.get("value"):
            return record["value"]
    return choose_english(records) or (records[0]["value"] if records else None)


def choose_first(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        if record.get("value"):
            return record["value"]
    return None


def infer_weight(style: str, qt_weights: list[int]) -> int | None:
    normalized_style = normalize_key(style)
    if normalized_style in EXACT_WEIGHT_BY_STYLE:
        return EXACT_WEIGHT_BY_STYLE[normalized_style]
    if normalized_style in WEIGHT_BY_STYLE:
        return WEIGHT_BY_STYLE[normalized_style]

    if qt_weights:
        matching_weights = []
    else:
        matching_weights = []

    key = normalized_style
    for token, weight in WEIGHT_BY_STYLE.items():
        if token in key:
            return weight
    if matching_weights:
        return sorted(matching_weights, key=lambda value: (abs(value - 400), value))[0]
    if qt_weights:
        return sorted(qt_weights, key=lambda value: (abs(value - 400), value))[0]
    return None


def qt_family_weights(qfont_db: Any, family: str) -> list[int]:
    weights = []
    for style in qfont_db.styles(family):
        try:
            weights.append(int(qfont_db.weight(family, style)))
        except Exception:
            continue
    return sorted(set(weights))


def build_face_candidate(
    font_path: Path,
    parsed_face: dict[str, Any],
    qt_families: list[str],
    qfont_db: Any,
    locale: str,
) -> FaceCandidate | None:
    if parsed_face.get("error"):
        return FaceCandidate(
            file=str(font_path),
            face_index=int(parsed_face.get("face_index", 0)),
            canonical_family=font_path.stem,
            display_family=font_path.stem,
            style_name="Regular",
            display_face=font_path.stem,
            weight=None,
            qt_families=qt_families,
            warnings=[f"parse_error: {parsed_face['error']}"],
        )

    typo_family = records_by_label(parsed_face, "typographic_family")
    family = records_by_label(parsed_face, "family")
    typo_subfamily = records_by_label(parsed_face, "typographic_subfamily")
    subfamily = records_by_label(parsed_face, "subfamily")
    full_name = records_by_label(parsed_face, "full_name")
    postscript_name = records_by_label(parsed_face, "postscript_name")

    canonical_family = choose_english(typo_family) or choose_english(family) or choose_first(typo_family) or choose_first(family)
    if not canonical_family:
        return None

    localized_family = choose_localized(typo_family, locale) or choose_localized(family, locale)
    english_family = choose_english(typo_family) or choose_english(family)
    style_name = simplify_style(choose_english(typo_subfamily) or choose_english(subfamily) or choose_first(typo_subfamily) or choose_first(subfamily))
    display_face = choose_localized(full_name, locale) or f"{localized_family or canonical_family} {style_name}".strip()
    weights = []
    for family_name in qt_families:
        weights.extend(qt_family_weights(qfont_db, family_name))

    warnings = []
    if not english_family:
        warnings.append("no_english_family")
    if localized_family and english_family and normalize_key(localized_family) != normalize_key(english_family):
        warnings.append("localized_display_differs")
    if qt_families and all(normalize_key(canonical_family) != normalize_key(qt_family) for qt_family in qt_families):
        warnings.append("qt_family_differs_from_canonical")
    if not qt_families:
        warnings.append("qt_load_failed_or_no_family")

    return FaceCandidate(
        file=str(font_path),
        face_index=int(parsed_face.get("face_index", 0)),
        canonical_family=canonical_family,
        display_family=localized_family or canonical_family,
        style_name=style_name,
        display_face=display_face,
        weight=infer_weight(style_name, weights),
        qt_families=qt_families,
        english_family=english_family,
        localized_family=localized_family,
        postscript_name=choose_english(postscript_name) or choose_first(postscript_name),
        warnings=warnings,
    )


def collect_custom_faces(fonts_dir: Path, qfont_db: Any, locale: str) -> list[FaceCandidate]:
    faces = []
    for font_path in iter_font_files(fonts_dir):
        font_id = qfont_db.addApplicationFont(str(font_path))
        qt_families = list(qfont_db.applicationFontFamilies(font_id)) if font_id >= 0 else []
        try:
            parsed_faces = parse_font_names(font_path)
        except Exception as exc:
            parsed_faces = [{"face_index": 0, "error": repr(exc), "names": []}]
        for parsed_face in parsed_faces:
            candidate = build_face_candidate(font_path, parsed_face, qt_families, qfont_db, locale)
            if candidate is not None:
                faces.append(candidate)
    return faces


def system_family_details(qfont_db: Any, family: str, custom_keys: set[str]) -> dict[str, Any]:
    styles = sorted(qfont_db.styles(family), key=str.casefold)
    weights = sorted({int(qfont_db.weight(family, style)) for style in styles})
    scalable = any(qfont_db.isScalable(family, style) for style in styles) if styles else qfont_db.isScalable(family)
    smoothly_scalable = any(qfont_db.isSmoothlyScalable(family, style) for style in styles) if styles else qfont_db.isSmoothlyScalable(family)
    fixed_pitch = any(qfont_db.isFixedPitch(family, style) for style in styles) if styles else qfont_db.isFixedPitch(family)
    warnings = []
    if normalize_key(family) in custom_keys:
        warnings.append("overridden_by_custom")
    if family in WINDOWS_LEGACY_RASTER_FAMILIES:
        warnings.append("windows_legacy_raster_candidate")
    if not scalable:
        warnings.append("not_scalable")

    return {
        "display": family,
        "canonical": family,
        "aliases": [],
        "merged_from": [family],
        "styles": styles,
        "weights": weights,
        "private": qfont_db.isPrivateFamily(family),
        "fixed_pitch": fixed_pitch,
        "scalable": scalable,
        "smoothly_scalable": smoothly_scalable,
        "warnings": warnings,
    }


def merge_system_alias_entries(entries: list[dict[str, Any]], alias_table: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not alias_table:
        return entries

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    passthrough = []
    for entry in entries:
        alias_group = alias_table.get(normalize_key(entry["canonical"]))
        if alias_group is None:
            passthrough.append(entry)
        else:
            grouped[alias_group["canonical"]].append(entry)

    merged_entries = []
    for canonical, group_entries in grouped.items():
        alias_group = alias_table[normalize_key(canonical)]
        weights = sorted({weight for entry in group_entries for weight in entry["weights"]})
        styles = sorted({style for entry in group_entries for style in entry["styles"]}, key=str.casefold)
        merged_from = sorted({family for entry in group_entries for family in entry["merged_from"]}, key=str.casefold)
        warnings = sorted({warning for entry in group_entries for warning in entry["warnings"]})
        if len(group_entries) > 1:
            warnings.append("merged_by_optional_alias_table")
        aliases = sorted(
            {alias for alias in alias_group.get("aliases", []) if alias not in {canonical, alias_group.get("display")}},
            key=str.casefold,
        )

        merged_entries.append(
            {
                "display": alias_group.get("display", canonical),
                "canonical": canonical,
                "aliases": aliases,
                "merged_from": merged_from,
                "styles": styles,
                "weights": weights,
                "private": any(entry["private"] for entry in group_entries),
                "fixed_pitch": any(entry["fixed_pitch"] for entry in group_entries),
                "scalable": any(entry["scalable"] for entry in group_entries),
                "smoothly_scalable": any(entry["smoothly_scalable"] for entry in group_entries),
                "warnings": warnings,
            }
        )

    return sorted([*passthrough, *merged_entries], key=lambda entry: entry["display"].casefold())


def build_system_entries(
    qfont_db: Any,
    system_families: list[str],
    custom_keys: set[str],
    alias_table: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    entries = [system_family_details(qfont_db, family, custom_keys) for family in system_families]
    return merge_system_alias_entries(entries, alias_table)


def serialize_face(face: FaceCandidate) -> dict[str, Any]:
    return {
        "file": face.file,
        "face_index": face.face_index,
        "canonical_family": face.canonical_family,
        "display_family": face.display_family,
        "style_name": face.style_name,
        "display_face": face.display_face,
        "weight": face.weight,
        "qt_families": face.qt_families,
        "english_family": face.english_family,
        "localized_family": face.localized_family,
        "postscript_name": face.postscript_name,
        "warnings": face.warnings,
    }


def build_report(
    faces: list[FaceCandidate],
    system_families: list[str],
    qfont_db: Any,
    alias_table: dict[str, dict[str, Any]],
    custom_group_table: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    groups: dict[str, list[FaceCandidate]] = defaultdict(list)
    for face in faces:
        group = custom_group_table.get(normalize_key(face.canonical_family))
        group_key = normalize_key(group["canonical"]) if group else normalize_key(face.canonical_family)
        groups[group_key].append(face)

    system_keys = {normalize_key(family): family for family in system_families}
    grouped_entries = []
    separate_entries = []
    warnings = []

    for key, group_faces in sorted(groups.items(), key=lambda item: item[1][0].display_family.casefold()):
        custom_group = custom_group_table.get(normalize_key(group_faces[0].canonical_family))
        display_family = custom_group["display"] if custom_group else group_faces[0].display_family
        canonical_family = custom_group["canonical"] if custom_group else group_faces[0].canonical_family
        weights = sorted(
            {
                custom_group_table.get(normalize_key(face.canonical_family), {}).get("member", {}).get("weight", face.weight)
                for face in group_faces
                if custom_group_table.get(normalize_key(face.canonical_family), {}).get("member", {}).get("weight", face.weight) is not None
            }
        )
        files = sorted({face.file for face in group_faces})
        styles = sorted(
            {
                custom_group_table.get(normalize_key(face.canonical_family), {}).get("member", {}).get("style", face.style_name)
                for face in group_faces
            },
            key=str.casefold,
        )
        qt_families = sorted({family for face in group_faces for family in face.qt_families}, key=str.casefold)
        face_canonicals = sorted({face.canonical_family for face in group_faces}, key=str.casefold)
        group_warnings = sorted({warning for face in group_faces for warning in face.warnings})
        if len({normalize_key(face.display_family) for face in group_faces}) > 1:
            group_warnings.append("multiple_display_names_in_group")
        if custom_group and len(face_canonicals) > 1:
            group_warnings.append("grouped_by_optional_custom_table")
        if key in system_keys:
            group_warnings.append(f"custom_overrides_system:{system_keys[key]}")

        grouped_entries.append(
            {
                "display": display_family,
                "canonical": canonical_family,
                "weights": weights,
                "styles": styles,
                "files": files,
                "face_canonicals": face_canonicals,
                "qt_families": qt_families,
                "warnings": group_warnings,
            }
        )

        for face in sorted(group_faces, key=lambda item: (item.display_face.casefold(), item.style_name.casefold())):
            separate_entries.append(serialize_face(face))

        for warning in group_warnings:
            warnings.append({"canonical": canonical_family, "display": display_family, "warning": warning})

    custom_keys = {normalize_key(entry["canonical"]) for entry in grouped_entries}
    system_entries = build_system_entries(qfont_db, system_families, custom_keys, alias_table)
    system_warning_entries = [
        {"canonical": entry["canonical"], "display": entry["display"], "warning": warning}
        for entry in system_entries
        for warning in entry["warnings"]
    ]
    non_ascii_system_entries = [entry for entry in system_entries if not entry["display"].isascii()]

    return {
        "counts": {
            "custom_faces": len(faces),
            "grouped_picker_entries": len(grouped_entries),
            "separate_picker_entries": len(separate_entries),
            "system_families": len(system_families),
            "system_picker_entries": len(system_entries),
            "system_alias_groups_loaded": len({group["canonical"] for group in alias_table.values()}),
            "custom_group_overrides_loaded": len({group["canonical"] for group in custom_group_table.values()}),
            "non_ascii_system_families": len(non_ascii_system_entries),
            "system_warning_entries": len(system_warning_entries),
            "warning_groups": len({item["canonical"] for item in warnings}),
        },
        "grouped_picker_entries": grouped_entries,
        "separate_picker_entries": separate_entries,
        "system_picker_entries": system_entries,
        "non_ascii_system_picker_entries": non_ascii_system_entries,
        "system_warnings": system_warning_entries,
        "warnings": warnings,
    }


def markdown_report(report: dict[str, Any], limit: int) -> str:
    counts = report["counts"]
    lines = [
        "# Font Registry Logic Probe",
        "",
        "## Summary",
        "",
        f"- Custom faces: {counts['custom_faces']}",
        f"- Grouped picker entries: {counts['grouped_picker_entries']}",
        f"- Separate picker entries: {counts['separate_picker_entries']}",
        f"- System families seen by Qt: {counts['system_families']}",
        f"- System picker entries after optional alias merge: {counts['system_picker_entries']}",
        f"- System alias groups loaded: {counts['system_alias_groups_loaded']}",
        f"- Custom group overrides loaded: {counts['custom_group_overrides_loaded']}",
        f"- Non-ASCII system families seen by Qt: {counts['non_ascii_system_families']}",
        f"- System warning entries: {counts['system_warning_entries']}",
        f"- Groups with warnings: {counts['warning_groups']}",
        "",
        "## Grouped Picker Entries",
        "",
    ]

    entries = report["grouped_picker_entries"]
    for entry in entries[:limit]:
        weights = ", ".join(str(weight) for weight in entry["weights"]) or "unknown"
        styles = ", ".join(entry["styles"]) or "unknown"
        lines.append(f"- {entry['display']} (`{entry['canonical']}`): weights {weights}; styles {styles}; files {len(entry['files'])}")
        if entry["warnings"]:
            lines.append(f"  - warnings: {', '.join(entry['warnings'])}")
        if len(entry["face_canonicals"]) > 1:
            lines.append(f"  - face canonicals: {', '.join(entry['face_canonicals'])}")
        if entry["qt_families"]:
            lines.append(f"  - Qt families: {', '.join(entry['qt_families'])}")
    if len(entries) > limit:
        lines.append(f"- ... {len(entries) - limit} more")

    lines.extend(["", "## Separate Face Entries", ""])
    faces = report["separate_picker_entries"]
    for face in faces[:limit]:
        weight = face["weight"] if face["weight"] is not None else "unknown"
        lines.append(f"- {face['display_face']} -> `{face['canonical_family']}` / {face['style_name']} / weight {weight}")
        if face["warnings"]:
            lines.append(f"  - warnings: {', '.join(face['warnings'])}")
    if len(faces) > limit:
        lines.append(f"- ... {len(faces) - limit} more")

    non_ascii_system_entries = report["non_ascii_system_picker_entries"]
    if non_ascii_system_entries:
        lines.extend(
            [
                "",
                "## Non-ASCII System Picker Entries",
                "",
                "These are system families Qt exposes with localized or non-ASCII names. Qt does not provide their English alias relationship here.",
                "",
            ]
        )
        for entry in non_ascii_system_entries:
            weights = ", ".join(str(weight) for weight in entry["weights"]) or "unknown"
            styles = ", ".join(entry["styles"][:8]) or "unknown"
            if len(entry["styles"]) > 8:
                styles += f", ... {len(entry['styles']) - 8} more"
            flags = []
            if entry["private"]:
                flags.append("private")
            if entry["fixed_pitch"]:
                flags.append("fixed_pitch")
            if entry["scalable"]:
                flags.append("scalable")
            if entry["smoothly_scalable"]:
                flags.append("smoothly_scalable")
            lines.append(f"- {entry['display']}: weights {weights}; styles {styles}; flags {', '.join(flags) or 'none'}")
            if entry["aliases"]:
                lines.append(f"  - aliases: {', '.join(entry['aliases'])}")
            if len(entry["merged_from"]) > 1:
                lines.append(f"  - merged from: {', '.join(entry['merged_from'])}")
            if entry["warnings"]:
                lines.append(f"  - warnings: {', '.join(entry['warnings'])}")

    lines.extend(
        [
            "",
            "## System Picker Entries",
            "",
            "System entries use only Qt-provided family/style/weight data. Localized or English alias records are not available through Qt here.",
            "",
        ]
    )
    system_entries = report["system_picker_entries"]
    for entry in system_entries[:limit]:
        weights = ", ".join(str(weight) for weight in entry["weights"]) or "unknown"
        styles = ", ".join(entry["styles"][:8]) or "unknown"
        if len(entry["styles"]) > 8:
            styles += f", ... {len(entry['styles']) - 8} more"
        flags = []
        if entry["private"]:
            flags.append("private")
        if entry["fixed_pitch"]:
            flags.append("fixed_pitch")
        if entry["scalable"]:
            flags.append("scalable")
        if entry["smoothly_scalable"]:
            flags.append("smoothly_scalable")
        lines.append(f"- {entry['display']}: weights {weights}; styles {styles}; flags {', '.join(flags) or 'none'}")
        if entry["aliases"]:
            lines.append(f"  - aliases: {', '.join(entry['aliases'])}")
        if len(entry["merged_from"]) > 1:
            lines.append(f"  - merged from: {', '.join(entry['merged_from'])}")
        if entry["warnings"]:
            lines.append(f"  - warnings: {', '.join(entry['warnings'])}")
    if len(system_entries) > limit:
        lines.append(f"- ... {len(system_entries) - limit} more")

    if report["warnings"]:
        lines.extend(["", "## Warning Index", ""])
        for warning in report["warnings"][:limit]:
            lines.append(f"- {warning['display']} (`{warning['canonical']}`): {warning['warning']}")
        if len(report["warnings"]) > limit:
            lines.append(f"- ... {len(report['warnings']) - limit} more")

    if report["system_warnings"]:
        lines.extend(["", "## System Warning Index", ""])
        for warning in report["system_warnings"][:limit]:
            lines.append(f"- {warning['display']}: {warning['warning']}")
        if len(report["system_warnings"]) > limit:
            lines.append(f"- ... {len(report['system_warnings']) - limit} more")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe the proposed font registry picker logic.")
    parser.add_argument("--qt-api", default="pyqt6", choices=["pyqt6", "pyside6", "pyqt5", "pyside2"])
    parser.add_argument("--fonts-dir", default="fonts")
    parser.add_argument("--locale", default="ko-KR")
    parser.add_argument("--font-registry-config", help="Optional unified JSON file for system aliases and custom font groups.")
    parser.add_argument("--system-alias-table", help="Optional JSON alias table for merging Qt system font families.")
    parser.add_argument("--custom-group-table", help="Optional JSON table for grouping custom font faces in the picker.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--limit", type=int, default=80, help="Limit Markdown entry count per section.")
    parser.add_argument("--output", help="Write the report to this path instead of stdout.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["QT_API"] = args.qt_api

    from qtpy import API, QT_VERSION
    from qtpy.QtGui import QFontDatabase
    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    system_families = sorted(QFontDatabase.families(), key=str.casefold)
    faces = collect_custom_faces(Path(args.fonts_dir), QFontDatabase, args.locale)
    alias_table = load_system_alias_table(args.font_registry_config)
    alias_table.update(load_system_alias_table(args.system_alias_table))
    custom_group_table = load_custom_group_table(args.font_registry_config)
    custom_group_table.update(load_custom_group_table(args.custom_group_table))
    report = build_report(faces, system_families, QFontDatabase, alias_table, custom_group_table)
    report["qt"] = {"api": API, "version": QT_VERSION}
    report["policy"] = {
        "canonical": "prefer English typographic family, then English family, then localized family",
        "display": "prefer requested locale typographic family/family, then English fallback",
        "grouping": "group only by explicit name-table canonical family",
        "system_conflict": "custom family wins when canonical name matches a system family",
        "system_alias_merge": "system families are merged only when an optional alias table is provided",
        "custom_group_override": "custom faces may be grouped by optional data, while face canonical names remain intact",
    }

    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n" if args.format == "json" else markdown_report(report, args.limit)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
