"""Odyssey-2 Pro as a benchmark renderer.

Odyssey takes text only: no keyboard, mouse or camera input. So the authoritative game state reaches it only
through the compiled prompt. One probe family is one stream (the API caps a stream at 150 s), so revisit and
propagation are judged inside one continuous session.

SDK usage follows https://documentation.api.odyssey.ml (Python SDK, `pip install git+https://github.com/odysseyml/odyssey-python.git`):
`Odyssey(api_key=...)`, `connect(on_video_frame=...)`, `start_stream(prompt, portrait=...)`, `interact(prompt)`,
`end_stream()`, `disconnect()`. Frames arrive as RGB uint8 numpy arrays.
"""
from __future__ import annotations

import asyncio
import io
import os
import time

from .probes import ProbeStep

STREAM_LIMIT_S = 150.0
CHANGE_THRESHOLD = 12.0     # mean absolute pixel change that counts as "the picture responded"


class OdysseyAdapter:
    name = "odyssey"

    def __init__(self, api_key: str | None = None, settle_s: float = 5.0, portrait: bool = False):
        self.api_key = api_key or os.environ.get("ODYSSEY_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set ODYSSEY_API_KEY to run the Odyssey adapter.")
        self.settle_s = settle_s
        self.portrait = portrait
        self.client = None
        self.started_at: float | None = None
        self.frames: list[tuple[float, object]] = []      # (arrival time, VideoFrame)
        self.response_s: list[float] = []

    def _on_frame(self, frame) -> None:
        self.frames.append((time.monotonic(), frame))
        if len(self.frames) > 400:
            del self.frames[:200]

    async def open(self, probe: str) -> None:
        from odyssey import Odyssey

        self.client = Odyssey(api_key=self.api_key)
        await self.client.connect(on_video_frame=self._on_frame)
        self.started_at = None
        self.frames.clear()

    def _responded_after(self, t0: float, before) -> float | None:
        """Seconds from the prompt until the picture first moved past the threshold."""
        import numpy as np

        if before is None:
            return None
        ref = before.data.astype(np.int16)
        for t, f in self.frames:
            if t <= t0 or f.data.shape != ref.shape:
                continue
            if float(np.abs(f.data.astype(np.int16) - ref).mean()) >= CHANGE_THRESHOLD:
                return t - t0
        return None

    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]:
        from PIL import Image

        t0 = time.monotonic()
        before = self.frames[-1][1] if self.frames else None
        if self.started_at is None or t0 - self.started_at > STREAM_LIMIT_S - self.settle_s - 5:
            if self.started_at is not None:
                await self.client.end_stream()
            await self.client.start_stream(step.prompt, portrait=self.portrait)
            self.started_at = time.monotonic()
        else:
            await self.client.interact(step.prompt)
        await asyncio.sleep(self.settle_s)
        if not self.frames:
            return None, time.monotonic() - t0
        r = self._responded_after(t0, before)
        if r is not None:
            self.response_s.append(r)
        buf = io.BytesIO()
        Image.fromarray(self.frames[-1][1].data).save(buf, format="PNG")
        return buf.getvalue(), r if r is not None else time.monotonic() - t0

    async def close(self) -> None:
        if self.client is None:
            return
        try:
            if self.started_at is not None:
                await self.client.end_stream()
        finally:
            await self.client.disconnect()
            self.client = None
