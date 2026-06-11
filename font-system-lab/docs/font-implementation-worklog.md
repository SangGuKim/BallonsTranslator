# 폰트 구현 작업 기록

이 문서는 폰트 레지스트리 설계와 별도로, 구현과 수동 검증 중 발견한 문제,
원인, 해결 방식을 기록한다. 설계 문서는 목표 구조를 설명하고, 이 문서는 실제
작업 중 왜 특정 보정 코드가 필요해졌는지 추적하기 위한 내부 기록이다.

## 배경

초기 목표는 다음 세 가지였다.

- 내부 저장용 family name은 가능한 영어 canonical name으로 유지한다.
- UI 표시명은 로컬라이즈된 display name을 우선 사용한다.
- grouped/separate 표시 모드를 제공하되 기존 프로젝트 JSON의
  `font_family`/`font_weight` 구조는 유지한다.

구현 후 실제 프로젝트를 열고 저장/복원 동작을 확인하면서, 단순 picker 표시를
넘어 `QTextDocument`의 rich text fragment와 font weight 보정까지 함께 다뤄야
한다는 점이 확인됐다.

## 발견한 문제와 해결

### 1. 같은 저장값인데 일부 블록만 로컬라이즈명으로 표시됨

테스트 프로젝트 `W:\work\test`에서 여러 text block이 모두
`font_family: KoPubWorldBatang`으로 저장되어 있었지만, GUI에서는 일부만
`KoPubWorld바탕체`로 보이고 나머지는 `KoPubWorldBatang`으로 보였다.

원인은 family가 아니라 weight였다. 첫 번째 블록은 `font_weight: 300`이었고,
나머지 대부분은 `font_weight: 400`이었다. KoPubWorldBatang custom font는 실제
face weight가 `300`, `500`, `700`만 있으므로, 기존 picker 매칭은 `400`을 가진
entry를 찾지 못하고 raw 저장 문자열을 그대로 표시했다.

해결 방식은 다음과 같다.

- `FontRegistry.resolve_family()`가 saved family와 weight를 받아 nearest face를
  고르게 한다.
- 동일 거리에서는 더 굵은 weight를 선택한다. 따라서 `400`은 `300`이 아니라
  `500 Medium`으로 간다.
- grouped mode와 separate mode 모두에서 registry가 고른 entry 또는 face를
  picker 항목에 매칭한다.

이 정책은 기존 데이터에 정확한 weight가 없더라도 표시와 렌더링을 가능한 face로
안정화한다.

### 2. 공통 alias가 마지막 face로 덮어써짐

KoPubWorldBatang의 name table에는 Light/Medium/Bold face 모두에
`KoPubWorldBatang` 같은 공통 alias가 들어 있었다. 단순히 모든 face alias를
`faces_by_key`에 넣으면 마지막으로 처리된 face가 공통 family name을 덮어쓴다.
그 결과 `KoPubWorldBatang + 400`이 entry 기반 nearest face가 아니라 특정 face로
고정될 수 있었다.

해결 방식은 다음과 같다.

- entry 자체의 family/display/qt family는 entry key로 취급한다.
- 여러 face에 반복되는 이름은 family-level alias로 본다.
- 한 face에만 나타나는 이름만 face-specific alias로 본다.

이로써 `KoPubWorldBatang`은 weight 기반으로 face를 고르고,
`KoPubWorldBatang Bold` 같은 이름은 해당 face로 고정된다.

### 3. 부분 선택 후 weight 변경 시 family가 원래 family로 돌아감

텍스트 일부만 선택해 다른 font family로 바꾼 뒤 weight를 바꾸면, 선택한
fragment의 family가 원래 block 대표 family로 되돌아가고 weight만 바뀌는 문제가
있었다.

원인은 weight 변경 경로가 fragment의 현재 family를 보존하지 않고
`self.fontformat.font_family`를 기준으로 family를 다시 resolve했기 때문이다.

해결 방식은 다음과 같다.

- `setFontWeight()`를 단순 `QTextCharFormat.setFontWeight()` merge에서
  fragment 순회 방식으로 바꾼다.
- 각 fragment의 현재 `QFont.family()`를 먼저 storage/canonical family로 해석한다.
- 그 family와 새 weight를 기준으로 render family/styleName을 다시 적용한다.

검증 결과, 앞 3글자만 `KoPubWorldDotum / 700`으로 바꾸고 뒤 3글자는
`KoPubWorldBatang / 400`으로 유지되는 것을 확인했다.

### 4. `fontformat`은 canonical인데 rich text HTML은 localized family로 저장됨

폰트 패밀리를 변경하면 `fontformat.font_family`는 `KoPubWorldDotum`처럼 영어
canonical name으로 저장되지만, `rich_text` 내부 HTML의 `font-family`에는
`KoPubWorld돋움체`처럼 로컬라이즈된 이름이 남을 수 있었다.

이 상태는 즉시 렌더링에는 문제가 없을 수 있지만, 프로젝트 파일 안에 저장용
canonical name과 표시용 localized name이 섞이게 만든다. OS를 옮기거나 Qt backend가
달라지면 rich text fragment가 `fontformat`과 다르게 복원될 위험이 있다.

해결 방식은 다음과 같다.

- `TextBlkItem.toHtml()` 반환 직전에 HTML 안의 `font-family:'...'` 값을 registry
  resolver로 canonical family로 정규화한다.
- 이 정규화는 프로젝트 저장 시점의 serialization 보정이며, UI 표시명 정책과는
  별개다.

검증 결과 `KoPubWorld바탕체`는 `KoPubWorldBatang`으로,
`KoPubWorld돋움체`는 `KoPubWorldDotum`으로 정규화됐다.

## 최소 수정성 점검

현재 구현은 upstream/dev 대비 다음 범위에 손을 댄다.

- `ballontranslator/utils/font_registry.py`: 새 runtime registry와 font name table
  parser를 추가한다.
- `ballontranslator/launch.py`: 기존 custom/system font list 생성 지점을 registry
  빌드로 교체한다.
- `ballontranslator/ui/text_panel.py`: `QFontComboBox`를 registry entry 기반
  `QComboBox`로 교체하고 weight picker를 연결한다.
- `ballontranslator/ui/custom_widget/combobox.py`: weight picker를 추가한다.
- `ballontranslator/ui/mainwindow.py`: custom-only/grouped-separate 설정 변경 시
  picker list를 다시 빌드한다.
- `ballontranslator/ui/textitem.py`: 저장명/render family/styleName/rich text
  정규화를 적용한다.
- `ballontranslator/ui/text_style_presets.py`: style preview도 registry resolver를
  사용하게 한다.
- `ballontranslator/ui/fontformat_commands.py`, `config.py`, `configpanel.py`,
  `shared.py`: UI 설정과 호환 필드를 연결한다.

이 범위는 작지는 않지만, 같은 문제를 해결하기 위해 서로 필요한 연결이다.

- registry 없이 picker 표시명과 저장명을 분리할 수 없다.
- picker 교체 없이 localized display와 canonical storage를 동시에 유지하기 어렵다.
- weight picker 없이 grouped family mode에서 Medium/SemiBold 같은 face를 선택할
  수 없다.
- `textitem.py` 보정 없이 선택된 fragment, 저장 rich text, 실제 render family가
  서로 다른 상태로 남는다.

따라서 기능 관점에서는 과도한 구조 변경이라기보다, 폰트 family/weight 저장과
렌더링을 한 경로로 묶기 위한 최소 연결로 본다.

## PR 전 재검토할 부분

현재 브랜치는 실험/검증 문서와 구현이 함께 들어 있다. PR을 만들기 전에는 다음을
정리해야 한다.

- `font-system-lab/` 문서와 도구는 PR 본문으로 옮기거나 별도 개발 참고 자료로
  제외할지 결정한다.
- `launch.py`는 `font-system-lab/data/*.example.json`을 직접 읽지 않는다.
  런타임 설정은 `config/font_registry.json` 하나로 통합했다. 형식 설명과 예제
  코드는 `doc/font_registry_config.md`에 둔다.
- system alias table은 `바탕`/`Batang`처럼 확실한 케이스에만 유효하다. 자동 추정
  병합은 여전히 하지 않는 것이 안전하다.
- global font/template 선택 상태, 선택 중 rendering cache, text style 활성/비활성
  전환 문제는 이번 font registry PR과 분리한다.
- PR 설명에는 rich text 정규화가 serialization 안정성을 위한 변경이라는 점을
  명시한다.

## 검증 기록

현재까지 수행한 검증은 다음과 같다.

- `conda run -n BallonsTranslator python -m py_compile ...`
- `git diff --check`
- KoPubWorldBatang grouped/separate picker 매칭 수동 재현
- 부분 선택 family 변경 후 weight 변경 최소 재현
- rich text `font-family` canonical 정규화 최소 재현
- `W:\work\test\imgtrans_test.json` 수동 프로젝트 저장/복원 확인

남은 검증은 실제 GUI에서 다음 흐름을 반복 확인하는 것이다.

- custom-only on/off
- grouped/separate 전환
- 기존 프로젝트 열기와 저장 후 재열기
- 부분 선택 family/weight 변경
- text style preset 적용 후 저장/복원
