"""CLI surface: the commands the README tells people to type.

`grade` is exercised against the fake client from conftest.py, so the whole
suite still runs with no key and no network.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from opic_rater.cli import cli

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_session.json"
QUESTIONS = EXAMPLE.parent / "questions.md"


def test_help_lists_every_command():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for command in ("transcribe", "segment", "grade", "run"):
        assert command in result.output


def test_module_entry_point_works():
    """`python -m opic_rater --help` must work, not just the console script."""
    proc = subprocess.run(
        [sys.executable, "-m", "opic_rater", "--help"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert "Local-first OPIc practice grader" in proc.stdout


def test_dry_run_reports_boundaries_without_writing(tmp_path):
    result = CliRunner().invoke(
        cli, ["segment", str(EXAMPLE), "--dry-run", "-o", str(tmp_path)]
    )
    assert result.exit_code == 0
    assert "4 answers detected." in result.output
    assert list(tmp_path.iterdir()) == []


def test_segment_writes_answers_and_stats(tmp_path):
    result = CliRunner().invoke(
        cli, ["segment", str(EXAMPLE), "-o", str(tmp_path), "--questions", str(QUESTIONS)]
    )
    assert result.exit_code == 0
    answers = (tmp_path / "sample_session.answers.md").read_text(encoding="utf-8")
    stats = (tmp_path / "sample_session.stats.md").read_text(encoding="utf-8")
    assert "## Q1. Let's start the interview. Tell me about yourself." in answers
    assert "NOT ACTFL criteria" in stats


def test_segment_failure_suggests_a_next_step(tmp_path):
    """A silent 'no answers' is useless; the error must say what to try."""
    empty = tmp_path / "empty.json"
    empty.write_text('{"text": "", "segments": []}', encoding="utf-8")
    result = CliRunner().invoke(cli, ["segment", str(empty), "-o", str(tmp_path)])
    assert result.exit_code != 0
    assert "--strategy silence" in result.output


def test_prompts_engine_writes_six_prompts_and_never_calls_the_api(tmp_path):
    answers = tmp_path / "s.answers.md"
    answers.write_text("## Q1. beach\nI went to the beach.", encoding="utf-8")
    result = CliRunner().invoke(
        cli, ["grade", str(answers), "-o", str(tmp_path), "--engine", "prompts"]
    )
    assert result.exit_code == 0
    written = sorted(p.name for p in (tmp_path / "s.prompts").iterdir())
    assert written == [
        "01_function.txt", "02_accuracy.txt", "03_content_context.txt",
        "04_texttype.txt", "05_holistic.txt", "06_synth.txt",
    ]


def test_grade_writes_report_and_prints_every_band(tmp_path, fake_api):
    answers = tmp_path / "s.answers.md"
    answers.write_text("## Q1. beach\nI went to the beach.", encoding="utf-8")
    result = CliRunner().invoke(cli, ["grade", str(answers), "-o", str(tmp_path)])
    assert result.exit_code == 0
    assert "function         IH" in result.output
    assert (tmp_path / "s.report.md").read_text(encoding="utf-8").startswith("# Report")
    assert (tmp_path / "s.report.html").exists()


def test_grade_always_prints_the_disclaimer(tmp_path, fake_api):
    """The 'not an official rating' line is a promise made in NOTICE.md."""
    answers = tmp_path / "s.answers.md"
    answers.write_text("## Q1. beach\nI went to the beach.", encoding="utf-8")
    result = CliRunner().invoke(cli, ["grade", str(answers), "-o", str(tmp_path)])
    assert "not an official rating" in result.output
    assert "Pronunciation was not evaluated" in result.output
