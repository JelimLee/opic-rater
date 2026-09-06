"""The reliability harness itself, driven in mock mode.

Mock mode exists so this script can be tested and demonstrated with no key
and no spend. These tests check the reporting maths, not the rater.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reliability_check.py"

_spec = importlib.util.spec_from_file_location("reliability_check", SCRIPT)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def test_capped_rating_takes_the_lowest_criterial_axis():
    """ACTFL does not average: one weak axis caps the whole rating."""
    assert rc.capped_rating({
        "function": "IM2", "accuracy": "AL",
        "content_context": "AL", "texttype": "AL",
    }) == "IM2"


def test_holistic_does_not_cap_the_rating():
    """Holistic is an independent cross-check, not a fifth criterion."""
    assert rc.capped_rating({
        "function": "AL", "accuracy": "AL", "content_context": "AL",
        "texttype": "AL", "holistic": "IL",
    }) == "AL"


def test_identical_runs_report_total_agreement():
    runs = [{"function": "AL", "accuracy": "AL", "content_context": "AL",
             "texttype": "AL", "holistic": "AL"}] * 4
    report = rc.summarize(runs, mocked=False)
    assert "| function | AL | 100% | 1 |" in report
    assert "All five axes identical to run 1: 4/4" in report
    assert "0 band(s) wide" in report


def test_disagreement_shows_up_as_spread():
    runs = [
        {"function": "AL", "accuracy": "AL", "content_context": "AL", "texttype": "AL"},
        {"function": "IM2", "accuracy": "AL", "content_context": "AL", "texttype": "AL"},
    ]
    report = rc.summarize(runs, mocked=False)
    assert "50%" in report
    assert "IM2 to AL" in report


def test_mock_output_is_labelled_as_worthless():
    """A mock number must never be quotable as a result."""
    report = rc.summarize([rc.mock_run(__import__("random").Random(0), 0.2)] * 2, mocked=True)
    assert "MOCK RUN" in report
    assert "Do not quote them as results" in report


def test_mock_is_reproducible_from_the_seed():
    import random
    a = [rc.mock_run(random.Random(7), 0.3) for _ in range(5)]
    b = [rc.mock_run(random.Random(7), 0.3) for _ in range(5)]
    assert a == b


def test_cli_runs_in_mock_mode_without_a_key():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--mock", "-n", "10", "--seed", "1"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "MOCK RUN" in proc.stdout
    assert "Runs: 10." in proc.stdout


def test_a_single_run_is_rejected():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--mock", "-n", "1"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode != 0
    assert "at least 2" in proc.stderr


def test_real_mode_requires_a_sample_file():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode != 0
    assert "sample file is required" in proc.stderr


def test_load_context_accepts_a_whisper_json():
    context = rc.load_context(ROOT / "examples" / "sample_session.json")
    assert "Hard rules for every rater" in context
    assert "## Q1." in context


def test_real_run_path_works_against_the_mocked_api(fake_api):
    """The non-mock path, exercised without spending anything."""
    context = rc.load_context(ROOT / "examples" / "sample_session.json")
    runs = [rc.real_run(context, "claude-opus-5", "low") for _ in range(2)]
    assert runs[0]["function"] == "IH"
    assert rc.capped_rating(runs[0]) == "IH"
    assert "All five axes identical to run 1: 2/2" in rc.summarize(runs, mocked=False)
