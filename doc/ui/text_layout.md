# Text layout

Read [Text engine](text_engine.md) first. This guide records the behavior and
ownership shared by shaping, wrapping, vertical flow, painting, and editing.
Implementation-specific algorithms belong in code comments and focused tests.

## Mental model

```text
QTextDocument rich text (Qt UTF-16 positions)
  -> SceneTextLayout fragment metrics
  -> horizontal lines or vertical columns
  -> settled placement
  -> fill, effects, annotations, cursor, selection, and hit testing
  -> TextItemGeometryController bounds and visual mapping
```

Qt remains the editable text model and shaper. The custom layouts place Qt
`QTextLine`s; they do not create a second text representation.

## Core contract

- `FontFormat` supplies item-wide writing mode, alignment, and compatibility
  defaults. `QTextDocument` formats own range-bound typography and
  paragraph-bound line spacing.
- Placement records, ink bounds, and caches are derived. Rebuild them together
  for one settled layout generation and never persist them.
- Fill, effects, annotations, cursor, selection, hit testing, and visual bounds
  must consume the same settled cells and transforms.
- Qt positions are UTF-16 code units. Use the shared UTF-16 and grapheme helpers
  wherever Python strings meet Qt positions; never expose a caret inside a
  surrogate pair or grapheme cluster.
- Effect padding and visible ink overflow belong to source geometry, not the
  persistent logical rectangle.

`TextBlock.text_layout_version` versions item-wide layout semantics. Missing or
version-zero vertical blocks migrate to right alignment, matching their earlier
effective placement. Inline HTML extensions remain versionless and follow the
compatibility rules in [Text engine](text_engine.md).

## Writing modes

### Horizontal

`HorizontalTextDocumentLayout` keeps Qt shaping, glyph runs, cursor behavior,
and word-boundary wrapping. It adds only the geometry Qt does not expose in the
form the editor needs. In particular, overflowing trailing U+0020 spaces stay
in the document but receive derived continuation-row cells so wrapping, box
growth, cursor, selection, and hit testing agree. Other Unicode separators keep
Qt behavior.

Common ligatures work under both bindings; discretionary/contextual ligatures
and oldstyle figures require Qt 6.11. Qt 5 preserves unsupported CSS without
applying it. Font-metric fallbacks and binding differences belong at the
layout/annotation boundary.

### Vertical

`VerticalTextDocumentLayout` normally creates one cell per grapheme and places
columns from right to left. Punctuation orientation and alignment are semantic
classes near the top of `vertical_layout.py`; extend those classes instead of
adding paint-time glyph exceptions.

Cell probes retain the legacy CJK metrics for faces supporting either reference
Han character. A requested face lacking both probes but supporting Hangul uses
its own Hangul ink instead, so a Korean-only face cannot inherit undersized
cells from a substitute Han font. Unresolved families keep the legacy fallback.

Standard Roman mode keeps proportional Roman glyphs upright and centered. The
alternate mode rotates them clockwise and uses the Chinese mixed-layout
punctuation path. Compact punctuation shortens eligible punctuation cells
without clipping their ink. Repeated dashes, bars, leaders, and ellipses form
indivisible runs, with character spacing applied after the run.

Tate-chu-yoko (TCY) is an authored horizontal run occupying one vertical cell.
Only its selected range participates in shaping; surrounding whitespace keeps
vertical cells. Multi-character runs shape full-width forms as narrow equivalents
without changing document text or UTF-16 positions. Single-character runs and
unrelated compatibility characters stay unchanged. `TateChuYokoRun` owns index
mapping between the isolated run and source block. Native IME composition remains
authoritative until commit.

TCY ignores authored letter spacing. Standard Roman mode keeps its natural
shaped width; alternate mode shrinks excess width to one em. Visible ink is
centered, and overhang affects paint and interaction bounds without widening
neighboring columns.

Ruby/furigana is attached layout content, not a detached overlay. Group Ruby is
indivisible; mono Ruby may wrap only between base/reading pairs. Each unit uses
the larger of its base and annotation advances, and the shorter run is spaced
within that cell. Horizontal Ruby appears above or below; vertical Ruby remains
upright on the right or left. Ruby and TCY cannot overlap, and automatic Ruby
overhang is not supported.

## Flow and spacing

For paragraph spacing, a caret formats its paragraph, a selection formats
intersected paragraphs, and Enter inherits the block format.

Whitespace remains document content and must consume explicit editable cells.
Horizontal and vertical layouts may represent those cells differently, but
neither may move whitespace into a second text model or drop it from cursor and
hit geometry. Vertical whitespace contributes flow advance, not the ink bounds
used to center the neighboring glyph in its column.

Character spacing is a trailing advance for the affected glyph or joined run.
On a squeezed single-column vertical item, increasing it may grow the logical
height to preserve that column; multi-column items keep normal fixed-area
reflow, and automatic growth never silently shrinks the box.

Line spacing is owned by the destination row or column. The first visual row or
column stays anchored without leading spacing; each later one uses its
paragraph's spacing value and mode. Paragraph boundaries do not restart this
visual leading-edge rule.

## Alignment and resize

Vertical alignment translates settled columns horizontally:

| Alignment | Fixed growth anchor | Added-width movement |
| --- | --- | --- |
| Left | Top-left | Columns stay fixed and grow rightward |
| Center | Top-center | Columns move by half and grow evenly |
| Right | Top-right | Columns move with the right edge and grow leftward |

Alignment changes every placement and ink-bound record together but does not
reshape text or change document content. A width-only resize may reuse that
translation when the settled content still fits; height, padding, or flow
changes require full layout. The geometry controller preserves the matching
scene-space anchor, so layout and scene movement must not both compensate for
the same resize.

## Painting and interaction

`vertical_line_placement()` is the shared boundary for rotated glyphs, TCY,
emphasis, Glyph Slant, effects, and editing geometry. Ligatures and joined glyphs
may change shaping, but not the logical UTF-16 editing range.

Document backgrounds paint below selection, and glyph ink paints above it.
Foreground and effect layouts must reuse the same settled offsets. Caches tied
to placement must be invalidated with the layout generation and must not retain
records from a replaced document layout.

## 기존 텍스트의 크기 재평가

실행 창의 **Font Size** 작업은 프로젝트 페이지의 시작·끝 범위를 받는다.
시작 전 최신 텍스트 상태를 저장하며 [프로젝트 저장 이력](../project_save_history.md)으로
이전 저장 상태를 보존한다. 저장에 실패하면 재평가를 시작하지 않는다.
블록의 폰트를 변경한 뒤 **Recalculate Font Sizes**를 실행하면 각 블록의
현재 family·weight·italic을 원본 스캔의 문자 크기와 비교한다. worker는 저장된
원문 `lines`와 `src_is_vertical`을 사용한다. 같은 페이지에서 동일한 원문 줄
좌표를 공유하는 블록은 분할·복제된 것으로 보고, 사용자가 맞춘 현재 편집 박스
안의 픽셀만 측정한다. 원문 줄의 기울기와 저장 좌표는 유지한다. 측정할 글자가
없으면 박스 밖으로 되돌아가 측정하지 않고 건너뛴다. 공유 줄이 없는 일반 블록은
번역문 박스와 독립적으로 측정하므로 세로 원문이 가로 번역 박스 밖에 있어도
측정할 수 있다. 분할 이력이 별도로 저장된 것은 아니므로 형제 블록이 삭제되거나
줄 좌표가 달라진 경우에는 공유 관계를 알아낼 수 없다. 이 작업에서 원문이나
번역문을 재검출·재정렬·병합·분할·교체하지 않는다.

효과·변형이 활성인 블록이나 리치텍스트의 구간별 문자 서식이 서로 다른 블록은 건너뛴다. 리치텍스트의 평문과 번역문이 다를 때도 보존한다. 전체에 동일한 서식은 재평가 대상으로 삼으며 HTML 태그 문자열이 아닌 Qt가 해석한 문자 서식을 비교한다. 측정과 재평가에 성공한 블록은 폰트 크기와 원문 측정 baseline을 갱신하고 균일한 리치텍스트를 제거한다. 실패한 블록의 리치텍스트는 유지한다.
박스 위치·폭·각도, 블록 순서, 이미지·마스크 픽셀은 유지한다. 원본 파일 누락,
검출기 정보 없는 수동 생성 박스, 유효하지 않은 원문 좌표, 불확실한 잉크 측정은
건너뛴다. 현재 편집 박스만으로 사라진 원문 좌표나 분할 후 잘못 공유된 좌표를
복원하지는 못한다. 그런 블록은 원문 대응을 바로잡은 뒤 재평가한다.

기존 검출기의 배율·크기 제한은 적용하되 자동 보정 활성화 여부와 무관하게 명시적
수동 작업을 실행한다. 반복 실행은 기존 크기를 곱하지 않고 원본을 다시 측정한다.
중단하면 이미 측정한 결과까지 반영하며, 실패·건너뛴 블록은 유지한다. 프로젝트
전환을 막기 위해 진행창은 worker가 종료할 때까지 모달 상태를 유지한다. 결과는
프로젝트의 미저장 변경이며, 출력 이미지는 별도로 저장·렌더링해야 갱신된다.
현재 페이지는 기존 항목의 서식만 갱신하며 장면이나 블록 목록을 재생성하지 않는다.
크기를 적용한 문서와 현재 페이지의 텍스트 실행 취소 기록은 초기화된다.

## Invalidation and verification

The normal path is:

```text
document or format change
  -> rebuild fragment metrics and position maps
  -> settle lines or columns
  -> update draw offsets and ink bounds
  -> publish size and refresh geometry/effects
```

Test relationships rather than exact font-dependent pixels. Cover affected
writing modes, fonts, spacing, annotations, effects, UTF-16 editing, resize, and
mode switches. Start with `tests/test_horizontal_whitespace.py`,
`tests/test_vertical_*.py`, `tests/test_rich_text_annotations.py`, and
`tests/test_ruby_furigana.py`; add focused font/effect suites when those owners change.

Follow the shared [text-engine verification](text_engine.md#invalidation-and-verification)
for binding and visual checks.

전각 구점·독점 `、。，．`는 영문 방향 설정과 관계없이 글자 칸의 오른쪽 위에 배치한다. 이는 업스트림과 구분하여 유지하는 main의 조판 정책이다.
