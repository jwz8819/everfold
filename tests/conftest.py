import json
from types import SimpleNamespace

import pytest


class FakeClaude:
    """Stands in for anthropic.AsyncAnthropic. `replies` is a list of dicts (JSON bodies) or callables(kw)->dict."""

    def __init__(self, *replies, stop_reason="end_turn"):
        self.replies = list(replies)
        self.calls = []
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **kw):
        self.calls.append(kw)
        body = self.replies.pop(0) if self.replies else {}
        if callable(body):
            body = body(kw)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="thinking", thinking=""),
                     SimpleNamespace(type="text", text=json.dumps(body))],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=80, cache_read_input_tokens=900,
                                  cache_creation_input_tokens=0))


@pytest.fixture
def fake_claude():
    return FakeClaude
