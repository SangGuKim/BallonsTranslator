# Font System Lab

이 폴더는 BallonsTranslator 본체에 적용하기 전 폰트 레지스트리 설계와 검증 도구를
모아 두는 임시 작업 공간이다. 기존 앱 구조와 실행 경로를 가능한 건드리지 않고,
Windows/macOS/Linux에서 Qt가 실제로 어떤 폰트 정보를 주는지 비교하는 것이 목적이다.

## 폴더 구조

- `docs/`: 내부 검토용 설계/조사 문서와 PR용 영문 초안
- `docs/font-implementation-worklog.md`: 구현 중 발견한 문제, 해결 방식, 최소 수정성 점검 기록
- `docs/format-inspector-issues.md`: multi-select와 rich text selection format inspector 문제 정리
- `docs/font-storage-policy-decision.md`: family group 저장과 face canonical 저장 정책 검토
- `data/`: 과거 분리형 optional alias/group table 예시. 런타임 설정은
  `config/font_registry.json`을 사용한다.
- `tools/dump_font_info.py`: Qt가 주는 원본 폰트 정보와 custom font name table을 JSON으로 덤프한다.
- `tools/probe_font_registry_logic.py`: 제안한 registry 정책을 적용했을 때의 picker 후보, weight, 경고를 요약한다.

## 실행

이 저장소에서는 conda 환경 `BallonsTranslator`를 기준으로 실행한다.

```powershell
conda run -n BallonsTranslator python font-system-lab\tools\probe_font_registry_logic.py --output tmp\font-registry-probe.md
conda run -n BallonsTranslator python font-system-lab\tools\probe_font_registry_logic.py --format json --output tmp\font-registry-probe.json
conda run -n BallonsTranslator python font-system-lab\tools\probe_font_registry_logic.py --font-registry-config config\font_registry.json --output tmp\font-registry-probe-unified.md
conda run -n BallonsTranslator python font-system-lab\tools\dump_font_info.py --output tmp\font-dump.json
```

macOS에서도 같은 명령을 사용하되, 해당 환경의 conda env 이름이 다르면 `-n` 값만 바꾼다.
PyQt6/macOS에서는 `QFontDatabase.addApplicationFont()`가 상대경로 font path를
실패시킬 수 있으므로, macOS 검증은 `--fonts-dir "$(pwd)/fonts"`처럼 절대경로를
넘긴다.

```bash
conda run -n bt python font-system-lab/tools/probe_font_registry_logic.py --fonts-dir "$(pwd)/fonts" --output tmp/font-registry-probe-macos.md --limit 200
conda run -n bt python font-system-lab/tools/probe_font_registry_logic.py --fonts-dir "$(pwd)/fonts" --format json --output tmp/font-registry-probe-macos.json
conda run -n bt python font-system-lab/tools/probe_font_registry_logic.py --fonts-dir "$(pwd)/fonts" --font-registry-config config/font_registry.json --output tmp/font-registry-probe-unified-macos.md --limit 200
conda run -n bt python font-system-lab/tools/dump_font_info.py --fonts-dir "$(pwd)/fonts" --output tmp/font-dump-macos.json
```

## 판정 기준

`probe_font_registry_logic.py` 결과에서 다음 항목을 우선 확인한다.

- custom font의 grouped picker entry가 의도한 family 단위로 묶이는가.
- Korail Round Gothic처럼 name table 자체가 weight별 family를 가진 폰트가 무리하게 합쳐지지 않는가.
- display name은 로컬라이즈된 이름을 보여 주고 canonical family는 가능한 영어 이름을 유지하는가.
- custom/system 이름 충돌이 `custom_overrides_system` 경고로 드러나는가.
- weight 값이 style/subfamily 이름과 크게 어긋나지 않는가.
- `config/font_registry.json`의 `system_aliases`를 제공했을 때만 `바탕`/`Batang`
  같은 항목이 병합되는가.
- `config/font_registry.json`의 `custom_groups`를 제공했을 때만
  `Korail Round Gothic Bold/Light/Medium` 같은 weight-specific family가 하나의
  picker family로 표시되는가.
- custom group을 쓰더라도 face canonical은 보존되는가.

raw JSON은 정보량이 많으므로, 일반 검토는 probe Markdown을 먼저 보고 이상 항목만
`dump_font_info.py --family-filter`로 좁혀 확인한다.

## 확인된 macOS 결과

2026-06-10 Apple Silicon macOS(M4, Miniforge `bt`, Python 3.12.13, PyQt6 6.11.0)
검증 결과는 설계한 정책과 일치했다.

- custom faces 54개가 grouped picker entry 25개로 정리되었다.
- macOS Qt는 custom font family를 대체로 하나씩만 반환했다.
- system non-ASCII family와 system warning은 없었다.
- `Korail Round Gothic Bold/Light/Medium`은 기본 상태에서 분리되고, optional
  custom group table을 넣었을 때만 `Korail Round Gothic`으로 묶였다.
- optional custom group table을 사용해도 원래 face canonical은 보존되었다.
- `온글잎 윤우체`는 canonical과 Qt render family가 달라 resolver 검증 케이스로
  남았다.

Windows 결과는 `tmp/font-system-lab-windows-backup/`에 백업해 두었다.
