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
    snap = await recv_until(a, "snapshot")
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
