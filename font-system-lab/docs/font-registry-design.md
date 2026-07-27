# 폰트 레지스트리 설계안

## 목적

이 문서는 BT의 폰트 목록, 폰트명 저장, UI 표시명, weight 선택 방식을 안정화하기
위한 설계안이다. 목표는 Windows, macOS, Linux에서 프로젝트 호환성을 유지하면서
커스텀 폰트와 시스템 폰트를 예측 가능하게 표시하고 선택하는 것이다.

이 설계는 `fontsys` 브랜치의 시행착오를 반영한다. 특히 다음 전제를 둔다.

- "Show only custom fonts" 스위치를 존중한다.
- custom font와 system font를 무리하게 한 목록으로 합치지 않는다.
- 내부 저장명과 UI 표시명을 분리한다.
- weight 통합 선택은 가능한 경우에만 한다.
- XPU 관련 수정은 이번 폰트 통합 범위에서 제외한다.

## 현재 문제

현재 `dev`의 폰트 흐름은 단순하다.

- `fonts/` 폴더의 폰트를 `QFontDatabase.addApplicationFont()`로 등록한다.
- 각 파일의 `applicationFontFamilies(font_id)[0]`를 `shared.CUSTOM_FONTS`에
  append한다.
- custom-only 설정이 켜지면 `shared.CUSTOM_FONTS`만 표시한다.
- custom-only 설정이 꺼지면 `shared.FONT_FAMILIES` 전체를 표시한다.

이 방식은 다음 문제를 만든다.

- 같은 family의 여러 weight 파일이 custom list에 중복 표시된다.
- `shared.FONT_FAMILIES`가 `set`이라 시스템 폰트 표시 순서가 안정적이지 않다.
- Windows에서는 시스템 폰트명이 로컬라이즈된 이름으로 나오고, macOS에서는
  영문명으로 나오는 등 OS별 family name이 달라질 수 있다.
- 커스텀 폰트는 폰트 파일 name table에 따라 영문명, 로컬라이즈명, 깨진 이름,
  weight별 family명 등으로 제각각 표시된다.
- Windows에서는 localized family와 English family가 별도 이름으로 노출되거나,
  하나의 TTC 파일 안에 여러 관련 family가 함께 들어 있어 목록상 중복처럼 보일 수
  있다. 예를 들어 `바탕`/`Batang`, `바탕체`/`BatangChe` 같은 localized alias
  쌍은 Qt backend와 locale에 따라 다르게 보일 수 있다.
- `폰트명 Bold`, `폰트명 Light`처럼 weight가 family name 뒤에 붙어 있는 face가
  Qt를 거치면 모두 `폰트명` family로만 표시될 수 있다. 이 경우 리스트에서는
  weight preview로만 구분해야 하는데, 일부 폰트는 preview 굵기도 동일하게 보여
  사용자가 face를 구분할 수 없다.
- non-scalable Windows bitmap font가 목록에 들어오면 Qt6 DirectWrite 경고가
  반복될 수 있다.

## 추가 확인된 Qt 노출 한계

실제 Windows 테스트에서 다음 두 문제가 추가로 확인됐다.

### localized family 중복 노출

`바탕`/`Batang`, `바탕체`/`BatangChe`처럼 localized family와 English family가
alias 관계에 있거나, 같은 TTC 파일 안의 관련 family가 함께 노출되는 경우가 있다.
이것이 Qt의 `QFontDatabase.families()` 단계에서 이미 별도 family 문자열로
들어오면, 단순 문자열 dedup이나 stable sort만으로는 alias 관계인지 실제로 별개
family인지 알 수 없다.

커스텀 폰트는 파일의 `name` table을 직접 읽어서 English family, localized
family, typographic family, full name, PostScript name을 비교할 수 있으므로 어느
정도 보정 가능하다. 반면 시스템 폰트는 Qt가 반환하는 family/style 정보만으로
실제 물리 폰트 파일이나 동일 font face를 안정적으로 역추적하기 어렵다.

따라서 시스템 폰트에 대해서는 다음 정도를 안전한 목표로 둔다.

- Qt가 `writingSystems()`, `styles()`, `weight()`, `bold()`, `isSmoothlyScalable()`
  등으로 제공하는 정보는 표시와 경고에만 사용한다.
- 시스템 폰트 alias는 자동 추정으로 병합하지 않는다.
- optional alias table이 제공되면 그 테이블에 명시된 group만 병합한다.
- alias table이 없거나 해당 family가 table에 없으면 별도 entry로 유지한다.
- 확신이 없으면 별도 entry로 남기고, tooltip/debug 정보에 `Qt family`와 source를
  표시한다.
- 추후 platform별 backend가 가능해지면 Windows DirectWrite/registry, macOS
  CoreText, Linux fontconfig에서 실제 file 또는 face id를 얻어 강한 dedup을 한다.

즉 `바탕`/`Batang`, `바탕체`/`BatangChe` 같은 이름을 항상 하나로 합치는 것을
1차 PR의 필수 목표로 두지 않는다. 대신 registry 구조가 alias/dedup 정보를 담을 수
있게 만들고, optional data가 있을 때만 system alias를 병합한다. 확실한 custom
font부터 정확도를 높이고, system alias table은 배포판이나 사용자 설정이 제공할 수
있는 보조 데이터로 둔다.

### weight suffix가 family로 접히는 문제

일부 폰트는 `FontName Bold`, `FontName Light`, `FontName Medium`처럼 weight가
family name에 포함된 형태로 설치되어 있거나, name table이 그렇게 작성되어 있다.
하지만 Qt는 이를 하나의 family `FontName`과 여러 style/weight로 정규화해서
반환할 수 있다.

이 동작 자체는 family+weight UI에는 유리할 수 있지만, 다음 경우 문제가 된다.

- 원래 family name 자체가 weight suffix를 포함하는 별도 제품명인 경우
- Qt의 style/weight 값이 실제 face 구분을 충분히 보존하지 못하는 경우
- preview rendering에서 weight 차이가 보이지 않아 UI에서 같은 항목처럼 보이는 경우
- 사용자가 파일 단위 또는 face 단위로 명확히 선택해야 하는 경우

따라서 grouped mode에서도 `FontFace`에는 원본 face 이름을 최대한 보존해야 한다.
커스텀 폰트는 name table의 `full name`, `subfamily`, `typographic subfamily`,
`PostScript name`, 파일명을 face identity 후보로 기록한다. 시스템 폰트는 Qt가
주는 `style_name`과 weight를 우선 쓰되, 확실하지 않으면 separate mode에서
`display_family + style_name` 또는 `display_family + weight label`을 함께 표시한다.

## upstream Qt/font 히스토리 확인

폰트명+weight 방식과 개별 폰트 나열 방식은 단순 UI 취향 문제가 아니라 Qt
업그레이드 후 드러난 호환성 문제다.

확인한 upstream 흐름은 다음과 같다.

- 2024-03-01 `5e5245f`: macOS의 최소 Qt 버전을 6.6.2 이상으로 올렸다.
- 2024-03-05 `9c6bdf1`: Windows의 최소 Qt 버전도 6.6.2 이상으로 올렸다.
- 2024-06-11 `ffa0636`: PyQt 요구사항을 `>=6.6.2,<6.7.0`으로 제한했다.
- 2024-07-03 `91f2ee4`: `QFontComboBox` 입력/선택 동작을 수정했다.
- 2024-07-22 `82d2df2`: Windows headless/offscreen에서 font database가 초기화되지
  않아 글자가 네모로 나오는 문제를 고쳤다. 이때 headless Windows에서 system
  font directory를 `addApplicationFont()`로 직접 등록하는 경로가 추가됐다.
- 2024-08-25 `c7d5207`: normal font weight 문제를 고쳤다.
- 2024-08-30 `5c8344e`, `2debb6d`: Qt5와 Qt6의 font weight 값 체계가 다른
  문제를 변환 함수로 보정했다.

관련 upstream 이슈도 같은 방향을 보여준다.

- #555에서 maintainer는 font가 얇아지는 문제를 "qt6와 qt5 font weight 규격
  불일치"로 설명하고 `2debb6d` 이후 오래된 프로젝트의 weight가 보정된다고
  안내했다.
- #570의 댓글에는 `DirectWrite: CreateFontFaceFromHDC()` 경고가 포함되어
  있지만, maintainer의 대응은 GDI fallback이 아니라 config/global format과
  재현 조건 확인이었다.
- #1042는 custom font가 시스템 설치/`fonts/` 폴더에서 이름 공백, 중복 이름,
  일부 font 미적용을 보이는 open issue다. 이 이슈에는 `Terminal`, `MS Serif`
  DirectWrite 경고도 함께 보고되어 있다.

따라서 upstream 관점에서 확인되는 스탠스는 다음과 같다.

- Qt6/DirectWrite 경로를 유지한다.
- GDI 강제 전환은 upstream 정책으로 확인되지 않는다.
- `font_family`와 `font_weight`의 기존 저장 구조는 유지한다.
- Qt5/Qt6 차이는 runtime 변환으로 보정한다.
- custom font 로딩 문제는 아직 완결된 upstream 설계가 없다.

이 설계의 grouped/separate face 선택은 upstream을 뒤집는 변경이 아니라,
현재 Qt가 노출하는 family/face 차이를 사용자가 선택 가능한 방식으로 안정화하는
제안으로 둔다.

## 설계 원칙

### 0. upstream PR 관점의 제약

BT 소유자 입장에서 이 변경은 다음 조건을 만족해야 한다.

- 기존 project JSON shape를 바꾸지 않는다.
- mandatory dependency를 추가하지 않는다.
- custom-only 스위치의 의미를 바꾸지 않는다.
- 기존 `font_family` 저장값을 즉시 rewriting하지 않는다.
- UI 변경은 작은 단위로 나누어 검토 가능해야 한다.
- 같은 커스텀 폰트나 동일 family가 설치된 경우 macOS, Windows, Linux에서 같은
  project가 최대한 같은 폰트를 resolve해야 한다.

분석에는 `fontTools`를 사용할 수 있지만, PR 구현에서 `fontTools`를 새 필수
의존성으로 추가하는 것은 피한다. 필요하다면 TTF/OTF `name` table에서 family
record만 읽는 작은 내부 parser를 두거나, 해당 기능을 optional helper로 둔다.

문서 공개 범위도 구분한다.

- 한국어 문서는 내부 설계와 fork/branch 맥락을 기록한다.
- 영문 문서는 PR용 설계 문서로 작성한다.
- 영문 문서에는 XPU, 개인 브랜치 이름, 한국어 전용 임시 수정, "외부 노출용"
  같은 메타 설명을 넣지 않는다.

### 0-1. locale-specific 기본 UI 폰트 제거

현재 `shared.DEFAULT_FONT_FAMILY`, `shared.APP_DEFAULT_FONT`, `launch.py`의
`app_font` 초기화에는 `Microsoft YaHei UI`가 명시되어 있다. 이는 중국어
사용자에게는 자연스러울 수 있지만, 한국어 환경에서는 원치 않는 fallback이나
둥근고딕 계열 표시로 이어질 수 있다.

이번 폰트 시스템 정리에서는 앱 UI 기본 폰트와 새 텍스트 스타일 기본 폰트도
locale-aware하게 정리한다.

후보 fallback 순서는 다음과 같다.

1. 기존 user config에 저장된 기본 폰트
2. 현재 UI locale에 맞는 platform UI font
3. Qt application default font
4. 기존 hard-coded fallback

단, 기존 project JSON이나 기존 text style 파일의 `font_family`를 자동으로
rewrite하지 않는다. 이 변경은 새 config 생성 또는 런타임 application font
선택에만 적용하는 것이 안전하다.

### 0-2. OS별 시스템 폰트 자동 매핑은 하지 않는다

Windows의 `Malgun Gothic`을 macOS의 `Apple SD Gothic Neo`로 바꾸는 식의
시스템 폰트 자동 매핑 테이블은 두지 않는다. 시스템 폰트는 OS별 로컬 자원이고,
이름이 비슷하더라도 metrics, glyph coverage, weight 매핑이 다를 수 있다.

크로스 플랫폼 프로젝트 호환성이 필요하면 `fonts/` 폴더에 커스텀 폰트를 넣고
custom-only 스위치를 사용하는 것이 명시적인 해법이다. resolver는 저장된 시스템
폰트가 현재 OS에 없을 때 다른 OS의 시스템 폰트로 조용히 대체하지 않는다. 대신
기존 `font_family`를 Qt fallback으로 넘기거나, 이후 UI에서 missing/resolved
상태를 표시하는 방향이 안전하다.

### 1. 내부 저장명은 canonical family를 우선한다

프로그램 내부와 프로젝트 JSON에서 유통되는 `font_family`는 가능한 한
canonical family name이어야 한다. canonical family는 OS가 달라도 가장 안정적인
이름을 뜻한다.

우선순위는 다음과 같다.

1. English typographic family
2. English family
3. Qt가 반환한 family 중 ASCII family
4. localized typographic family
5. localized family
6. Qt가 실제 렌더링 가능한 family

영문명이 없는 폰트는 localized family를 canonical family로 사용한다. 중요한
제약은 canonical family가 Qt 렌더링에 직접 사용 가능하거나, runtime registry가
Qt 렌더링 가능한 family로 resolve할 수 있어야 한다는 점이다.

### 2. UI 표시명은 display family를 사용한다

UI에는 가능하면 로컬라이즈된 이름을 표시한다.

우선순위는 다음과 같다.

1. 현재 UI locale과 일치하는 typographic family
2. 현재 UI locale과 일치하는 family
3. Korean typographic family 또는 Korean family
4. English typographic family 또는 English family
5. canonical family
6. Qt family

다만 저장되는 값은 display family가 아니라 canonical family이다.

### 3. custom-only 스위치를 그대로 존중한다

폰트 목록 source는 설정에 따라 분리한다.

- `Show only custom fonts = true`: custom font registry만 표시한다.
- `Show only custom fonts = false`: system font registry와 custom font
  registry를 함께 표시한다.

통합 목록을 만들 때도 source 우선순위는 유지한다.

```text
custom > system
```

같은 canonical family가 system과 custom에 모두 있으면 custom entry를 우선한다.
사용자가 `fonts/`에 직접 넣은 폰트는 명시적인 사용자 의도로 본다.

### 4. weight 통합은 폰트가 명시적으로 같은 family일 때만 한다

weight 선택 방식은 두 모드를 둔다.

```text
Font weight selection mode:
- Group weights by family
- Show font faces separately
```

기본값은 `Group weights by family`로 한다.

하지만 무리한 병합은 하지 않는다. 다음 조건 중 하나가 성립할 때만 여러 파일을
하나의 family로 묶는다.

- 폰트 파일들의 typographic family가 같다.
- Qt가 같은 family로 반환한다.
- name table의 family가 같고 subfamily만 다르다.

다음과 같은 경우는 별도 family로 둔다.

- `Korail Round Gothic Bold`, `Korail Round Gothic Light`,
  `Korail Round Gothic Medium`처럼 폰트 자체가 weight별 family name을
  명시하는 경우
- typographic family 자체가 weight별 이름인 경우
- 자동 추론만으로 같은 family라고 판단해야 하는 경우

즉 파일명 패턴만 보고 `Bold`, `Light`, `Medium`을 제거해 합치지 않는다.

예외적으로 optional custom group table이 제공되면, 테이블에 명시된 face만 하나의
picker family로 표시할 수 있다. 이 경우에도 각 face의 원래 canonical family는
잃지 않는다. 예를 들어 `Korail Round Gothic Bold` face는 grouped picker 안에서
`Korail Round Gothic` family의 Bold weight로 보일 수 있지만, 렌더링과 저장에
필요한 face canonical 후보로는 `Korail Round Gothic Bold`를 유지한다.

이 테이블은 폰트 metadata를 자동 추론해서 고치는 장치가 아니라, 사용자가 알고 있는
폰트 패밀리 관계를 명시적으로 제공하는 optional data이다. 테이블이 없으면 기존처럼
분리 표시한다.

### 5. fallback은 명시적으로 기록한다

폰트 name table은 폰트마다 품질이 다르다. 따라서 fallback 정책은 코드와 문서에
명시되어야 한다.

fallback 예시는 다음과 같다.

- English name이 있으면 canonical family로 사용한다.
- English name이 없으면 localized name을 canonical family로 사용한다.
- Qt가 깨진 이름을 반환하면 name table에서 display name을 복구하되, Qt 렌더링
  key는 별도 보관한다.
- name table이 불완전하면 Qt family를 canonical/display fallback으로 사용한다.
- 모든 이름이 비어 있으면 파일 stem을 display fallback으로 쓰되, 저장명으로는
  사용하지 않는다.

### 6. 구현 중 추가 확인된 보정

초기 설계 이후 실제 Paperlogy와 일부 한글 custom font를 다시 검증하면서 다음 보정이
추가로 필요하다는 점이 확인됐다. 이 항목들은 PR 설명에도 포함한다.

#### OS/2 `usWeightClass` 우선 사용

custom font weight는 Qt가 반환한 style weight나 style name 추정보다 폰트 파일의
OS/2 table `usWeightClass`를 우선한다. Paperlogy처럼 style name과 실제 OpenType
weight가 명확한 폰트에서 Qt backend가 weight를 뭉뚱그리거나 오래된 Qt5식 weight로
보여 줄 수 있으므로, custom font에 대해서는 파일 내부의 선언값을 source of truth로
삼는다.

단, 일부 vendor는 구형 Windows GDI 렌더링 문제를 피하기 위해 Thin/ExtraLight 계열을
표준 `100`/`200` 대신 `250`으로 저장한다. 이런 경우 같은 family 안에서 `250` face가
여러 개 생겨 weight picker에서 하나만 도달 가능해질 수 있다. 따라서 동일
`usWeightClass`가 중복되고 style name만으로 `Thin`, `ExtraLight`, `Light` 등을
명확히 구분할 수 있으면, UI/registry weight는 style name 기반의 표준값으로
분리한다. 원래 폰트 파일 값이 잘못됐다고 보는 것이 아니라, 사용자 선택 가능성을
보존하기 위한 runtime 보정이다.

#### 손상된 Qt family 후보 제외

Windows/Qt 조합에서는 한글 family가 `??? ???` 또는 공백과 `?`만 있는 문자열로
반환되는 경우가 있다. 이런 값은 렌더링 family 후보나 alias key로 사용하지 않는다.
name table에서 canonical/display family를 읽을 수 있으면 그 값을 우선하고, Qt가
반환한 정상 family만 alias에 포함한다.

#### face-level key 충돌 방지

같은 picker family 안의 여러 face가 family alias를 공유할 수 있다. 이 alias를 그대로
face resolve key로 등록하면 `Paperlogy`처럼 family 이름으로 resolve할 때 특정 face가
우연히 고정되어, weight `800` 요청이 `900` face로 가는 식의 문제가 생긴다.

따라서 registry index는 entry-level key와 face-level key를 분리한다. canonical,
display, Qt family처럼 family 전체를 가리키는 key는 entry resolve에만 사용하고,
face resolve에는 같은 entry 안에서 유일하며 entry key가 아닌 key만 등록한다. 실제
face 선택은 요청 weight와 `FontEntry.face_for_weight()`로 결정한다.

## 제안 자료구조

런타임 전용 `FontRegistry`를 둔다.

```python
@dataclass
class FontFace:
    qt_family: str
    style_name: str
    weight: int
    file_path: str | None
    full_name: str | None
    postscript_name: str | None
    original_family: str | None
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

역할은 다음과 같다.

- `canonical_family`: 프로젝트 저장과 내부 유통에 쓰는 이름
- `display_family`: UI 표시용 이름
- `qt_family`: `QFont`, `QTextCharFormat`에 넘기는 실제 Qt family
- `source`: custom/system 구분
- `file_paths`: custom font일 때 원본 파일 경로
- `weights`: 사용 가능한 weight 목록
- `styles`: Qt style 목록
- `faces`: grouped mode에서도 face별 `style_name`과 실제 Qt family를 잃지 않기
  위한 정보
- `full_name`/`postscript_name`/`original_family`: `FontFace`가 Qt 반환값 밖의
  face identity를 추적하기 위한 보조 정보. Qt가 weight suffix를 접어 버린 경우
  특히 중요하다.
- `aliases`: old project, localized name, English name, Qt family 등 resolve 후보
- `alias_source`: alias가 custom font name table에서 온 것인지, optional alias
  table에서 온 것인지, 아니면 병합되지 않은 항목인지 표시하는 런타임/debug용 값

## resolve 정책

기존 project JSON 호환성을 위해 `font_family` 값을 바로 바꾸지 않는다.
대신 런타임에서 다음 순서로 resolve한다.

1. canonical family exact match
2. alias exact match
3. Qt family exact match
4. display family exact match
5. case-insensitive match
6. 실패 시 기존 `font_family`를 그대로 Qt에 넘김

resolve에 성공하면 렌더링은 `qt_family`로 수행한다. 저장은 기존
`font_family`를 유지하거나, 사용자가 새로 폰트를 선택했을 때만
`canonical_family`로 갱신한다.

## UI 정책

### 폰트 콤보박스

콤보박스는 단순 문자열 목록이 아니라 entry model을 사용한다.

- 표시 텍스트: `display_family`
- 실제 선택 값: `canonical_family`
- tooltip 또는 보조 텍스트: source, qt family, file name, available weights

정렬은 안정적이어야 한다.

- custom-only 목록도 stable sort한다.
- system 목록도 stable sort한다.
- locale-aware sort는 별도 검토하되, 최소한 `casefold` 기반 정렬을 적용한다.

### family 중복과 alias 표시

동일 폰트로 보이는 localized/English family가 동시에 들어온 경우에는 다음 순서로
처리한다.

1. custom font에서 name table 기준으로 같은 face임이 확인되면 하나의 entry로
   병합하고, 나머지 이름은 `aliases`에 넣는다.
2. system font는 optional alias table에 명시된 group만 병합한다.
3. alias table이 없거나 table에 없는 family는 병합하지 않는다.
4. 병합하지 않은 항목은 UI tooltip에 Qt family와 source를 보여주어 사용자가
   원인을 추적할 수 있게 한다.

`바탕`/`Batang`, `바탕체`/`BatangChe` 같은 케이스는 OS와 Qt backend에 따라
다르게 보일 수 있으므로, 1차 구현에서는 optional data가 제공될 때만 병합한다.
한국어 Windows alias table은 검증용 또는 사용자 설정용 데이터로 둘 수 있지만,
테이블이 없으면 두 family를 별도 항목으로 유지한다.

### face 표시명

separate mode에서는 family만 표시하지 말고 face identity가 드러나도록 표시한다.

예시는 다음과 같다.

```text
FontName
FontName — Light
FontName — Medium
FontName — Bold
Batang / 바탕
```

표시 suffix의 우선순위는 다음과 같다.

1. name table의 typographic subfamily 또는 subfamily
2. Qt `style_name`
3. numeric weight를 사람이 읽을 수 있는 label로 변환한 값
4. 파일 stem 또는 full name에서 얻은 face suffix

단, grouped mode의 family combobox에서는 suffix를 숨기고 weight combobox에서만
표시한다.

### system/custom 충돌

같은 canonical family가 system과 custom에 모두 있으면 custom을 표시한다.

custom entry에 localized display name이 있으면 그 이름을 표시한다. 예를 들어
macOS system font가 영문 family를 반환하고, 같은 canonical family의 custom
font가 한국어 display name을 가진다면 custom display name을 우선한다.

### Windows legacy raster font

기본 폰트 콤보박스에서는 DirectWrite 경고를 반복시키는 Windows legacy
bitmap/raster font를 우선 제외한다.

초기 정책은 명시적 blacklist가 안전하다.

```text
Fixedsys
MS Sans Serif
MS Serif
Terminal
System
Small Fonts
```

`QFontComboBox.FontFilter.ScalableFonts`나
`QFontDatabase.isSmoothlyScalable(family)` 기반의 광범위한 필터는 이후 단계에서
검토한다. 일부 오래된 CJK 폰트나 특수 폰트가 의도치 않게 사라질 수 있으므로,
첫 PR에서는 경고가 확인된 legacy raster family만 숨기는 편이 안전하다.

## weight UI 정책

### fontsys 브랜치의 UI prototype 참고

`fontsys` 브랜치에는 weight 선택 UI를 이미 한 번 구현한 흔적이 있다. 최종 구현은
현재 `dev` 구조와 새 registry 설계에 맞춰 다시 작성해야 하지만, 레이아웃 구조와
상호작용 방향은 참고할 만하다.

확인한 주요 변경은 다음과 같다.

- `FontWeightComboBox`를 추가해 family별 사용 가능한 weight를 숫자 combobox로
  표시했다.
- text panel 첫 줄을 `font family`, `font size`, `font weight` 순서로 배치했다.
- 기존 첫 줄에 있던 line spacing control은 stroke/letter spacing이 있는 아래 줄로
  이동했다.
- `B` 버튼은 별도 `bold` boolean 토글이 아니라 `font_weight` shortcut으로
  동작했다. 켜면 700 계열, 끄면 400 계열로 보내고, 실제 bold weight가 따로 있으면
  `QFontDatabase.bold()`/`weight()`로 가능한 값을 찾았다.
- family가 바뀌면 weight combobox를 다시 채우고 기존 weight에 가장 가까운 항목을
  선택했다.
- 여러 text block을 선택했을 때 공통값은 표시하고, 값이 섞인 항목은 비워 두는
  multi-select UI 갱신도 실험했다.

이 prototype의 위젯 코드를 그대로 가져오지는 않는다. 기존 구현은 숫자 weight와
`QFontDatabase.styles()`에 직접 의존하므로, 새 구현에서는 registry의 `FontFace`
목록과 grouped/separate mode를 기준으로 weight 후보를 만들어야 한다. 다만
`family + size + weight`를 한 줄에 둔 레이아웃과, `B` 버튼을 weight shortcut으로
취급하는 상호작용은 유지할 가치가 있다.

### Group weights by family

family combobox에는 family만 표시한다. 별도 weight combobox에는 사용 가능한
weight를 표시한다.

렌더링 시에는 단순히 family와 weight만 넘기지 않고 가능한 face 정보를 함께
사용한다. 우선순위는 다음과 같다.

1. 선택된 weight에 대응하는 `FontFace.style_name`이 있으면 `QFont.setStyleName()`
   또는 동등한 Qt API로 style을 지정한다.
2. style name을 사용할 수 없으면 `qt_family`와 `font_weight`를 함께 지정한다.
3. 둘 다 실패하면 기존처럼 `qt_family`만 Qt fallback으로 넘긴다.

이 정보는 `Medium`, `SemiBold`처럼 Qt weight enum만으로 구분이 흔들릴 수 있는
face를 grouped mode에서도 안정적으로 고르기 위해 필요하다.

이 모드는 다음 family에 적합하다.

- `Noto Sans KR`
- `Paperlogy`
- `KoPubWorldBatang`
- `KoPubWorldDotum`
- `NanumGothic`
- `NanumMyeongjo`

### Show font faces separately

폰트 파일 또는 Qt family가 분리되어 있으면 각각 표시한다. 이 모드는 다음
경우에 필요하다.

- 폰트 자체가 weight별 family명을 갖는 경우
- 사용자가 파일 단위/face 단위 선택을 원할 경우
- 자동 grouping이 오히려 오해를 만들 수 있는 경우

예시는 다음과 같다.

- `Korail Round Gothic Bold`
- `Korail Round Gothic Light`
- `Korail Round Gothic Medium`

단, optional custom group table이 이 세 face를 같은 picker family로 묶도록
명시하면 grouped mode에서도 함께 표시할 수 있다. 이때 separate mode와 project
저장 호환성을 위해 원래 face canonical은 계속 보존한다.

## 저장 정책

현재 project JSON shape를 바로 바꾸지 않는다.

- 기존 `font_family` 필드를 유지한다.
- 새로 선택한 폰트는 `canonical_family`를 `font_family`에 저장한다.
- `font_weight`는 기존 `FontFormat.font_weight`를 사용한다.
- display name은 저장하지 않는다.
- optional custom group table로 만든 pseudo family는 그대로 저장하지 않는다.
  선택된 weight가 가리키는 실제 face canonical 또는 기존에 Qt가 렌더링 가능한
  canonical을 저장한다.

필요하면 나중에 backward-compatible field를 추가한다.

```json
{
  "font_family": "Noto Sans KR",
  "font_weight": 700,
  "font_source": "custom"
}
```

다만 `font_source` 같은 필드는 migration/default 정책이 준비된 뒤에만 추가한다.

## 구현 단계

### 1단계: 최소 안정화

- custom-only 스위치 동작 유지
- custom font family 중복 제거
- system font list stable sort
- Windows legacy raster font blacklist 적용
- project JSON shape 변경 없음

이 단계는 PR을 가장 작게 만들 수 있다. UI 표시명과 weight UI를 아직 바꾸지
않아도 Windows DirectWrite 경고와 중복 표시 문제를 줄일 수 있다.

### 2단계: registry 도입

- runtime-only `FontRegistry` 추가
- 기존 `shared.CUSTOM_FONTS`, `shared.FONT_FAMILIES`와 호환되는 adapter 제공
- 저장값 변경 없이 resolve layer만 추가

### 3단계: display/canonical 분리

- custom font name table parsing
- `.ttc` collection은 헤더와 각 font offset을 처리한다.
- display family와 canonical family 분리
- combobox가 display text와 internal value를 분리하도록 변경
- mandatory dependency 추가 없음

### 4단계: weight UI

- weight selection mode 설정 추가
- grouped mode에서 family + weight 선택
- separate mode에서 face 단위 표시
- Bold button과 `font_weight` 동기화

### 5단계: 호환성 검증

- 기존 project JSON 로드
- 기존 `font_family` 값 resolve
- rich text의 `font-family` 처리
- Windows/macOS/Linux에서 family name 차이 확인
- Windows에서 `바탕`/`Batang`, `바탕체`/`BatangChe`처럼 localized/English alias
  또는 TTC 관련 family가 중복처럼 노출되는지 확인하고, 병합 여부와 alias 기록을
  검증
- `폰트명 Bold`, `폰트명 Light`처럼 weight suffix가 family에 포함된 폰트가
  grouped mode와 separate mode에서 각각 구분 가능한지 검증
- preview weight가 동일하게 보이는 폰트에서도 separate mode의 표시 텍스트나
  tooltip만으로 face를 구분할 수 있는지 확인

## 이번 통합 범위에서 제외할 것

- XPU text detector 수정
- module manager/lazy loading 동작 변경
- project JSON shape 변경
- custom-only 스위치 자동 활성화
- font stretch/장평 기능

font stretch/장평은 과거 실험에서 Qt 렌더링 버그로 중단된 기능이다. 특정
font size 이상에서 장평이 100%로 되돌아가고 letter spacing만 벌어지는 현상이
있었다. 이 문제는 font registry나 weight picker 안정화와 별개이며, 이번 PR에
묶으면 review 범위와 리스크가 커진다.

장평을 다시 검토하려면 `QFont.setStretch()`/`QTextCharFormat.setFontStretch()`
경로가 실제 렌더링에서 안정적인지 먼저 재현 테스트를 만들고, Qt rich text
renderer 대신 glyph/path 또는 painter transform을 쓰는 우회가 필요한지 별도
설계해야 한다.

## PR 목표

PR 가능한 목표는 다음과 같다.

- 기존 동작을 보존한다.
- custom-only 스위치를 명확히 존중한다.
- system/custom 폰트 목록이 안정적으로 정렬된다.
- Windows legacy raster font로 인한 DirectWrite 경고를 줄인다.
- custom font 중복 표시를 제거한다.
- OS별 localized family 차이를 다룰 수 있는 구조를 만든다.
- Windows에서 localized/English alias나 TTC 관련 family가 중복처럼 노출되는 경우를
  alias/dedup 후보로 추적할 수 있는 구조를 만든다.
- Qt가 weight suffix를 family에서 제거하더라도 face identity를 잃지 않는다.
- weight UI는 선택 가능한 모드로 제공한다.
