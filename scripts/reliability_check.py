#!/usr/bin/env python3
"""Measure how much this rater disagrees with itself.

A grader is an instrument, and an instrument nobody has measured is a
guess with a number attached. This script does the cheapest useful
measurement: re-rate one unchanged sample N times and report the spread.

    python scripts/reliability_check.py examples/sample_session.json -n 5
    python scripts/reliability_check.py --mock -n 200      # no key, no spend

WHAT THIS MEASURES
    Test-retest reliability of the rater under a fixed input: given
    identical bytes, how often does it return the identical band? That is
    an upper bound on how much any single run can be trusted. A rater that
    cannot reproduce its own verdict cannot be measuring anything stable.

WHAT THIS DOES NOT MEASURE
    Validity — whether the band is *correct*. Perfect agreement with
    itself is perfectly compatible with being consistently wrong, and this
    script cannot tell the difference. Only a human ACTFL-certified rating
    of the same sample can, and that comparison is not implemented here
    because it needs data this repository does not have. See the README's
    limits section.

`--mock` replaces the API with a seeded random band generator. It exercises
the reporting path only, so the harness can be tested and demonstrated with
no key and no spend. Numbers produced under `--mock` say nothing whatever
about the real rater; they are labelled as such in the output.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from opic_rater.rate import RATERS, build_context, grade  # noqa: E402
from opic_rater.segment import segment, stats_table, to_markdown  # noqa: E402

# Worst to best. Used to order output and to apply the ACTFL capping rule.
BAND_ORDER = ["?", "NL", "NM", "NH", "IL", "IM1", "IM2", "IM3", "IH", "AL"]

# Holistic is an independent whole-sample judgement, not one of the four
# criterial axes, so it is reported but excluded from the cap.
CRITERIAL_AXES = [axis for axis, _ in RATERS if axis != "holistic"]


def load_context(path: Path) -> str:
    """Build a grading context from either a `.answers.md` or a Whisper `.json`."""
    if path.suffix == ".json":
        answers = segment(path, strategy="auto")
        if not answers:
            raise SystemExit(f"No answers detected in {path}.")
        return build_context(
            transcript=to_markdown(answers, path.stem),
            stats=stats_table(answers, path),
        )
    return build_context(transcript=path.read_text(encoding="utf-8"))


def capped_rating(bands: dict[str, str]) -> str:
    """Lowest of the four criterial axes.

    ACTFL does not average: performance must be sustained across all
    criteria of a level, so one axis below Advanced caps the whole rating
    below Advanced. `min` over the axis bands is that rule.
    """
    return min((bands[a] for a in CRITERIAL_AXES if a in bands), key=BAND_ORDER.index)


def real_run(context: str, model: str, effort: str) -> dict[str, str]:
    verdicts, _report = grade(context, model=model, effort=effort)
    return {v.axis: v.band for v in verdicts}


def mock_run(rng: random.Random, drift: float) -> dict[str, str]:
    """Seeded stand-in: each axis sits on a true band and slips by `drift`."""
    truth = {"function": "IH", "accuracy": "AL", "content_context": "AL",
             "texttype": "AL", "holistic": "IH"}
    out = {}
    for axis, true_band in truth.items():
        i = BAND_ORDER.index(true_band)
        if rng.random() < drift:
            step = rng.choice([-1, 1])
            # Reflect at the ends of the scale rather than clamping, so a
            # slip at AL is still visible as a slip.
            if not 1 <= i + step < len(BAND_ORDER):
                step = -step
            i += step
        out[axis] = BAND_ORDER[i]
    return out


def _agreement(values: list[str]) -> tuple[str, float]:
    """Modal value and the fraction of runs that produced it."""
    mode, count = Counter(values).most_common(1)[0]
    return mode, count / len(values)


def summarize(runs: list[dict[str, str]], *, mocked: bool) -> str:
    n = len(runs)
    lines = [
        "# Rater reliability — test-retest on one unchanged sample",
        "",
        f"Runs: {n}. Same input bytes every time.",
        "",
    ]
    if mocked:
        lines += [
            "> **MOCK RUN.** Bands came from a seeded random generator, not "
            "from the model. These numbers measure this script, not the "
            "rater. Do not quote them as results.",
            "",
        ]

    lines += ["## Per axis", "",
              "| axis | modal band | agreement | distinct bands | observed |",
              "|---|---|---|---|---|"]
    for axis, _ in RATERS:
        values = [r.get(axis, "?") for r in runs]
        mode, share = _agreement(values)
        spread = sorted(set(values), key=BAND_ORDER.index)
        observed = ", ".join(f"{b}x{values.count(b)}" for b in spread)
        lines.append(f"| {axis} | {mode} | {share:.0%} | {len(spread)} | {observed} |")

    ratings = [capped_rating(r) for r in runs]
    mode, share = _agreement(ratings)
    indices = [BAND_ORDER.index(b) for b in ratings]
    exact = sum(1 for r in runs if all(r.get(a) == runs[0].get(a) for a, _ in RATERS))

    lines += [
        "",
        "## Overall rating (lowest criterial axis — ACTFL does not average)",
        "",
        f"- Modal rating: **{mode}** in {share:.0%} of runs",
        f"- Range: {BAND_ORDER[min(indices)]} to {BAND_ORDER[max(indices)]} "
        f"({max(indices) - min(indices)} band(s) wide)",
        f"- Spread: {statistics.pstdev(indices):.2f} bands (population SD, band steps)",
        f"- All five axes identical to run 1: {exact}/{n}",
        "",
        "## How to read this",
        "",
        "Agreement is an upper bound on trust, not evidence of correctness:",
        "a rater that reproduces its own verdict every time may still be",
        "consistently wrong. Validity against a certified human rating is a",
        "separate question this script does not answer.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Re-rate one sample N times and report the spread.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("sample", nargs="?", type=Path,
                   help="A .answers.md file, or a Whisper .json to segment first.")
    p.add_argument("-n", "--runs", type=int, default=5, help="Number of re-rates (default 5).")
    p.add_argument("--model", default="claude-opus-5")
    p.add_argument("--effort", default="high",
                   choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--mock", action="store_true",
                   help="Seeded fake bands. No API key, no spend. Tests this script only.")
    p.add_argument("--seed", type=int, default=0, help="Mock seed (default 0).")
    p.add_argument("--drift", type=float, default=0.2,
                   help="Mock per-axis slip probability (default 0.2).")
    p.add_argument("-o", "--out", type=Path, default=None, help="Write the report here too.")
    args = p.parse_args(argv)

    if args.runs < 2:
        p.error("--runs must be at least 2; reliability needs something to compare.")

    if args.mock:
        rng = random.Random(args.seed)
        runs = [mock_run(rng, args.drift) for _ in range(args.runs)]
    else:
        if not args.sample:
            p.error("a sample file is required unless --mock is given")
        if not args.sample.exists():
            p.error(f"no such file: {args.sample}")
        context = load_context(args.sample)
        print(
            f"Re-rating {args.sample} {args.runs}x with {args.model} "
            f"(effort={args.effort}). This calls the API "
            f"{args.runs * (len(RATERS) + 1)} times and costs real money.",
            file=sys.stderr,
        )
        runs = [real_run(context, args.model, args.effort) for _ in range(args.runs)]

    report = summarize(runs, mocked=args.mock)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
