> [!IMPORTANT]
> **기계번역 결과를 공개 공유하고, 숙련된 번역자가 전체 번역 또는 교정을 거치지 않았다면 눈에 잘 띄는 곳에 기계번역임을 표시한다.**

# BallonsTranslator Korean Fork

[简体中文](README_CN.md) | 한국어 | [English](README_EN.md)

이 저장소는 [dmMaze/BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)를 기반으로 한 개인 fork이다. 원본 BallonsTranslator(BT)를 한국어 식자 작업 환경에서 쓰기 편하게 유지하기 위해 폰트, 실행 환경, 편집 UX 문제를 단계적으로 보완한다.

## 이 fork의 브랜치 정책

- `dev`: upstream `dmMaze/BallonsTranslator:dev`와 일치시키는 동기화 기준 브랜치이다.
- `main`: 이 fork의 공개/실사용 기준 브랜치이다.
- `codex/*`: 기능 실험, 검증, PR 정리용 작업 브랜치이다.
- upstream에 보낼 PR은 `dev` 기준의 별도 브랜치에서 필요한 변경만 선별해 만든다.

## 현재 주요 변경

- custom/system font를 구분해 폰트 표시명과 저장명을 분리하는 font registry 실험을 포함한다.
- custom font의 로컬라이즈 표시명, canonical 저장명, grouped/separate face 표시 모드를 검증 중이다.
- rich text 저장 시 localized font family가 project JSON에 섞이지 않도록 정규화하는 방향을 실험 중이다.
- 내부 검토 문서와 폰트 검증 도구는 `font-system-lab/`에 둔다.

## 원본 프로젝트 개요

BallonsTranslator는 딥러닝 기반 만화/웹툰 번역 보조 도구이다. 텍스트 검출, OCR, 글자 지우기, 기계번역, 번역문 식자 과정을 한 번에 실행할 수 있으며, 간단한 이미지 편집과 WYSIWYG 방식의 텍스트 편집을 제공한다.

AI 개조판 [Ballonstranslator-Pro](https://github.com/thomaswantstobeaskeleton/BallonsTranslator-Pro)는 여러 기능을 추가한 별도 프로젝트이다. 원본 BT 주요 기여자가 직접 개발한 것이 아니므로 사용 시 주의한다.

<img src="doc/src/ui0.jpg" div align=center>

<p align=center>
화면 미리보기
</p>

# 기능

- 일괄 기계번역
  - 텍스트 검출, OCR, 글자 제거, 번역, 번역문 배치를 자동화한다.
  - 원문 레이아웃 추정 결과를 참고해 색상, 외곽선, 각도, 방향, 정렬 등을 반영한다.
  - 최종 품질은 텍스트 검출, OCR, inpainting, 번역 모듈 성능에 좌우된다.
  - 일본 만화와 서구권 comics, 웹툰 작업에 사용할 수 있다.

- 이미지 편집
  - mask 편집과 복구 브러시를 지원한다.
  - 세로로 긴 웹툰 이미지에도 대응한다.

- 텍스트 편집
  - rich text 편집과 기본 식자 서식 조정을 지원한다.
  - [텍스트 스타일 프리셋](https://github.com/dmMaze/BallonsTranslator/pull/311)을 지원한다.
  - 전체/원문/번역문 검색과 치환을 지원한다.
  - Word 문서 가져오기/내보내기를 지원한다.

# 설치와 실행

## Windows 패키지 사용

Python과 Git을 직접 설치하고 싶지 않고 인터넷 접속이 가능하다면, 원본 프로젝트가 제공하는 패키지를 사용할 수 있다.

1. [MEGA](https://mega.nz/folder/gmhmACoD#dkVlZ2nphOkU5-2ACb5dKw) 또는 [Google Drive](https://drive.google.com/drive/folders/1uElIYRLNakJj-YS0Kd3r3HE-wzeEvrWd?usp=sharing)에서 `BallonsTranslator_dev_src_with_gitpython.7z`를 내려받는다.
2. 압축을 풀고 `launch_win.bat`를 실행한다.
3. 라이브러리나 모델 자동 다운로드가 실패하면 `data`와 `ballontrans_pylibs_win.7z`를 수동으로 내려받아 프로그램 폴더에 압축 해제한다.
4. `scripts/local_gitpull.bat`로 업데이트할 수 있다.

제공 패키지는 Windows 7에서 동작하지 않는다. Windows 7 사용자는 [Python 3.8](https://www.python.org/downloads/release/python-3810/)을 직접 설치해 소스 실행 방식을 사용한다.

## 소스 실행

[Python](https://www.python.org/downloads/release/python-31011) **3.12 이하**와 [Git](https://git-scm.com/downloads)을 설치한다. Microsoft Store판 Python은 피한다.

```bash
git clone https://github.com/SangGuKim/BallonsTranslator.git
cd BallonsTranslator
python3 -m ballontranslator
```

업데이트는 다음처럼 실행한다.

```bash
python3 -m ballontranslator --update
```

프로그램은 시작 시 핵심 의존성을 확인한다. 추가 라이브러리가 필요한 모듈을 선택하면 누락된 optional dependency 설치를 안내한다. 모델 다운로드가 실패하면 [MEGA](https://mega.nz/folder/gmhmACoD#dkVlZ2nphOkU5-2ACb5dKw) 또는 [Google Drive](https://drive.google.com/drive/folders/1uElIYRLNakJj-YS0Kd3r3HE-wzeEvrWd?usp=sharing)에서 `data` 폴더나 오류 메시지에 나온 파일을 내려받아 소스 디렉터리의 대응 위치에 둔다.

## macOS 앱 빌드

Apple silicon용 macOS 앱 빌드는 [macOS 앱 문서](doc/macOS_app_CN.md)를 참고한다. 아직 여러 문제가 있을 수 있으므로 소스 실행을 권장한다.

# 기본 사용

## 일괄 번역

처음 실행할 때는 명령줄 터미널에서 실행하는 것을 권장한다. 원문 언어와 번역 언어를 설정한 뒤 이미지가 들어 있는 폴더를 열고 `Run`을 누른다.

<img src="doc/src/run.gif">

자동 식자의 글꼴 크기, 색상 등은 기본적으로 프로그램이 추정한다. 설정 패널의 식자 메뉴에서 전역 서식을 사용하도록 바꿀 수 있다. 전역 글꼴 서식은 아무 text block도 편집하지 않을 때 오른쪽 글꼴 패널에 표시되는 서식이다.

<img src="doc/src/global_font_format.png">

## 이미지 편집

### 복구 브러시

<img src="doc/src/imgedit_inpaint.gif">

<p align="center">
복구 브러시
</p>

### 사각형 도구

<img src="doc/src/rect_tool.gif">

<p align="center">
사각형 도구
</p>

마우스 왼쪽 버튼으로 사각형을 드래그하면 사각형 안의 글자를 제거한다. 오른쪽 버튼으로 사각형을 드래그하면 해당 영역의 복구 결과를 지운다.

글자 제거 결과는 알고리즘이 문자 영역을 얼마나 잘 추정하는지에 따라 달라진다. 일반적으로 제거할 텍스트보다 약간 크게 영역을 잡는 편이 좋다. `자동`을 켜면 영역을 잡자마자 복구하고, 끄면 `복구` 버튼 또는 스페이스바를 눌러 복구한다. `Ctrl+D`로 사각형 선택 영역을 삭제할 수 있다.

## 텍스트 편집

<img src="doc/src/textedit.gif">

<p align="center">
텍스트 편집
</p>

<img src="doc/src/multisel_autolayout.gif" div align=center>

<p align=center>
여러 text block 서식 조정과 자동 배치
</p>

<img src="doc/src/ocrselected.gif" div align=center>

<p align=center>
선택한 text block OCR과 번역
</p>

## UI와 단축키

- `Ctrl+Z`, `Ctrl+Y`: 대부분의 작업을 실행 취소/다시 실행한다. 페이지를 넘기면 undo/redo stack은 비워진다.
- `A`/`D` 또는 `PageUp`/`PageDown`: 페이지를 넘긴다. 현재 페이지가 저장되지 않았으면 자동 저장한다.
- `T`: 텍스트 편집 모드로 전환한다.
- `W`: text block 생성 모드를 활성화한다. canvas에서 오른쪽 버튼으로 text box를 만든다.
- `P`: paint 모드로 전환한다.
- `Ctrl++`/`Ctrl+-` 또는 마우스 휠: canvas를 확대/축소한다.
- `Ctrl+A`: 화면의 모든 text block을 선택한다.
- `Ctrl+F`: 현재 페이지에서 찾는다.
- `Ctrl+G`: 전체 프로젝트에서 찾는다.
- `0`-`9`: 식자/원본 이미지 opacity를 조정한다.
- 텍스트 편집 중 `Ctrl+B`, `Ctrl+U`, `Ctrl+I`: 굵게, 밑줄, 기울임을 적용한다.
- `Alt+방향키` 또는 `Alt+WASD`: text block 사이를 이동한다. 편집 중에는 `PageDown`/`PageUp`도 사용할 수 있다.

<img src="doc/src/configpanel.png">

## Headless 모드

GUI 없이 실행하려면 다음처럼 사용한다.

```bash
python -m ballontranslator --headless --exec_dirs "[DIR_1],[DIR_2]..."
```

검출 모델, 원문/번역 언어 등 설정은 `config/config.json`에서 읽는다. 렌더링 글꼴 크기가 맞지 않으면 `--ldpi`로 logical DPI를 지정한다. 보통 `96` 또는 `72`를 사용한다.

# 자동화 모듈

BT는 [manga-image-translator](https://github.com/zyddnys/manga-image-translator)에 크게 의존한다. 온라인 서버와 모델 학습에는 비용이 들므로 여건이 된다면 원 프로젝트를 후원한다.

- Ko-fi: <https://ko-fi.com/voilelabs>
- Patreon: <https://www.patreon.com/voilelabs>
- 爱发电: <https://afdian.net/@voilelabs>

Sugoi 번역기 작성자는 [mingshiba](https://www.patreon.com/mingshiba)이다.

## 텍스트 검출

- 현재는 주로 일본어와 영어 텍스트 검출을 지원한다. 학습 코드와 설명은 <https://github.com/dmMaze/comic-text-detector>를 참고한다.
- [星河云/团子漫画OCR](https://cloud.stariver.org.cn/) 텍스트 검출을 지원한다. 사용자 이름과 비밀번호가 필요하며 시작 시 자동 로그인한다.
- `YSGDetector`는 [lhj5426](https://github.com/lhj5426)이 학습한 모델이며, 일본 만화/CG의 의성어 필터링에 더 강하다. [YSGYoloDetector](https://huggingface.co/YSGforMTL/YSGYoloDetector)에서 모델을 내려받아 `data/models`에 둔다.

## OCR

- 대부분의 MIT 모델은 manga-image-translator에서 온 것이며 일/영/중 인식과 색상 추출을 지원한다.
- [manga_ocr](https://github.com/kha-white/manga-ocr)는 일본어 인식을 지원하지만 색상은 추출하지 않는다.
- [PaddleOCRVLManga](https://huggingface.co/jzhang533/PaddleOCR-VL-For-Manga)는 일본어 인식을 지원하지만 색상은 추출하지 않는다.
- [星河云/团子漫画OCR](https://cloud.stariver.org.cn/) OCR도 지원한다. 현재 구현은 text block별 OCR이라 느리고 정확도 이점도 크지 않아 권장하지 않는다.
- 폰트 인식 기능은 [YuzuMarker.FontDetection](https://github.com/JeffersonQin/YuzuMarker.FontDetection) 모델을 사용한다. 모델 파일을 `data/models/YuzuMarker.FontDetection`에 배치한다.

## 이미지 복구

- AOT 복구 모델은 manga-image-translator에서 왔다.
- `patchmatch`는 Photoshop 복구 브러시와 같은 계열의 비딥러닝 알고리즘이며, [PyPatchMatch](https://github.com/vacancy/PyPatchMatch)의 수정판을 사용한다.
- `lama*`는 [lama](https://github.com/advimman/lama)를 fine-tuning한 모델이다.

## 번역기

- Google 번역은 중국 서비스가 종료되어 중국 본토에서는 proxy와 URL 설정이 필요하다.
- 彩云은 [token](https://dashboard.caiyunapp.com/)이 필요하다.
- Papago를 지원한다.
- DeepL과 Sugoi, CT2 Translation 변환을 지원한다. Sugoi 번역기는 [오프라인 모델](https://drive.google.com/drive/folders/1KnDlfUM9zbnYFTo6iCbnBaBKabXfnVJm)을 내려받아 `BallonsTranslator/ballontranslator/data/models`에 둔다.
- [Sakura-13B-Galgame](https://github.com/SakuraLLM/Sakura-13B-Galgame)을 지원한다.
- DeepLX는 [Vercel](https://github.com/bropines/Deeplx-vercel) 또는 [deeplx](https://github.com/OwO-Network/DeepLX)를 참고한다.
- OpenAI 호환 번역기 두 종류를 지원한다. 공식 OpenAI API 또는 OpenAI API 호환 third-party LLM provider를 설정 패널에서 사용할 수 있다.
- [m2m100](https://huggingface.co/facebook/m2m100_1.2B)은 `m2m100-1.2B-ctranslate2`를 내려받아 `data/models`에 둔다.

다른 오프라인 영어 번역 모델은 [이 토론](https://github.com/dmMaze/BallonsTranslator/discussions/515)을 참고한다. 새 번역기를 추가하려면 [加别的翻译器](doc/加别的翻译器.md)를 참고한다.

# 기타

- Nvidia GPU 또는 Apple silicon이 있으면 기본적으로 GPU 가속을 사용한다.
- 러시아어 번역은 [bropines](https://github.com/bropines)가 제공했다.
- 일부 third-party 입력기는 오른쪽 편집창 표시 문제를 일으킬 수 있다. 관련 이슈는 [#76](https://github.com/dmMaze/BallonsTranslator/issues/76)을 참고한다.
- 선택 텍스트 mini menu는 [沙拉查词](https://saladict.crimx.com)를 이용한 단어장/사전 연동을 지원한다. 설치는 [saladict_chs.md](doc/saladict_chs.md)를 참고한다.

# 라이선스와 upstream

이 fork의 기반은 원본 [dmMaze/BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)이다. 라이선스와 세부 고지는 원본 프로젝트의 파일을 따른다.
