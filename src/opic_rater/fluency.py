"""Quantitative fluency proxies extracted from a Whisper JSON transcript.

None of these are ACTFL criteria. ACTFL defines proficiency by *what the speaker
can do*, not by words per minute. These numbers exist only to (a) locate silence
that may coincide with a communication breakdown and (b) let a learner compare
one session against their own earlier sessions.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

WORD_RE = re.compile(r"[A-Za-z']+")
FILLER_RE = re.compile(r"\b(um+|uh+|erm*|hmm+|like,|you know,)\b", re.IGNORECASE)

LONG_PAUSE_SEC = 1.5


@dataclass
class FluencyStats:
    """Timing and word-count proxies for one run of transcript segments.

    Deliberately not a score. See the module docstring: these numbers
    locate places worth listening to, they do not rate anything.
    """

    total_sec: float
    speech_sec: float
    words: int
    wpm_wall_clock: float
    wpm_speech_only: float
    long_pauses: list[tuple[float, float]] = field(default_factory=list)
    filler_count: int = 0

    def as_dict(self) -> dict:
        """Plain-dict form, for logging or JSON serialization."""
        return asdict(self)

    def render(self) -> str:
        """Format as the fixed-width block that gets pasted into a prompt.

        Carries its own "NOT an ACTFL criterion" warnings, because this
        text ends up in front of an LLM that would otherwise be happy to
        treat words-per-minute as evidence of proficiency.
        """
        pauses = ", ".join(f"{at:.0f}s({dur:.1f}s)" for at, dur in self.long_pauses[:12])
        more = "" if len(self.long_pauses) <= 12 else f" (+{len(self.long_pauses) - 12} more)"
        return "\n".join(
            [
                f"duration          : {self.total_sec:.0f}s ({self.total_sec / 60:.1f} min)",
                f"speech time       : {self.speech_sec:.0f}s (silence excluded)",
                f"words             : {self.words}",
                f"WPM (wall clock)  : {self.wpm_wall_clock:.0f}   <- proxy only, NOT an ACTFL criterion",
                f"WPM (speech only) : {self.wpm_speech_only:.0f}",
                f"pauses >= {LONG_PAUSE_SEC}s   : {len(self.long_pauses)}"
                + (f" at {pauses}{more}" if self.long_pauses else ""),
                f"fillers (approx)  : {self.filler_count}"
                " <- lower bound; Whisper strips many disfluencies",
            ]
        )


def _segments(data: dict) -> list[dict]:
    segs = data.get("segments") or []
    return [s for s in segs if "start" in s and "end" in s]


def analyse(segments: list[dict], full_text: str = "") -> FluencyStats:
    """Compute fluency proxies for one contiguous run of Whisper segments."""
    if not segments:
        return FluencyStats(0.0, 0.0, 0, 0.0, 0.0)

    start = segments[0]["start"]
    total = segments[-1]["end"] - start
    words = 0
    speech = 0.0
    pauses: list[tuple[float, float]] = []
    prev_end: float | None = None

    for seg in segments:
        words += len(WORD_RE.findall(seg.get("text", "")))
        speech += seg["end"] - seg["start"]
        if prev_end is not None:
            gap = seg["start"] - prev_end
            if gap >= LONG_PAUSE_SEC:
                pauses.append((round(prev_end, 1), round(gap, 1)))
        prev_end = seg["end"]

    text = full_text or " ".join(s.get("text", "") for s in segments)
    return FluencyStats(
        total_sec=total,
        speech_sec=speech,
        words=words,
        wpm_wall_clock=words / (total / 60) if total else 0.0,
        wpm_speech_only=words / (speech / 60) if speech else 0.0,
        long_pauses=pauses,
        filler_count=len(FILLER_RE.findall(text)),
    )


def analyse_file(json_path: str | Path) -> FluencyStats:
    """Compute fluency proxies for a whole Whisper JSON transcript."""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return analyse(_segments(data), data.get("text", ""))
