# Font Registry Design

## Purpose

This document proposes a safer font registry and font picker design for
BalloonsTranslator. The goal is to make custom fonts, localized font names, and
font weights behave predictably across Windows, macOS, and Linux while preserving
existing project compatibility.

## Current Behavior

At startup, BalloonsTranslator loads font files from the local `fonts/` directory
with `QFontDatabase.addApplicationFont()`.

The current implementation stores the first family returned by Qt for each font
file:

```python
QFontDatabase.applicationFontFamilies(font_id)[0]
```

The font picker then switches between two sources:

- `Show only custom fonts = true`: show the custom font list
- `Show only custom fonts = false`: show the full Qt font family list

This switch should remain meaningful. Custom fonts and system fonts should not be
forcibly merged in a way that makes this option confusing.

## Problems

The current approach has several edge cases:

- Multiple font files for different weights can add the same family many times.
- Some fonts expose a shared typographic family, while others expose separate
  family names per weight.
- Windows can return localized system family names, while macOS often returns
  English names.
- Some custom fonts contain localized names that Qt does not return reliably.
- The full system font list can include legacy bitmap fonts on Windows, causing
  repeated Qt DirectWrite warnings.
- The system font list is currently based on a set, so display order can be
  unstable.
- The application/default text font is currently initialized from a hard-coded
  family. That can produce poor fallback results for users whose UI language does
  not match that family.

## Upstream Qt And Font History

The family-plus-weight versus separate-face behavior is tied to Qt version and
font backend behavior, not just picker presentation.

Relevant upstream history:

- `5e5245f` raised the minimum Qt version to 6.6.2 or newer on macOS.
- `9c6bdf1` raised the minimum Qt version to 6.6.2 or newer on Windows.
- `ffa0636` later constrained PyQt to `>=6.6.2,<6.7.0`.
- `91f2ee4` adjusted `QFontComboBox` selection/input behavior.
- `82d2df2` fixed Windows headless/offscreen font database initialization by
  explicitly registering system font files for that path.
- `c7d5207`, `5c8344e`, and `2debb6d` fixed normal/bold weight behavior and
  Qt5/Qt6 font-weight value conversion.

Related upstream issues point in the same direction:

- #555 identifies thin/bold rendering as a Qt5/Qt6 font-weight value mismatch
  and fixes it through conversion, not by switching away from Qt's normal font
  backend.
- #570 includes DirectWrite font warnings in logs, but the follow-up focuses on
  saved/global format behavior and reproduction details.
- #1042 is an open custom-font loading issue that reports blank font names,
  duplicate names for different weights, missing application of some fonts, and
  DirectWrite warnings.

The design should therefore assume the current Qt6 font backend remains in use.
It should preserve existing `font_family` and `font_weight` storage while adding
a registry layer that makes Qt-exposed family/face differences predictable.

## Design Principles

### Preserve Existing Projects

Do not change the project JSON shape for the first implementation. Existing
`font_family` and `font_weight` fields should remain valid.

Existing saved family values should be resolved at runtime. They should not be
rewritten just because a registry can map them to a newer canonical name.

### Avoid Locale-Specific Hard-Coded Defaults

Application UI fonts and default text fonts should be selected from the current
platform and UI locale instead of a single hard-coded CJK family.

Suggested fallback order:

1. Existing user-configured default font
2. UI-locale-appropriate platform font
3. Qt application default font
4. Existing hard-coded fallback only as a last resort

Changing this should not rewrite existing project text styles. It should only
affect newly created default configuration or runtime application font selection.

### Do Not Map System Fonts Across Operating Systems

The resolver should not silently map one operating system's system font to
another system font on a different platform. For example, a saved Windows-only
system font should not be rewritten or automatically substituted with a macOS
system font.

System fonts are local platform resources. Similar-looking families can have
different metrics, glyph coverage, and weight behavior. Projects that require
cross-platform font stability should use bundled custom fonts in `fonts/` and,
when appropriate, the custom-only picker option.

If a saved system font is missing on the current platform, the first
implementation should preserve the saved family and let Qt fallback handle
rendering. A later UI can expose missing or resolved font state explicitly.

### Merge System Aliases Only From Optional Data

Qt can expose localized and English system family names as separate entries,
such as `Batang` and `바탕` on Korean Windows. Qt does not provide a stable alias
relationship for these names through `QFontDatabase` alone.

System font aliases should therefore not be inferred automatically. If an
optional alias table is provided, only the groups explicitly listed in that
table should be merged. If no table is provided, or a family is not listed, the
families should remain separate Qt-provided entries.

This keeps the default behavior conservative while allowing distributors or
users to provide locale-specific alias data.

### Separate Internal Family and Display Name

The value used internally and saved into projects should be a canonical family
name where possible. The text shown in the UI should be a display name.

Suggested canonical fallback order:

1. English typographic family
2. English family
3. ASCII family returned by Qt
4. Localized typographic family
5. Localized family
6. Qt-renderable family

Suggested display fallback order:

1. Family name matching the current UI locale
2. Localized typographic family
3. Localized family
4. English typographic family
5. English family
6. Canonical family
7. Qt family

The rendering key must always remain resolvable by Qt. Display names should not
be treated as rendering keys unless they are also known Qt family aliases.

### Respect the Custom-Only Switch

The custom-only option should remain simple:

- On: show only fonts loaded from `fonts/`
- Off: show system fonts plus custom fonts

When a system font and a custom font have the same canonical family, the custom
font should take priority. A font placed in `fonts/` is an explicit user choice.

### Group Weights Only When the Font Metadata Supports It

The preferred UI is family selection plus separate weight selection, but only
when the font metadata actually identifies the faces as one family.

Fonts can be grouped when:

- the typographic family is the same,
- Qt returns the same family, or
- the family is the same and only the subfamily differs.

Fonts should not be grouped when:

- the font itself declares weight-specific family names,
- the typographic family is already weight-specific, or
- grouping would require guessing from filenames alone.

For example, if a font declares separate families such as `Example Sans Bold`,
`Example Sans Light`, and `Example Sans Medium`, those should remain separate
unless the font metadata provides a shared typographic family.

An optional custom group table can override this for known font families. This
is useful when separate files declare weight-specific family names but users
expect one picker family with separate weights. The override should affect the
picker grouping only: each face must keep its original canonical family and Qt
rendering family for persistence and rendering.

If no custom group table is provided, these faces remain separate. The
implementation should not infer such groups by stripping words like `Bold`,
`Light`, or `Medium` from filenames.

## Proposed Runtime Model

Introduce a runtime-only font registry:

```python
@dataclass
class FontFace:
    qt_family: str
    style_name: str
    weight: int
    file_path: str | None
    aliases: set[str]


@dataclass
class FontEntry:
    canonical_family: str
    display_family: str
    qt_family: str
    source: Literal["custom", "system"]
    file_paths: list[str]
    weights: list[int]
    styles: list[str]
    faces: list[FontFace]
    is_scalable: bool
    aliases: set[str]
    alias_source: Literal["name-table", "optional-table", "none"]
```

Field meanings:

- `canonical_family`: stable internal name
- `display_family`: UI label
- `qt_family`: family passed to `QFont` and `QTextCharFormat`
- `source`: `custom` or `system`
- `file_paths`: source font files for custom entries
- `weights`: available weights
- `styles`: Qt styles
- `faces`: per-face metadata used to keep style selection precise in grouped
  mode
- `is_scalable`: whether the font should appear in the normal font picker
- `aliases`: older names, localized names, and Qt names accepted by resolver
- `alias_source`: whether aliases came from custom font name tables, optional
  system alias data, or no merge data

## Resolver Policy

Resolve an existing saved `font_family` in this order:

1. canonical family exact match
2. alias exact match
3. Qt family exact match
4. display family exact match
5. case-insensitive match
6. fallback to the original family string

When a user selects a new font from the picker, save the canonical family. When
loading an existing project, preserve the stored value unless the user changes
the font.

If a picker family comes from an optional custom group table, do not save the
pseudo group family directly unless it is also renderable by Qt. Save the
selected face's canonical family together with the selected weight, so the
project still resolves when the optional table is unavailable.

## Font Picker Policy

The picker should be model-backed instead of a plain string list.

- visible text: `display_family`
- selected value: `canonical_family`
- rendering family: `qt_family`

The list should be stable-sorted. A simple casefold-based sort is acceptable for
the first implementation; locale-aware sorting can be considered later.

Known legacy bitmap fonts should be hidden by default on Windows to avoid
repeated DirectWrite warnings. The initial implementation should use an explicit
family blacklist for the known problematic families:

```text
Fixedsys
MS Sans Serif
MS Serif
Terminal
System
Small Fonts
```

A broader scalability filter such as `QFontComboBox.FontFilter.ScalableFonts` or
`QFontDatabase.isSmoothlyScalable(family)` can be considered later. Starting
with an explicit blacklist reduces the chance of hiding unusual CJK or legacy
fonts that users may still expect to see.

The picker should not rely on the visual text alone to identify fonts. Display
names may be localized, while stored values should resolve through the registry.

## Weight Selection Modes

Two modes should be supported:

```text
Font weight selection mode:
- Group weights by family
- Show font faces separately
```

### Prior UI Prototype Reference

An earlier prototype already added a font-weight control to the text format
panel. The implementation should be rewritten for the registry model, but the UI
layout and interaction model are useful references.

Useful parts of that prototype:

- Add a compact font-weight combobox next to font family and font size.
- Keep the first text-format row ordered as family, size, weight.
- Move line-spacing controls to the lower row near stroke and letter-spacing
  controls.
- Treat the `B` button as a weight shortcut rather than an independent saved
  boolean. Turning it on should select a bold weight, and turning it off should
  select a regular weight.
- Refresh available weights when the family changes, while preserving the
  nearest selected weight when possible.
- For multi-selection, show common values and clear controls whose values differ
  between selected text blocks.

The final implementation should source weight options from registry `FontFace`
metadata instead of querying Qt styles ad hoc, so grouped and separate-face modes
remain consistent.

### Group Weights by Family

The family picker shows one entry per family. A separate weight picker shows
available weights. This is best for fonts that expose a shared family with
multiple styles or weights.

Rendering should keep per-face metadata available instead of relying only on a
family name and numeric weight. Suggested order:

1. Use `QFont.setStyleName()` or an equivalent Qt API when the selected
   `FontFace` has a matching `style_name`.
2. Otherwise pass `qt_family` plus the selected `font_weight`.
3. If neither is reliable, fall back to `qt_family` and let Qt resolve the face.

This avoids losing distinctions such as `Medium` and `SemiBold` when a font's
style metadata is more precise than Qt's generic weight matching.

### Show Font Faces Separately

The picker shows each face/family as Qt exposes it. This is necessary for fonts
that intentionally declare weight-specific family names.

The default can be grouped mode, but separate-face mode should remain available
for fonts with unusual metadata or for users who prefer exact face selection.

## Dependency Policy

Do not add a mandatory dependency just to inspect font names.

If localized names from font files are needed, prefer a small internal parser for
the `name` table records required by this feature. A development-only inspection
script may use external tooling, but the application should not require it at
runtime.

If the internal parser supports font files directly, it should account for TrueType
Collection files (`.ttc`) by reading the collection header and per-font offsets
before parsing each contained font's `name` table.

## Suggested Implementation Phases

### Phase 1: Small Stabilization

- Keep the custom-only switch behavior unchanged.
- Deduplicate custom font families.
- Stable-sort system and custom font lists.
- Hide known legacy Windows bitmap fonts from the picker.
- Avoid locale-specific hard-coded default font selection for new defaults.
- Do not change project JSON.

### Phase 2: Runtime Registry

- Add a runtime font registry.
- Keep compatibility adapters for the existing custom/system font lists.
- Add resolver logic for old saved family names.

### Phase 3: Display Name Separation

- Parse custom font metadata for display names.
- Separate displayed label from saved family key.
- Keep Qt-renderable family names as rendering keys.

### Phase 4: Weight UI

- Add the weight selection mode setting.
- Add family + weight UI for grouped fonts.
- Preserve separate-face mode.
- Keep `font_weight` backward-compatible.

## Non-Goals

- Do not change module loading behavior.
- Do not change project JSON shape in the initial PR.
- Do not automatically enable the custom-only setting.
- Do not add mandatory dependencies.
- Do not add font stretch or horizontal scaling support.

Font stretch should be treated as a separate feature. Earlier experiments hit a
Qt rendering issue where large text sizes could lose the intended stretch and
only keep expanded letter spacing. Reintroducing stretch requires a dedicated
reproduction test and may need a rendering workaround outside Qt rich text.

## Pull Request Scope

A good first PR should be intentionally small:

- stable font ordering,
- custom font deduplication,
- known legacy bitmap font filtering,
- no saved project format changes,
- no automatic custom-only preference changes.
- no forced rewrite of existing default font settings.

The registry and weight UI can follow once the low-risk behavior is accepted.
