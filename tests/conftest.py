"""Shared fakes.

The grading pipeline is the part of this package worth testing hardest and
the part that costs money to run, so every test here drives it through a
stand-in for `anthropic.AsyncAnthropic`. Nothing in the suite touches the
network or reads an API key.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from opic_rater import rate


class FakeAnthropic:
    """Minimal stand-in for `AsyncAnthropic` covering the surface rate.py uses.

    Records every request in `calls` so tests can assert on what was sent,
    and answers each one from `replies`, a callable taking the prompt text
    and returning the assistant text to hand back.
    """

    #: populated per-instance, but tests reach for it on the class because
    #: rate.py constructs the client itself.
    calls: list[dict] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs):
        type(self).calls.append(kwargs)
        prompt = kwargs["messages"][0]["content"]
        return _FakeStreamContext(type(self).replies(prompt))


class _FakeStreamContext:
    def __init__(self, text: str) -> None:
        self._text = text

    async def __aenter__(self):
        return SimpleNamespace(get_final_message=self._final)

    async def __aexit__(self, *_exc):
        return False

    async def _final(self):
        return SimpleNamespace(
            content=[
                # A thinking block the parser must ignore, alongside the text.
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=self._text),
            ]
        )


def _axis_of(prompt: str) -> str:
    """Recover which axis a prompt belongs to by matching its prompt file."""
    for axis, filename in rate.RATERS:
        if rate._prompt_text(filename).splitlines()[0] in prompt:
            return axis
    return "synth"


@pytest.fixture
def fake_api(monkeypatch):
    """Patch `anthropic.AsyncAnthropic` and return the recording fake.

    By default each axis rater answers with a fixed band (`function` says
    IH, everyone else says AL) and the synthesizer returns a stub report.
    Override `fake_api.replies` for a different script.
    """
    bands = {
        "function": "IH",
        "accuracy": "AL",
        "content_context": "AL",
        "texttype": "AL",
        "holistic": "IH",
    }

    def replies(prompt: str) -> str:
        axis = _axis_of(prompt)
        if axis == "synth":
            return "# Report\n\nsynthesized coaching text"
        return f"quoted evidence for {axis}\n\nBAND: {bands[axis]}"

    FakeAnthropic.calls = []
    FakeAnthropic.replies = staticmethod(replies)
    monkeypatch.setattr("anthropic.AsyncAnthropic", FakeAnthropic)
    # A stray real key in the environment must not change what the tests do.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    return FakeAnthropic
