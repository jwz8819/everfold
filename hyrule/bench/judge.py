"""A vision judge: given one frame and the list of things that are true, which ones does the frame show?

The judge never sees the prompt or the probe's purpose, only the image and neutral claims, so it cannot
reward a model for following text it was given. Calibrate it against human labels before trusting numbers.
"""
from __future__ import annotations

import base64
import json
import logging

from .probes import ProbeStep

log = logging.getLogger("hyrule.judge")

JUDGE_SYSTEM = """You check whether an image shows specific things. You get one image and a numbered list of claims.
For each claim answer:
- present: the image clearly shows it.
- absent: the image clearly does not show it, or shows something that contradicts it.
- unclear: the image is too blurry, dark or ambiguous to decide.
Judge only what is visible. Claims describe a stylized game world, so judge the thing, not the art style.
A claim about a specific person's clothing or props is present only if a figure with those details is visible.
Do not be generous: a vaguely similar object is not present."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object",
        "properties": {"n": {"type": "integer"}, "verdict": {"type": "string", "enum": ["present", "absent", "unclear"]},
                       "why": {"type": "string"}},
        "required": ["n", "verdict", "why"],
        "additionalProperties": False,
    }}},
    "required": ["verdicts"],
    "additionalProperties": False,
}

JUDGE_MODEL = "claude-opus-5-5"


def media_type(img: bytes) -> str:
    if img[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if img[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if img[:4] == b"RIFF" and img[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("unsupported image format")


class Judge:
    def __init__(self, client, model: str = JUDGE_MODEL):
        self.client = client
        self.model = model
        self.usage = {"input": 0, "output": 0}
        self.failures = 0

    async def check(self, step: ProbeStep, image: bytes) -> dict[str, str]:
        """Map fact id -> present | absent | unclear. Facts the judge skipped come back unclear."""
        import anthropic

        claims = step.view.facts
        listing = "\n".join(f"{i + 1}. {f.text}" for i, f in enumerate(claims))
        try:
            resp = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                system=[{"type": "text", "text": JUDGE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type(image),
                                                 "data": base64.standard_b64encode(image).decode()}},
                    {"type": "text", "text": f"Claims:\n{listing}"},
                ]}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            self.usage["input"] += resp.usage.input_tokens
            self.usage["output"] += resp.usage.output_tokens
            if resp.stop_reason in ("refusal", "max_tokens"):
                raise ValueError(f"stop_reason={resp.stop_reason}")
            out = json.loads(next(b.text for b in resp.content if b.type == "text"))
        except (anthropic.APIStatusError, anthropic.APIConnectionError, ValueError, StopIteration,
                json.JSONDecodeError) as e:
            log.warning("judge failed on %s: %s", step.id, e)
            self.failures += 1
            return {f.id: "unclear" for f in claims}
        verdicts = {f.id: "unclear" for f in claims}
        for v in out.get("verdicts", []):
            n = v.get("n")
            if isinstance(n, int) and 1 <= n <= len(claims) and v.get("verdict") in ("present", "absent", "unclear"):
                verdicts[claims[n - 1].id] = v["verdict"]
        return verdicts
