# Font Registry Implementation Handoff

이 문서는 새 세션이나 다른 PC에서 BT 폰트 레지스트리 구현을 바로 이어가기 위한
인계 문서이다. 먼저 이 파일을 읽고, 필요하면 `README.md`와 `docs/`의 설계 문서를
참조한다.

## 현재 결론

- custom font는 Qt 결과에만 기대지 말고 TTF/OTF/TTC `name` table을 직접 읽는다.
- system font는 기본적으로 Qt가 반환한 family/style/weight를 그대로 사용한다.
- system alias는 자동 추정으로 병합하지 않는다.
- optional system alias table이 제공된 경우에만 명시된 group을 병합한다.
- optional custom group table이 제공된 경우에만 weight-specific family를 하나의
  picker family로 표시한다.
- optional custom group으로 만든 pseudo family는 project JSON에 그대로 저장하지
  않는다. 선택된 실제 face canonical과 weight를 보존한다.
- 기존 project JSON shape는 1차 구현에서 바꾸지 않는다.

## 중요 정책

### Custom Font

Custom font는 `fonts/` 아래 파일을 기준으로 registry를 만든다.

우선 읽을 name table record:

- family
- subfamily
- full name
- PostScript name
- typographic family
- typographic subfamily

Canonical fallback:

1. English typographic family
2. English family
3. localized typographic family
4. localized family
5. Qt-renderable family

Display fallback:

1. current locale typographic family/family
2. localized typographic family/family
3. English typographic family/family
4. canonical family

### System Font

System font는 Qt API의 한계를 인정한다.

- `QFontDatabase.families()`
- `QFontDatabase.styles(family)`
- `QFontDatabase.weight(family, style)`
- `isFixedPitch`, `isScalable`, `isSmoothlyScalable`, `isPrivateFamily`

Qt가 `Batang`과 `바탕`을 모두 반환해도, Qt API만으로 둘의 alias 관계를 안정적으로
알 수 없다. 그러므로 optional table 없이 병합하지 않는다.

### Optional Tables

현재 검증용 예시:

- `data/system-font-aliases.ko-kr.example.json`
- `data/custom-font-groups.ko-kr.example.json`

System alias table:

- `Batang`/`바탕`처럼 Qt system family alias를 명시적으로 병합한다.
- table이 없으면 분리한다.

Custom group table:

- `Korail Round Gothic Bold/Light/Medium`처럼 metadata상 weight-specific family인
  face들을 표시상 하나의 picker family로 묶을 수 있다.
- 원래 face canonical은 반드시 보존한다.

## 구현 순서 제안

1. `ballontranslator/launch.py`의 custom font loading 결과를 보존하되, name table
   parser 기반 metadata 수집 계층을 추가한다.
2. 런타임 전용 `FontRegistry` 모델을 추가한다. 저장 포맷은 바꾸지 않는다.
3. custom-only switch 의미를 유지한다.
   - on: custom registry만 표시
   - off: system registry + custom registry 표시
4. font picker를 plain string list가 아니라 entry model 기반으로 바꾼다.
5. grouped/separate weight mode를 config/UI 옵션으로 둔다.
6. Windows legacy raster font blacklist를 적용해 DirectWrite 경고를 줄인다.
7. optional table 로딩은 없으면 no-op이 되게 한다.

## 먼저 볼 파일

- `ballontranslator/launch.py`
- `ballontranslator/ui/mainwindow.py`
- `ballontranslator/ui/text_panel.py`
- `ballontranslator/utils/config.py`
- `ballontranslator/utils/shared.py`

## 하지 말아야 할 것

- project JSON shape를 바로 바꾸지 않는다.
- system font alias를 문자열 유사도나 LLM 추정으로 자동 병합하지 않는다.
- filename에서 `Bold`, `Light`, `Medium` 등을 제거해 custom font를 자동 병합하지
  않는다.
- mandatory dependency를 추가하지 않는다.
- custom-only switch를 system/custom 병합 옵션처럼 의미 변경하지 않는다.
- `font_family` 저장값을 일괄 rewrite하지 않는다.

## 검증 명령

Windows 기준:

```powershell
conda run -n BallonsTranslator python font-system-lab\tools\probe_font_registry_logic.py --output tmp\font-registry-probe.md --limit 200
conda run -n BallonsTranslator python font-system-lab\tools\probe_font_registry_logic.py --system-alias-table font-system-lab\data\system-font-aliases.ko-kr.example.json --output tmp\font-registry-probe-alias.md --limit 200
conda run -n BallonsTranslator python font-system-lab\tools\probe_font_registry_logic.py --custom-group-table font-system-lab\data\custom-font-groups.ko-kr.example.json --output tmp\font-registry-probe-custom-groups.md --limit 200
conda run -n BallonsTranslator python font-system-lab\tools\dump_font_info.py --output tmp\font-dump.json
```

macOS/Linux에서는 경로 구분자만 `/`로 바꾸면 된다.

```bash
conda run -n BallonsTranslator python font-system-lab/tools/probe_font_registry_logic.py --output tmp/font-registry-probe-macos.md --limit 200
conda run -n BallonsTranslator python font-system-lab/tools/dump_font_info.py --output tmp/font-dump-macos.json
```

## macOS에서 확인할 것

- custom font canonical/display/weight 결과가 Windows와 같은지
- `qt_families`가 Windows처럼 여러 alias를 반환하는지, 하나만 반환하는지
- system non-ASCII family가 있는지
- custom/system conflict가 어떻게 잡히는지
- optional custom group table로 `Korail Round Gothic`이 정상 grouping되는지

macOS 결과가 통과하면 1차 구현 설계는 충분히 안정적이라고 본다. Linux 검증은
추가 확신용으로 수행한다.

## macOS 검증 결과

2026-06-10에 Apple Silicon macOS(M4, Miniforge env `bt`, Python 3.12.13,
PyQt6 6.11.0)에서 검증했다. 결과 파일은 다음 위치에 생성했다.

```text
tmp/font-registry-probe-macos.md
tmp/font-registry-probe-macos.json
tmp/font-registry-probe-custom-groups-macos.md
tmp/font-registry-probe-alias-macos.md
tmp/font-dump-macos.json
```

기존 Windows 결과는 다음 위치에 백업했다.

```text
tmp/font-system-lab-windows-backup/
```

macOS 최종 요약:

- custom faces: 54
- grouped picker entries: 25
- separate picker entries: 54
- Qt system families: 181
- Qt custom families: 25
- non-ASCII system families: 0
- system warning entries: 0
- custom/system conflicts: 0

검증 결론:

- macOS에서는 custom font마다 Qt family가 대체로 하나씩만 반환된다.
- `Korail Round Gothic Bold/Light/Medium`은 기본 probe에서 분리되고,
  optional custom group table을 넣었을 때만 `Korail Round Gothic`으로 묶인다.
- optional custom group table을 사용해도 face canonical
  `Korail Round Gothic Bold/Light/Medium`은 보존된다.
- `온글잎 윤우체`는 canonical `Ownglyph YoonwooChae`와 Qt render family
  `온글잎 윤우체`가 달라 `qt_family_differs_from_canonical` 경고가 붙었다.
  이는 canonical/display/qt_family 분리와 resolver가 필요하다는 좋은 검증
  케이스이다.
- Windows와 macOS 모두 현재 설계 정책을 지지한다. 구현으로 넘어가도 된다.

macOS 주의사항:

- PyQt6/macOS에서 `QFontDatabase.addApplicationFont()`에 상대경로를 넘기면
  실패할 수 있다. 실제 앱 구현과 검증 스크립트 실행에서는 font path를
  `Path(...).resolve()` 등으로 절대경로화해서 넘기는 것이 안전하다.
- 검증 중 pasteboard/notification 관련 macOS 경고가 stderr에 출력될 수 있으나,
  스크립트 종료 코드가 0이고 산출물이 생성되면 검증 결과로 사용할 수 있다.
