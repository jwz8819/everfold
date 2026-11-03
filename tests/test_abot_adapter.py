"""The ABot adapter against a stand-in fal WMA bridge: a real aiortc peer on localhost, so the whole signalling,
data-channel and video path runs without fal or the network."""
import asyncio
import json
import time

import pytest

pytest.importorskip("aiortc")
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

from everfold.bench.abot_adapter import APP, FALLBACK_STUN, IMAGE_APP, ABotAdapter, ice_servers, plan_drive
from everfold.bench.probes import build


class ColourTrack(VideoStreamTrack):
    """Grey until the first world update, then a colour that changes with every update."""

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge

    async def recv(self):
        pts, base = await self.next_timestamp()
        shade = (40 * self.bridge.updates) % 256 if self.bridge.updates else 128
        f = VideoFrame.from_ndarray(np.full((64, 96, 3), shade, np.uint8), format="rgb24")
        f.pts, f.time_base = pts, base
        return f


class FakeBridge:
    def __init__(self, exhaust_after: int | None = None):
        self.exhaust_after = exhaust_after
        self.updates = 0
        self.received: list[dict] = []
        self.auth: set[str] = set()
        self.heartbeats = 0
        self.sessions = 0
        self.peers: list[RTCPeerConnection] = []

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/ice", self.ice)
        app.router.add_post("/session", self.session)
        app.router.add_post("/session/heartbeat", self.heartbeat)
        app.router.add_post(f"/{IMAGE_APP}", self.image)
        return app

    async def ice(self, request):
        self.auth.add(request.headers.get("authorization", ""))
        assert (await request.json())["app_id"] == APP
        return web.json_response({"ice_servers": []})

    async def image(self, request):
        self.auth.add(request.headers.get("authorization", ""))
        return web.json_response({"images": [{"url": "https://example.test/start.png"}]})

    async def heartbeat(self, request):
        assert (await request.json())["session_id"].startswith("s")
        self.heartbeats += 1
        return web.json_response({"ok": True})

    async def session(self, request):
        body = await request.json()
        assert body["app_id"] == APP and body["type"] == "offer" and "a=candidate" in body["sdp"]
        self.sessions += 1
        pc = RTCPeerConnection()
        self.peers.append(pc)

        @pc.on("datachannel")
        def on_channel(ch):
            assert ch.label == "control"

            @ch.on("message")
            def on_message(raw):
                msg = json.loads(raw)
                self.received.append(msg)
                ack = {"configure": "configured", "prompt": "prompt_applied"}.get(msg["type"])
                if ack:
                    self.updates += 1
                    if self.exhaust_after and self.updates > self.exhaust_after:
                        self.exhaust_after = None
                        ch.send(json.dumps({"type": "stream_exhausted"}))
                    else:
                        ch.send(json.dumps({"type": ack}))

        await pc.setRemoteDescription(RTCSessionDescription(body["sdp"], body["type"]))
        pc.addTrack(ColourTrack(self))
        await pc.setLocalDescription(await pc.createAnswer())
        return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type,
                                  "session_id": f"s{self.sessions}"})

    async def close(self):
        for pc in self.peers:
            await pc.close()


async def run_steps(aiohttp_server, bridge, start="preset", n=2, heartbeat_s=5.0, **kw):
    server = await aiohttp_server(bridge.app())
    base = str(server.make_url("")).rstrip("/")
    a = ABotAdapter(api_key="kid:secret", settle_s=0.6, start=start, wma_url=base, run_url=base,
                    heartbeat_s=heartbeat_s, ack_timeout_s=5, **kw)
    steps = build(42, ["revisit"])[:n]
    frames = []
    try:
        await a.open("revisit")
        for s in steps:
            frames.append(await a.frame(s))
        await a.close()
    finally:
        await a.aclose()
        await bridge.close()
    return a, steps, frames


async def test_headless_session_configures_then_prompts_and_returns_frames(aiohttp_server):
    bridge = FakeBridge()
    a, steps, frames = await run_steps(aiohttp_server, bridge)
    kinds = [m["type"] for m in bridge.received]
    assert kinds == ["configure", "prompt", "stop"]
    assert bridge.received[0]["prompt"] == steps[0].prompt and "image_url" not in bridge.received[0]
    assert bridge.received[1]["prompt"] == steps[1].prompt
    assert bridge.auth == {"Key kid:secret"}
    for img, seconds in frames:
        assert img.startswith(b"\x89PNG") and seconds >= 0
    st = a.stats()
    assert st["sessions"] == 1 and st["session_seconds"] > 0 and st["est_cost_usd"] > 0
    assert st["responded_steps"] >= 1 and a.name == "abot-preset"


async def test_image_start_generates_one_start_image_per_family(aiohttp_server):
    bridge = FakeBridge()
    a, _, _ = await run_steps(aiohttp_server, bridge, start="image")
    configure = [m for m in bridge.received if m["type"] == "configure"]
    assert len(configure) == 1 and configure[0]["image_url"] == "https://example.test/start.png"
    assert a.name == "abot-image"


async def test_an_exhausted_stream_reopens_and_resends(aiohttp_server):
    bridge = FakeBridge(exhaust_after=1)
    a, _, frames = await run_steps(aiohttp_server, bridge)
    assert bridge.sessions == 2
    assert [m["type"] for m in bridge.received if m["type"] != "stop"] == ["configure", "prompt", "configure"]
    assert all(img for img, _ in frames) and a.stats()["sessions"] == 2


async def test_heartbeats_keep_the_lease(aiohttp_server):
    bridge = FakeBridge()
    await run_steps(aiohttp_server, bridge, n=3, heartbeat_s=0.3)
    assert bridge.heartbeats >= 2


def test_plan_drive_turns_toward_each_leg_walks_forward_then_faces_the_view():
    # facing north at (0,0) -> facing east at (3,-4): turn none, walk 4 north, turn right, walk 3 east
    assert plan_drive((0, 0, "N"), (3, -4, "E"), 0.5, 1.0) == [("forward", 2.0), ("look_right", 1.0),
                                                               ("forward", 1.5)]
    # walking back south from a north-facing pose is a half turn, then the final facing is restored
    assert plan_drive((0, 0, "N"), (0, 12, "N"), 0.5, 1.0) == [("look_right", 2.0), ("forward", 6.0),
                                                               ("look_right", 2.0)]
    assert plan_drive((5, 5, "E"), (5, 5, "N"), 0.5, 1.0) == [("look_left", 1.0)]
    assert plan_drive((5, 5, "E"), (5, 5, "E"), 0.5, 1.0) == []


async def test_drive_walks_the_avatar_between_poses_before_each_prompt(aiohttp_server):
    bridge = FakeBridge()
    steps = build(42, ["revisit"])
    a, _, frames = await run_steps(aiohttp_server, bridge, start="preset", n=4, drive=True, tile_s=0.01,
                                   turn_s=0.05)
    seq = [m["type"] for m in bridge.received]
    assert seq[0] == "configure" and seq.count("prompt") == 3 and seq[-1] == "stop"
    held = [m["active"][0] for m in bridge.received if m["type"] == "commands" and m["active"]]
    assert {"forward", "look_right"} <= set(held)
    first_move = seq.index("commands")
    assert seq[first_move - 1] == "configure"           # movement happens between updates, after the world exists
    released = [m for m in bridge.received if m["type"] == "commands" and not m["active"]]
    assert released and all(m["activated"] == [] for m in released)
    assert a.name == "abot-preset-drive" and a.pose == (steps[3].view.x, steps[3].view.y, steps[3].view.facing)
    assert a.stats()["drive_seconds"] > 0 and all(img for img, _ in frames)


def test_ice_servers_put_tls_turn_first_for_aiortc():
    vended = [{"urls": "stun:relay.example:80"},
              {"urls": "turn:relay.example:80", "username": "u", "credential": "c"},
              {"urls": "turn:relay.example:80?transport=tcp", "username": "u", "credential": "c"},
              {"urls": "turns:relay.example:443?transport=tcp", "username": "u", "credential": "c"}]
    out = ice_servers(vended, lambda **kw: kw)
    assert out[0] == {"urls": FALLBACK_STUN} and out[1] == {"urls": "stun:relay.example:80"}
    turns = [s["urls"] for s in out if s["urls"].startswith("turn")]
    assert turns[0].startswith("turns:") and turns[-1] == "turn:relay.example:80"
    assert all(s.get("username") == "u" for s in out[2:])


def test_needs_a_key(monkeypatch):
    for k in ("FAL_KEY", "FAL_KEY_ID", "FAL_KEY_SECRET"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError):
        ABotAdapter()
