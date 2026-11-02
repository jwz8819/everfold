"""One place that talks to Claude. Every caller passes a scripted fallback, so the game never waits on a model."""
from __future__ import annotations

import asyncio
import json
import logging
import os

log = logging.getLogger("everfold.llm")

DEFAULT_MODEL = os.environ.get("EVERFOLD_MODEL", "claude-opus-5-5")


class LLM:
    """Structured-output JSON calls with usage accounting. `client=None` means scripted content only."""

    def __init__(self, client=None, model: str = DEFAULT_MODEL, effort: str = "low", timeout: float = 20.0):
        self.client = client
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.calls = 0
        self.failures = 0
        self.usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    @property
    def enabled(self) -> bool:
        return self.client is not None

    async def json(self, system: str, payload: dict, schema: dict, max_tokens: int = 4000) -> dict | None:
        """Return the parsed object, or None on any failure so the caller can fall back."""
        if self.client is None:
            return None
        import anthropic

        self.calls += 1
        try:
            resp = await asyncio.wait_for(self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": json.dumps(payload, sort_keys=True, ensure_ascii=False)}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ), timeout=self.timeout)
            u = resp.usage
            self.usage["input"] += u.input_tokens
            self.usage["output"] += u.output_tokens
            self.usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
            self.usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
            if resp.stop_reason in ("refusal", "max_tokens"):
                raise ValueError(f"stop_reason={resp.stop_reason}")
            text = next(b.text for b in resp.content if b.type == "text")
            out = json.loads(text)
            if not isinstance(out, dict):
                raise ValueError("expected a JSON object")
            return out
        except asyncio.TimeoutError:
            log.warning("model call timed out after %ss", self.timeout)
        except anthropic.RateLimitError as e:
            log.warning("rate limited: %s", e)
        except anthropic.APIStatusError as e:
            log.warning("API error %s: %s", e.status_code, e.message)
        except anthropic.APIConnectionError as e:
            log.warning("connection error: %s", e)
        except (ValueError, StopIteration, json.JSONDecodeError) as e:
            log.warning("unusable model output: %s", e)
        self.failures += 1
        return None


def make_client():
    """An async client if credentials exist, else None. Never raises."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    try:
        import anthropic
        return anthropic.AsyncAnthropic()
    except Exception as e:  # missing package or bad config: run scripted
        log.warning("Claude client unavailable, running scripted content: %s", e)
        return None
