"""The grading pipeline: context assembly, prompt building, output parsing.

Every test runs against the fake client in conftest.py — no network, no key.
"""

from __future__ import annotations

from opic_rater.rate import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    RATERS,
    SHARED_RULES,
    Verdict,
    _extract_band,
    assemble,
    build_context,
    grade,
    rater_prompt,
)

TRANSCRIPT = "## Q1. beach\nI went to the beach last summer."


# --- context assembly ------------------------------------------------------

def test_context_always_carries_the_shared_rules():
    assert SHARED_RULES in build_context(TRANSCRIPT)


def test_optional_blocks_are_omitted_when_empty():
    """An absent stats/questions/prior file must not leave an empty header.

    A labelled but empty section reads to the model as "measured, found
    nothing", which is not the same as "not measured".
    """
    context = build_context(TRANSCRIPT)
    assert "[Fluency proxies" not in context
    assert "[Question list]" not in context
    assert "[Previous session report" not in context


def test_optional_blocks_appear_when_supplied():
    context = build_context(
        TRANSCRIPT, stats="WPM: 120", questions="1. Tell me about the beach.",
        prior_report="last time: IH",
    )
    assert "[Fluency proxies" in context and "WPM: 120" in context
    assert "[Question list]" in context and "Tell me about the beach." in context
    assert "[Previous session report" in context and "last time: IH" in context


def test_fluency_stats_are_labelled_as_non_actfl():
    """The stats header must disclaim itself, or a rater will score WPM."""
    context = build_context(TRANSCRIPT, stats="WPM: 120")
    assert "not ACTFL criteria" in context


def test_criteria_directory_is_injected(tmp_path):
    (tmp_path / "b.md").write_text("second note", encoding="utf-8")
    (tmp_path / "a.md").write_text("first note", encoding="utf-8")
    context = build_context(TRANSCRIPT, criteria_dir=tmp_path)
    assert "Reference criteria supplied by the user" in context
    # Sorted, so the same directory always produces byte-identical context.
    assert context.index("first note") < context.index("second note")


def test_missing_criteria_directory_is_ignored(tmp_path):
    assert "Reference criteria" not in build_context(TRANSCRIPT, criteria_dir=tmp_path / "nope")
    assert "Reference criteria" not in build_context(TRANSCRIPT, criteria_dir=tmp_path)


# --- prompt building -------------------------------------------------------

def test_every_rater_prompt_carries_the_same_context():
    """Comparability rests on this: one context, six prompts."""
    context = build_context(TRANSCRIPT, stats="WPM: 120")
    for _axis, filename in RATERS:
        assert context in rater_prompt(filename, context)


def test_assembled_prompts_are_numbered_in_run_order():
    prompts = assemble(build_context(TRANSCRIPT))
    assert sorted(prompts) == [
        "01_function", "02_accuracy", "03_content_context",
        "04_texttype", "05_holistic", "06_synth",
    ]


def test_assembled_prompts_carry_transcript_and_rules():
    for text in assemble(build_context(TRANSCRIPT)).values():
        assert "I went to the beach last summer." in text
        assert "Pronunciation, stress and intonation are NOT evaluable" in text


def test_offline_synth_prompt_has_a_slot_for_the_verdicts():
    assert "[Rater verdicts]" in assemble(build_context(TRANSCRIPT))["06_synth"]


# --- band parsing ----------------------------------------------------------

def test_band_is_read_from_the_trailing_band_line():
    assert _extract_band("blah IH blah\nmore text\nBAND: AL") == "AL"


def test_trailing_line_wins_over_bands_mentioned_in_prose():
    """Raters quote other levels while reasoning; only the verdict counts."""
    assert _extract_band("could be IM2, argued up to IH\nBAND: AL") == "AL"


def test_band_falls_back_to_a_bare_mention():
    assert _extract_band("no marker but IM2 appears") == "IM2"


def test_unparseable_output_is_reported_not_guessed():
    assert _extract_band("nothing here") == "?"
    assert _extract_band("") == "?"


# --- the graded pipeline, end to end against the fake --------------------

def test_grade_runs_every_rater_plus_one_synthesizer(fake_api):
    verdicts, report = grade(build_context(TRANSCRIPT))
    assert len(fake_api.calls) == len(RATERS) + 1
    assert [v.axis for v in verdicts] == [axis for axis, _ in RATERS]
    assert all(isinstance(v, Verdict) for v in verdicts)
    assert "synthesized coaching text" in report


def test_grade_attaches_each_band_to_the_right_axis(fake_api):
    verdicts, _ = grade(build_context(TRANSCRIPT))
    assert {v.axis: v.band for v in verdicts} == {
        "function": "IH", "accuracy": "AL", "content_context": "AL",
        "texttype": "AL", "holistic": "IH",
    }


def test_grade_keeps_the_full_rater_prose(fake_api):
    verdicts, _ = grade(build_context(TRANSCRIPT))
    assert "quoted evidence for accuracy" in next(
        v.report for v in verdicts if v.axis == "accuracy"
    )


def test_synthesizer_sees_every_verdict(fake_api):
    grade(build_context(TRANSCRIPT))
    synth = fake_api.calls[-1]["messages"][0]["content"]
    for axis, _ in RATERS:
        assert f"=== {axis} (band:" in synth
    assert "quoted evidence for function" in synth


def test_model_and_effort_reach_every_request(fake_api):
    grade(build_context(TRANSCRIPT), model="claude-sonnet-5", effort="low")
    assert {c["model"] for c in fake_api.calls} == {"claude-sonnet-5"}
    assert {c["output_config"]["effort"] for c in fake_api.calls} == {"low"}


def test_defaults_are_the_documented_ones(fake_api):
    grade(build_context(TRANSCRIPT))
    assert fake_api.calls[0]["model"] == DEFAULT_MODEL == "claude-opus-5"
    assert fake_api.calls[0]["output_config"]["effort"] == DEFAULT_EFFORT == "high"
    assert fake_api.calls[0]["thinking"] == {"type": "adaptive"}


def test_a_rater_that_will_not_commit_does_not_get_a_guessed_band(fake_api):
    fake_api.replies = staticmethod(
        lambda prompt: "I cannot judge this from a transcript."
    )
    verdicts, _ = grade(build_context(TRANSCRIPT))
    assert {v.band for v in verdicts} == {"?"}
