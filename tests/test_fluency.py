"""Fluency proxies. Explicitly not scores — see fluency.py's module docstring."""

from opic_rater.fluency import analyse


def _seg(start, end, text):
    return {"start": start, "end": end, "text": text}


def test_empty_input_is_zeroed():
    stats = analyse([])
    assert stats.words == 0
    assert stats.wpm_wall_clock == 0.0


def test_counts_words_and_wpm():
    segs = [_seg(0, 30, "one two three four five six seven eight nine ten")]
    stats = analyse(segs)
    assert stats.words == 10
    assert round(stats.wpm_wall_clock) == 20


def test_detects_long_pause_between_segments():
    segs = [_seg(0, 5, "hello there"), _seg(20, 25, "back again")]
    stats = analyse(segs)
    assert len(stats.long_pauses) == 1
    assert stats.long_pauses[0] == (5.0, 15.0)


def test_short_gap_is_not_a_pause():
    segs = [_seg(0, 5, "hello"), _seg(5.4, 8, "there")]
    assert analyse(segs).long_pauses == []


def test_speech_only_wpm_excludes_silence():
    segs = [_seg(0, 10, "a b c d"), _seg(50, 60, "e f g h")]
    stats = analyse(segs)
    assert stats.wpm_speech_only > stats.wpm_wall_clock


def test_as_dict_round_trips_every_field():
    stats = analyse([_seg(0, 10, "one two three")])
    assert stats.as_dict()["words"] == 3
    assert set(stats.as_dict()) == {
        "total_sec", "speech_sec", "words", "wpm_wall_clock",
        "wpm_speech_only", "long_pauses", "filler_count",
    }


def test_render_disclaims_itself():
    """This text goes into a prompt; it has to carry its own warning."""
    assert "NOT an ACTFL criterion" in analyse([_seg(0, 10, "a b c")]).render()
