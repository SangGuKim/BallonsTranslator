> [!NOTE]
> 이 문서는 원 프로젝트의 `README.md`를 보존한 `README_CN.md`를 GPT 5.5로 번역한 한국어 번역본이며, 번역본의 내용은 이 프로젝트의 개발자가 검수했다.

> [!IMPORTANT]
> **이 도구의 기계번역 결과를 공개적으로 공유하려 하고, 숙련된 번역자가 전체 번역 또는 교정을 진행하지 않았다면 눈에 잘 띄는 위치에 기계번역임을 표시하라.**

# BallonTranslator
[简体中文](README_CN.md) | 한국어 | [English](README_EN.md)

딥러닝으로 만화 번역을 보조하는 도구이다. 원클릭 기계번역과 간단한 이미지/텍스트 편집을 지원한다.

AI 개조판 [Ballonstranslator-Pro](https://github.com/thomaswantstobeaskeleton/BallonsTranslator-Pro)는 여러 기능을 추가했지만, 이 프로젝트의 주요 기여자는 해당 개발에 참여하지 않았다. 사용은 본인 책임이다.

<img src="doc/src/ui0.jpg" div align=center>

<p align=center>
화면 미리보기
</p>

# 기능
* 원클릭 기계번역
  - 번역문 삽입은 원문 레이아웃 추정 결과를 참고한다. 색상, 외곽선, 각도, 방향, 정렬 등이 포함된다.
  - 최종 결과는 텍스트 검출, 인식, 글자 제거, 기계번역 네 모듈의 전체 성능에 좌우된다.
  - 일본 만화와 미국 comics를 지원한다.
  - 영어에서 중국어, 일본어에서 영어로의 조판은 최적화되어 있다. 텍스트 레이아웃은 추출된 말풍선 영역을 참고하며, 중국어는 pkuseg 기반으로 문장을 나눈다. 일본어에서 중국어 세로쓰기는 아직 개선이 필요하다.

* 이미지 편집
  mask 편집과 복구 브러시를 지원한다.

* 텍스트 편집
  - WYSIWYG rich text 편집과 일부 기본 조판 서식 조정을 지원하며, [글꼴 스타일 프리셋](https://github.com/dmMaze/BallonsTranslator/pull/311)을 지원한다.
  - 전체/원문/번역문 찾기와 바꾸기를 지원한다.
  - Word 문서 가져오기와 내보내기를 지원한다.

* 웹툰에 적합하다.

# 사용 설명

## Windows
Windows를 사용하고, 직접 환경을 설정하고 싶지 않으며, 인터넷 접속이 정상이라면 다음 방법을 사용하라.

[MEGA](https://mega.nz/folder/gmhmACoD#dkVlZ2nphOkU5-2ACb5dKw) 또는 [Google Drive](https://drive.google.com/drive/folders/1uElIYRLNakJj-YS0Kd3r3HE-wzeEvrWd?usp=sharing)에서 `BallonsTranslator_dev_src_with_gitpython.7z`를 내려받고, 압축을 푼 뒤 `launch_win.bat`를 실행해 프로그램을 시작한다. 라이브러리와 모델을 자동으로 내려받지 못하면 `data`와 `ballontrans_pylibs_win.7z`를 수동으로 내려받아 프로그램 디렉터리에 압축 해제한다.

업데이트를 받으려면 `scripts/local_gitpull.bat`를 실행한다.

이 패키지들은 Windows 7에서 실행할 수 없다. Windows 7 사용자는 [Python 3.8](https://www.python.org/downloads/release/python-3810/)을 직접 설치해 소스 코드로 실행해야 한다.

Windows에서 소스 코드로 실행하면서 PyTorch나 딥러닝 모듈을 사용할 때 `msvcp140.dll`, `c10.dll`, `[WinError 1114]` 관련 오류가 발생하면 [Microsoft Visual C++ Redistributable x64](https://aka.ms/vc14/vc_redist.x64.exe)를 설치하거나 업데이트하라. Visual Studio 2015-2022 버전이며, [공식 다운로드 안내](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)를 참고할 수 있다.

## 소스 코드 실행

[Python](https://www.python.org/downloads/release/python-31011) **3.12 이하**와 [Git](https://git-scm.com/downloads)을 설치한다. Microsoft Store판 Python은 사용하지 마라.

```bash
# 저장소 복제
$ git clone https://github.com/dmMaze/BallonsTranslator.git ; cd BallonsTranslator

# 프로그램 시작. 시작에 필요한 핵심 의존성을 자동으로 확인하고 설치한다.
$ python3 -m ballontranslator

# 프로그램 업데이트
python3 -m ballontranslator --update
```

프로그램 시작 시 핵심 의존성을 확인한다. 추가 라이브러리가 필요한 모듈을 선택하면 프로그램이 누락된 선택 의존성 설치를 안내한다. 설정에서 자동 설치를 켤 수도 있다. 모델 다운로드가 실패하면 [MEGA](https://mega.nz/folder/gmhmACoD#dkVlZ2nphOkU5-2ACb5dKw) 또는 [Google Drive](https://drive.google.com/drive/folders/1uElIYRLNakJj-YS0Kd3r3HE-wzeEvrWd?usp=sharing)에서 `data` 폴더 또는 오류 메시지에 언급된 누락 파일을 수동으로 내려받아 소스 코드 디렉터리의 해당 위치에 저장한다.

## macOS 앱 빌드(Apple silicon 칩용)
[참고](doc/macOS_app_CN.md)

여러 문제가 생길 수 있으므로 현재는 소스 코드를 직접 실행하는 것을 권장한다.

## 원클릭 번역
**명령줄 터미널에서 프로그램을 실행하는 것을 권장한다.** 처음 실행할 때는 먼저 원문 언어와 목표 언어를 설정하고, 이미지가 들어 있는 폴더를 연 뒤 `Run`을 눌러 번역 완료를 기다린다.

<img src="doc/src/run.gif">

원클릭 기계번역으로 삽입되는 글자의 크기와 색상 같은 서식은 기본적으로 프로그램이 결정한다. 설정 패널 -> 조판 메뉴에서 전역 설정을 사용하도록 바꿀 수 있다. 전역 글꼴 서식은 어떤 텍스트 블록도 편집하지 않을 때 오른쪽 글꼴 패널에 표시되는 서식이다.

<img src="doc/src/global_font_format.png">

## 캔버스

## 복구 브러시
<img src="doc/src/imgedit_inpaint.gif">
<p align = "center">
복구 브러시
</p>

### 사각형 도구
<img src="doc/src/rect_tool.gif">
<p align = "center">
사각형 도구
</p>

마우스 왼쪽 버튼을 누른 채 사각형 영역을 드래그하면 영역 안의 글자를 지운다. 오른쪽 버튼을 누른 채 영역을 드래그하면 영역 안의 복구 결과를 지운다.

글자 제거 결과는 알고리즘(gif의 "방법1"과 "방법2")이 글자 영역을 얼마나 정확히 추정하는지에 좌우된다. 일반적으로 제거할 텍스트 블록보다 사각형을 조금 크게 잡는 것이 좋다. 두 방법 모두 다소 시행착오가 필요하지만, 대부분의 단순한 글자/단순한 배경, 일부 복잡한 배경/단순한 글자 또는 단순한 배경/복잡한 글자에는 대응할 수 있다. 복잡한 배경과 복잡한 글자가 함께 있는 경우에는 여러 번 시도해 볼 수 있다.

`자동`을 체크하면 영역을 드래그한 직후 바로 복구한다. 체크하지 않으면 `복구`를 누르거나 스페이스바를 눌러야 복구가 진행된다. `Ctrl+D`로 사각형 선택 영역을 삭제할 수도 있다.

## 텍스트 편집
<img src="doc/src/textedit.gif">

<p align = "center">
텍스트 편집
</p>

<img src="doc/src/multisel_autolayout.gif" div align=center>
<p align=center>
일괄 텍스트 서식 조정과 자동 조판
</p>

<img src="doc/src/ocrselected.gif" div align=center>
<p align=center>
선택한 텍스트 박스 OCR 및 번역
</p>

## 인터페이스 설명과 단축키
* `Ctrl+Z`, `Ctrl+Y`로 대부분의 작업을 실행 취소/다시 실행할 수 있다. 페이지를 넘기면 실행 취소/다시 실행 스택이 비워진다는 점에 주의하라.
* `A`/`D` 또는 `pageUp`/`pageDown`으로 페이지를 넘긴다. 현재 페이지가 저장되지 않았다면 자동 저장한다.
* `T`를 누르면 텍스트 편집 모드(하단 맨 오른쪽 `T` 아이콘)로 전환한다. `W`를 누르면 텍스트 블록 생성 모드가 활성화되며, 캔버스에서 오른쪽 버튼으로 드래그해 텍스트 박스를 만든다.
* `P`를 누르면 캔버스 모드로 전환한다. 오른쪽 아래 슬라이더로 원본 이미지 투명도를 조정한다.
* 제목 표시줄 -> 실행에서 임의의 자동화 모듈을 켜거나 끌 수 있다. 모두 끄고 `Run`을 실행하면 전역 글꼴 스타일과 조판 설정에 따라 텍스트를 다시 렌더링한다.
* 설정 패널에서 각 자동화 모듈의 매개변수를 설정한다.
* `Ctrl++`/`Ctrl+-` 또는 마우스 휠로 캔버스를 확대/축소한다.
* `Ctrl+A`로 화면의 모든 텍스트 블록을 선택할 수 있다.
* `Ctrl+F`로 현재 페이지를 검색하고, `Ctrl+G`로 전체 검색을 한다.
* `0`-`9`로 삽입 글자/원본 이미지 투명도를 조정한다.
* 텍스트 편집 중 `Ctrl+B`는 굵게, `Ctrl+U`는 밑줄, `Ctrl+I`는 기울임이다.
* 글꼴 스타일 패널의 `특수 효과`에서 투명도를 수정하고 그림자를 추가한다.
* `Alt+Arrow Keys` 또는 `Alt+WASD`로 텍스트 블록 사이를 전환한다. 텍스트 블록을 편집 중일 때는 `pageDown` 또는 `pageUp`을 사용한다.

<img src="doc/src/configpanel.png">

## 명령줄 모드(GUI 없음)
```python
python -m ballontranslator --headless --exec_dirs "[DIR_1],[DIR_2]..."
```

모든 설정(검출 모델, 원문 언어, 목표 언어 등)은 `config/config.json`에서 불러온다.

렌더링 글꼴 크기가 맞지 않으면 `--ldpi`로 Logical DPI 크기를 지정한다. 보통 `96` 또는 `72`를 사용한다.

# 자동화 모듈
이 프로젝트는 [manga-image-translator](https://github.com/zyddnys/manga-image-translator)에 크게 의존한다. 온라인 서버와 모델 훈련에는 비용이 필요하므로 여유가 있다면 지원을 고려하라.

- Ko-fi: <https://ko-fi.com/voilelabs>
- Patreon: <https://www.patreon.com/voilelabs>
- 爱发电: <https://afdian.net/@voilelabs>

Sugoi 번역기 작성자: [mingshiba](https://www.patreon.com/mingshiba)

### 텍스트 검출
* 현재는 일본어(네모난 글자는 대체로 비슷하다)와 영어 검출만 지원한다. 훈련 코드와 설명은 <https://github.com/dmMaze/comic-text-detector>를 참고하라.
* [星河云(团子漫画OCR)](https://cloud.stariver.org.cn/)의 텍스트 검출을 지원한다. 사용자 이름과 비밀번호를 입력해야 하며, 시작할 때마다 자동 로그인한다.
  * 자세한 설명은 [团子OCR说明](doc/团子OCR说明.md)을 참고하라.
* `YSGDetector`는 [lhj5426](https://github.com/lhj5426)이 훈련한 모델로, 일본 만화/CG의 의성어를 더 잘 걸러낼 수 있다. [YSGYoloDetector](https://huggingface.co/YSGforMTL/YSGYoloDetector)에서 모델을 수동으로 내려받아 `data/models` 디렉터리에 넣어야 한다.

### OCR
* 모든 mit 모델은 manga-image-translator에서 왔으며, 일본어/영어/중국어 인식과 색상 추출을 지원한다.
* [manga_ocr](https://github.com/kha-white/manga-ocr)는 [kha-white](https://github.com/kha-white)의 모델이며 일본어 인식을 지원한다. 이 모델을 선택하면 프로그램이 색상을 추출하지 않는다는 점에 주의하라.
* [PaddleOCRVLManga](https://huggingface.co/jzhang533/PaddleOCR-VL-For-Manga)는 일본어 인식을 지원한다. 이 모델을 선택하면 프로그램이 색상을 추출하지 않는다.
* [星河云(团子漫画OCR)](https://cloud.stariver.org.cn/)의 OCR을 지원한다. 사용자 이름과 비밀번호를 입력해야 하며, 시작할 때마다 자동 로그인한다.
  * 현재 구현은 텍스트 블록별로 OCR을 수행하므로 속도가 느리고 정확도도 뚜렷하게 향상되지 않는다. 필요하다면 团子 Detector를 사용하라.
  * 텍스트 검출을 团子 Detector로 설정했다면 OCR은 `none_ocr`로 설정해 텍스트를 직접 읽는 것을 권장한다. 시간과 요청 횟수를 줄일 수 있다.
  * 자세한 설명은 [团子OCR说明](doc/团子OCR说明.md)을 참고하라.
* OCR 설정 항목: 글꼴 인식. [글꼴 인식 모델(YuzuMarker.FontDetection)](https://github.com/JeffersonQin/YuzuMarker.FontDetection)을 내려받아 `data\models\YuzuMarker.FontDetection` 디렉터리에 넣는다.
  필요한 세 파일은 각각 `data\models\YuzuMarker.FontDetection\font_dataset`, `data\models\YuzuMarker.FontDetection\name=4x-epoch=18-step=368676.ckpt`, `data\font_demo_cache.bin`이다.
  인식 신뢰도가 60%보다 높은 글꼴 이름은 json 파일의 `_detected_font_name` 필드에 저장된다. 현재는 시각적으로 표시하지 않는다. [스크립트](scripts/BTjson_to_LPtxt.pyw)를 사용해 LabelPlus txt로 내보낼 때 글꼴과 글자 크기 정보를 포함하도록 선택할 수 있으며, PS/ID 같은 다른 소프트웨어에 가져가 식자 작업에 사용할 수 있다.

### 이미지 복구
* AOT 복구 모델은 manga-image-translator에서 왔다.
* patchmatch는 딥러닝이 아닌 알고리즘이며 PS 복구 브러시의 배경이 되는 알고리즘이기도 하다. 구현은 [PyPatchMatch](https://github.com/vacancy/PyPatchMatch)에서 왔고, 이 프로그램은 필자의 [수정판](https://github.com/dmMaze/PyPatchMatchInpaint)을 사용한다.
* lama*는 [lama](https://github.com/advimman/lama)를 fine-tuning한 것이다.

### 번역기

* Google 번역기는 중국 서비스를 종료했다. 중국 본토에서 계속 사용하려면 전역 프록시를 설정하고 설정 패널에서 url을 `*.com`으로 바꿔야 한다.
* 彩云은 [token](https://dashboard.caiyunapp.com/) 신청이 필요하다.
* papago
* DeepL과 Sugoi 및 Sugoi의 CT2 Translation 변환 번역기는 [Snowad14](https://github.com/Snowad14)에게 감사한다. Sugoi 번역기(일본어에서 영어만 지원)를 사용하려면 [오프라인 모델](https://drive.google.com/drive/folders/1KnDlfUM9zbnYFTo6iCbnBaBKabXfnVJm)을 내려받아 `sugoi_translator`를 `BallonsTranslator/ballontranslator/data/models`로 옮긴다.
* [Sakura-13B-Galgame](https://github.com/SakuraLLM/Sakura-13B-Galgame)을 지원한다. 로컬 단일 GPU에서 실행할 때 VRAM이 부족하다면 설정 패널에서 `low vram mode`를 체크할 수 있다. 기본값은 활성화이다.
* DeepLX는 [Vercel](https://github.com/bropines/Deeplx-vercel) 또는 [deeplx](https://github.com/OwO-Network/DeepLX)를 참고하라.
* 두 버전의 OpenAI 호환 번역기를 지원한다. 공식 OpenAI API 또는 OpenAI API와 호환되는 서드파티 LLM 제공자를 지원하며, 설정 패널에서 구성해야 한다.
  * 접미사가 없는 버전은 token 소모가 더 적지만 문장 분할 안정성이 조금 낮고 긴 텍스트 번역에 문제가 있을 수 있다.
  * `exp` 접미사 버전은 token 소모가 더 많지만 안정성이 더 좋고, Prompt에 "탈옥" 처리가 들어 있어 긴 텍스트 번역에 적합하다.
* [m2m100](https://huggingface.co/facebook/m2m100_1.2B): `m2m100-1.2B-ctranslate2`를 내려받아 `data/models` 디렉터리에 넣는다.

다른 우수한 오프라인 영어 번역 모델은 [이 토론](https://github.com/dmMaze/BallonsTranslator/discussions/515)을 참고하라.

새 번역기를 추가하려면 [加别的翻译器](doc/加别的翻译器.md)를 참고하라. 이 프로그램에서 새 번역기를 추가하려면 기반 클래스를 상속하고 두 인터페이스만 구현하면 되며, 코드의 다른 부분을 신경 쓸 필요는 없다. PR을 환영한다.

## 기타
* Nvidia GPU 또는 Apple silicon이 있는 컴퓨터는 기본적으로 GPU 가속을 활성화한다.
* 러시아어 번역을 제공한 [bropines](https://github.com/bropines)에게 감사한다.
* 서드파티 입력기는 오른쪽 편집 상자 표시 버그를 일으킬 수 있다. [#76](https://github.com/dmMaze/BallonsTranslator/issues/76)을 참고하라. 현재는 수정할 계획이 없다.
* 선택한 텍스트의 미니 메뉴는 *집합 사전 전문 드래그 번역* [Saladict](https://saladict.crimx.com)를 지원한다. [설치 설명](doc/saladict_chs.md)을 참고하라.

<details>
  <summary><i>AMD ROCm GPU 가속 활성화 방법</i></summary>

### 일반 방식 ZLUDA (ROCm)

**장점:**
텍스트와 텍스트 박스 인식 속도가 커뮤니티 프리뷰 버전보다 약간 빠르며, 물론 CPU보다 빠르다.

**단점:**
추가 설치와 관련 설정이 필요하다. 첫 시작, 인식 모델 변경, 그래픽 드라이버 업그레이드 등에는 캐시 예열에 긴 시간이 필요하다.

**설치 단계:**

1. 그래픽 드라이버를 최신 버전으로 업데이트한다. 24.12.1 이상을 권장하며, 자신의 시스템 환경에 맞게 [AMD HIP SDK Page](https://www.amd.com/en/developer/resources/rocm-hub/hip-sdk.html)에서 내려받아 설치한다.
2. [ZLUDA](https://github.com/lshqqytiger/ZLUDA/releases)를 내려받아 `zluda` 폴더에 압축 해제한다. `zluda` 폴더를 시스템 드라이브, 예를 들어 `C:\zluda`에 복사한다.
3. 시스템 환경 변수를 설정한다. Windows 10 기준으로 설정 - 시스템 속성 - 고급 시스템 설정 - 환경 변수 - 시스템 변수 - `Path` 변수 - 편집을 누른 뒤 마지막에 `C:\zluda`와 `%HIP_PATH%bin` 두 항목을 추가한다.
4. CUDA 라이브러리의 동적 링크 파일을 교체한다. `C:\zluda` 폴더 안의 `cublas.dll`, `cusparse.dll`, `nvrtc.dll`을 데스크톱에 복사한 뒤 아래 규칙대로 파일 이름을 바꾼다.

**주의 사항**

HIP SDK와 ZLUDA 버전 대응 관계에 주의하라. 비교적 최신 AMD 그래픽 드라이버 사용을 권장한다.

|Windows 버전 | HIP SDK 버전 | ZLUDA 버전 |
|---|---|---|
|Windows 11 | 7.1.1 | 3.9.6 |
|Windows 10 및 11 | 6.4.2 | 3.9.5 |
|Windows 10 및 11 | 6.2.4 | 3.9.5 |
|Windows 10 및 11 | 6.1.2 | 3.9.5 |


```
  원래 파일명 -> 새 파일명

  cublas.dll -> cublas64_11.dll

  cusparse.dll -> cusparse64_11.dll

  nvrtc.dll -> nvrtc64_112_0.dll
```

이름을 바꾼 파일을 `BallonsTranslator\ballontrans_pylibs_win\Lib\site-packages\torch\lib\` 디렉터리 안의 같은 이름 파일과 교체한다.

5. 프로그램을 시작하고 OCR과 텍스트 검출을 Cuda로 설정한다. **이미지 복구는 계속 CPU를 사용하라.**
6. OCR을 실행하고 ZLUDA가 PTX 파일을 컴파일할 때까지 기다린다. **첫 컴파일은 CPU 성능에 따라 대략 5-10분이 걸린다.** **다음 실행부터는 컴파일이 필요 없다.**
