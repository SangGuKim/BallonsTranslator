# Font Registry Config

이 문서는 폰트 레지스트리의 선택적 alias/group 설정 파일 위치와 형식을 정의한다.

## 위치

런타임 설정 파일은 저장소 루트 기준 `config/font_registry.json`에 둔다. 이 파일은
실험용 `font-system-lab/` 아래에 두지 않는다. 앱 시작 시 파일이 있으면 읽고, 없으면
alias/group 보정을 적용하지 않는다.

`font-system-lab/`의 data 파일은 probe와 설계 검증용 자료로만 사용한다. 본체
런타임은 `font-system-lab/` 경로를 참조하지 않는다.

## 구조

하나의 JSON 파일에 두 종류의 설정을 함께 둔다.

- `system_aliases`: Qt가 별도 system family로 노출한 localized/English alias를
  명시적으로 병합한다.
- `custom_groups`: custom font 파일이 weight별 family를 선언했을 때 picker 표시만
  하나의 family로 묶는다.

자동 추정 병합은 하지 않는다. 확실한 항목만 JSON에 명시한다.

```json
{
  "system_aliases": [
    {
      "canonical": "BatangChe",
      "display": "바탕체",
      "aliases": ["바탕체"],
      "note": "Windows Korean fixed-pitch serif alias."
    }
  ],
  "custom_groups": [
    {
      "canonical": "Korail Round Gothic",
      "display": "코레일 둥근고딕",
      "members": [
        {
          "canonical": "Korail Round Gothic Light",
          "display": "코레일 둥근고딕 Light",
          "weight": 300,
          "style": "Light",
          "aliases": ["Korail Round Gothic L", "코레일 둥근고딕 Light"]
        },
        {
          "canonical": "Korail Round Gothic Bold",
          "display": "코레일 둥근고딕 Bold",
          "weight": 700,
          "style": "Bold",
          "aliases": ["Korail Round Gothic B", "코레일 둥근고딕 Bold"]
        }
      ]
    }
  ]
}
```

## 필드 의미

`system_aliases` 항목은 다음 필드를 사용한다.

- `canonical`: 저장과 비교에 사용할 대표 family name이다.
- `display`: picker에 보여 줄 표시명이다.
- `aliases`: 같은 system family로 볼 Qt family name 목록이다.
- `note`: 사람이 읽는 설명이다. 런타임 동작에는 영향을 주지 않는다.

`custom_groups` 항목은 다음 필드를 사용한다.

- `canonical`: picker에서 보여 줄 group canonical이다. pseudo group이므로 저장값으로
  강제하지 않는다.
- `display`: picker에 보여 줄 group 표시명이다.
- `members`: group에 포함할 실제 face 목록이다.
- `members[].canonical`: 실제 face canonical이다. pseudo group에서 선택된 weight를
  저장할 때 이 값을 보존한다.
- `members[].weight`: picker weight 값이다.
- `members[].style`: Qt style name 보정값이다.
- `members[].aliases`: 해당 face로 해석할 추가 family name 목록이다.

## 로더 사용 예

본체는 `build_font_registry()`에 통합 설정 파일 경로를 넘긴다.

```python
from ballontranslator.utils.font_registry import build_font_registry

registry = build_font_registry(
    qfont_db=QFontDatabase,
    font_paths=font_paths,
    system_families=system_families,
    locale="ko-KR",
    font_registry_config_path="config/font_registry.json",
)
```

probe 스크립트에서는 다음처럼 확인한다.

```bash
python font-system-lab/tools/probe_font_registry_logic.py \
  --font-registry-config config/font_registry.json \
  --output tmp/font-registry-probe-unified.md
```

## 호환성

기존 probe용 `groups` 기반 단일 목적 JSON도 당분간 읽을 수 있다. 다만 새 본체
런타임 경로는 `config/font_registry.json` 하나만 사용한다.
