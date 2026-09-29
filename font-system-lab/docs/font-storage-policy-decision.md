# 폰트 저장명 정책 검토

이 문서는 `font_family` 저장값을 어떤 기준으로 유지할지 결정하기 위한 검토 메모다.
문제는 크게 두 선택지로 나뉜다.

- family group canonical + `font_weight`
- 실제 face canonical + `font_weight`

BT의 기존 project JSON은 `font_family`와 `font_weight`를 별도 필드로 저장한다.
따라서 새 정책은 이 JSON shape를 바꾸지 않고, 두 필드의 의미를 얼마나 강하게
정의할지의 문제이다.

## 현재 구현 상태

현재 브랜치의 구현은 완전한 단일 정책이 아니라 하이브리드에 가깝다.

### 일반 family group

KoPubWorldBatang처럼 폰트 metadata상 family가 하나이고 face가 Light/Medium/Bold로
나뉘는 경우는 다음처럼 저장한다.

```json
{
  "font_family": "KoPubWorldBatang",
  "font_weight": 500
}
```

즉 저장명은 family group canonical이고, 실제 face 선택은 weight와 registry로
복원한다.

### optional pseudo group

Korail Round Gothic처럼 실제 폰트 파일의 family name 자체가
`Korail Round Gothic Light`, `Korail Round Gothic Medium`,
`Korail Round Gothic Bold`처럼 나뉘어 있지만 optional custom group table로
하나의 picker family처럼 보여 주는 경우는 face canonical을 저장한다.

예를 들어 grouped picker에는 `코레일 둥근고딕` 하나로 보일 수 있지만, 저장은
다음처럼 실제 face canonical을 유지한다.

```json
{
  "font_family": "Korail Round Gothic Bold",
  "font_weight": 700
}
```

이때 `font_weight`는 보조 정보로 남는다. 같은 face canonical만으로도 어느 정도
복원 가능하지만, weight UI와 기존 JSON shape를 유지하기 위해 함께 저장한다.

## 선택지 A: family group canonical + weight

예시는 다음과 같다.

```json
{
  "font_family": "KoPubWorldBatang",
  "font_weight": 500
}
```

### 장점

- 기존 BT 저장 모델과 가장 잘 맞는다.
- Qt의 family+style/weight 모델과 자연스럽다.
- 같은 family 안에서 weight를 바꾸는 UI가 단순하다.
- grouped picker와 separate picker를 오가도 저장값이 흔들리지 않는다.
- KoPubWorldBatang처럼 일반적인 font family에는 가장 직관적이다.

### 단점

- 저장된 weight가 실제 face 목록에 없으면 nearest face 정책이 필요하다.
- Qt 또는 OS별 font backend가 같은 family/weight를 다르게 해석할 수 있다.
- 원래 face name 자체가 별도 family인 폰트를 무리하게 group으로 저장하면 잘못
  복원될 수 있다.
- rich text HTML 안의 fragment가 face 이름을 갖고 있을 때 저장 대표값과 fragment
  값이 달라질 수 있다.

## 선택지 B: 실제 face canonical + weight

예시는 다음과 같다.

```json
{
  "font_family": "KoPubWorldBatang Medium",
  "font_weight": 500
}
```

또는 실제 폰트 family가 face별로 나뉘는 경우:

```json
{
  "font_family": "Korail Round Gothic Bold",
  "font_weight": 700
}
```

### 장점

- 특정 face를 더 직접적으로 가리킨다.
- Qt가 family+weight matching을 잘못할 때 우회할 여지가 있다.
- separate face mode와 저장값이 직관적으로 대응한다.
- Korail Round Gothic처럼 실제 family 자체가 face별로 나뉜 폰트에는 안전하다.

### 단점

- 일반 family+weight 모델과 어긋난다.
- 같은 family 안에서 weight를 바꿀 때 `font_family`도 계속 바뀌어야 한다.
- 기존 프로젝트가 기대하는 `font_family` 의미와 멀어진다.
- OS 또는 Qt backend가 face full name을 family로 받지 않으면 오히려 렌더링이
  불안정해질 수 있다.
- grouped picker와 separate picker를 오갈 때 저장값이 더 자주 변한다.
- `font_weight`가 face canonical과 중복 정보가 된다.

## 판단 기준

### metadata가 같은 family임을 명시하는 경우

typographic family 또는 family name이 같고 subfamily/style만 다른 경우에는
family group canonical + weight를 저장하는 것이 맞다.

예:

- `KoPubWorldBatang` + Light/Medium/Bold
- `KoPubWorldDotum` + Light/Medium/Bold

이 경우 face canonical을 저장하면 기존 BT의 family+weight 모델을 불필요하게
깨뜨린다.

### metadata상 family 자체가 나뉘는 경우

폰트 자체가 weight별 family name을 명시하고, 자동 병합 근거가 없는 경우에는
개별 face canonical을 보존하는 것이 맞다.

예:

- `Korail Round Gothic Light`
- `Korail Round Gothic Medium`
- `Korail Round Gothic Bold`

optional custom group table로 picker 표시만 하나로 묶더라도, 저장과 복원에는 원래
face canonical을 유지하는 것이 안전하다.

### 시스템 폰트 alias

시스템 폰트는 Qt가 반환하는 정보만으로 실제 face identity를 안정적으로 알기
어렵다. 따라서 system alias table이 없는 한 자동으로 face canonical을 재정의하지
않는다.

`바탕`/`Batang`처럼 optional alias table로 병합한 경우에도 저장은 table의 canonical
family를 기준으로 한다.

## 현재 권장 정책

현재 PR에서는 하이브리드 정책을 유지하는 것이 가장 안전하다.

```text
1. metadata상 같은 family인 일반 group:
   저장 = family group canonical + font_weight

2. optional custom group table로만 묶인 pseudo group:
   저장 = 실제 face canonical + font_weight

3. system alias table로 병합된 system family:
   저장 = alias table canonical + font_weight

4. 정확한 weight가 없는 기존 저장값:
   표시/렌더링 = nearest face
   저장 rewrite = 하지 않음
```

이 정책은 기존 JSON shape를 유지하면서도, 자동 추론으로 잘못 합치는 위험을 줄인다.

## 남은 질문

### desired weight와 actual face weight

현재 구현은 UI에서 선택 가능한 weight를 registry가 아는 실제 face weight에 맞춘다.
따라서 family에 `300`, `500`, `700` face만 있으면 `400`은 표시/렌더링 시
nearest face인 `500`으로 resolve된다. 이 정책은 "존재하는 face를 정확히 고른다"는
관점에서는 안전하지만, 기존 BT의 Bold 버튼 의미와는 완전히 같지 않다.

기존 인터페이스의 Bold 버튼은 사용자가 "이 글자를 굵게 하라"고 요청하는 명령에
가깝다. 폰트 파일에 Bold face가 없더라도 Qt가 synthetic bold 또는 backend fallback을
시도할 수 있다. 반면 현재 weight picker는 "이 family 안에 실제로 존재하는 face 중
하나를 고른다"는 모델에 가깝다.

따라서 weight에는 두 의미가 섞여 있다.

```text
desired weight:
  사용자가 요청한 굵기이다. 예: Bold 버튼을 눌러 700을 요구한다.

actual face weight:
  registry가 실제 폰트 파일에서 확인한 face weight이다. 예: family에는 500만 있다.
```

현재 PR에서는 이 둘을 분리하지 않는다. `font_weight`는 저장 JSON shape를 유지하기
위한 대표 weight로 쓰이며, UI에서는 가능한 한 actual face weight에 맞춘다. 이 결정은
기존 프로젝트 저장값을 크게 흔들지 않고, grouped/separate picker 매칭을 안정화하는 데
초점을 둔 것이다.

하지만 다음 스테이지에서는 desired weight를 별도 정책으로 다루는 것이 좋다.
예를 들어 family에 `500`만 있는데 사용자가 Bold를 누르면 다음 두 선택지가 있다.

```text
선택지 1: 500 유지
  실제 face 목록에 충실하다. 렌더링 예측성은 높지만 Bold 버튼의 기대와 다르다.

선택지 2: 700* 표시/저장
  사용자의 desired weight를 보존한다. 실제 face는 500을 쓰되 QFont weight는 700을
  요청한다. UI에는 정확한 face가 없음을 `*` 같은 표식으로 보여 준다.
```

얇게 만드는 경우도 같은 문제가 있다. family에 `500`만 있는데 사용자가 `400`을
요구하면 `500`으로 고정할지, `400*`로 보존하고 Qt에 400을 요청할지 결정해야 한다.
Qt backend가 synthetic light를 얼마나 잘 처리하는지는 OS와 버전에 따라 다를 수
있으므로, 이 정책은 별도 검증이 필요하다.

현재 PR에서는 `700*`, `400*` 같은 desired/actual 분리 UI를 넣지 않는다. 이는 font
registry 안정화 범위를 넘어서는 format/weight editing 정책 변경이다. 다만 문서상
결론은 다음과 같이 둔다.

```text
1. 이번 PR:
   actual face weight 기반 picker와 nearest face resolve를 유지한다.

2. 다음 스테이지 후보:
   font_weight를 desired weight로 재정의할지 검토한다.
   실제 face가 없을 때는 nearest actual face + requested QFont weight로 렌더링한다.
   UI에는 `700*`처럼 fallback 상태를 표시한다.

3. 주의:
   이 변경은 Bold 버튼, weight combo, rich text fragment weight, 저장/복원 정책을
   함께 바꾸므로 font registry PR에 섞지 않는 것이 안전하다.
```

### rich text fragment 저장명

현재 rich text HTML의 `font-family`도 저장 시 canonical family로 정규화한다.
이때 일반 group은 group canonical으로 저장된다. face-specific HTML 저장이 필요한지
검토할 수 있지만, `font-weight`가 함께 저장되므로 우선은 family+weight 모델을
유지한다.

### nearest face 선택 후 저장값 rewrite 여부

`KoPubWorldBatang + 400`은 실제 face가 없으므로 UI와 렌더링에서는
`Medium(500)`으로 resolve한다. 하지만 저장값을 자동으로 `500`으로 고쳐 쓰지는
않는다.

자동 rewrite를 하면 기존 프로젝트의 저장값이 사용자가 명시적으로 바꾸지 않았는데
변할 수 있다. PR 초기에는 표시/렌더링만 안정화하고, 저장 rewrite는 사용자가 해당
필드를 실제로 변경했을 때만 일어나게 하는 것이 안전하다.

### PR 설명에 넣을 내용

PR에는 다음처럼 설명하는 것이 좋다.

- 저장 JSON shape는 유지한다.
- 일반 font family는 canonical family + weight로 저장한다.
- metadata상 별도 family인 face를 optional group으로 보여 줄 때는 원래 face
  canonical을 보존한다.
- display name과 storage name은 분리한다.
- 기존 프로젝트의 비정확한 weight는 nearest face로 resolve하지만 자동 rewrite하지
  않는다.
- Bold 버튼처럼 실제 face가 없는 weight를 요청하는 문제는 desired weight와 actual
  face weight를 분리해야 하므로 후속 작업으로 남긴다.
