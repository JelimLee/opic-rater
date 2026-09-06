# opic-rater

**Grade your own OPIc speaking practice on your own machine — and measure the grader.**

내 OPIc 모의고사 녹음을 로컬에서 전사하고, ACTFL 축별로 나눠 채점하고,
**어느 축이 등급을 막고 있는지**를 전사문 인용과 함께 돌려주는 도구.

> 채점기를 만들었으면, 그 채점기가 잘 되는지도 재야 한다.
> 그래서 이 저장소에는 채점기(`src/`)와 **채점기를 재는 도구**(`scripts/`)가 같이 있다.

<sub>**What it is** — A local-first CLI that transcribes an OPIc mock test with a
Whisper model on your machine, splits it into per-question answers, scores each
answer on four ACTFL criteria plus an independent holistic pass using the
Anthropic API, and writes a coaching report in Markdown/HTML/PDF. Audio never
leaves the machine. Ratings are LLM estimates for self-study, not official
ACTFL ratings.</sub>

```bash
opic run recording.m4a --questions questions.md --pdf
```

> ⚠️ **공식 등급이 아니다.** 자습용 LLM 추정치다. 자세한 것은 [NOTICE.md](NOTICE.md).

---

## 문제

OPIc 모의고사를 혼자 보면 **점수는 나오는데 뭘 고쳐야 할지는 안 나온다.**
"IH입니다"는 정보량이 거의 0이다. 다음 주에 뭘 연습해야 하는지를 말해주지 않기 때문이다.

그리고 등급을 그냥 LLM에 물어보면 두 가지가 동시에 망가진다.

1. **평균을 내버린다.** ACTFL은 평균을 내지 않는다.
   [Proficiency Guidelines](https://www.actfl.org/educator-resources/actfl-proficiency-guidelines)는
   한 레벨의 **모든** 기준에서 수행이 유지될 것을 요구한다. 즉 한 축만 Advanced 아래여도
   나머지가 아무리 좋아도 전체가 Advanced 아래로 깎인다. "대충 IH쯤"이라는 답은
   이 규칙을 무시한 결과다.
2. **근거 없이 말한다.** 인용이 없으면 검증할 수 없고, 검증할 수 없으면 연습에 못 쓴다.

이 도구가 푸는 문제는 "등급을 맞히는 것"이 아니라
**"어느 축이 등급을 막았는지, 어느 문장에서 무너졌는지"를 재현 가능하게 짚는 것**이다.

---

## 설계

### 1. 루브릭 분해 — 왜 채점자를 다섯으로 쪼갰나

한 프롬프트에 "ACTFL 기준으로 채점해줘"라고 넣으면 모델은 축들을 섞어서 하나의 인상 점수를 낸다.
그래서 **축마다 독립된 rater를 하나씩** 두고, 각자 자기 축 외에는 판단하지 못하게 했다.

| Rater | 이 축이 보는 것 | 프롬프트 |
|---|---|---|
| **Function** | 문항이 요구한 언어 과제를 실제로 수행했는가 (묘사·과거서사·complication 해결) | `01_function.md` |
| **Accuracy** | 비원어민에 익숙하지 않은 원어민이 이해할 수 있는가, **어디서** 깨지는가 | `02_accuracy.md` |
| **Content / Context** | 이 문항에 대한 진짜 답인가, 어디에 갖다 붙여도 되는 암기 블록인가 | `03_content_context.md` |
| **Text Type** | 문단 길이의 연결된 담화인가, 문장 나열인가 | `04_texttype.md` |
| **Holistic** | 전체 샘플에 대한 독립적인 바닥/천장 판단 | `05_holistic.md` |

앞의 네 개가 **기준 축(criterial axes)**이고, Holistic은 그 넷과 독립적으로 도는
**교차검증**이다. Holistic이 네 축의 결론과 크게 어긋나면 그 자체가 "뭔가 이상하다"는
신호이므로, 기준 축과 섞지 않고 따로 본다.

비평균 규칙은 두 군데에서 강제된다. 하나는 **프롬프트의 하드룰 4번**(`rate.py`의
`SHARED_RULES`)으로, 모든 rater와 종합 패스에 같은 문장이 들어간다. 다른 하나는
**측정 스크립트**로, 거기서는 네 기준 축의 `min`을 코드로 계산한다.

파이프라인 자체는 최종 한 글자를 코드로 확정하지 않는다. 축별 밴드를 그대로 내놓고
종합 패스가 산문으로 설명한다 — **어느 축이 막았는지가 요점이지 한 글자가 요점이 아니기
때문이다.** 한 글자로 줄이는 순간 이 도구가 존재할 이유가 없어진다.

여섯 번째 패스(`06_synth.md`)가 다섯 결과와 전사문을 모두 읽고 학습자용 피드백을 쓴다.

**여섯 호출 모두에 완전히 동일한 컨텍스트 블록이 들어간다.** 축별 결론이 서로 비교
가능하려면 근거가 같아야 하기 때문이다. rater끼리 의견이 갈리면 그건 증거 차이가 아니라
축 프롬프트 차이다. (`tests/test_rate.py::test_every_rater_prompt_carries_the_same_context`)

### 2. 파이프라인

```
recording.m4a
    │
    │  ┌─ 결정적(deterministic) ─────────────────────────────┐
    ├──┤ transcribe   로컬 Whisper (mlx / faster-whisper)    │  오디오 반출 없음
    │  │              → {stem}.json  (start/end/text)        │
    │  │                                                     │
    ├──┤ segment      침묵 기준 또는 프롬프트 기준 분할       │  --dry-run 으로
    │  │              → {stem}.answers.md                    │  경계 먼저 확인
    │  │                                                     │
    ├──┤ fluency      WPM·긴 침묵·필러 카운트                 │  ※ ACTFL 기준 아님
    │  │              → {stem}.stats.md                      │
    │  └─────────────────────────────────────────────────────┘
    │
    │  ┌─ LLM 판단 ──────────────────────────────────────────┐
    ├──┤ build_context  ← answers.md + stats.md + questions   │  동일 바이트
    │  │                  + 이전 회차 리포트 + criteria/       │  6회 호출에 공유
    │  │       ┌───────┬───────┬────────────┬──────────┬──────┴───┐
    │  │       │Function│Accuracy│Content/Ctx│Text Type │Holistic │  ← 병렬 5회
    │  │       └───┬───┴───┬───┴─────┬──────┴────┬─────┴────┬────┘
    │  │           └───────┴─────────┴───────────┴──────────┘
    │  │                            ↓
    │  │                    Synthesizer (06_synth)
    │  └─────────────────────────────────────────────────────┘
    │
    └── {stem}.report.md → .html → .pdf   (로컬 headless Chrome)
```

세션당 API 호출은 **정확히 6회**(rater 5 + 종합 1)다.

### 3. 결정적 처리 vs LLM 판단 — 경계를 어디에 그었나

**세는 것은 코드가, 판단하는 것만 모델이 한다.** 모델에 넘기면 비싸지고, 느려지고,
무엇보다 매번 답이 달라져서 회차 간 비교가 안 되기 때문이다.

| 하는 일 | 누가 | 왜 |
|---|---|---|
| 음성 → 텍스트 | 로컬 Whisper | 오디오를 반출하지 않기 위해. 이 도구의 전제다. |
| 답변 경계 분할 | 코드 (`segment.py`) | 침묵 길이와 문항 개시 패턴은 규칙으로 잡힌다. 규칙이므로 `--dry-run`으로 **채점 전에** 검증할 수 있다. |
| WPM·침묵·필러 | 코드 (`fluency.py`) | 세는 일이다. LLM에 세게 하면 틀리고 비싸다. |
| 등급 판단 | LLM | 여기만. 규칙으로 안 되는 유일한 부분. |
| 비평균(capping) 규칙 | 프롬프트 하드룰 + 측정 스크립트의 `min` | ACTFL 비평균 규칙은 **정책**이지 판단이 아니다. 모델이 매번 재발명하게 두면 안 되므로 모든 프롬프트에 같은 문장으로 박아 넣고, 측정할 때는 코드로 계산한다. |
| Markdown → HTML/PDF | 코드 (`report.py`) | 의존성 없는 로컬 렌더. |

그래서 `src/`의 약 1,000줄 중 LLM을 호출하는 것은 `rate.py` 하나뿐이고,
나머지는 전부 결정적이며 단위 테스트로 덮여 있다.

프롬프트 파일(약 11KB) 자체를 이 프로젝트의 **본체**로 본다. 코드는 그것을 나르는 배관이다.

### 4. 모델 티어 — 왜 Opus / effort=high 인가

기본값은 `claude-opus-5`, `effort=high`, `thinking={"type": "adaptive"}`이다.
(`tests/test_rate.py::test_defaults_are_the_documented_ones`가 이 값들이 README와
어긋나지 않도록 고정한다.)

- **왜 상위 티어인가.** 이 작업은 요약이 아니라 **판단**이다. 축마다 "이 발화가 이 밴드의
  기준을 충족하는가"를 근거 인용과 함께 결정해야 하고, 하위 티어에서는 인용 없는 총평으로
  뭉개지는 경향이 관찰됐다. 값싼 오답은 연습 시간을 잘못된 곳에 쓰게 만들므로,
  이 용도에서는 호출 단가보다 그쪽 비용이 크다.
- **왜 그래도 옵션으로 열어뒀나.** `--model`과 `--effort`로 전부 바꿀 수 있다.
  `--effort low`는 훨씬 싸고 눈에 띄게 무디다. 어느 쪽이 자기 목적에 맞는지는
  아래 신뢰도 스크립트로 **직접 재서** 결정하는 것이 맞다.
- **왜 rater를 병렬로 도는가.** 다섯 축은 서로를 보지 않아야 한다(그게 분해의 요점이다).
  독립이므로 `asyncio.gather`로 동시에 돌려도 결과가 달라지지 않고, 대기 시간만 줄어든다.
- **비용.** 세션당 6회 호출이고, 각 호출의 입력은 전사문 + 해당 축 프롬프트다.
  실제 금액은 모델·effort·녹음 길이에 따라 달라지므로 여기에 숫자를 적지 않는다.
  응답의 `usage`로 직접 확인하는 편이 정확하다.

---

## 신뢰도와 타당도

LLM 채점기의 결과를 믿으려면 최소한 **자기 자신과는 일치하는지**를 재야 한다.
이 저장소에는 그 측정 도구가 들어 있다.

### 검증 스크립트 — `scripts/reliability_check.py`

같은 입력을 **바이트 단위로 동일하게** N번 다시 채점해서 흩어짐을 보고한다.

```bash
# 실제 채점기를 5번 재채점 (API 호출 5 x 6 = 30회, 실제 과금됨)
python scripts/reliability_check.py examples/sample_session.json -n 5

# 하네스만 확인 (키 불필요, 과금 없음)
python scripts/reliability_check.py --mock -n 20
```

보고 내용:

- **축별**: 최빈 밴드, 그 밴드가 나온 비율, 관측된 밴드 분포
- **전체 등급**: 최빈값, 범위(몇 밴드 폭), 밴드 단위 표준편차
- **다섯 축이 전부 1회차와 동일했던 횟수**

여기서 "전체 등급"은 네 기준 축의 **최솟값**이다(평균이 아니다). Holistic은
독립 교차검증이므로 보고는 하되 이 계산에서는 뺀다.
(`tests/test_reliability_check.py::test_holistic_does_not_cap_the_rating`)

### 이 숫자가 말하는 것과 말하지 않는 것

- **재현성(reliability)은 신뢰의 상한이지 정확성의 증거가 아니다.**
  매번 같은 답을 내면서 매번 똑같이 틀릴 수 있다.
- **타당도(validity)는 아직 재지 않았다.** 이 채점기의 밴드가 ACTFL 공인 채점자의
  실제 등급과 얼마나 맞는지는 **측정된 바 없다.** 그러려면 같은 샘플에 대한 공인 등급이
  있어야 하는데 이 저장소에는 없다. 없는 숫자를 지어내는 것보다 없다고 적어두는 편이 낫다.
  공인 등급이 붙은 샘플이 생기면, 위 스크립트와 같은 형태로 사람-모델 일치도를
  추가하는 것이 다음 단계다.
- **앵커 응답도 아직 없다.** 각 밴드의 기준 샘플을 고정해두고 채점기가 그것들을
  올바른 순서로 배열하는지 보는 검사는 구현되어 있지 않다.

**이 README에는 측정되지 않은 성능 수치가 없다.** 위 스크립트를 돌리면 나오는 숫자만
있고, 그 숫자는 각자의 샘플에서 각자 나온다.

---

## 한계

- **발음·강세·억양을 평가하지 않는다.** 채점 입력이 텍스트 전사문이기 때문이다.
  이것들은 ACTFL의 Accuracy 구인에 포함되지만 여기서는 **원리적으로 보이지 않는다.**
  모든 리포트가 이 사실을 명시한다. rater가 어떤 단어를 "알아들을 수 없다"고 표시하면
  그건 판정이 아니라 **직접 오디오를 들어보라는 힌트**다.
- **공인 채점자를 대체하지 않는다.** 공식 등급은 ACTFL 인증 채점자만 매길 수 있다.
- **전사가 나쁘면 결과도 나쁘다.** Whisper는 긴 파일에서 구절을 반복 생성하고
  비원어민 강세를 잘못 옮긴다. rater들은 의심스러운 구간을 깎아내리는 대신
  *verify against audio*로 표시하도록 지시받지만, 큰 감점이 보이면 믿기 전에 확인할 것.
- **한 번의 실행은 한 번의 표본이다.** 위 신뢰도 스크립트를 먼저 돌려보길 권한다.

---

## 설치

```bash
pip install opic-rater[mlx]   # Apple Silicon
pip install opic-rater[cpu]   # 그 외
```

음성 인식은 **로컬에서** 돈다 — Apple Silicon은 `mlx-whisper`, 그 외는 `faster-whisper`.
**오디오는 어디에도 업로드되지 않는다.**

채점에는 Anthropic API 키가 필요하다:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

`.env.example`을 `.env`로 복사해 써도 된다. 키가 없으면 `--engine prompts`로
프롬프트만 뽑아 아무 채팅 UI에 붙여넣으면 된다(아래).

---

## 사용

### 예제로 먼저 돌려보기 (녹음 파일 없이)

`examples/sample_session.json`은 이 저장소용으로 만든 **합성** 전사문이다.
실제 응시자도, 녹음도 아니다. 오디오 없이 파이프라인 전체를 확인할 수 있다.

```bash
$ opic segment examples/sample_session.json --dry-run
  Q 1  <0:34 | 56 words | 99 WPM | 0:10-0:44>  Let's start the interview. Tell me about yourself.
  Q 2  <0:47 | 86 words | 110 WPM | 1:05-1:52>  Tell me about your favourite beach. Where is it, what do
  Q 3  <0:33 | 60 words | 108 WPM | 2:13-2:47>  What do you usually do when you go to the beach? Describ
  Q 4  <0:55 | 100 words | 108 WPM | 3:08-4:03>  Tell me about a memorable experience you had at the beac

4 answers detected.
```

```bash
opic segment examples/sample_session.json --questions examples/questions.md
opic grade   out/sample_session.answers.md --stats out/sample_session.stats.md --engine prompts
```

### 전체 한 번에

```bash
opic run recording.m4a --questions questions.md --pdf
```

### 단계별

```bash
opic transcribe recording.m4a                 # -> out/recording.json
opic segment    out/recording.json --dry-run  # 경계부터 확인
opic segment    out/recording.json --questions questions.md
opic grade      out/recording.answers.md --stats out/recording.stats.md --pdf
```

### 녹음을 답변 단위로 나누는 전략

어떻게 녹음했느냐가 전략을 정한다. `--dry-run`을 먼저 돌려볼 것.

| 이렇게 녹음했다면 | 이걸 쓴다 | 왜 |
|---|---|---|
| 문항을 이어폰으로 들음 — 테이프에 내 목소리만 | `--strategy silence` | 답변은 긴 침묵 사이의 발화 구간. `--gap 10`으로 조정. |
| 문항이 스피커로 나와 같이 녹음됨 | `--strategy prompt` | 답변은 감지된 문항 뒤에 오는 부분. |
| 모르겠다 | `--strategy auto` (기본값) | 둘 다 해보고 답변을 더 많이 찾은 쪽을 쓴다. |

`--questions questions.md`로 실제 문항을 넣어주면 Function rater가 훨씬 날카로워진다.
과제 수행 여부는 **과제가 뭔지 알아야** 판단할 수 있기 때문이다.
형식은 [examples/questions.md](examples/questions.md) 참고.

### 회차 간 추적

```bash
opic grade out/session3.answers.md --prior out/session2.report.md
```

종합 패스가 이전 리포트와 비교해서 **반복된 약점 / 해결된 약점 / 새로 생긴 약점**을
구분해준다. 행동으로 옮길 가치가 있는 건 "반복됐는데 아직 안 고쳐진" 목록이다.

### API 키 없이

```bash
opic grade out/recording.answers.md --engine prompts
# -> out/recording.prompts/01_function.txt ... 06_synth.txt
```

rater 프롬프트 5개를 아무 채팅 UI에서 돌리고, 결과를 `06_synth.txt`에 붙여넣어 다시 돌린다.
**API 경로와 완전히 같은 프롬프트다.** 과금 없음.

### 알아둘 만한 옵션

| 플래그 | 기본값 | 설명 |
|---|---|---|
| `--model` | `claude-opus-5` | Anthropic 모델 ID 아무거나. |
| `--effort` | `high` | `low`…`max`. `low`는 훨씬 싸고 눈에 띄게 무디다. |
| `--gap` | `13` | 답변을 가르는 침묵 길이(초). |
| `--criteria DIR` | – | 내 참고 노트를 rater마다 주입. gitignore됨 — [NOTICE.md](NOTICE.md) 참고. |
| `--pdf` | off | headless Chrome이 있으면 PDF까지 렌더. |

---

## 무엇이 이 기기 밖으로 나가는가

| 단계 | 밖으로 나가는 것 |
|---|---|
| `transcribe` | 없음. 로컬 모델. |
| `segment` | 없음. |
| `grade --engine prompts` | 없음. |
| `grade --engine api` | **전사문 텍스트**, 문항, 통계 — Anthropic API로 전송. |

**오디오는 어떤 경로로도 업로드되지 않는다.** `recordings/`, `transcripts/`, `reports/`,
`out/`, `criteria/`와 흔한 오디오 확장자는 gitignore되어 있어서 연습 세션이 실수로
커밋되지 않는다.

---

## 프로젝트 구조

```
src/opic_rater/
  cli.py          click CLI — transcribe / segment / grade / run
  transcribe.py   로컬 STT (mlx-whisper | faster-whisper)   ── 결정적
  segment.py      답변 분할 (침묵 / 문항 감지) + 라벨링       ── 결정적
  fluency.py      WPM·침묵·필러 프록시 (ACTFL 기준 아님)      ── 결정적
  rate.py         컨텍스트 조립 · rater 병렬 실행 · 밴드 파싱  ── 유일한 LLM 호출 지점
  report.py       Markdown → 자체완결 HTML → PDF             ── 결정적
  prompts/        01_function … 06_synth (한국어)  ← 이 프로젝트의 본체
scripts/
  reliability_check.py   같은 샘플 N회 재채점 → 흩어짐 보고
tests/            67 tests. conftest.py가 Anthropic 클라이언트를 대역으로 바꾼다
examples/         합성 전사문 + 문항 목록 (오디오 없이 실행 가능)
```

## 개발

```bash
git clone https://github.com/JelimLee/opic-rater && cd opic-rater
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest        # 67 passed — 네트워크·API 키 불필요
ruff check .
```

전체 테스트 스위트는 **API를 호출하지 않는다.** `tests/conftest.py`가
`anthropic.AsyncAnthropic`을 기록형 대역으로 바꾸고, 모든 요청을 검사할 수 있게 남긴다.

`src/opic_rater/prompts/`의 rater 프롬프트가 이 프로젝트의 실질이다.
OPIc을 보는 사람들이 한국어 화자이므로 프롬프트도 한국어로 쓰여 있다.
프롬프트를 고칠 거라면 PR에 **어느 전사문에서 판정이 어떻게 바뀌었는지** 적어달라.
프롬프트 수정은 하기는 쉽고 평가하기는 어렵다.

## 라이선스

MIT — [LICENSE](LICENSE), [NOTICE.md](NOTICE.md) 참고.
ACTFL Proficiency Guidelines는 재배포하지 않는다. 상표·비공식 고지는 NOTICE.md에.
