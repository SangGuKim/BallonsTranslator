# fontsys 브랜치 기준 dev 변경 분석

## 목적

이 문서는 `fontsys` 브랜치가 시작된 뒤 upstream `dev`에 어떤 변화가
들어왔는지 기록한다. 새 통합 브랜치에서 기존 로컬 폰트 변경 중 무엇을
살릴지 판단하기 위한 기준 문서이다.

현재 통합 브랜치는 다음과 같다.

- `codex/integrate-peperu-fontsys`

기준 커밋은 다음과 같다.

- `fontsys` 첫 고유 커밋: `3958816` (`Changed the UI layout of text panel to support text weight`)
- `fontsys` 분기 기준 부모: `a5d2942` (`update torch install command, close #1120`)
- 현재 `dev`: `391c8eb` (`fix typo in "fix bound issues in vertical text layout"`)

분석 대상 upstream 범위는 다음과 같다.

```text
a5d2942..dev
```

## 요약

`fontsys`가 시작된 뒤 `dev`에 들어온 가장 큰 변화는 폰트 정책 변경이
아니다. 프로젝트 전체의 패키지 구조와 실행 구조가 크게 바뀐 것이다.

- 최상위 `ui/`, `utils/`, `modules/` 소스가 `ballontranslator/` 패키지
  아래로 이동했다.
- 아이콘과 번역 리소스가 `resources/` 아래로 이동했다.
- 실행 진입점이 `python -m ballontranslator` 기반으로 바뀌었다.
- 모듈 로딩이 lazy registry와 explicit preparation 중심으로 바뀌었다.
- `requirements.txt`가 핵심 의존성 위주로 줄고, 모듈별 의존성은 package
  manager 쪽으로 이동했다.

폰트 통합 관점에서 현재 `dev`는 이미 다음 요소를 가지고 있다.

- `FontFormat.font_weight`
- `TextBlock.font_weight`
- `ffmt_change_font_weight`
- `fix_fontweight_qt` 기반 Qt5/Qt6 font weight 변환

따라서 `fontsys`를 통째로 이식하면 안 된다. 현재 남은 유효한 아이디어는
대체로 UI와 상호작용이다. 예를 들면 weight 선택 UI를 노출할지, Bold
버튼을 `font_weight`와 어떻게 동기화할지 같은 부분이다.

## 주요 dev 변경 흐름

### 대형 패키지 구조 변경 이전

- `16e491c` (`close #1144`)
  - 소스 트리 이동 전에 text/font 관련 경로를 일부 건드렸다.
- `258be0f` (`Implement lazy module loading and preparation`)
  - lazy module loading과 module preparation 동작을 도입했다.
  - `launch.py`, `ui/module_manager.py`, `ui/mainwindow.py`,
    `utils/config.py`, module base class, registry 동작이 바뀌었다.
  - 통합 작업에서는 lazy/eager model loading 동작을 건드리지 않도록
    주의해야 한다.

### 소스 트리와 리소스 구조 변경

- `12b2731` (`refactor src code into ballontranslator layout`)
  - 소스가 패키지 경로로 이동했다.
    - `ui/*` -> `ballontranslator/ui/*`
    - `utils/*` -> `ballontranslator/utils/*`
    - `modules/*` -> `ballontranslator/modules/*`
  - `ballontranslator/__main__.py`가 추가되었다.
  - import가 package-qualified path로 바뀌었다.
  - launch 구현이 `ballontranslator/launch.py`로 이동했다.

- `f97c178` (`move icons and translate into resources folder`)
  - 아이콘과 번역 리소스가 `resources/` 아래로 이동했다.
  - `shared.PROGRAM_PATH`, `RESOURCE_DIR`, `ICON_DIR`, `TRANSLATE_DIR`
    해석 방식이 바뀌었다.

### 모듈과 패키지 관리 변경

- `5945fa3` (`add py package manager`)
- `2b57d6e` (`Merge pull request #1197 from dmMaze/easy_install`)
- `4ded2f7` (`remove load_model_on_demand`)
- `0e2072d` (`make module selection lazy and consistant`)

영향은 다음과 같다.

- `requirements.txt`가 핵심 UI/project dependency 위주로 줄었다.
- backend/module dependency는 module metadata와 package manager code 쪽으로
  이동했다.
- startup, config, module manager를 건드리는 변경은 이 lazy module loading
  흐름과 충돌하지 않는지 확인해야 한다.

### 세로쓰기 레이아웃 수정

- `3c8392d` (`fix bound issues in vertical text layout`)
- `f9c2762` (`fix left bracket spacing issue`)
- `391c8eb` (`fix typo in "fix bound issues in vertical text layout"`)

영향은 다음과 같다.

- `ballontranslator/ui/scene_textlayout.py`에서 vertical cursor positioning,
  bracket handling, IME preedit cursor handling이 크게 바뀌었다.
- `peperu`의 한국어 세로쓰기 보정은 현재 구현을 기준으로 다시 검토해야
  한다. 예전 patch를 그대로 다시 적용하면 안 된다.

## 현재 dev의 폰트 모델

중요 파일은 다음과 같다.

- `ballontranslator/utils/fontformat.py`
- `ballontranslator/utils/textblock.py`
- `ballontranslator/ui/fontformat_commands.py`
- `ballontranslator/ui/textitem.py`
- `ballontranslator/ui/text_panel.py`

현재 `dev`는 font weight를 이미 저장하고 전달한다.

- `FontFormat.font_weight: int = None`
- `TextBlock.font_weight`
- legacy project loading에서 deprecated `weight`를 `font_weight`로 매핑한다.
- `fix_fontweight_qt`가 Qt5와 Qt6 numeric weight를 변환한다.
- `ffmt_change_font_weight`가 `TextBlkItem.setFontWeight`로 dispatch한다.
- `ffmt_change_bold`는 Bold on/off를 `QFont.Weight.Bold`와
  `QFont.Weight.Normal`로 바꾼 뒤 `setFontWeight`를 호출한다.

현재 `dev`의 text panel에는 별도 font-weight control이 없다. 보이는 UI는
다음과 같다.

- font family combobox
- font size control
- Bold/Italic/Underline button
- spacing/stroke/color 등 기존 format control

## 현재 dev와 겹치는 fontsys 변경

`fontsys` 브랜치는 현재 `dev` 대비 다음 파일을 바꾼다.

- `ballontranslator/launch.py`
- `ballontranslator/ui/custom_widget/__init__.py`
- `ballontranslator/ui/custom_widget/combobox.py`
- `ballontranslator/ui/mainwindow.py`
- `ballontranslator/ui/text_panel.py`
- `ballontranslator/ui/text_style_presets.py`
- `ballontranslator/ui/textitem.py`
- `ballontranslator/utils/config.py`

`fontsys`의 주요 아이디어는 다음과 같다.

- `FontWeightComboBox` 추가
- family/size control 옆에 compact weight selector 추가
- Bold button을 `bold`가 아니라 `font_weight`로 route
- `font_weight >= 700`이면 `bold`로 간주
- weight/bold/italic 변경 시 text style preview 갱신
- custom font loading 시 Qt가 반환한 family list 중 선호 family name 선택
- custom font가 있으면 custom-font-only view를 자동 활성화
- per-project text style이 켜진 경우 text style load 경로 변경

## 통합 위험

### 1. fontsys를 통째로 이식하면 안 된다

`fontsys`는 현재 upstream에 `font_weight`가 이미 들어오기 전에 만든
브랜치이다. 그대로 이식하면 upstream policy를 중복 구현하거나 일부
덮어쓸 위험이 있다.

### 2. Qt5/Qt6 weight 값은 쉽게 섞인다

`dev`에는 명시적인 변환 테이블이 있다.

- Qt5 style value: `0`, `12`, `25`, `50`, `57`, `63`, `75`, `81`, `87`
- Qt6/CSS-like value: `100`부터 `900`

`100..900` 값을 보여주는 UI control을 추가한다면 기존 변환 경로를
사용하거나 `shared.FLAG_QT6`로 보호해야 한다.

### 3. Bold를 비호환 저장 정책으로 바꾸면 안 된다

오래된 project에는 다음 상태가 있을 수 있다.

- `bold=True`, `font_weight=None`
- Qt5 값으로 저장된 `font_weight`
- Qt6 값으로 저장된 `font_weight`
- HTML `font-weight`가 들어간 rich text span

통합 작업은 backward compatibility를 유지해야 하며, old project에 대한
default 동작을 깨면 안 된다.

### 4. custom font 자동 선택은 사용자에게 놀라울 수 있다

`fontsys`는 custom font가 로드되면 `let_show_only_custom_fonts_flag`를
자동으로 켠다. 이는 launch 시점에 persistent UI preference를 바꾸는
동작이다. 유지한다면 명시적인 UI 설정이나 non-persistent 동작으로
재설계해야 한다.

### 5. vertical layout patch는 다시 검증해야 한다

`peperu`에는 한국어 세로쓰기 정렬 보정이 있다. 그러나 upstream은 그 뒤
세로쓰기 레이아웃을 여러 번 고쳤다. 현재 `dev` 기준으로 bracket, cursor,
IME preedit behavior를 다시 확인해야 한다.

## 권장 통합 방향

현재 `dev`를 다음 항목의 source of truth로 삼는다.

- package layout
- resource path
- lazy module loading과 package-manager behavior
- 저장되는 `FontFormat` / `TextBlock` schema
- Qt5/Qt6 font weight conversion

`fontsys`에서 선별 이식할 후보는 다음 정도로 제한한다.

- weight UI가 필요할 경우 focused `FontWeightComboBox`
- `font_weight`, `bold`, `italic` 변경 시 preview 갱신
- 현재 `dev`와 비교 후 필요한 경우에만 좁게 적용하는 `TextBlkItem`
  rendering fix
- 현재 재현 가능한 bug를 고치는 경우에만 per-project text style load guard

다음 항목은 피하거나 뒤로 미룬다.

- `let_show_only_custom_fonts_flag`의 자동 persistent toggle
- `FontFormatPanel.set_textblk_item`의 광범위한 재작성
- compatibility plan 없이 `bold`를 순수 derived field로 바꾸는 것

## 사용한 명령

```text
git show --no-patch --pretty=raw 3958816
git log --oneline --decorate --reverse a5d2942..dev
git log --oneline --decorate --reverse a5d2942..dev -- <font/text paths>
git diff --stat a5d2942..dev
git diff --name-status a5d2942..dev -- ui modules utils launch.py requirements.txt pyproject.toml ballontranslator resources config scripts tests
git diff a5d2942..dev -- <font/text paths>
```
