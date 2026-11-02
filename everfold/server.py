"""Multiplayer server: one authoritative Game, WebSocket clients, a fixed-rate tick.

Protocol (JSON over one WebSocket):
  client -> server  join{name, pid?}  move{dx,dy}  interact  campfire  talk{npc?, text}  give{npc}
                    accept  decline  chat{text}  chunks
  server -> client  welcome  chunk  tile  snapshot  event  say  offer  quests  inventory  chat  view
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path

from aiohttp import WSMsgType, web

from . import config as C
from .falproxy import FalProxy
from .game import Game
from .render.prompt import compile_prompt
from .render.view import view
from .world import FEATURES, GROUND, ITEM_LABELS, chunk_of

log = logging.getLogger("everfold.server")
CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"
PALETTE = {
    "ground": {k: {"color": g.color, "label": g.label} for k, g in GROUND.items()},
    "feature": {k: {"color": f.color, "label": f.label, "blocks": f.blocks} for k, f in FEATURES.items()},
    "items": ITEM_LABELS,
}


class Session:
    def __init__(self, ws: web.WebSocketResponse, pid: str):
        self.ws = ws
        self.pid = pid
        self.chunks: set[tuple[int, int]] = set()
        self.last_view = 0.0
        self.last_prompt = ""


class Server:
    def __init__(self, game: Game, save_every: float = 10.0, fal: FalProxy | None = None):
        self.game = game
        self.fal = fal or FalProxy()
        self.sessions: dict[str, Session] = {}
        self.save_every = save_every
        self._last_save = time.monotonic()
        self._loop_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ app
    def app(self) -> web.Application:
        app = web.Application(middlewares=[no_cache])
        app.router.add_get("/ws", self.ws_handler)
        app.router.add_post("/odyssey/credentials", self.odyssey_credentials)
        for method in ("GET", "POST", "PUT"):
            app.router.add_route(method, "/api/fal/proxy", self.fal.handle)
        app.router.add_get("/", self.index)
        app.router.add_static("/client/", CLIENT_DIR)
        app.on_startup.append(self._start)
        app.on_cleanup.append(self._stop)
        return app

    async def index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(CLIENT_DIR / "index.html")

    async def _start(self, app) -> None:
        self._loop_task = asyncio.ensure_future(self._tick_loop())

    async def _stop(self, app) -> None:
        if self._loop_task:
            self._loop_task.cancel()
        await self.fal.close()
        self.game.save()

    async def odyssey_credentials(self, request: web.Request) -> web.Response:
        """Mint a short-lived Odyssey session token so the API key never reaches the browser."""
        import os

        key = os.environ.get("ODYSSEY_API_KEY")
        if not key:
            raise web.HTTPNotFound(text="ODYSSEY_API_KEY is not set on the server")
        if request.remote not in ("127.0.0.1", "::1"):
            raise web.HTTPForbidden(text="local players only")
        try:
            from odyssey import Odyssey
        except ImportError:
            raise web.HTTPServiceUnavailable(text="install the Odyssey SDK: uv pip install -e '.[odyssey]'")
        creds = await Odyssey(api_key=key).create_client_credentials()
        return web.json_response(creds.to_dict())

    # -------------------------------------------------------------- sockets
    async def ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        session: Session | None = None
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                if session is None:
                    if data.get("type") != "join":
                        continue
                    session = await self._join(ws, data)
                    continue
                await self._handle(session, data)
        finally:
            if session is not None:
                self.sessions.pop(session.pid, None)
                self.game.leave(session.pid)
        return ws

    async def _join(self, ws, data: dict) -> Session:
        pid = str(data.get("pid") or "")[:40]
        if not pid.startswith("p_") or not pid[2:].isalnum():
            pid = "p_" + secrets.token_hex(6)
        old = self.sessions.pop(pid, None)
        if old is not None:
            await old.ws.close()
        p = self.game.join(pid, str(data.get("name", ""))[:20])
        s = Session(ws, pid)
        self.sessions[pid] = s
        await ws.send_json({"type": "welcome", "pid": pid, "seed": self.game.seed, "chunk": C.CHUNK,
                            "you": p.public() | {"inventory": p.inventory}, "palette": PALETTE})
        await self._send_chunks(s)
        self.game._send_quests(p)
        return s

    async def _handle(self, s: Session, d: dict) -> None:
        g, pid, kind = self.game, s.pid, d.get("type")
        if kind == "move":
            g.set_move(pid, _num(d.get("dx")), _num(d.get("dy")))
        elif kind == "interact":
            g.interact(pid)
        elif kind == "campfire":
            g.campfire(pid)
        elif kind == "chat":
            g.chat(pid, str(d.get("text", "")))
        elif kind == "talk":
            p = g.players[pid]
            npc = g.npcs.get(str(d.get("npc", ""))) or g.nearest_npc(p)
            if npc is None:
                g.outbox.append((pid, {"type": "say", "npc": None, "text": "There is nobody close enough to talk to."}))
            else:
                g.outbox.append((pid, {"type": "thinking", "npc": npc.public()}))
                g._spawn(g.talk(pid, npc.id, str(d.get("text", ""))))
        elif kind == "give":
            p = g.players[pid]
            npc = g.npcs.get(str(d.get("npc", ""))) or g.nearest_npc(p)
            if npc is not None and not g.give(pid, npc.id):
                g.outbox.append((pid, {"type": "say", "npc": npc.public(),
                                       "text": "I don't think you have what I need yet."}))
        elif kind == "accept":
            g.accept(pid)
        elif kind == "decline":
            g.decline(pid)
        elif kind == "chunks":
            await self._send_chunks(s)

    async def _send_chunks(self, s: Session) -> None:
        p = self.game.players[s.pid]
        keys = self.game.ensure_around(p.x, p.y)
        for k in keys:
            if k not in s.chunks:
                s.chunks.add(k)
                await s.ws.send_json({"type": "chunk", **self.game.world.chunk_payload(*k)})
        cx, cy = chunk_of(p.x, p.y)
        s.chunks = {k for k in s.chunks if max(abs(k[0] - cx), abs(k[1] - cy)) <= C.VIEW_CHUNKS + 1}

    # ----------------------------------------------------------------- tick
    async def _tick_loop(self) -> None:
        dt = 1.0 / C.TICK_HZ
        while True:
            start = time.monotonic()
            try:
                await self.tick(dt)
            except Exception:
                log.exception("tick failed")
            await asyncio.sleep(max(0.0, dt - (time.monotonic() - start)))

    async def tick(self, dt: float) -> None:
        g = self.game
        g.step(dt)
        outbox, g.outbox = g.outbox, []
        for pid, msg in outbox:
            s = self.sessions.get(pid)
            if s is None or s.ws.closed:
                continue
            if msg.get("type") == "need_chunks":
                await self._send_chunks(s)
            else:
                await s.ws.send_json(msg)
        now = time.monotonic()
        for s in list(self.sessions.values()):
            if s.ws.closed:
                continue
            await s.ws.send_json(g.snapshot(s.pid))
            if now - s.last_view >= C.VIEW_PROMPT_EVERY:
                s.last_view = now
                v = view(g, s.pid)
                prompt = compile_prompt(v)
                await s.ws.send_json({"type": "view", "prompt": prompt, "changed": prompt != s.last_prompt,
                                      "facts": [f.text for f in v.facts]})
                s.last_prompt = prompt
        if now - self._last_save >= self.save_every:
            self._last_save = now
            g.save()


@web.middleware
async def no_cache(request: web.Request, handler):
    """A dev testbed: always serve the current client files."""
    resp = await handler(request)
    if request.path == "/" or request.path.startswith("/client/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
