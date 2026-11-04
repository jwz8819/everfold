"""Decart Lucy Restyle on fal as a benchmark renderer: the engine draws the geometry, the model restyles it.

The "engine renders, model restyles" integration pattern. For each probe family the engine renders one continuous
greybox clip from the true state (render/greybox.py): it holds at each probe pose and walks the camera between
poses, as a player would. Lucy restyles the whole clip in one call (`decart/lucy-restyle`, billed per second of
video), and each step's frame is taken from the restyled clip at the end of that step's hold. Lucy is a batch
video model on fal, not a stream, so the adapter renders a family's clip before its first frame is asked for
(`prepare`); a realtime version of the same model exists on Decart's own platform.

The prompt carries only the art direction and what stays true for the whole clip (the people and landmarks), never
a state change: whether a felled tree becomes a stump has to come from the geometry. With `per_player`, each
player's steps get their own clip (the two-player condition; cross_view only).

Requires FAL_KEY.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import math
import time
from fractions import Fraction

from aiohttp import ClientSession, ClientTimeout

from .. import config as C
from ..render.greybox import FACING_HEADING, H, W, outfit_color, render
from ..render.view import LANDMARK_CLAIMS
from .probes import ProbeStep

log = logging.getLogger("everfold.lucy")

APP = "decart/lucy-restyle"
QUEUE_URL = "https://queue.fal.run"
PRICE_PER_S = 0.01          # fal page, 2026-11-04
FPS = 16
LEAD_S, HOLD_S = 1.5, 1.5   # still camera before the first step, and at every step
WALK_TILES_PER_S, TURN_RAD_PER_S = 3.0, math.pi / 2
MAX_WALK_S = 4.0


def _turn(a: float, b: float) -> float:
    return (b - a + math.pi) % (2 * math.pi) - math.pi


def plan_clip(steps: list[ProbeStep]) -> tuple[list[tuple[ProbeStep, float, float, float]], dict[str, float]]:
    """Camera frames for one clip, as (step whose world is shown, x, y, heading), and when each step is sampled."""
    frames, sample = [], {}
    prev = None
    for s in steps:
        x, y, h = s.view.x, s.view.y, FACING_HEADING[s.view.facing]
        if prev is not None:
            px, py, ph = prev
            dist, turn = math.hypot(x - px, y - py), _turn(ph, h)
            walk = min(max(dist / WALK_TILES_PER_S, abs(turn) / TURN_RAD_PER_S), MAX_WALK_S)
            n = round(walk * FPS)
            for i in range(1, n + 1):
                t = i / n
                frames.append((s, px + (x - px) * t, py + (y - py) * t, ph + turn * t))
        hold = LEAD_S + HOLD_S if prev is None else HOLD_S
        frames += [(s, x, y, h)] * round(hold * FPS)
        sample[s.id] = (len(frames) - 2) / FPS          # just before the end of the hold
        prev = (x, y, h)
    return frames, sample


def encode(frames: list[tuple[ProbeStep, float, float, float]]) -> bytes:
    import av

    buf = io.BytesIO()
    with av.open(buf, mode="w", format="mp4") as out:
        stream = out.add_stream("libx264", rate=FPS)
        stream.width, stream.height, stream.pix_fmt = W, H, "yuv420p"
        stream.options = {"crf": "18", "preset": "veryfast"}
        cache: dict[tuple, object] = {}
        for s, x, y, h in frames:
            key = (s.id, round(x, 3), round(y, 3), round(h, 4))
            if key not in cache:
                cache = {key: render(s.scene, x, y, h, outfit_color(s.view.signature))}
            for packet in stream.encode(av.VideoFrame.from_image(cache[key])):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return buf.getvalue()


def decode(video: bytes) -> list[tuple[float, object]]:
    """(seconds, PIL image) for every frame."""
    import av

    out = []
    with av.open(io.BytesIO(video)) as c:
        stream = c.streams.video[0]
        for frame in c.decode(stream):
            t = float(frame.pts * stream.time_base) if frame.pts is not None else len(out) / FPS
            out.append((t, frame.to_image()))
    return out


def prompt_for(steps: list[ProbeStep]) -> str:
    """Art direction plus the people and landmarks of the clip: things true throughout, never a state change."""
    seen, things = set(), []
    for s in steps:
        for x in s.view.seen:
            # a landmark whose description carries its state (the shrine's gate) gets its stateless claim instead
            label = LANDMARK_CLAIMS.get(x.id.split(":", 1)[0], x.label) if x.kind == "landmark" else x.label
            if x.kind in ("person", "landmark") and label not in seen:
                seen.add(label)
                things.append(label)
    people = sorted({s.view.signature for s in steps})
    return (f"Restyle this blocky game render into a {C.STYLE_ANCHOR}. The player character is "
            f"{' / '.join(people)}, seen from behind. In the world: {'; '.join(things) or 'open countryside'}. "
            "Keep every building, tree, rock, person and object exactly where it is and keep the camera motion; "
            "turn the simple shapes into detailed versions of what they are.")[:2000]


class LucyAdapter:
    def __init__(self, api_key: str | None = None, per_player: bool = False, queue_url: str = QUEUE_URL,
                 poll_s: float = 3.0, timeout_s: float = 900.0):
        from .. import falproxy

        self.key = api_key or falproxy.fal_key()
        if not self.key:
            raise RuntimeError("Set FAL_KEY to run Lucy Restyle on fal.")
        self.per_player = per_player
        self.name = "lucy-greybox" + ("-2p" if per_player else "")
        self.queue_url, self.poll_s, self.timeout_s = queue_url.rstrip("/"), poll_s, timeout_s
        self.http: ClientSession | None = None
        self.frames: dict[str, bytes] = {}
        self.cost = 0.0
        self.clips = 0
        self.clip_seconds = 0.0
        self.wait_s: list[float] = []
        self.errors: list[str] = []

    @property
    def headers(self) -> dict:
        return {"authorization": f"Key {self.key}", "content-type": "application/json", "accept": "application/json"}

    async def _json(self, method: str, url: str, body: dict | None = None) -> dict:
        async with self.http.request(method, url, json=body, headers=self.headers,
                                     timeout=ClientTimeout(total=120)) as r:
            text = await r.text()
            if r.status >= 400:
                raise RuntimeError(f"{url} -> HTTP {r.status}: {text[:300]}")
            return json.loads(text)

    async def restyle(self, video: bytes, prompt: str, seed: int) -> bytes:
        """Submit to fal's queue, wait, download the restyled clip."""
        body = {"prompt": prompt, "video_url": "data:video/mp4;base64," + base64.b64encode(video).decode(),
                "enhance_prompt": False, "seed": seed}
        job = await self._json("POST", f"{self.queue_url}/{APP}", body)
        t0 = time.monotonic()
        while True:
            status = await self._json("GET", job["status_url"])
            if status.get("status") == "COMPLETED":
                break
            if time.monotonic() - t0 > self.timeout_s:
                raise TimeoutError(f"lucy job {job.get('request_id')} not done after {self.timeout_s:.0f}s")
            await asyncio.sleep(self.poll_s)
        self.wait_s.append(time.monotonic() - t0)
        result = await self._json("GET", job["response_url"])
        async with self.http.get(result["video"]["url"], timeout=ClientTimeout(total=300)) as r:
            r.raise_for_status()
            return await r.read()

    async def _clip(self, steps: list[ProbeStep], seed: int) -> None:
        frames, sample = plan_clip(steps)
        video = encode(frames)
        seconds = len(frames) / FPS
        try:
            styled = decode(await self.restyle(video, prompt_for(steps), seed))
        except Exception as e:          # noqa: BLE001 - a failed clip is missing frames, not a crashed run
            self.errors.append(f"{steps[0].id}: {type(e).__name__}: {e}")
            return
        self.clips += 1
        self.clip_seconds += seconds
        self.cost += seconds * PRICE_PER_S
        scale = (styled[-1][0] + 1 / FPS) / seconds if styled else 1.0       # output may be retimed
        for sid, t in sample.items():
            _, img = min(styled, key=lambda f: abs(f[0] - t * scale))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            self.frames[sid] = buf.getvalue()

    async def prepare(self, steps: list[ProbeStep]) -> None:
        """Render and restyle every clip of the run before any frame is asked for (clips run concurrently)."""
        if self.http is None:
            self.http = ClientSession()
        groups: dict[tuple, list[ProbeStep]] = {}
        for s in steps:
            groups.setdefault((s.probe, s.player) if self.per_player else (s.probe,), []).append(s)
        await asyncio.gather(*(self._clip(g, seed=i) for i, g in enumerate(groups.values())))

    async def open(self, probe: str) -> None:
        return None

    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]:
        return self.frames.get(step.id), 0.0

    async def close(self) -> None:
        return None

    async def aclose(self) -> None:
        if self.http is not None:
            await self.http.close()
            self.http = None

    def stats(self) -> dict:
        return {"model": APP, "per_player": self.per_player, "clips": self.clips,
                "clip_seconds": round(self.clip_seconds, 1), "est_cost_usd": round(self.cost, 4),
                "mean_wait_seconds": round(sum(self.wait_s) / len(self.wait_s), 1) if self.wait_s else None,
                "errors": self.errors[:10]}
