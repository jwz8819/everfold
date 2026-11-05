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

from aiohttp import ClientSession, ClientTimeout

from .. import config as C
from ..render.greybox import FACING_HEADING, H, W, outfit_color, render
from ..render.view import LANDMARK_CLAIMS
from .probes import ProbeStep, build

log = logging.getLogger("everfold.lucy")

APP = "decart/lucy-restyle"
QUEUE_URL = "https://queue.fal.run"
UPLOAD_URL = "https://rest.alpha.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3"
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


# Lucy on fal fails fast (inference ~2 s, then HTTP 500 on the result) when the prompt is over ~900 characters: all
# 11 failed clips of the first sweep had prompts of 907+ characters, all 29 that worked had 895 or fewer, and the
# same clip went through once the prompt was shortened (2026-11-04). Undocumented; this cap stays under it.
MAX_PROMPT_CHARS = 895


def prompt_for(steps: list[ProbeStep]) -> str:
    """Art direction plus the people and landmarks of the clip, in the order first seen: things true throughout,
    never a state change. If that is over MAX_PROMPT_CHARS, people are dropped from the end until it fits."""
    things: list[tuple[str, str]] = []
    for s in steps:
        for x in s.view.seen:
            # a landmark whose description carries its state (the shrine's gate) gets its stateless claim instead
            label = LANDMARK_CLAIMS.get(x.id.split(":", 1)[0], x.label) if x.kind == "landmark" else x.label
            if x.kind in ("person", "landmark") and (x.kind, label) not in things:
                things.append((x.kind, label))
    players = " / ".join(sorted({s.view.signature for s in steps}))

    def text() -> str:
        return (f"Restyle this blocky game render into a {C.STYLE_ANCHOR}. The player character is {players}, "
                f"seen from behind. In the world: {'; '.join(t for _, t in things) or 'open countryside'}. "
                "Keep every building, tree, rock, person and object exactly where it is and keep the camera motion; "
                "turn the simple shapes into detailed versions of what they are.")

    while len(text()) > MAX_PROMPT_CHARS and any(k == "person" for k, _ in things):
        del things[max(i for i, (k, _) in enumerate(things) if k == "person")]
    return text()[:MAX_PROMPT_CHARS]


class LucyAdapter:
    def __init__(self, api_key: str | None = None, per_player: bool = False, queue_url: str = QUEUE_URL,
                 upload_url: str | None = UPLOAD_URL, poll_s: float = 3.0, timeout_s: float = 900.0):
        from .. import falproxy

        self.key = api_key or falproxy.fal_key()
        if not self.key:
            raise RuntimeError("Set FAL_KEY to run Lucy Restyle on fal.")
        self.per_player = per_player
        self.name = "lucy-greybox" + ("-2p" if per_player else "")
        self.queue_url, self.poll_s, self.timeout_s = queue_url.rstrip("/"), poll_s, timeout_s
        self.upload_url = upload_url
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

    async def upload(self, video: bytes) -> str:
        """Put the clip on fal's file storage. Clips sent inline as data URIs failed on fal's side for about half
        of the ~1 MB revisit clips (HTTP 500), and again on retry; uploaded ones go through."""
        if self.upload_url is None:
            return "data:video/mp4;base64," + base64.b64encode(video).decode()
        d = await self._json("POST", self.upload_url, {"content_type": "video/mp4", "file_name": "clip.mp4"})
        async with self.http.put(d["upload_url"], data=video, headers={"content-type": "video/mp4"},
                                 timeout=ClientTimeout(total=120)) as r:
            r.raise_for_status()
        return d["file_url"]

    async def restyle(self, video: bytes, prompt: str, seed: int) -> bytes:
        """Upload the clip, submit to fal's queue, wait, download the restyled clip."""
        body = {"prompt": prompt, "video_url": await self.upload(video), "enhance_prompt": False, "seed": seed}
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


async def repair(out, judge, per_player: bool = False) -> dict:
    """Redo the clips of a finished Lucy run that failed on fal's side, judge only their new frames, and rescore.

    A failed clip leaves its steps without frames; retrying it later costs only that clip. Clips that fail again
    stay missing and are recorded in the run's renderer errors."""
    from pathlib import Path

    from .run import _ext, rescore

    out = Path(out)
    m = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    steps = build(m["seed"])
    missing = [s for s in steps if not any((out / "frames").glob(f"{s.id}.*"))]
    if not missing:
        return {"run": out.name, "redone": 0}
    a = LucyAdapter(per_player=per_player)
    a.http = ClientSession()
    groups: dict[tuple, list[ProbeStep]] = {}
    for s in steps:
        groups.setdefault((s.probe, s.player) if per_player else (s.probe,), []).append(s)
    todo = [g for g in groups.values() if any(s in missing for s in g)]
    await asyncio.gather(*(a._clip(g, seed=100 + i) for i, g in enumerate(todo)))
    await a.aclose()
    rows = [json.loads(line) for line in (out / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()]
    for s in missing:
        img = a.frames.get(s.id)
        if img is None:
            continue
        (out / "frames" / f"{s.id}.{_ext(img)}").write_bytes(img)
        rows.append({"id": s.id, "verdicts": await judge.check(s, img)})
    (out / "verdicts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    r = m["renderer"]
    r["errors"] = [e for e in r.get("errors", []) if e.split(":")[0] not in {s.id for s in missing}] + a.errors
    r["repair_clips"], r["repair_cost_usd"] = a.clips, round(a.cost, 4)
    r["est_cost_usd"] = round(r["est_cost_usd"] + a.cost, 4)
    (out / "metrics.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    await rescore(out, judge)
    return {"run": out.name, "redone": a.clips, "still_failed": len(a.errors), "usd": round(a.cost, 3)}
