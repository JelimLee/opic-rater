"""Command line interface.

    opic transcribe recording.m4a
    opic segment    out/recording.json --questions questions.md
    opic grade      out/recording.answers.md --stats out/recording.stats.md
    opic run        recording.m4a --questions questions.md      # all of the above
"""

from __future__ import annotations

from pathlib import Path

import click

from . import __version__
from . import rate as rate_mod
from . import report as report_mod
from . import segment as segment_mod
from . import transcribe as transcribe_mod

DEFAULT_OUT = "out"


def _read(path: str | Path | None) -> str:
    if not path:
        return ""
    p = Path(path).expanduser()
    return p.read_text(encoding="utf-8") if p.exists() else ""


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="opic")
def cli() -> None:
    """Local-first OPIc practice grader.

    Audio and transcripts stay on this machine. Only `grade --engine api`
    sends text (the transcript) to the Anthropic API.
    """


@cli.command()
@click.argument("audio", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--out", default=DEFAULT_OUT, show_default=True, help="Output directory.")
@click.option("--backend", type=click.Choice(["auto", "mlx", "faster"]), default="auto", show_default=True)
@click.option("--model", default=None, help="Whisper model override.")
@click.option("--language", default="en", show_default=True)
def transcribe(audio: str, out: str, backend: str, model: str | None, language: str) -> None:
    """Transcribe AUDIO locally to JSON with timestamps."""
    click.echo(f"backend: {transcribe_mod.available_backend() if backend == 'auto' else backend}")
    path = transcribe_mod.transcribe(audio, out, backend=backend, model=model, language=language)
    click.secho(f"wrote {path}", fg="green")


@cli.command()
@click.argument("transcript_json", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--out", default=DEFAULT_OUT, show_default=True)
@click.option("--strategy", type=click.Choice(["auto", "silence", "prompt"]), default="auto", show_default=True,
              help="silence = questions played to headphones; prompt = questions on the recording.")
@click.option("--gap", default=segment_mod.DEFAULT_SILENCE_GAP, show_default=True,
              help="Silence in seconds that separates two answers.")
@click.option("--questions", type=click.Path(exists=True, dir_okay=False), default=None,
              help="Markdown list of the real questions, used as labels.")
@click.option("--dry-run", is_flag=True, help="Print detected boundaries and exit.")
def segment(transcript_json: str, out: str, strategy: str, gap: float,
            questions: str | None, dry_run: bool) -> None:
    """Split a transcript into per-question answers."""
    answers = segment_mod.segment(transcript_json, strategy=strategy, gap=gap)
    if not answers:
        raise click.ClickException(
            "No answers detected. Try --strategy silence --gap 8, or check the transcript."
        )
    if questions:
        answers = segment_mod.apply_labels(answers, _read(questions))

    if dry_run:
        for a in answers:
            click.echo(f"  Q{a.index:>2}  {a.stats_line()}  {(a.label or a.prompt or '')[:56]}")
        click.echo(f"\n{len(answers)} answers detected.")
        return

    stem = Path(transcript_json).stem
    out_dir = Path(out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    note = ("Pronunciation is not represented here. Treat repeated phrases and odd "
            "proper nouns as possible transcription artifacts.")
    ans_path = out_dir / f"{stem}.answers.md"
    ans_path.write_text(segment_mod.to_markdown(answers, stem, note), encoding="utf-8")
    stats_path = out_dir / f"{stem}.stats.md"
    stats_path.write_text(segment_mod.stats_table(answers, transcript_json), encoding="utf-8")

    click.secho(f"wrote {ans_path}", fg="green")
    click.secho(f"wrote {stats_path}", fg="green")


@cli.command()
@click.argument("answers_md", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--out", default=DEFAULT_OUT, show_default=True)
@click.option("--stats", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--questions", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--prior", type=click.Path(exists=True, dir_okay=False), default=None,
              help="Previous session's report, to track recurring weaknesses.")
@click.option("--criteria", type=click.Path(file_okay=False), default=None,
              help="Directory of your own reference notes (not redistributed).")
@click.option("--engine", type=click.Choice(["api", "prompts"]), default="api", show_default=True,
              help="prompts = write the prompts to disk instead of calling the API.")
@click.option("--model", default=rate_mod.DEFAULT_MODEL, show_default=True)
@click.option("--effort", type=click.Choice(["low", "medium", "high", "xhigh", "max"]),
              default=rate_mod.DEFAULT_EFFORT, show_default=True)
@click.option("--pdf", is_flag=True, help="Also render a PDF via headless Chrome.")
def grade(answers_md: str, out: str, stats: str | None, questions: str | None,
          prior: str | None, criteria: str | None, engine: str, model: str,
          effort: str, pdf: bool) -> None:
    """Score ANSWERS_MD on four ACTFL axes and write a coaching report."""
    context = rate_mod.build_context(
        transcript=_read(answers_md),
        stats=_read(stats),
        questions=_read(questions),
        prior_report=_read(prior),
        criteria_dir=criteria,
    )
    stem = Path(answers_md).stem.replace(".answers", "")
    out_dir = Path(out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    if engine == "prompts":
        d = out_dir / f"{stem}.prompts"
        d.mkdir(parents=True, exist_ok=True)
        for name, text in rate_mod.assemble(context).items():
            (d / f"{name}.txt").write_text(text, encoding="utf-8")
        click.secho(f"wrote {len(rate_mod.RATERS) + 1} prompts to {d}", fg="green")
        click.echo("Run the five rater prompts, paste their output into 06_synth.txt, run that.")
        return

    click.echo(f"grading with {model} (effort={effort}) — 5 raters in parallel...")
    verdicts, report_md = rate_mod.grade(context, model=model, effort=effort)

    for v in verdicts:
        click.echo(f"  {v.axis:<16} {v.band}")

    md_path = out_dir / f"{stem}.report.md"
    md_path.write_text(report_md, encoding="utf-8")
    click.secho(f"wrote {md_path}", fg="green")

    html_path = report_mod.to_html(report_md, f"OPIc report — {stem}", out_dir / f"{stem}.report.html")
    click.secho(f"wrote {html_path}", fg="green")

    if pdf:
        pdf_path = report_mod.to_pdf(html_path, out_dir / f"{stem}.report.pdf")
        if pdf_path:
            click.secho(f"wrote {pdf_path}", fg="green")
        else:
            click.secho("PDF skipped: no Chrome/Chromium found.", fg="yellow")

    click.secho(
        "\nThis is an LLM estimate for self-study, not an official rating. "
        "Pronunciation was not evaluated.",
        fg="yellow",
    )


@cli.command("run")
@click.argument("audio", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--out", default=DEFAULT_OUT, show_default=True)
@click.option("--questions", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--prior", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--criteria", type=click.Path(file_okay=False), default=None)
@click.option("--strategy", type=click.Choice(["auto", "silence", "prompt"]), default="auto", show_default=True)
@click.option("--gap", default=segment_mod.DEFAULT_SILENCE_GAP, show_default=True)
@click.option("--engine", type=click.Choice(["api", "prompts"]), default="api", show_default=True)
@click.option("--model", default=rate_mod.DEFAULT_MODEL, show_default=True)
@click.option("--effort", type=click.Choice(["low", "medium", "high", "xhigh", "max"]),
              default=rate_mod.DEFAULT_EFFORT, show_default=True)
@click.option("--pdf", is_flag=True)
@click.pass_context
def run_all(ctx: click.Context, audio: str, out: str, questions: str | None,
            prior: str | None, criteria: str | None, strategy: str, gap: float,
            engine: str, model: str, effort: str, pdf: bool) -> None:
    """Transcribe, segment and grade AUDIO in one go."""
    ctx.invoke(transcribe, audio=audio, out=out, backend="auto", model=None, language="en")
    json_path = Path(out).expanduser() / f"{Path(audio).stem}.json"
    ctx.invoke(segment, transcript_json=str(json_path), out=out, strategy=strategy,
               gap=gap, questions=questions, dry_run=False)
    stem = json_path.stem
    ctx.invoke(grade,
               answers_md=str(Path(out) / f"{stem}.answers.md"),
               out=out, stats=str(Path(out) / f"{stem}.stats.md"),
               questions=questions, prior=prior, criteria=criteria,
               engine=engine, model=model, effort=effort, pdf=pdf)


if __name__ == "__main__":
    cli()
