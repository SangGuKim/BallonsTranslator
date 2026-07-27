# 이미지 스케일 변경과 프로젝트 좌표 호환성 설계

이 문서는 MangaJaNai 같은 외부 업스케일러로 원본 이미지를 고해상도로 교체했을 때
기존 BallonsTranslator 프로젝트의 text block 좌표, text line polygon, font size가
이미지와 맞지 않는 문제를 정리한다. 목표는 당장 쓸 수 있는 변환 도구와 장기적인
비율 기반 저장 모델을 분리해 단계적으로 해결하는 것이다.

## 문제

현재 프로젝트는 text block의 공간 정보를 이미지 픽셀 좌표에 직접 묶어 저장한다.

- `TextBlock.xyxy`: block bounding box의 절대 픽셀 좌표이다.
- `TextBlock.lines`: text line polygon의 절대 픽셀 좌표이다.
- `TextBlock._bounding_rect`: 수동 편집 결과의 절대 픽셀 rect일 수 있다.
- `FontFormat.font_size`: 렌더링에 쓰는 픽셀 기준 크기이다.
- `stroke_width`, `shadow_radius`, `shadow_offset`, `letter_spacing`, distance type line spacing 같은 값도 시각적으로 픽셀 스케일 영향을 받는다.
- `ProjImgTrans.image_info`에는 width/height가 들어갈 수 있지만, 이 값은 현재 좌표계를 선언하는 기준 메타데이터로 쓰이지 않는다.

따라서 1000x1500 이미지로 편집한 프로젝트를 2000x3000 업스케일 이미지에 그대로
열면 block은 원래 위치의 절반 크기와 절반 위치에 남는다. 번역문도 기존 font size로
렌더링되어 풍선 안에서 너무 작아진다.

## 단기 해결: 프로젝트 스케일 변환 도구

우선 별도 Python 스크립트로 기존 프로젝트 JSON을 안전하게 변환한다. 이 도구는
저장 형식을 바꾸지 않고, 절대 픽셀 값을 새 이미지 크기에 맞게 곱해 준다.

권장 이름은 다음 중 하나로 둔다.

```text
scripts/scale_project_geometry.py
scripts/scale_bt_project.py
```

기본 사용 형태는 다음과 같다.

```powershell
python scripts\scale_project_geometry.py W:\path\project --scale 2
python scripts\scale_project_geometry.py W:\path\project --scale-xy 2,2 --offset 0,120 --font-scale 2
python scripts\scale_project_geometry.py W:\path\imgtrans_project.json --scale-xy 1,1 --offset 0,-40 --font-scale 1
```

### 변환 대상

같은 배율인 경우 `scale = 2.0`처럼 단일 값을 사용한다. 가로/세로 배율이 다르면
`sx`, `sy`를 분리하고, 위치에는 `offset_x`, `offset_y`를 추가로 적용한다.
비등방 크기 차이는 업스케일 자체보다 여백 추가/제거에서 오는 경우가 많으므로,
font size를 `sqrt(sx * sy)` 같은 추정값으로 자동 계산하지 않는다. 좌표는
`x' = x * sx + offset_x`, `y' = y * sy + offset_y`로 변환하고, font size는 사용자가
명시한 단일 `font_scale`만 적용한다.

반드시 변환할 값은 다음과 같다.

- `xyxy`: `[x1, y1, x2, y2]`에 각각 `sx`, `sy`를 적용한다.
- `lines`: 모든 polygon 점에 `sx`, `sy`를 적용한다.
- `_bounding_rect`: `[x, y, w, h]`에 각각 위치와 크기 배율을 적용한다.
- `fontformat.font_size`: font scale을 적용한다.
- `_detected_font_size`: 양수이면 font scale을 적용한다.
- `rich_text` HTML 내부의 `font-size: ...pt`: font scale을 적용한다.
- `region_inpaint_dict`, `region_mask`: 구조가 확인된 뒤에만 변환한다. 구조를 모르면 건드리지 않는다.

조건부 변환 값은 다음과 같다.

- `line_spacing`: `line_spacing_type == Distance`일 때만 font scale을 적용한다.
  `Proportional`이면 비율값이므로 바꾸지 않는다.
- `letter_spacing`: 현재 값이 비율 의미로 쓰이면 바꾸지 않는다. 실제 렌더링에서 픽셀
  거리로 해석되는 경로가 확인되면 별도 정책을 추가한다.
- `stroke_width`, `shadow_radius`, `shadow_offset`: 현재 렌더링 경로에서는 font size에
  곱해지는 비율값에 가깝기 때문에 스케일하지 않는다.
- rich text HTML의 font size를 보존해야 하는 특수한 경우에는 변환 스크립트에서
  `--no-rich-text`를 사용한다.

### 안전 정책

도구는 원본 프로젝트를 timestamp suffix `.backup` 파일로 자동 백업한 뒤 원본 JSON을
덮어쓴다.

- 별도 저장 옵션 없이 항상 변환 결과를 저장한다.
- 기존 JSON은 저장 직전에 `.YYYYMMDD-HHMMSS.backup` suffix로 보존한다.
- 이미지 파일은 수정하지 않는다.
- mask와 inpainted 결과는 기본적으로 수정하지 않는다. 좌표만 맞추는 도구로 시작한다.
- 페이지별 이미지 크기가 다르면 page별 `from_size`, `to_size`를 계산한다.
- 같은 파일명으로 이미지만 교체된 경우에는 기존 `image_info.width/height`를 기준
  크기로 삼을 수 있다. 해당 값이 없으면 `--from-size`를 요구한다.

## 중기 해결: 프로젝트에 기준 이미지 크기 저장

기존 절대 좌표 저장을 유지하더라도, 각 page의 좌표가 어느 이미지 크기를 기준으로
계산됐는지 명시해야 자동 보정이 가능하다.

권장 메타데이터는 `image_info` 아래에 추가한다.

```json
{
  "image_info": {
    "page001.png": {
      "width": 2000,
      "height": 3000,
      "geometry_base_width": 1000,
      "geometry_base_height": 1500,
      "geometry_scale_policy": "absolute_px"
    }
  }
}
```

기존 프로젝트에는 `geometry_base_width/height`가 없으므로, 로드 시 다음 순서로
해석한다.

1. 값이 있으면 그 크기를 좌표 기준 이미지 크기로 사용한다.
2. 값이 없고 `image_info.width/height`가 있으면 그것을 legacy 기준 크기로 사용한다.
3. 둘 다 없으면 현재 이미지 크기를 기준으로 간주해 기존 동작을 유지한다.

이 단계에서는 저장 JSON shape가 확장되지만 기존 필드는 바꾸지 않는다. 따라서 이전
프로젝트는 그대로 로드되고, 새 필드를 모르는 구버전도 기존 절대 좌표만 읽을 수 있다.

## 장기 해결: 비율 기반 내부 좌표 모델

근본 해결은 저장된 좌표를 이미지 픽셀에 직접 묶지 않는 것이다. 다만 기존 프로젝트
호환성을 위해 한 번에 저장 형식을 갈아엎지 않는다.

권장 모델은 다음과 같다.

- 저장은 당분간 기존 절대 픽셀 필드를 유지한다.
- 런타임에는 page별 `GeometryContext`를 만들고, 기준 이미지 크기와 현재 이미지
  크기 사이의 transform을 명시한다.
- 새 helper가 `TextBlock`의 절대 좌표를 normalized 좌표로 변환하고, 렌더링 직전에
  현재 이미지 크기의 절대 좌표로 투영한다.
- 저장 시에는 사용자가 명시적으로 마이그레이션하기 전까지 기존 절대 픽셀 필드를
  유지한다.
- 새 저장 필드를 추가한다면 `geometry_v2`처럼 opt-in 형태로 두고, legacy 필드와
  동기화 정책을 먼저 정한다.

예상 내부 모델은 다음과 같다.

```text
GeometryContext:
  base_width, base_height
  current_width, current_height
  sx = current_width / base_width
  sy = current_height / base_height
  font_scale = sqrt(sx * sy)
```

normalized 좌표는 `[0.0, 1.0]` 범위 비율로 표현한다. polygon도 같은 방식으로
보관한다. 렌더링, hit test, crop, OCR 재실행 등 픽셀 좌표가 필요한 경로에서는
`GeometryContext`를 통해 변환한다.

## 폰트 크기와 DPI 호환성

현재 `FontFormat.font_size`는 앱 내부에서 픽셀 기준으로 다루고, `size_pt`는
`shared.LDPI`를 통해 point로 변환한다. README에도 `--ldpi`로 logical DPI를
조정하라는 안내가 있다. 이 구조에서는 Windows/macOS 사이에서 같은 point 값이
같은 픽셀 결과를 보장하지 않을 수 있다.

따라서 이미지 스케일 문제와 OS별 point 차이를 함께 풀려면 font size의 의미를
명시해야 한다.

권장 정책은 다음과 같다.

- 프로젝트 저장의 대표 font size는 렌더링 기준 픽셀 크기로 유지한다.
- UI에서 point를 표시하더라도 저장값은 `LDPI`에 따라 흔들리지 않는 내부 픽셀 값을
  기준으로 둔다.
- OS별 Qt point 해석 차이는 font registry/resolver 또는 렌더링 계층에서 보정한다.
- image scale 변환은 내부 픽셀 font size에 `font_scale`을 적용한다.
- rich text HTML에 point 단위가 들어가는 경우에는 저장 정규화 단계에서 내부 픽셀
  font size와의 대응을 별도 검증한다.

이 정책은 좌표 비율화와 font registry를 같은 PR에 묶자는 뜻이 아니다. 다만 font
size의 기준 단위를 정하지 않으면 업스케일 호환성과 Windows/macOS 호환성이 같은
증상으로 다시 섞인다.

## 구현 순서 제안

1. `scale_project_geometry.py`를 만든다.
   - scale, offset, font scale, 자동 백업 후 덮어쓰기를 지원한다.
   - `TextBlock.xyxy`, `lines`, `_bounding_rect`, `fontformat.font_size`부터 변환한다.
2. 작은 fixture JSON으로 변환 helper 테스트를 만든다.
   - 같은 배율 2x
   - 가로/세로 배율이 다른 경우
   - `_bounding_rect`가 없는 경우
   - old project처럼 `image_info.width/height`가 없는 경우
3. `image_info`에 geometry 기준 크기를 저장하는 정책을 추가한다.
   - 기존 프로젝트는 기본값으로 로드한다.
   - 저장 시 현재 이미지 크기와 기준 크기를 덮어쓸지 여부를 명시한다.
4. UI에서 이미지 크기 불일치를 감지한다.
   - "현재 이미지 크기와 프로젝트 좌표 기준 크기가 다르다"는 상태를 표시한다.
   - 자동 변환은 하지 않고, 사용자가 변환을 승인하는 흐름으로 둔다.
5. `GeometryContext` helper를 도입한다.
   - 렌더링, hit test, crop 경로 중 작은 곳부터 적용한다.
   - 모든 좌표 경로를 한 번에 바꾸지 않는다.
6. normalized 저장은 마지막 단계로 둔다.
   - legacy 절대 좌표와 v2 비율 좌표의 동기화 정책이 정해진 뒤에만 추가한다.

## 열린 질문

- MangaJaNai 업스케일 결과가 항상 정수 배율인지, 페이지마다 배율이 달라질 수 있는지 확인해야 한다.
- 외부 업스케일 후 파일명이 그대로인지, 별도 폴더/파일명으로 관리하는지에 따라
  자동 매칭 전략이 달라진다.
- mask와 inpainted 이미지를 함께 업스케일할지, 새 이미지에서 다시 생성할지 정책이 필요하다.
- rich text HTML 안의 `font-size`가 실제 프로젝트에서 어떤 단위로 저장되는지 샘플로 확인해야 한다.
- `letter_spacing`이 렌더링에서 비율인지 픽셀 거리인지 확인해야 한다.
- 비등방 스케일에서 font size를 평균 배율로 둘지, x/y 중 작은 값으로 둘지 UX 정책이 필요하다.

## 이번 문서의 결론

첫 구현은 변환 스크립트가 맞다. 사용자는 이미 업스케일된 이미지를 갖고 있고, 기존
작업을 살리는 즉시성이 가장 크다. 다만 스크립트는 임시방편으로 남기고, 이후
프로젝트가 page별 기준 이미지 크기를 알고 있도록 만든다. 최종 목표는 런타임에서
기준 좌표계와 현재 이미지 좌표계를 분리하는 것이며, 저장 형식 변경은 그 다음에
작게 진행한다.
