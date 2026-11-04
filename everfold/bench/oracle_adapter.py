"""FLUX oracle: the ceiling the world models are measured against.

Every probe step is drawn fresh by a text-to-image model (FLUX schnell on fal) from that step's full prompt, which
the engine compiles from the true state. Nothing carries over between frames, so there is no memory to lose: the
engine holds the world and the image model only draws it. This is the "engine holds state, model renders" pattern
at its simplest, and an upper bound on what a renderer told the truth every frame can score under the same judge.

It is not a perfect ceiling. The same landmark is drawn independently each time, so it only matches across views
as far as its description does, and FLUX can still leave out or invent things; those misses are the image model's,
and the score shows how many there are.

Billed per image (IMAGE_PRICE). Requires FAL_KEY.
"""
from __future__ import annotations

import time
import zlib

from aiohttp import ClientSession, ClientTimeout

from .fal_adapter import IMAGE_APP, IMAGE_PRICE, MAX_PROMPT, RUN_URL
from .probes import ProbeStep


class FluxOracleAdapter:
    name = "flux-oracle"

    def __init__(self, api_key: str | None = None, run_url: str = RUN_URL):
        from .. import falproxy

        self.key = api_key or falproxy.fal_key()
        if not self.key:
            raise RuntimeError("Set FAL_KEY to run the FLUX oracle.")
        self.run_url = run_url.rstrip("/")
        self.http: ClientSession | None = None
        self.cost = 0.0
        self.images = 0
        self.seconds: list[float] = []
        self.errors: list[str] = []

    async def open(self, probe: str) -> None:
        if self.http is None:
            self.http = ClientSession()

    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]:
        t0 = time.monotonic()
        prompt = step.prompt[:MAX_PROMPT]
        body = {"prompt": prompt, "image_size": "landscape_16_9", "num_images": 1,
                "seed": zlib.crc32(prompt.encode()), "enable_safety_checker": False}
        headers = {"authorization": f"Key {self.key}", "content-type": "application/json",
                   "accept": "application/json"}
        try:
            async with self.http.post(f"{self.run_url}/{IMAGE_APP}", json=body, headers=headers,
                                      timeout=ClientTimeout(total=120)) as r:
                if r.status >= 400:
                    raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:200]}")
                url = (await r.json())["images"][0]["url"]
            self.cost += IMAGE_PRICE
            self.images += 1
            async with self.http.get(url, timeout=ClientTimeout(total=60)) as r:
                r.raise_for_status()
                image = await r.read()
        except Exception as e:          # noqa: BLE001 - a missing frame is scored as missing, not a crashed run
            self.errors.append(f"{step.id}: {type(e).__name__}: {e}")
            return None, time.monotonic() - t0
        self.seconds.append(time.monotonic() - t0)
        return image, self.seconds[-1]

    async def close(self) -> None:
        return None

    async def aclose(self) -> None:
        if self.http is not None:
            await self.http.close()
            self.http = None

    def stats(self) -> dict:
        return {"model": "flux-schnell", "images": self.images, "est_cost_usd": round(self.cost, 4),
                "mean_image_seconds": round(sum(self.seconds) / len(self.seconds), 3) if self.seconds else None,
                "errors": self.errors[:10]}
