# opic-rater

Grade your own OPIc speaking practice on your own machine.

Record a mock test, run one command, get a report that tells you **which axis is
holding your rating down** and quotes the exact sentence where it broke.

```bash
opic run recording.m4a --questions questions.md --pdf
```

```
backend: mlx
wrote out/recording.json
wrote out/recording.answers.md
wrote out/recording.stats.md
grading with claude-opus-5 (effort=high) — 5 raters in parallel...
  function         IH
  accuracy         AL
  content_context  AL
  texttype         AL
  holistic         IH
wrote out/recording.report.md
wrote out/recording.report.html
wrote out/recording.report.pdf
```

> **This is not an official rating.** It is an LLM estimate for self-study.
> See [NOTICE.md](NOTICE.md).

---

## Why the axes matter more than the number

ACTFL does not average. The [Proficiency
Guidelines](https://www.actfl.org/educator-resources/actfl-proficiency-guidelines)
require performance sustained across **all** criteria of a level — so a single
axis below Advanced caps you below Advanced no matter how strong the rest is.

That is the whole point of this tool. A single letter grade tells you nothing
actionable. Five independent raters, one per axis, tell you *where to spend your
practice time*. In the run above, vocabulary and discourse structure were already
Advanced; the rating was held down by task completion on description questions.
Nothing about studying more vocabulary would have moved it.

Each rater scores one axis and nothing else:

| Rater | Asks |
|---|---|
| **Function** | Did you actually perform the task the question set — narrate, describe, resolve the complication? |
| **Accuracy** | Would a native speaker unused to non-natives understand you, and where does that break? |
| **Content / Context** | Is this a real answer to *this* question, or a memorized block that could go anywhere? |
| **Text Type** | Paragraph-length connected discourse, or a string of sentences? |
| **Holistic** | An independent floor/ceiling judgement over the whole sample. |

A sixth pass reads all five and writes the coaching report: the moments that cost
you the rating, rewrites in your own words, and a short measurable practice list.

---

## Install

```bash
pip install opic-rater[mlx]   # Apple Silicon
pip install opic-rater[cpu]   # everything else
```

Speech-to-text runs locally — `mlx-whisper` on Apple Silicon, `faster-whisper`
elsewhere. **Your audio is never uploaded.**

Grading needs an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

No key? Use `--engine prompts` and paste into any chat UI (see below).

---

## Use

### Everything at once

```bash
opic run recording.m4a --questions questions.md --pdf
```

### Or step by step

```bash
opic transcribe recording.m4a                 # -> out/recording.json
opic segment    out/recording.json --dry-run  # check the boundaries first
opic segment    out/recording.json --questions questions.md
opic grade      out/recording.answers.md --stats out/recording.stats.md --pdf
```

### Splitting the recording into answers

How you recorded determines the strategy, and `--dry-run` is worth running first:

| You recorded | Use | Why |
|---|---|---|
| Questions through headphones — tape has only your voice | `--strategy silence` | Answers are the speech runs between long silences. Tune with `--gap 10`. |
| Questions out loud — tape has the examiner too | `--strategy prompt` | Answers are what follows each detected question. |
| Not sure | `--strategy auto` (default) | Tries both, keeps whichever finds more answers. |

`--questions questions.md` labels each block with the real question, which makes
the Function rater far sharper — it can only judge task completion if it knows
the task. See [examples/questions.md](examples/questions.md).

### Tracking progress across sessions

```bash
opic grade out/session3.answers.md --prior out/session2.report.md
```

The synthesizer compares against the previous report and tells you which
weaknesses recurred, which closed, and which are new. Recurring-but-unfixed is
the list worth acting on.

### No API key

```bash
opic grade out/recording.answers.md --engine prompts
# -> out/recording.prompts/01_function.txt ... 06_synth.txt
```

Run the five rater prompts in any chat UI, paste their output into `06_synth.txt`,
run that. Same prompts, no spend.

---

## What it will not do

- **Pronunciation, stress, intonation.** Grading reads a transcript. These are
  part of ACTFL's Accuracy construct and are simply not visible here. Every
  report says so. If a rater flags a word as unintelligible, that is a hint to
  listen to the audio yourself, not a verdict.
- **Replace a certified rater.** Only ACTFL-certified humans assign official
  ratings.
- **Survive bad transcription.** Whisper invents repeated phrases on long files
  and mangles non-native stress. The raters are instructed to flag suspicious
  spans as *verify against audio* rather than score them down, but check anything
  that looks like a big deduction before believing it.

---

## What leaves your machine

| Step | Leaves the machine |
|---|---|
| `transcribe` | Nothing. Local model. |
| `segment` | Nothing. |
| `grade --engine prompts` | Nothing. |
| `grade --engine api` | The **transcript text**, questions, and stats — sent to the Anthropic API. |

Audio is never uploaded by any path. `recordings/`, `transcripts/`, `reports/`,
`out/` and common audio extensions are gitignored so a practice session cannot be
committed by accident.

---

## Options worth knowing

| Flag | Default | Notes |
|---|---|---|
| `--model` | `claude-opus-5` | Any Anthropic model id. |
| `--effort` | `high` | `low` … `max`. `low` is much cheaper and noticeably blunter. |
| `--gap` | `13` | Seconds of silence that separate two answers. |
| `--criteria DIR` | – | Your own reference notes, injected into every rater. Gitignored — see [NOTICE.md](NOTICE.md). |
| `--pdf` | off | Renders via headless Chrome if installed. |

Cost is roughly a few cents to a few tens of cents per 30-minute session,
depending on model and effort.

---

## Library use

```python
from opic_rater import segment_answers, analyse_file
from opic_rater.rate import build_context, grade

answers = segment_answers("out/recording.json", strategy="auto")
stats = analyse_file("out/recording.json")

verdicts, report = grade(build_context(
    transcript="\n\n".join(f"{a.header()}\n{a.text}" for a in answers),
    stats=stats.render(),
))
print({v.axis: v.band for v in verdicts})
```

---

## Development

```bash
git clone https://github.com/OWNER/opic-rater && cd opic-rater
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

The rater prompts in `src/opic_rater/prompts/` are the substance of this project.
They are written in Korean because that is who takes OPIc. If you improve one,
say in the PR **which transcript it changed the verdict on and how** — prompt
edits are easy to make and hard to evaluate.

## License

MIT — see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
