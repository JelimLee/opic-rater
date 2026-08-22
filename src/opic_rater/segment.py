"""Split a whole-test recording into per-question answers.

Two strategies, because the two ways people record a mock test differ:

`silence`  The prompt audio went to headphones, so the recording holds only the
           test-taker's voice with long silences where the questions played.
           Answers are the speech runs between those silences.

`prompt`   The prompt audio was picked up by the mic, so the transcript contains
           the examiner's questions. Answers are what follows each question.

Neither is perfect. `opic segment --dry-run` prints the proposed boundaries so
you can eyeball them before grading, and `--questions` lets you supply the real
question list to label the blocks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .fluency import analyse

# Openers used by OPIc prompt audio. Matched only near the start of a segment.
PROMPT_RE = re.compile(
    r"^\W*(let'?s start|tell me (?:about|what|more)|describe |please (?:describe|compare|tell)|"
    r"what (?:do|did|kind|activities|chores|types|are|was|were)|who (?:do|did|is|was|were)|"
    r"when (?:was|did|do)|where (?:do|did|is)|how (?:has|have|did|do|was|were|often|about)|"
    r"why (?:do|did|is|are)|have you ever|has your|can you (?:tell|recall|describe)|could you|"
    r"i'?d like (?:you|to)|i'?m sorry,? but|i want you to|you (?:indicated|mentioned|have just|are)|"
    r"a friend (?:asks|has|invited|wants)|imagine |pretend |in your background survey|"
    r"that'?s the end of|give me as many details)",
    re.IGNORECASE,
)

# Synthesized prompt audio is read fast, is short, and is phrased as a question.
# A learner answer that hits all three at once does not really happen, so blocks
# matching all of them are treated as prompt echo rather than speech.
PROMPT_ECHO_WPM = 160.0
PROMPT_ECHO_MAX_SEC = 20.0

DEFAULT_SILENCE_GAP = 13.0
MIN_ANSWER_SEC = 8.0
MIN_ANSWER_WORDS = 12


@dataclass
class Answer:
    index: int
    start: float
    end: float
    text: str
    prompt: str | None = None
    label: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def wpm(self) -> float:
        return self.words / (self.duration / 60) if self.duration else 0.0

    def header(self) -> str:
        name = self.label or self.prompt or f"Answer {self.index}"
        return f"## Q{self.index}. {name}"

    def stats_line(self) -> str:
        m, s = divmod(int(self.duration), 60)
        return (
            f"<{m}:{s:02d} | {self.words} words | {self.wpm:.0f} WPM | "
            f"{_ts(self.start)}-{_ts(self.end)}>"
        )


def _ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def _load(json_path: str | Path) -> list[dict]:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return [s for s in (data.get("segments") or []) if "start" in s and "end" in s]


def _looks_like_prompt_echo(segs: list[dict]) -> bool:
    dur = segs[-1]["end"] - segs[0]["start"]
    if dur <= 0 or dur > PROMPT_ECHO_MAX_SEC:
        return False
    text = " ".join(s.get("text", "").strip() for s in segs).strip()
    words = len(text.split())
    wpm = words / (dur / 60)
    return wpm >= PROMPT_ECHO_WPM and text.endswith("?")


def _keep(segs: list[dict]) -> bool:
    if not segs:
        return False
    dur = segs[-1]["end"] - segs[0]["start"]
    words = sum(len(s.get("text", "").split()) for s in segs)
    if dur < MIN_ANSWER_SEC or words < MIN_ANSWER_WORDS:
        return False
    return not _looks_like_prompt_echo(segs)


def _mk(idx: int, segs: list[dict], prompt: str | None = None) -> Answer:
    return Answer(
        index=idx,
        start=segs[0]["start"],
        end=segs[-1]["end"],
        text=" ".join(s.get("text", "").strip() for s in segs).strip(),
        prompt=prompt,
    )


def by_silence(json_path: str | Path, gap: float = DEFAULT_SILENCE_GAP) -> list[Answer]:
    segs = _load(json_path)
    blocks: list[list[dict]] = []
    current: list[dict] = []
    for seg in segs:
        if current and seg["start"] - current[-1]["end"] >= gap:
            blocks.append(current)
            current = []
        current.append(seg)
    if current:
        blocks.append(current)
    return [_mk(i, b) for i, b in enumerate((b for b in blocks if _keep(b)), start=1)]


def by_prompt(json_path: str | Path) -> list[Answer]:
    segs = _load(json_path)
    marks = [i for i, s in enumerate(segs) if PROMPT_RE.match(s.get("text", "").strip())]
    if not marks:
        return []

    answers: list[Answer] = []
    idx = 1
    for n, start_i in enumerate(marks):
        stop_i = marks[n + 1] if n + 1 < len(marks) else len(segs)
        body = segs[start_i + 1 : stop_i]
        # Repeated prompt lines (OPIc plays each question twice) are not answers.
        body = [s for s in body if not PROMPT_RE.match(s.get("text", "").strip())]
        if not _keep(body):
            continue
        answers.append(_mk(idx, body, prompt=segs[start_i].get("text", "").strip()))
        idx += 1
    return answers


def segment(json_path: str | Path, strategy: str = "auto", gap: float = DEFAULT_SILENCE_GAP) -> list[Answer]:
    if strategy == "silence":
        return by_silence(json_path, gap)
    if strategy == "prompt":
        return by_prompt(json_path)
    if strategy != "auto":
        raise ValueError(f"unknown strategy: {strategy}")

    prompt_based = by_prompt(json_path)
    silence_based = by_silence(json_path, gap)
    # Prompt detection is more precise when the questions were actually recorded.
    return prompt_based if len(prompt_based) >= len(silence_based) else silence_based


def apply_labels(answers: list[Answer], questions_md: str) -> list[Answer]:
    """Attach human question labels from a markdown list (one item per line).

    Lines starting with `-`, `*`, or `N.` are treated as questions, in order.
    """
    items = [
        re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        for line in questions_md.splitlines()
        if re.match(r"^\s*(?:[-*]|\d+[.)])\s+\S", line)
    ]
    for answer, label in zip(answers, items):
        answer.label = label
    return answers


def to_markdown(answers: list[Answer], title: str, note: str = "") -> str:
    out = [f"# {title}", ""]
    if note:
        out += [note, ""]
    total = sum(a.duration for a in answers)
    out += [
        f"{len(answers)} answers | {total / 60:.1f} min total speaking",
        "",
    ]
    for a in answers:
        out += ["---", a.header(), a.stats_line(), ""]
        if a.prompt and a.label:
            out += [f"> heard prompt: {a.prompt}", ""]
        out += [a.text, ""]
    return "\n".join(out)


def stats_table(answers: list[Answer], json_path: str | Path) -> str:
    overall = analyse(_load(json_path))
    rows = [
        "# Fluency proxies (NOT ACTFL criteria)",
        "",
        overall.render(),
        "",
        "## Per answer",
        "",
        "| # | duration | words | WPM | label |",
        "|---|---|---|---|---|",
    ]
    for a in answers:
        m, s = divmod(int(a.duration), 60)
        label = (a.label or a.prompt or "")[:60]
        rows.append(f"| {a.index} | {m}:{s:02d} | {a.words} | {a.wpm:.0f} | {label} |")
    return "\n".join(rows)
