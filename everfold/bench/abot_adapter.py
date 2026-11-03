"""ABot-World-0 (fal.ai) as a benchmark renderer, headless over WebRTC.

ABot keeps its own world. It starts from an image (a built-in preset unless `configure` names one), takes a text
description that it may change mid-session, and walks a third-person avatar on movement commands. The benchmark
sends only text, like the Odyssey adapter, so the two are compared under the same condition. One probe family is
one session, so revisit and propagation are judged inside one continuous world.

Two start conditions, because ABot draws from its start image far more than from the prompt:
  preset   the model's own default world, steered by prompt only
  image    a start image generated from the family's first prompt (FLUX schnell on fal), then prompt updates

The wire protocol follows fal's WMA client (`@fal-ai/client` src/realtime/wma.js) and the session contract at
https://fal.ai/models/fal-ai/abot-world-0/start-session/llms.txt:
  POST wma.fal.run/ice {app_id}                    -> ice_servers
  POST wma.fal.run/session {app_id, sdp, type}     -> answer sdp + session_id (one complete offer, no trickle ICE)
  POST wma.fal.run/session/heartbeat {session_id}  every 5 s, or the lease lapses
  data channel "control": JSON messages both ways (configure/prompt/stop out; configured/prompt_applied/... in)
Requires `uv pip install -e ".[abot]"` and FAL_KEY. Billed per session second ($0.00125/s at the time of writing).
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import time

from aiohttp import ClientSession, ClientTimeout

from .probes import ProbeStep

log = logging.getLogger("everfold.abot")

WMA_URL = "https://wma.fal.run"
RUN_URL = "https://fal.run"
APP = "fal-ai/abot-world-0"
IMAGE_APP = "fal-ai/flux/schnell"
PRICE_PER_S = 0.00125
MAX_PROMPT = 2000
CHANGE_THRESHOLD = 12.0     # mean absolute pixel change that counts as "the picture responded"
ACKS = {"configure": "configured", "prompt": "prompt_applied", "reset": "reset_applied"}
FALLBACK_STUN = "stun:stun.l.google.com:19302"


def _turn_rank(url: str) -> int:
    """TLS over TCP 443 first: it passes the firewalls that drop UDP on port 80, where fal's list starts."""
    if url.startswith("turns:"):
        return 0
    if "transport=tcp" in url:
        return 1
    return 2 if ":443" in url else 3


def ice_servers(vended: list[dict], make) -> list:
    """Reorder fal's ICE servers for aiortc, which uses only the first STUN and the first usable TURN URL.

    A browser tries every server and finds a path; aiortc would try only UDP port 80, which many networks block.
    So: one STUN that answers widely, then the TURN URLs most likely to get through, each as its own entry.
    """
    out = [make(urls=FALLBACK_STUN)]
    turns = []
    for s in vended:
        urls = s.get("urls") or []
        for u in urls if isinstance(urls, list) else [urls]:
            if u.startswith("stun:"):
                out.append(make(urls=u))
            elif u.startswith(("turn:", "turns:")):
                turns.append((_turn_rank(u), u, s.get("username"), s.get("credential")))
    out += [make(urls=u, username=user, credential=cred) for _, u, user, cred in sorted(turns, key=lambda t: t[0])]
    return out


class ABotAdapter:
    def __init__(self, api_key: str | None = None, settle_s: float = 5.0, start: str = "preset",
                 wma_url: str = WMA_URL, run_url: str = RUN_URL, heartbeat_s: float = 5.0,
                 ack_timeout_s: float = 30.0):
        from .. import falproxy

        self.key = api_key or falproxy.fal_key()
        if not self.key:
            raise RuntimeError("Set FAL_KEY to run the ABot adapter.")
        if start not in ("preset", "image"):
            raise ValueError("start must be 'preset' or 'image'")
        self.name = f"abot-{start}"
        self.start, self.settle_s = start, settle_s
        self.wma_url, self.run_url = wma_url.rstrip("/"), run_url.rstrip("/")
        self.heartbeat_s, self.ack_timeout_s = heartbeat_s, ack_timeout_s
        self.http: ClientSession | None = None
        self.pc = None
        self.channel = None
        self.session_id: str | None = None
        self.opened_at: float | None = None
        self.configured = False
        self.exhausted = False
        self.start_image: str | None = None
        self.latest = None                                  # newest frame as an RGB numpy array
        self._watch: tuple[float, object] | None = None     # (sent at, frame before) while timing a response
        self._responded: float | None = None
        self._acks: asyncio.Queue = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self.response_s: list[float] = []
        self.ack_s: list[float] = []
        self.session_s = 0.0
        self.sessions = 0
        self.errors: list[str] = []

    # transport -----------------------------------------------------------------------------------------------

    async def _post(self, url: str, body: dict, timeout: float = 60.0) -> dict:
        headers = {"authorization": f"Key {self.key}", "content-type": "application/json",
                   "accept": "application/json"}
        async with self.http.post(url, json=body, headers=headers, timeout=ClientTimeout(total=timeout)) as r:
            text = await r.text()
            if r.status >= 400:
                raise RuntimeError(f"{url} -> HTTP {r.status}: {text[:300]}")
            return json.loads(text)

    async def _connect(self) -> None:
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

        ice = (await self._post(f"{self.wma_url}/ice", {"app_id": APP}, timeout=15)).get("ice_servers") or []
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=ice_servers(ice, RTCIceServer)))
        self.pc.addTransceiver("video", direction="recvonly")
        self.channel = self.pc.createDataChannel("control")
        opened = asyncio.get_running_loop().create_future()
        self.channel.on("open", lambda: opened.done() or opened.set_result(True))
        self.channel.on("message", self._on_message)
        self.pc.on("track", lambda track: self._tasks.append(asyncio.create_task(self._receive(track))))
        self.pc.on("iceconnectionstatechange", lambda: log.info("ice %s", self.pc and self.pc.iceConnectionState))
        self.pc.on("connectionstatechange", lambda: log.info("peer %s", self.pc and self.pc.connectionState))

        await self.pc.setLocalDescription(await self.pc.createOffer())    # aiortc gathers ICE fully here
        offer = self.pc.localDescription
        answer = await self._post(f"{self.wma_url}/session", {"app_id": APP, "sdp": offer.sdp, "type": offer.type},
                                  timeout=120)
        # The runner answers with no candidates and end-of-candidates: it reaches us by checking the candidates
        # in our offer, and a browser learns its address from those checks (peer-reflexive). aioice instead fails
        # at once on an empty candidate list after end-of-candidates, so drop that line and let it wait.
        sdp = "".join(line + "\r\n" for line in answer["sdp"].splitlines() if line != "a=end-of-candidates")
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=answer["type"]))
        self.session_id = answer["session_id"]
        self.opened_at = time.monotonic()
        self.sessions += 1
        self.configured = self.exhausted = False
        self._acks = asyncio.Queue()
        self._tasks.append(asyncio.create_task(self._heartbeat()))
        try:
            await asyncio.wait_for(opened, timeout=30)
        except asyncio.TimeoutError:
            state = f"ice {self.pc.iceConnectionState}, peer {self.pc.connectionState}"
            await self._teardown()
            raise RuntimeError(f"ABot control channel did not open within 30 s ({state})") from None

    async def _heartbeat(self) -> None:
        strikes = 0
        while True:
            await asyncio.sleep(self.heartbeat_s)
            try:
                await self._post(f"{self.wma_url}/session/heartbeat", {"session_id": self.session_id}, timeout=4)
                strikes = 0
            except Exception as e:      # noqa: BLE001 - three misses in a row means the lease is gone
                strikes += 1
                log.warning("heartbeat failed (%d): %s", strikes, e)
                if strikes >= 3:
                    self.errors.append("heartbeat lease lost")
                    self.exhausted = True
                    return

    async def _receive(self, track) -> None:
        import numpy as np
        from aiortc.mediastreams import MediaStreamError

        while True:
            try:
                frame = await track.recv()
            except MediaStreamError:
                return
            img = frame.to_ndarray(format="rgb24")
            self.latest = img
            if self._watch and self._responded is None:
                t0, ref = self._watch
                if ref is not None and ref.shape == img.shape:
                    diff = np.abs(img[::4, ::4].astype(np.int16) - ref[::4, ::4].astype(np.int16)).mean()
                    if float(diff) >= CHANGE_THRESHOLD:
                        self._responded = time.monotonic() - t0

    def _on_message(self, raw) -> None:
        try:
            msg = json.loads(raw if isinstance(raw, str) else raw.decode())
        except (ValueError, UnicodeDecodeError):
            return
        kind = msg.get("type")
        if kind in ACKS.values():
            self._acks.put_nowait(kind)
        elif kind == "stream_exhausted":
            self.exhausted = True
            self._acks.put_nowait(kind)
        elif kind == "error":
            self.errors.append(str(msg.get("error") or msg)[:300])

    def _send(self, msg: dict) -> None:
        self.channel.send(json.dumps(msg))

    async def _update(self, msg: dict) -> float:
        """Send one world update and wait for its acknowledgement. Returns seconds to the ack."""
        t0 = time.monotonic()
        self._send(msg)
        want = ACKS[msg["type"]]
        while True:
            got = await asyncio.wait_for(self._acks.get(), timeout=self.ack_timeout_s)
            if got == want:
                return time.monotonic() - t0
            if got == "stream_exhausted":
                raise EOFError("stream exhausted")

    async def _teardown(self) -> None:
        if self.pc is None:
            return
        try:
            if self.channel is not None and self.channel.readyState == "open":
                self._send({"type": "stop"})
                await asyncio.sleep(0.2)
        finally:
            for t in self._tasks:
                t.cancel()
            self._tasks.clear()
            await self.pc.close()
            self.pc = self.channel = None
            if self.opened_at is not None:
                self.session_s += time.monotonic() - self.opened_at
                self.opened_at = None

    async def _image_for(self, prompt: str) -> str:
        out = await self._post(f"{self.run_url}/{IMAGE_APP}",
                               {"prompt": prompt, "image_size": "landscape_16_9", "num_images": 1}, timeout=120)
        return out["images"][0]["url"]

    # adapter -------------------------------------------------------------------------------------------------

    async def open(self, probe: str) -> None:
        if self.http is None:
            self.http = ClientSession()
        self.start_image = None
        self.latest = None
        await self._connect()

    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]:
        from PIL import Image

        t0 = time.monotonic()
        prompt = step.prompt[:MAX_PROMPT]
        for attempt in range(2):
            if self.exhausted:
                await self._teardown()
                await self._connect()
            if self.configured:
                msg = {"type": "prompt", "prompt": prompt}
            else:
                msg = {"type": "configure", "prompt": prompt}
                if self.start == "image":
                    self.start_image = self.start_image or await self._image_for(prompt)
                    msg["image_url"] = self.start_image
            self._watch, self._responded = (time.monotonic(), self.latest), None
            try:
                self.ack_s.append(await self._update(msg))
                self.configured = True
                break
            except EOFError:
                continue        # the session ran out mid-update; open a fresh one and resend once
            except asyncio.TimeoutError:
                self.errors.append(f"{step.id}: no {ACKS[msg['type']]} within {self.ack_timeout_s:.0f}s")
                break
        await asyncio.sleep(self.settle_s)
        if self._responded is not None:
            self.response_s.append(self._responded)
        self._watch = None
        if self.latest is None:
            return None, time.monotonic() - t0
        buf = io.BytesIO()
        Image.fromarray(self.latest).save(buf, format="PNG")
        return buf.getvalue(), self._responded if self._responded is not None else time.monotonic() - t0

    async def close(self) -> None:
        await self._teardown()

    async def aclose(self) -> None:
        await self._teardown()
        if self.http is not None:
            await self.http.close()
            self.http = None

    def stats(self) -> dict:
        mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
        return {"start": self.start, "sessions": self.sessions, "session_seconds": round(self.session_s, 1),
                "est_cost_usd": round(self.session_s * PRICE_PER_S, 4), "mean_ack_seconds": mean(self.ack_s),
                "mean_response_seconds": mean(self.response_s), "responded_steps": len(self.response_s),
                "errors": self.errors[:10]}
