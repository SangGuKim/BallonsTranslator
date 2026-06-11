# Format Inspector와 Rich Text 편집 문제 정리

이 문서는 폰트 레지스트리 PR에서 직접 다루지 않을 문제를 다음 스테이지에서
검토하기 위해 정리한다. 문제의 중심은 font registry가 아니라 우측 format panel이
현재 선택 상태를 어떤 모델로 해석하고 표시해야 하는가이다.

## 현재 관찰된 증상

### 여러 text block 선택 시 global format이 표시됨

여러 text block을 선택하면 우측 패널에 선택된 block들의 공통 서식이 아니라
`global_format`이 표시된다. font size는 `16+`처럼 `+`가 붙어 multi-select 상태를
암시하지만, font family와 weight 등은 global 값 그대로 보인다.

이 동작은 원본 `dev`부터 존재한다.

- `ScenetextManager.on_incanvas_selection_changed()`에서 여러 block 선택 시
  `formatpanel.set_textblk_item(multi_select=True)`를 호출한다.
- `FontFormatPanel.set_textblk_item(None, multi_select=True)`는
  `set_active_format(self.global_format, multi_select)`를 호출한다.
- `set_active_format()`은 `multi_size=True`일 때 size 문자열에만 `+`를 붙인다.

따라서 현재 구현은 multi-selection aggregate inspector가 아니라, multi-select
상태에서 global format을 보여 주고 size만 상대 조정 가능성을 표시하는 단순 모델이다.

### 여러 block의 공통값/혼합값을 표시하지 않음

여러 block을 선택했을 때 다음 계산을 하지 않는다.

- 모든 block의 font family가 같으면 그 family 표시
- 다르면 공백 또는 mixed 상태 표시
- weight, size, color, alignment, stroke 등도 같은 방식으로 aggregate

결과적으로 사용자는 패널에 보이는 font family가 선택된 block들의 실제 공통값인지,
아니면 global 기본값인지 구분하기 어렵다.

### Rich Text 편집 중 커서 위치의 서식을 표시하지 않음

텍스트 블록 내부에서 직접 텍스트를 편집하고 커서를 옮겨도, 우측 패널은 현재 커서
위치의 `QTextCharFormat`을 실시간으로 반영하지 않는다.

현재 format panel 갱신은 주로 다음 이벤트에 의존한다.

- scene에서 text block 선택 변경
- text block 선택 해제
- format panel 컨트롤 조작
- 일부 undo/redo 또는 text edit command 후 수동 `set_active_format()`

반면 `QTextDocument`/`QTextCursor`의 cursor position 또는 selection change를
format panel로 연결하는 inspector 경로가 없다.

### Rich Text 일부 선택 시 mixed 상태를 표시하지 않음

텍스트 일부를 선택한 경우 선택 범위 안의 fragment들을 훑어 공통 서식을 계산해야
하지만, 현재 구조는 대표 `TextBlock.fontformat` 또는 현재 cursor char format 하나에
의존한다.

따라서 다음 상태를 정확히 표현하지 못한다.

- 선택 범위 전체가 같은 font family인 경우
- 선택 범위에 여러 font family가 섞인 경우
- 선택 범위 전체가 같은 weight인 경우
- 선택 범위에 여러 weight/size/color가 섞인 경우

### Rich Text fragment 서식과 TextBlock 대표 서식의 역할이 섞임

현재 `TextBlock.fontformat`은 다음 역할을 동시에 맡고 있다.

- 새 text block 생성 시 기본 서식
- text block 전체 대표 서식
- format panel 표시값
- rich text fragment 편집 시 fallback 또는 저장 보조값

그러나 rich text가 생기면 실제 렌더링 서식은 `QTextDocument` 내부 fragment
format에 들어간다. 이때 `TextBlock.fontformat`은 대표값일 뿐이며, fragment별
서식과 항상 같을 수 없다.

## 현재 구조의 핵심 원인

### active_format이 하나뿐이다

`C.active_format`은 global format, text block 대표 format, text style preset 편집
상태를 모두 가리킬 수 있다. 사용자가 지금 편집하는 대상이 다음 중 무엇인지 별도
상태로 명확히 분리되어 있지 않다.

- 아무 것도 선택하지 않은 global format
- 선택된 단일 text block의 대표 format
- 여러 text block의 aggregate format
- rich text cursor 위치의 char format
- rich text selection aggregate format
- 활성 text style preset

### 패널 표시값과 적용 대상이 분리되어 있지 않다

현재 format panel은 `set_active_format()`으로 표시값을 설정하고, 컨트롤 변경 시
`on_param_changed()`에서 global mode인지 아닌지를 보고 값을 적용한다.

하지만 rich text cursor selection이 있는 경우에는 표시값과 적용 대상이 다음처럼
나뉘어야 한다.

- 표시값: 현재 selection aggregate
- 적용 대상: 현재 selection의 fragment 범위
- 대표값 갱신: 필요한 경우에만 TextBlock.fontformat에 반영

현재 구조는 이 세 가지를 분리하지 않는다.

### mixed value 표현이 없다

font size에는 `+` suffix라는 제한적 표현이 있지만, family/weight/color 등에는
mixed 상태 표현이 없다. 공백, placeholder, indeterminate state 같은 UI 정책이
정해져 있지 않다.

## 다음 스테이지에서 정해야 할 정책

### 선택 상태 모델

우측 format panel의 source mode를 명시적으로 나누는 것이 좋다.

- `global`: 아무 text block도 선택하지 않은 상태. 새 block 생성 기본값을 편집한다.
- `block`: 단일 text block 선택. block 대표 format 또는 전체 document 공통값을 표시한다.
- `multi_block`: 여러 text block 선택. block별 aggregate 값을 표시한다.
- `rich_cursor`: text editing 중 cursor만 있는 상태. 현재 cursor char format을 표시한다.
- `rich_selection`: text editing 중 일부 텍스트가 선택된 상태. 선택 범위 fragment
  aggregate 값을 표시한다.
- `style_preset`: text style label이 활성화된 상태. global format과 preset 연결
  편집을 한다.

### mixed value 표시

각 format field별로 mixed 상태 표시 방식을 정해야 한다.

- font family: 공백 또는 placeholder
- font weight: 공백 또는 indeterminate combo
- font size: 기존 `+` 유지 또는 공백/mixed 표기로 변경
- color: indeterminate swatch 또는 공백
- bold/italic/underline: tri-state 또는 unchecked-with-mixed-marker
- alignment/vertical: 공통값만 표시, 다르면 mixed

`fontsys` 브랜치에서 사용했던 "같으면 표시하고 다르면 공백" 정책은 가장 단순하고
이해하기 쉬운 후보이다.

### 적용 정책

mixed 상태에서 사용자가 새 값을 입력하면 다음 대상에만 적용해야 한다.

- `multi_block`: 선택된 block 전체 또는 각 block의 현재 대표 format
- `rich_selection`: 선택된 text fragment 범위
- `rich_cursor`: 이후 입력될 텍스트의 char format
- `global`: global format
- `style_preset`: 활성 preset과 global format

이때 `TextBlock.fontformat`은 fragment별 rich text를 완전히 대표할 수 없으므로,
partial rich text 변경 때마다 무조건 덮어쓰는 것은 피해야 한다.

## 구현 후보

### 후보 A: 최소 보정

- multi-select 때 font family/weight만 공백 처리한다.
- rich text cursor movement는 이번에도 다루지 않는다.

장점은 작고 안전하다. 단점은 현재 문제의 핵심인 rich text inspector 부재를
해결하지 못한다.

### 후보 B: selection aggregate helper 추가

`TextBlkItem` 또는 별도 helper에 다음 함수를 둔다.

- 단일 block document 전체 aggregate
- 현재 cursor 위치 char format
- 현재 cursor selection aggregate
- 여러 block 대표 format aggregate

이 helper가 `FontFormat`과 mixed field set을 반환하고, format panel은 mixed field를
UI에 반영한다.

장점은 현재 구조를 크게 뒤집지 않고도 문제를 체계적으로 줄일 수 있다. 단점은
각 UI control의 mixed 표현을 추가해야 한다.

### 후보 C: FormatInspector 상태 머신 도입

format panel 앞에 `FormatInspectorState` 같은 중간 모델을 둔다.

- source mode
- displayed values
- mixed fields
- apply target
- active preset linkage

를 명시적으로 들고, panel은 이 상태만 렌더링한다.

장점은 가장 명확하다. 단점은 변경 범위가 커지고, 이번 font registry PR과 같이
넣기에는 위험하다.

## 이번 PR과의 관계

이번 font registry PR은 family name의 canonical/display 분리, custom font metadata,
grouped/separate picker, weight picker, rich text 저장명 정규화만 다룬다.

반면 이 문서의 문제는 format panel의 selection state와 rich text inspector 문제다.
따라서 이번 PR에는 포함하지 않는 것이 안전하다. 다만 현재 구현에서 rich text
저장명 정규화를 넣은 이유는 serialization 안정성 때문이며, full inspector 문제를
해결했다는 의미는 아니다.

## 다음 작업 전 확인할 사항

- `QGraphicsTextItem`의 cursor/selection change를 안정적으로 감지할 수 있는 지점
- text editing mode와 scene selection mode 전환 시 panel 갱신 순서
- undo/redo 시 `TextBlock.fontformat`과 `QTextDocument` fragment format의 동기화
- text style preset 활성 상태와 rich text selection 편집이 동시에 발생할 때 우선순위
- multi-block 편집 시 부분 rich text가 있는 block의 대표값 정책

이 항목을 확인한 뒤 후보 B 또는 C 중 하나를 선택하는 것이 좋다.
