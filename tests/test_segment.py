import json

from opic_rater.segment import apply_labels, by_prompt, by_silence, to_markdown

LONG = " ".join(["word"] * 40)


def _write(tmp_path, segments):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"text": "", "segments": segments}), encoding="utf-8")
    return p


def test_silence_strategy_splits_on_long_gap(tmp_path):
    segs = [
        {"start": 0, "end": 30, "text": LONG},
        {"start": 60, "end": 95, "text": LONG},
    ]
    answers = by_silence(_write(tmp_path, segs))
    assert len(answers) == 2
    assert answers[0].index == 1 and answers[1].index == 2


def test_short_blocks_are_dropped(tmp_path):
    segs = [
        {"start": 0, "end": 30, "text": LONG},
        {"start": 60, "end": 62, "text": "yeah"},
    ]
    assert len(by_silence(_write(tmp_path, segs))) == 1


def test_prompt_strategy_uses_question_lines(tmp_path):
    segs = [
        {"start": 0, "end": 4, "text": "Tell me about your favourite beach."},
        {"start": 5, "end": 40, "text": LONG},
        {"start": 45, "end": 49, "text": "Have you ever had a problem there?"},
        {"start": 50, "end": 90, "text": LONG},
    ]
    answers = by_prompt(_write(tmp_path, segs))
    assert len(answers) == 2
    assert answers[0].prompt.startswith("Tell me about")


def test_repeated_prompt_line_is_not_an_answer(tmp_path):
    segs = [
        {"start": 0, "end": 4, "text": "Tell me about your favourite beach."},
        {"start": 5, "end": 9, "text": "Tell me about your favourite beach."},
        {"start": 10, "end": 45, "text": LONG},
    ]
    answers = by_prompt(_write(tmp_path, segs))
    assert len(answers) == 1
    assert "Tell me about" not in answers[0].text


def test_labels_are_applied_in_order(tmp_path):
    segs = [
        {"start": 0, "end": 30, "text": LONG},
        {"start": 60, "end": 95, "text": LONG},
    ]
    answers = apply_labels(by_silence(_write(tmp_path, segs)), "- first\n- second\n")
    assert [a.label for a in answers] == ["first", "second"]
    assert "## Q1. first" in to_markdown(answers, "t")


def test_package_exports_do_not_shadow_the_submodule():
    """Regression: `from . import segment` must yield the module, not the function."""
    import opic_rater
    from opic_rater import segment as segment_module

    assert hasattr(segment_module, "DEFAULT_SILENCE_GAP")
    assert callable(opic_rater.segment_answers)


def test_prompt_echo_block_is_dropped(tmp_path):
    """Fast, short, question-shaped blocks are TTS prompt audio, not answers."""
    segs = [
        {"start": 0, "end": 11, "text": " ".join(["word"] * 34) + " changed over the years?"},
        {"start": 40, "end": 90, "text": LONG},
    ]
    answers = by_silence(_write(tmp_path, segs))
    assert len(answers) == 1
    assert answers[0].start == 40


def test_slow_question_shaped_answer_is_kept(tmp_path):
    """A learner answer that happens to end in '?' must not be dropped."""
    segs = [{"start": 0, "end": 60, "text": " ".join(["word"] * 40) + " right?"}]
    assert len(by_silence(_write(tmp_path, segs))) == 1


def test_roleplay_prompt_is_detected(tmp_path):
    segs = [
        {"start": 0, "end": 5, "text": "A friend asks you to go to the park next weekend."},
        {"start": 6, "end": 50, "text": LONG},
        {"start": 55, "end": 60, "text": "You have just discovered that the park will be closed."},
        {"start": 61, "end": 110, "text": LONG},
    ]
    assert len(by_prompt(_write(tmp_path, segs))) == 2
