"""Run the five raters in parallel, then synthesize a coaching report.

Two engines:

`api`      Calls the Anthropic API. Five raters run concurrently, then a
           synthesizer reads all five verdicts and writes the report.

`prompts`  Writes the fully assembled prompts to disk and stops. Paste them into
           any chat UI. No API key, no spend, same prompts.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    from anthropic import AsyncAnthropic

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "high"
MAX_TOKENS = 32_000

RATERS: list[tuple[str, str]] = [
    ("function", "01_function.md"),
    ("accuracy", "02_accuracy.md"),
    ("content_context", "03_content_context.md"),
    ("texttype", "04_texttype.md"),
    ("holistic", "05_holistic.md"),
]
SYNTH_PROMPT = "06_synth.md"

BAND_RE = re.compile(r"\b(AL|IH|IM3|IM2|IM1|IL|NH|NM|NL)\b")

SHARED_RULES = """
[Hard rules for every rater]
1. Every claim must quote the transcript. No quote, no finding.
2. Pronunciation, stress and intonation are NOT evaluable here — the input is a
   text transcript. Say so explicitly rather than guessing.
3. Automatic-transcription artifacts are not speaker errors. Repeated phrases,
   restarts, and odd proper nouns may come from the recognizer. Flag anything
   suspicious as "verify against audio" instead of scoring it down.
4. Do not average the axes. ACTFL requires performance sustained across ALL
   criteria of a level; one axis below Advanced caps the rating below Advanced.
5. End your report with a line exactly of the form:  BAND: <AL|IH|IM3|IM2|IM1>
""".strip()


@dataclass
class Verdict:
    """One rater's judgement on one axis.

    `band` is the ACTFL level parsed out of the rater's own trailing
    `BAND:` line, or `"?"` if it did not emit one. `report` is the full
    prose, which is what the synthesizer actually reads — the band is a
    convenience for the CLI summary, not the product.
    """

    axis: str
    band: str
    report: str


def _prompt_text(name: str) -> str:
    return resources.files("opic_rater.prompts").joinpath(name).read_text(encoding="utf-8")


def _criteria_block(criteria_dir: str | Path | None) -> str:
    if not criteria_dir:
        return ""
    d = Path(criteria_dir).expanduser()
    if not d.is_dir():
        return ""
    parts = [p.read_text(encoding="utf-8") for p in sorted(d.glob("*.md"))]
    if not parts:
        return ""
    return "\n\n[Reference criteria supplied by the user]\n" + "\n\n".join(parts)


def build_context(
    transcript: str,
    stats: str = "",
    questions: str = "",
    prior_report: str = "",
    criteria_dir: str | Path | None = None,
) -> str:
    """Assemble the one context block every rater and the synthesizer share.

    Identical bytes go to all six calls, which is what makes the five axis
    verdicts comparable to each other: any disagreement between raters is
    attributable to the axis prompt, not to differing evidence.

    Only `transcript` is required. `stats` are fluency proxies, explicitly
    labelled as non-ACTFL so a rater does not score words-per-minute.
    `questions` sharpen the Function rater, which cannot judge task
    completion without knowing the task. `prior_report` turns the
    synthesizer into a progress tracker. `criteria_dir` injects the user's
    own reference notes, which are never redistributed (see NOTICE.md).
    """
    blocks = [SHARED_RULES, "", "[Transcript, segmented by question]", transcript]
    if stats:
        blocks += ["", "[Fluency proxies — not ACTFL criteria, context only]", stats]
    if questions:
        blocks += ["", "[Question list]", questions]
    if prior_report:
        blocks += [
            "",
            "[Previous session report — track whether the same weaknesses recur]",
            prior_report,
        ]
    crit = _criteria_block(criteria_dir)
    if crit:
        blocks.append(crit)
    return "\n".join(blocks)


def rater_prompt(axis_file: str, context: str) -> str:
    """Glue one axis prompt onto the shared context block."""
    return f"{_prompt_text(axis_file)}\n\n---\n\n{context}"


def assemble(context: str) -> dict[str, str]:
    """Build every prompt as text, for the keyless `--engine prompts` path.

    Returns `{file stem: full prompt}`, numbered so they sort in run order.
    The synthesizer entry carries a placeholder where the API path splices
    in the real verdicts, so the two engines run identical prompts.
    """
    out = {f.removesuffix(".md"): rater_prompt(f, context) for _axis, f in RATERS}
    out["06_synth"] = (
        f"{_prompt_text(SYNTH_PROMPT)}\n\n---\n\n{context}\n\n"
        "[Rater verdicts]\nPaste the five rater outputs here before running this prompt."
    )
    return out


def _extract_band(text: str) -> str:
    """Pull the ACTFL band out of a rater's reply.

    Prefers the trailing `BAND: <level>` line the shared rules mandate.
    Falls back to the first band-shaped token anywhere in the text, and
    finally to `"?"` — a rater that would not commit is reported as such
    rather than silently defaulting to a level.
    """
    for line in reversed(text.strip().splitlines()):
        if line.upper().startswith("BAND:"):
            m = BAND_RE.search(line)
            if m:
                return m.group(1)
    m = BAND_RE.search(text)
    return m.group(1) if m else "?"


async def _one(
    client: AsyncAnthropic, model: str, effort: str, axis: str, prompt: str
) -> Verdict:
    """Run a single axis rater to completion and parse its band."""
    async with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = await stream.get_final_message()
    text = "".join(b.text for b in message.content if b.type == "text")
    return Verdict(axis=axis, band=_extract_band(text), report=text)


async def _grade_async(
    context: str, model: str, effort: str
) -> tuple[list[Verdict], str]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic()

    verdicts = await asyncio.gather(
        *(
            _one(client, model, effort, axis, rater_prompt(f, context))
            for axis, f in RATERS
        )
    )

    joined = "\n\n".join(
        f"=== {v.axis} (band: {v.band}) ===\n{v.report}" for v in verdicts
    )
    synth_prompt = (
        f"{_prompt_text(SYNTH_PROMPT)}\n\n---\n\n{context}\n\n[Rater verdicts]\n{joined}"
    )
    async with client.messages.stream(
        model=model,
        max_tokens=64_000,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        messages=[{"role": "user", "content": synth_prompt}],
    ) as stream:
        message = await stream.get_final_message()
    report = "".join(b.text for b in message.content if b.type == "text")
    return list(verdicts), report


def grade(
    context: str, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT
) -> tuple[list[Verdict], str]:
    """Run every axis rater, then the synthesizer, against one context block.

    Blocking wrapper around the async pipeline. Returns the per-axis
    verdicts and the synthesized coaching report as markdown.
    """
    return asyncio.run(_grade_async(context, model, effort))
