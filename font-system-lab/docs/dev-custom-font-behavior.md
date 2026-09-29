# dev 커스텀 폰트 동작 분석

## 목적

이 문서는 현재 `dev` 기준으로 `fonts/` 폴더에 커스텀 TTF/OTF 폰트가 있을 때
앱이 어떻게 동작하는지 정리한다. `fontsys` 통합 전에 현재 upstream 동작을
source of truth로 삼기 위한 문서이다.

분석 기준 브랜치는 다음과 같다.

- `codex/integrate-peperu-fontsys`
- 기준 커밋: `391c8eb`

## 관련 파일

- `ballontranslator/launch.py`
- `ballontranslator/utils/shared.py`
- `ballontranslator/utils/config.py`
- `ballontranslator/ui/mainwindow.py`
- `ballontranslator/ui/text_panel.py`
- `ballontranslator/ui/configpanel.py`

## 시작 시 폰트 로딩 흐름

`ballontranslator/launch.py`는 앱 시작 시 다음 경로를 커스텀 폰트 폴더로 본다.

```text
PATH_FONTS = Path(shared.PROGRAM_PATH) / 'fonts'
```

`fonts/`가 있으면 `find_all_files_recursive(PATH_FONTS, FONT_EXTS)`로 다음
확장자를 찾는다.

```text
.ttf, .otf, .ttc, .pfb
```

각 파일은 `QFontDatabase.addApplicationFont(fp)`로 Qt application font에
등록된다. 등록에 성공하면 다음 값을 `shared.CUSTOM_FONTS`에 추가한다.

```python
QFontDatabase.applicationFontFamilies(fnt_idx)[0]
```

즉, 현재 구현은 폰트 파일 하나당 Qt가 돌려준 family list의 첫 번째 family만
저장한다.

## 전체 폰트 목록 구성

커스텀 폰트를 등록한 뒤 `shared.FONT_FAMILIES`를 Qt font database 전체
family 목록으로 채운다.

Qt6 경로:

```python
shared.FONT_FAMILIES = set(f for f in QFontDatabase.families())
```

Qt5 경로:

```python
fdb = QFontDatabase()
shared.FONT_FAMILIES = set(fdb.families())
```

커스텀 폰트는 이미 Qt application font로 등록되어 있으므로, 일반 GUI
환경에서는 `shared.FONT_FAMILIES`에도 포함된다. 따라서 "Show only custom
fonts" 설정이 꺼져 있으면 전체 시스템 폰트 목록 안에 커스텀 폰트가 섞여
들어간다.

현재 로컬 설정 파일에서는 다음 값이 켜져 있었다.

```json
"let_show_only_custom_fonts_flag": true
```

따라서 실제 실행 UI가 시스템 폰트를 무시하고 커스텀 폰트만 보여주는 것은
현재 설정값에 따른 정상 경로이다.

주의할 점은 headless/offscreen 검사와 일반 GUI 검사의 결과가 다르다는
점이다. `QT_QPA_PLATFORM=offscreen`으로 검사하면 시스템 폰트가 초기화되지
않아 application font만 보일 수 있다. 일반 Windows GUI 경로에서는 시스템
family가 함께 보인다.

## 커스텀 폰트만 보기 설정

설정 값은 `ProgramConfig.let_show_only_custom_fonts_flag`이다. 기본값은
`False`이다.

설정 패널에는 "Show only custom fonts" 체크박스가 있으며, 변경 시 다음
흐름이 실행된다.

```text
ConfigPanel.on_show_only_custom_fonts
  -> pcfg.let_show_only_custom_fonts_flag 갱신
  -> ConfigPanel.show_only_custom_font emit
  -> MainWindow.on_show_only_custom_font
  -> FontFamilyComboBox.update_font_list
```

`MainWindow.on_show_only_custom_font`의 목록 선택은 다음과 같다.

- `True`: `shared.CUSTOM_FONTS`
- `False`: `shared.FONT_FAMILIES`

앱 시작 시 설정이 이미 켜져 있으면 `setupConfig()`에서
`on_show_only_custom_font(True)`를 한 번 호출한다.

## 현재 true 값의 유력한 생성 경로

현재 `dev`와 `peperu`에는 `let_show_only_custom_fonts_flag`를 자동으로
`True`로 바꾸는 코드가 없다. 값을 바꾸는 현재 코드 경로는 설정 패널의
체크박스뿐이다.

```text
ConfigPanel.on_show_only_custom_fonts
  -> pcfg.let_show_only_custom_fonts_flag = checkbox state
```

반면 `fontsys` 브랜치의 `ballontranslator/launch.py`에는 다음 자동 설정
코드가 있었다.

```python
if shared.CUSTOM_FONTS and not config.let_show_only_custom_fonts_flag:
    config.let_show_only_custom_fonts_flag = True
```

즉 `fontsys` 상태에서 앱을 실행했고 `fonts/` 폴더에 커스텀 폰트가 하나라도
있었다면, 사용자가 설정 패널을 직접 만지지 않아도 런타임 config 값이
`True`가 될 수 있다. 이후 앱 종료나 설정 저장 경로에서 `config/config.json`
에 값이 저장되면 브랜치를 `dev`로 바꿔도 이 ignored local config가 계속
남는다.

현재 로컬 `config/config.json`은 git에 추적되지 않고 `.gitignore`에 의해
무시된다. 따라서 이 값은 저장소 기본값이 아니라 로컬 실행 상태에서 생긴
개인 설정이다.

## FontFamilyComboBox 동작

`FontFamilyComboBox.update_font_list(font_list)`는 다음 순서로 동작한다.

1. `currentFontChanged` 연결을 잠시 끊는다.
2. 현재 font family를 저장한다.
3. 콤보박스를 비운다.
4. 전달받은 `font_list`를 모두 추가한다.
5. 현재 font family를 한 번 더 추가한다.
6. `setCurrentText(current_font)`를 호출한다.
7. `currentFontChanged` 연결을 다시 붙인다.

주의할 점은 다음과 같다.

- 전달받은 `font_list`에 중복이 있어도 제거하지 않는다.
- `shared.FONT_FAMILIES`는 `set`이므로 전체 시스템 폰트 모드에서는 표시 순서가
  안정적이지 않다.
- 현재 font family를 무조건 한 번 더 추가하므로 목록에 이미 있으면 또
  중복될 수 있다.
- `apply_fontfamily()`는 `currentFont().family()`가 `shared.FONT_FAMILIES`에
  있을 때만 `font_family` 변경 신호를 낸다.
- 현재 `dev`에는 line edit의 `editingFinished`에서 `apply_fontfamily()`를
  호출하는 연결이 없다. 이 연결은 `peperu` 변경에 있다.

`QFontComboBox`의 기본 font filter는 `0`이며, 현재 구현은 별도 filter를
설정하지 않는다. 따라서 Windows의 오래된 bitmap/raster font도 목록에 들어갈
수 있다.

실제 Windows GUI 경로에서 다음 family들은 non-scalable로 확인되었다.

```text
Fixedsys: smooth=False, point sizes=[8, 10]
MS Sans Serif: smooth=False, point sizes=[7, 8, 10, 12, 13, 15, 18, 19, 23]
Terminal: smooth=False, point sizes=[3, 4, 6, 7, 8, 9, 10, 11, 14]
System: smooth=False, point sizes=[8, 10]
Small Fonts: smooth=False, point sizes=[2, 3, 4, 5, 6, 7]
```

이 폰트들은 Qt6 DirectWrite 경로에서 combobox preview나 font probing 중
다음 로그를 반복해서 낼 수 있다.

```text
qt.qpa.fonts: DirectWrite: CreateFontFaceFromHDC() failed ...
```

`QFontComboBox.FontFilter.ScalableFonts`를 적용하면 이 레거시 폰트들은
목록에서 제외된다.

## 현재 fonts 폴더 실측 결과

현재 작업 폴더의 `fonts/`에는 다중 weight 폰트가 많다. Qt offscreen
환경에서 커스텀 폰트 등록 결과를 확인한 결과, 파일 수는 54개이고 unique
family는 25개였다.

현재 `dev` 방식으로 만들어지는 `shared.CUSTOM_FONTS`는 파일 단위 목록이므로
중복이 많다. 대표 예시는 다음과 같다.

- `Noto Sans KR`: 9회
- `Paperlogy`: 9회
- `KoPubWorldBatang`: 3회
- `KoPubWorldDotum`: 3회
- `NanumGothic`: 4회
- `NanumMyeongjo`: 3회
- `Maplestory`: 2회
- `Yde street`: 2회
- `HSBomBaram 3.0`: 2회
- `HSBomBaram 3.0 Vertical`: 2회

따라서 "Show only custom fonts"를 켜면 family 목록이 파일 수 기준으로
반복될 수 있다.

## Qt가 본 주요 family/style/weight

현재 환경에서 Qt가 본 주요 family와 style/weight는 다음과 같다. 이 결과는
Qt binding과 OS font backend에 따라 달라질 수 있다.

```text
KoPubWorldBatang: Bold=75, Light=25, Medium=57
KoPubWorldDotum: Bold=75, Light=25, Medium=57
Maplestory: Bold=75, Light=25
NanumGothic: Regular=50, Bold=63, ExtraBold=75, Light=25
NanumMyeongjo: Regular=50, Bold=63, ExtraBold=75
Noto Sans KR: Black=87, Bold=75, ExtraBold=81, ExtraLight=25, Light=25, Medium=57, Regular=50, SemiBold=63, Thin=25
Paperlogy: 1 Thin=25, 2 ExtraLight=25, 3 Light=25, 4 Regular=50, 5 Medium=57, 6 SemiBold=63, 7 Bold=75, 8 ExtraBold=81, 9 Black=87
Yde street: B=75, L=25
```

현재 실행 환경에서는 일부 한글 family name이 깨져 보이는 경우도 있었다.

```text
HSBombaram2.1.ttf -> HS???? 2.1
온글잎 윤우체.ttf -> ??? ???
```

이는 레스터 폰트가 아니라 실제 TTF 폰트의 name table을 Qt/Windows font
backend가 해석한 결과이다. `fontTools`로 확인한 내부 name table은 다음과
같다.

```text
온글잎 윤우체.ttf
  family lang 1033: Ownglyph YoonwooChae
  family lang 1042: 온글잎 윤우체
  typographic family lang 1042: 온글잎 윤우체

HSBombaram2.1.ttf
  family lang 1033: HS봄바람체 2.1
  family lang 1042: HS봄바람체 2.1
  full lang 1033: HSBombaram 2.1
  typographic family lang 1033/1042: HS봄바람체 2.1
```

즉 폰트 파일 내부에는 한국어 이름이 존재한다. 하지만 `QFontDatabase`가
반환한 family는 각각 `??? ???`, `HS???? 2.1`이었다. `fontsys`의 "family
list 중 선호 family name 선택" 로직은 이 문제를 완전히 해결하지 못할 수
있다. Qt가 이미 깨진 문자열을 반환하면 application font family만으로는
복원할 수 없기 때문이다.

반대로 `Paperlogy`처럼 내부 family name은 weight별 이름이지만 typographic
family가 대표 family로 들어 있는 경우에는 Qt가 대표 family를 반환했다.

```text
Paperlogy-4Regular.ttf
  family: Paperlogy 4 Regular
  typographic family: Paperlogy
  typographic subfamily: 4 Regular
  QFontDatabase family: Paperlogy
```

그러나 `Korail Round Gothic`처럼 내부 typographic family 자체가
weight별 이름인 경우에는 Qt도 weight별 family로 분리한다.

```text
Korail_Round_Gothic_Bold.ttf
  typographic family: Korail Round Gothic Bold
  typographic subfamily: B
  QFontDatabase family: Korail Round Gothic Bold
```

## 현재 dev 동작의 의미

현재 `dev`는 다음 정책을 가진다.

- 커스텀 폰트를 별도 등록한다.
- 등록된 커스텀 폰트는 전체 Qt font family 목록에도 포함된다.
- `shared.CUSTOM_FONTS`는 "커스텀 폰트만 보기" UI 필터용 목록이다.
- `shared.CUSTOM_FONTS`는 set이 아니라 list이며 중복 제거를 하지 않는다.
- 같은 family의 여러 weight 파일은 같은 family 이름으로 여러 번 들어간다.
- 폰트 내부 name table이 weight별 family로 구성된 경우, Qt도 weight별로
  다른 family로 취급한다.
- weight 선택 UI는 없고, Bold button이 `font_weight` 변경 경로를 간접 사용한다.

## 통합 시 우선 확인할 문제

### 1. CUSTOM_FONTS 중복 제거

다중 weight 파일을 정상 지원하려면 family 표시 목록은 파일 수가 아니라
unique family 기준이어야 한다.

현재 `dev`의 `shared.CUSTOM_FONTS`는 다음 문제가 있다.

- 같은 family가 여러 번 표시된다.
- 파일 정렬 순서에 따라 표시 순서가 결정된다.
- family별 style/weight 정보는 별도로 보존하지 않는다.

전체 시스템 폰트 목록도 `set`을 그대로 UI에 넣지 말고 정렬된 list로 넘겨야
한다.

```text
sorted(shared.FONT_FAMILIES, key=str.casefold)
```

한국어/영어 혼합 정렬을 더 좋게 만들려면 locale-aware sort를 별도로 검토할
수 있다.

### 2. family name 선택 정책

`applicationFontFamilies(fnt_idx)[0]`만 쓰는 정책은 단순하지만, name table에
여러 family 이름이 들어 있는 폰트에서 잘못된 표시명을 고를 수 있다. 더
중요하게는, Qt가 이미 깨진 이름을 반환하는 경우 application font family
목록만으로는 한국어 이름을 되살릴 수 없다.

통합 시 후보 정책은 다음과 같다.

- Qt가 반환한 family를 모두 수집한다.
- 빈 문자열을 제거한다.
- `??? ???`처럼 Qt/Windows backend에서 손상된 로컬 family로 보이는 값은
  렌더링 family 후보에서 제외한다.
- 중복을 제거한다.
- name table의 English canonical family가 Qt 반환 family 중에 있거나, Qt
  반환값이 모두 비어 있거나 손상되어 있으면 canonical family를 렌더링 family로
  우선 사용한다.
- 필요하면 ASCII 우선, 짧은 이름 우선 같은 휴리스틱을 적용한다.
- 한국어 표시명을 원하면 `fontTools`로 name table의 Korean record
  (`langID=1042`)를 읽어 UI display name으로 따로 보관한다.

다만 이 정책은 폰트별 표시명 변경으로 이어질 수 있으므로 기존 project의
`font_family` 값과 호환성을 확인해야 한다.

중요한 제약은 Qt 렌더링에 넘기는 family key와 UI에 보여주는 display name을
분리해야 한다는 점이다. `font_family` 저장값은 기존 project와 프리셋 호환을
위해 canonical family를 유지한다. 렌더링은 resolver가 canonical/display/alias를
받아 최종 family를 결정한다. 한국어 표시명은 별도 label/display role로만 쓰는
편이 안전하다.

### 3. custom-only view와 global font database의 관계

커스텀 폰트는 이미 `shared.FONT_FAMILIES`에도 포함된다. 따라서
"Show only custom fonts"는 렌더링 가능 여부가 아니라 combobox filter이다.
이 설정을 자동으로 켜면 사용자 UI preference를 바꾸는 동작이 된다.

### 4. weight UI 추가 여부

현재 Qt는 family별 style/weight를 읽을 수 있다. 그러나 현재 `dev` UI는
weight를 직접 고르는 control이 없다. `fontsys`에서 살릴 수 있는 핵심은
이 부분이다.

추가한다면 다음 조건이 필요하다.

- 표시 목록은 unique custom family 기준이어야 한다.
- weight 값은 `fix_fontweight_qt`와 Qt5/Qt6 차이를 고려해야 한다.
- Bold button과 `font_weight`의 관계를 backward-compatible하게 유지해야 한다.

### 5. non-scalable system font 필터링

전체 시스템 폰트 모드에서 `Fixedsys`, `MS Sans Serif`, `Terminal`, `System`,
`Small Fonts` 같은 레거시 bitmap font가 들어오면 Qt6 DirectWrite 경고가
반복된다. 텍스트 렌더링 도구로서 실사용 가치도 낮으므로, font combobox에는
scalable font만 표시하는 정책을 우선 검토한다.

후보는 다음 둘이다.

- `QFontComboBox.setFontFilters(QFontComboBox.FontFilter.ScalableFonts)`
- 목록 생성 시 `QFontDatabase.isSmoothlyScalable(family)`가 참인 family만
  유지

전자는 Qt widget의 기본 동작을 활용하는 방식이고, 후자는 custom-only 목록과
system 목록에 같은 필터 정책을 적용하기 쉽다.

## 결론

현재 `dev`는 `fonts/` 폴더의 커스텀 폰트를 로드하고 렌더링 후보로 만든다.
현재 로컬 설정처럼 `let_show_only_custom_fonts_flag`가 켜져 있으면
combobox는 커스텀 폰트만 보여준다. custom-only font list는 파일 단위 family
append 방식이라 다중 weight 폰트가 중복 표시된다. 폰트 내부 name table에
따라서는 weight별 파일이 서로 다른 family 이름으로 보일 수도 있다.

따라서 통합 작업의 첫 번째 후보는 큰 폰트 시스템 변경이 아니라 다음과 같은
작은 정리이다.

- `shared.CUSTOM_FONTS`를 unique family 목록으로 만들기
- custom font family 선택 정책을 명시하기
- custom-only view는 사용자 설정으로만 유지하기
- system font 목록을 stable sort하기
- non-scalable raster/system font를 font combobox에서 제외하기
- Qt family key와 UI display name을 분리할지 결정하기
- weight UI는 그 다음 단계에서 현재 `dev`의 `font_weight` 모델 위에 얇게
  추가하기

## 사용한 명령

```text
rg "PATH_FONTS|CUSTOM_FONTS|FONT_FAMILIES|let_show_only_custom_fonts|QFontDatabase|addApplicationFont|applicationFontFamilies|update_font_list|FontFamilyComboBox" ballontranslator -n
Get-ChildItem -Force fonts
Select-String -Path ballontranslator\ui\mainwindow.py -Pattern "let_show_only_custom_fonts|update_font_list|show_only_custom_font|text_styles|global_format|setStyles|load_textstyle" -Context 4
Select-String -Path ballontranslator\ui\configpanel.py -Pattern "let_show_only_custom_fonts|show_only_custom_font|on_show_only_custom_fonts" -Context 4
Select-String -Path ballontranslator\utils\config.py -Pattern "let_show_only_custom_fonts|text_styles_path|load_textstyle|DEFAULT_TEXTSTYLE" -Context 4
QT_QPA_PLATFORM=offscreen python -c "<QFontDatabase inspection>"
```
