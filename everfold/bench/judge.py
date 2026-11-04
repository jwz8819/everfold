"""A vision judge: given one frame and the list of things that are true, which ones does the frame show?

The judge never sees the prompt or the probe's purpose, only the image and neutral claims, so it cannot
reward a model for following text it was given. Calibrate it against human labels before trusting numbers.
"""
from __future__ import annotations

import base64
import json
import logging

from .probes import ProbeStep

log = logging.getLogger("everfold.judge")

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

ANSWERS = ("present", "absent", "unclear")

PAIR_SYSTEM = """Two players stand in the same game world at the same moment, in different places, and look at the same
structure. You get image A (one player's view), image B (the other's), and a description of the structure.
- a: does image A show that structure? present, absent or unclear.
- b: the same for image B.
- same: if both show it, is it recognisably the one structure seen from two sides: the same shape, materials,
  colours and distinctive details, allowing for the different angle and distance? same, different, or unclear.
  Answer different if a player who saw one would not recognise the other as the same thing. If either image
  does not show it, answer unclear.
Judge only what is visible, not the art style. Do not be generous."""

PAIR_SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "string", "enum": ["present", "absent", "unclear"]},
                   "b": {"type": "string", "enum": ["present", "absent", "unclear"]},
                   "same": {"type": "string", "enum": ["same", "different", "unclear"]},
                   "why": {"type": "string"}},
    "required": ["a", "b", "same", "why"],
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

    def _image(self, image: bytes) -> dict:
        return {"type": "image", "source": {"type": "base64", "media_type": media_type(image),
                                            "data": base64.standard_b64encode(image).decode()}}

    async def _ask(self, system: str, content: list, schema: dict) -> dict:
        """One structured call; raises on any failure so callers can fall back to unclear."""
        resp = await self.client.beta.messages.create(
            model=self.model,
            max_tokens=4000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        self.usage["input"] += resp.usage.input_tokens
        self.usage["output"] += resp.usage.output_tokens
        if resp.stop_reason in ("refusal", "max_tokens"):
            raise ValueError(f"stop_reason={resp.stop_reason}")
        return json.loads(next(b.text for b in resp.content if b.type == "text"))

    async def check(self, step: ProbeStep, image: bytes) -> dict[str, str]:
        """Map fact id -> present | absent | unclear. Facts the judge skipped come back unclear."""
        import anthropic

        claims = step.claims
        listing = "\n".join(f"{i + 1}. {f.text}" for i, f in enumerate(claims))
        try:
            out = await self._ask(JUDGE_SYSTEM, [self._image(image), {"type": "text", "text": f"Claims:\n{listing}"}],
                                  JUDGE_SCHEMA)
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

    async def same_object(self, a: bytes, b: bytes, thing: str) -> dict[str, str]:
        """Two players' frames of one shared landmark: does each show it, and is it recognisably the same one?
        Returns {"a": present|absent|unclear, "b": ..., "same": same|different|unclear}."""
        import anthropic

        try:
            out = await self._ask(PAIR_SYSTEM, [{"type": "text", "text": "Image A:"}, self._image(a),
                                                {"type": "text", "text": "Image B:"}, self._image(b),
                                                {"type": "text", "text": f"The structure: {thing}"}], PAIR_SCHEMA)
        except (anthropic.APIStatusError, anthropic.APIConnectionError, ValueError, StopIteration,
                json.JSONDecodeError) as e:
            log.warning("pair judge failed: %s", e)
            self.failures += 1
            return {"a": "unclear", "b": "unclear", "same": "unclear"}
        ok = lambda k, allowed: out.get(k) if out.get(k) in allowed else "unclear"
        return {"a": ok("a", ANSWERS), "b": ok("b", ANSWERS), "same": ok("same", ("same", "different", "unclear"))}
