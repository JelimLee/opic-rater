# examples

## `sample_session.json`

**합성 데이터다.** 이 저장소를 위해 작성한 가짜 전사문이고, 실제 응시자도 실제 녹음도
아니다. 개인정보가 들어 있지 않다.

Whisper가 내놓는 것과 같은 모양(`{"text": ..., "segments": [{"start", "end", "text"}]}`)
이라서, **오디오 파일이나 STT 모델 없이** 파이프라인 전체를 돌려볼 수 있다.

문항 4개(자기소개 + 해변 콤보 3개)가 들어 있고, 문항 음성이 같이 녹음된 형태라
두 분할 전략이 모두 동작한다 — `--strategy auto`(문항 감지)와 `--strategy silence`가
각각 답변 4개를 찾는다.

```bash
# 경계 확인
opic segment examples/sample_session.json --dry-run

# 답변/통계 파일 쓰기
opic segment examples/sample_session.json --questions examples/questions.md

# API 키 없이 프롬프트만 뽑기
opic grade out/sample_session.answers.md --stats out/sample_session.stats.md --engine prompts

# 채점기 재현성 측정 (실제 API 호출 — 과금됨)
python scripts/reliability_check.py examples/sample_session.json -n 5
```

## `questions.md`

`--questions`에 넘기는 문항 목록의 형식 예시.

한 줄에 한 문항, 물어본 순서대로. 불릿은 `-`, `*`, `1.` 아무거나 된다.
그 외의 줄(제목·메모)은 전부 무시되므로 메모를 같이 적어둬도 된다.

문항을 넣어주면 Function rater가 훨씬 날카로워진다. 과제를 수행했는지는
**과제가 뭔지 알아야** 판단할 수 있기 때문이다.
