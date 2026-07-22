# BallonsTranslator Korean Fork

[한국어 안내](README_KO.md) | [简体中文 upstream README](README_CN.md) | [English upstream README](README_EN.md)

> [!NOTE]
> 이 저장소는 [dmMaze/BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)를 기반으로 한 개인 fork이다. 원본 중국어 README는 간체자 문서이므로 `README_CN.md`에 보존한다.

## 프로젝트 개요

BallonsTranslator Korean Fork는 원본 BallonsTranslator를 한국어 만화와 웹툰 식자 작업에 맞게 안정화하기 위한 작업판이다. 원본의 자동 번역 파이프라인, 이미지 편집, rich text 편집 기능을 유지하면서 한국어 환경에서 자주 드러나는 폰트, 저장 호환성, 편집 UX 문제를 단계적으로 정리한다.

이 fork의 목표는 별도 제품을 만드는 것이 아니다. upstream `dev` 흐름을 따라가며, 한국어 작업에서 검증한 개선을 작게 나누어 유지하고, upstream에 보낼 수 있는 변경은 별도 PR용 브랜치에서 선별한다.

## 원본 프로젝트

BallonsTranslator는 딥러닝 기반 만화 번역 보조 도구이다. 텍스트 검출, OCR, 글자 제거, 번역, 번역문 배치를 자동화하고, 사용자가 결과를 직접 편집할 수 있는 PyQt/qtpy 데스크톱 앱이다.

- Upstream: <https://github.com/dmMaze/BallonsTranslator>
- 원본 간체 중국어 README: [README_CN.md](README_CN.md)
- 원본 영어 README: [README_EN.md](README_EN.md)
- 한국어 안내 문서: [README_KO.md](README_KO.md)

## 이 fork에서 집중하는 문제

- 한국어 custom font의 표시명과 저장명을 안정화한다.
- Windows, macOS, Linux에서 같은 프로젝트가 가능한 한 같은 폰트로 복원되게 한다.
- Qt가 반환하는 localized family name과 canonical family name을 분리한다.
- weight별 font face를 grouped picker와 separate face picker로 다룰 수 있게 한다.
- rich text HTML 저장 시 localized font family가 project JSON에 섞이지 않도록 보정한다.
- upstream 동기화와 PR 제출이 가능하도록 실험 코드, 검증 도구, 본체 변경의 경계를 분명히 한다.

## 현재 주요 변경

### Font registry

런타임 전용 font registry를 추가해 custom/system font를 구분하고, UI 표시명과 프로젝트 저장명을 분리한다. custom font는 TTF/OTF/TTC name table을 직접 읽어 canonical family, localized display family, Qt render family, style, weight를 수집한다.

선택적 alias/group 설정은 [config/font_registry.json](config/font_registry.json)에 둔다. 이 파일은 두 종류의 보정을 한 곳에서 정의한다.

- `system_aliases`: Windows에서 `BatangChe`와 `바탕체`처럼 Qt가 별도 system family로 노출하는 alias를 명시적으로 병합한다.
- `custom_groups`: `Korail Round Gothic Light/Medium/Bold`처럼 폰트 파일이 독립 family로 선언한 face를 picker 표시상 하나의 family로 묶는다.

설정 형식과 예제 코드는 [doc/font_registry_config.md](doc/font_registry_config.md)에 정리한다.

### Font picker and storage

폰트 picker는 registry entry 기반으로 동작한다. 표시명은 로컬라이즈된 이름을 우선 사용하고, 저장값은 가능한 영어 canonical family를 유지한다. grouped mode에서는 family와 weight를 따로 선택하고, separate mode에서는 face 단위 항목을 표시한다.

기존 project JSON shape는 유지한다. `font_family`와 `font_weight` 구조를 바꾸지 않고, 런타임 resolver가 저장값을 현재 OS와 Qt font database에 맞게 해석한다.

### Rich text normalization

텍스트 블록 저장 시 rich text HTML 안의 `font-family` 값을 registry resolver로 canonical family에 가깝게 정규화한다. 이는 UI 표시명 정책과 별개로, 프로젝트 파일에 localized display name과 canonical name이 섞이는 문제를 줄이기 위한 serialization 보정이다.

## 개발 문서와 검증 도구

폰트 시스템 설계와 검증 기록은 [font-system-lab](font-system-lab/)에 둔다. 이 폴더는 본체 런타임이 의존하는 디렉터리가 아니라, 설계 문서와 probe 도구를 모아 둔 작업 공간이다.

주요 문서는 다음과 같다.

- [font-system-lab/IMPLEMENTATION_HANDOFF.md](font-system-lab/IMPLEMENTATION_HANDOFF.md): 새 세션에서 이어가기 위한 인계 문서이다.
- [font-system-lab/docs/font-registry-design.md](font-system-lab/docs/font-registry-design.md): 한국어 설계 문서이다.
- [font-system-lab/docs/font-registry-design-en.md](font-system-lab/docs/font-registry-design-en.md): PR 설명에 활용할 수 있는 영어 설계 초안이다.
- [font-system-lab/docs/font-implementation-worklog.md](font-system-lab/docs/font-implementation-worklog.md): 구현 중 발견한 문제와 해결 기록이다.
- [font-system-lab/docs/format-inspector-issues.md](font-system-lab/docs/format-inspector-issues.md): 이번 font registry 범위에서 분리한 format inspector 후속 과제이다.
- [font-system-lab/docs/image-scale-project-compatibility.md](font-system-lab/docs/image-scale-project-compatibility.md): 업스케일 이미지와 기존 project 좌표, font size 호환성 설계이다.

대표 probe 명령은 다음과 같다.

```bash
conda run -n bt python font-system-lab/tools/probe_font_registry_logic.py \
  --fonts-dir "$(pwd)/fonts" \
  --font-registry-config config/font_registry.json \
  --output tmp/font-registry-probe-unified-macos.md \
  --limit 200
```

## 실행

소스 실행 방식은 upstream과 같다.

```bash
python3 -m ballontranslator
```

headless 실행 예시는 다음과 같다.

```bash
python3 -m ballontranslator --headless --exec_dirs "[DIR_1],[DIR_2]"
```

설정은 기본적으로 `config/config.json`에서 읽는다. font registry alias/group 보정은 `config/font_registry.json`에서 읽으며, 파일이 없으면 해당 보정만 적용하지 않는다.

## 브랜치 정책

- `dev`: upstream `dmMaze/BallonsTranslator:dev`와 일치시키는 동기화 기준 브랜치이다.
- `main`: 이 fork의 공개/실사용 기준 브랜치이다.
- `codex/*`: 기능 실험, 검증, PR 정리용 작업 브랜치이다.
- upstream에 보낼 PR은 `dev` 기준의 별도 브랜치에서 필요한 변경만 선별해 만든다.

## PR 준비 기준

upstream PR을 준비할 때는 다음 원칙을 따른다.

- 기존 project JSON shape를 바꾸지 않는다.
- mandatory dependency를 추가하지 않는다.
- `Show only custom fonts` 설정의 의미를 바꾸지 않는다.
- 시스템 폰트 alias는 자동 추정으로 병합하지 않는다.
- custom font group도 filename 추정이 아니라 명시 설정이나 font metadata에 근거한다.
- long-running OCR, translation, inpainting, model loading은 Qt main thread를 막지 않는다.
- 실험 문서와 probe 결과는 PR 설명으로 옮기거나, 본체 변경과 분리해 설명한다.

## 라이선스와 출처

이 저장소는 원본 BallonsTranslator의 GPL-3.0-or-later 라이선스를 따른다. 원본 프로젝트와 관련 모듈, 모델 출처, 사용법은 언어별 README와 upstream 문서를 참고한다.
