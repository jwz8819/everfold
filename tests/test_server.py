import asyncio

from everfold.game import Game
from everfold.server import Server


async def recv_until(ws, kind, limit=200):
    for _ in range(limit):
        msg = await asyncio.wait_for(ws.receive_json(), 5)
        if msg["type"] == kind:
            return msg
    raise AssertionError(f"never got {kind}")


async def test_two_players_join_see_each_other_and_chat(aiohttp_client):
    server = Server(Game(42))
    client = await aiohttp_client(server.app())
    a = await client.ws_connect("/ws")
    await a.send_json({"type": "join", "name": "Ash"})
    welcome = await recv_until(a, "welcome")
    assert welcome["pid"].startswith("p_") and "ground" in welcome["palette"]
    chunk = await recv_until(a, "chunk")
    assert len(chunk["ground"]) == 32 * 32
    b = await client.ws_connect("/ws")
    await b.send_json({"type": "join", "name": "Briar"})
    await recv_until(b, "welcome")
    await server.tick(0.1)
    for _ in range(20):          # a snapshot queued before Briar joined may arrive first
        snap = await recv_until(a, "snapshot")
        if any(p["name"] == "Briar" for p in snap["players"]):
            break
    assert any(p["name"] == "Briar" for p in snap["players"])
    await a.send_json({"type": "chat", "text": "meet at the shrine?"})
    await asyncio.sleep(0.05)
    await server.tick(0.1)
    msg = await recv_until(b, "chat")
    assert msg["from"] == "Ash" and msg["text"] == "meet at the shrine?"
    view = await recv_until(a, "view")
    assert view["prompt"].endswith("no UI.") and view["facts"]


async def test_a_returning_player_keeps_their_id(aiohttp_client):
    server = Server(Game(42))
    client = await aiohttp_client(server.app())
    a = await client.ws_connect("/ws")
    await a.send_json({"type": "join", "name": "Ash"})
    pid = (await recv_until(a, "welcome"))["pid"]
    await a.close()
    await asyncio.sleep(0.05)
    a2 = await client.ws_connect("/ws")
    await a2.send_json({"type": "join", "name": "Ash", "pid": pid})
    assert (await recv_until(a2, "welcome"))["pid"] == pid
    bad = await client.ws_connect("/ws")
    await bad.send_json({"type": "join", "name": "X", "pid": "../etc"})
    assert (await recv_until(bad, "welcome"))["pid"] != "../etc"


async def test_odyssey_credentials_need_a_server_key(aiohttp_client, monkeypatch):
    monkeypatch.delenv("ODYSSEY_API_KEY", raising=False)
    client = await aiohttp_client(Server(Game(42)).app())
    r = await client.post("/odyssey/credentials")
    assert r.status == 404


# ------------------------------------------------------------------ fal proxy
import json

import pytest
from aiohttp import web

from everfold.falproxy import FalProxy, check_target

SESSION = "https://wma.fal.run/session"


@pytest.mark.parametrize("target,method,body,ok", [
    (SESSION, "POST", b'{"app_id": "fal-ai/abot-world-0"}', True),
    ("https://wma.fal.run/ice", "POST", b'{"app_id": "fal-ai/abot-world-0"}', True),
    ("https://wma.fal.run/session/heartbeat", "POST", b"{}", True),
    ("https://fal.run/fal-ai/abot-world-0/ice", "POST", b"{}", True),
    (SESSION, "POST", b'{"app_id": "fal-ai/flux-pro"}', False),                       # another model
    (SESSION, "POST", b'{"app_id": "fal-ai/abot-world-0", "app_id": "fal-ai/x"}', False),
    ("https://wma.fal.run/admin", "POST", b"{}", False),
    ("https://fal.run/fal-ai/flux-pro", "POST", b"{}", False),
    ("https://queue.fal.run/fal-ai/abot-world-0", "POST", b"{}", False),
    ("https://evil.example.com/session", "POST", b"{}", False),
    ("http://wma.fal.run/session/heartbeat", "POST", b"{}", False),
    ("https://user:pw@wma.fal.run/session/heartbeat", "POST", b"{}", False),
    ("https://wma.fal.run/session/heartbeat", "GET", b"", False),
])
def test_proxy_forwards_only_realtime_session_traffic_for_abot(target, method, body, ok):
    assert (check_target(target, method, body) is None) == ok


async def test_proxy_adds_the_key_and_the_browser_never_sees_it(aiohttp_client, aiohttp_server, monkeypatch):
    seen = {}

    async def fake_fal(request):
        seen["auth"] = request.headers.get("authorization")
        seen["path"] = request.path
        seen["body"] = await request.json()
        seen["extra"] = request.headers.get("x-fal-request-id")
        return web.json_response({"answer": "sdp"}, headers={"x-fal-trace": "t1"})

    up = web.Application()
    up.router.add_post("/session", fake_fal)
    upstream = await aiohttp_server(up)
    monkeypatch.setenv("FAL_KEY", "secret-key")
    proxy = FalProxy(rewrite={"https://wma.fal.run": str(upstream.make_url("")).rstrip("/")})
    client = await aiohttp_client(Server(Game(42), fal=proxy).app())
    r = await client.post("/api/fal/proxy", data=json.dumps({"app_id": "fal-ai/abot-world-0"}),
                          headers={"x-fal-target-url": SESSION, "x-fal-request-id": "abc"})
    assert r.status == 200 and await r.json() == {"answer": "sdp"} and r.headers["x-fal-trace"] == "t1"
    assert seen == {"auth": "Key secret-key", "path": "/session", "body": {"app_id": "fal-ai/abot-world-0"},
                    "extra": "abc"}
    assert "secret-key" not in await r.text()
    bad = await client.post("/api/fal/proxy", data=b"{}", headers={"x-fal-target-url": "https://fal.run/fal-ai/flux"})
    assert bad.status == 400


async def test_proxy_is_off_without_a_key(aiohttp_client, monkeypatch):
    for k in ("FAL_KEY", "FAL_KEY_ID", "FAL_KEY_SECRET"):
        monkeypatch.delenv(k, raising=False)
    client = await aiohttp_client(Server(Game(42)).app())
    r = await client.post("/api/fal/proxy", data=b"{}", headers={"x-fal-target-url": SESSION})
    assert r.status == 404


def test_env_file_is_read_without_overriding(tmp_path, monkeypatch):
    from everfold.cli import load_env
    monkeypatch.setenv("ALREADY_SET", "keep")
    monkeypatch.delenv("FAL_KEY", raising=False)
    (tmp_path / ".env").write_text("# keys\nFAL_KEY='abc:def'\nexport ALREADY_SET=nope\n")
    load_env(tmp_path / ".env")
    import os
    assert os.environ["FAL_KEY"] == "abc:def" and os.environ["ALREADY_SET"] == "keep"
    monkeypatch.delenv("FAL_KEY")
