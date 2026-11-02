"""A narrow fal.ai proxy so the browser can open realtime world-model sessions without ever holding FAL_KEY.

Same wire protocol as fal's own `@fal-ai/server-proxy`: the browser client sends each request to this route with
the real destination in the `x-fal-target-url` header, and the proxy forwards it with `Authorization: Key <FAL_KEY>`.
Unlike the stock proxy, this one forwards only what a realtime session for an allowed model needs:

  POST https://wma.fal.run/ice | /session | /session/heartbeat     (WebRTC negotiation)
  POST https://fal.run/<allowed app>/...                            (the client's fallback ICE route)

and `/ice` or `/session` must name an allowed app in their `app_id`. Anything else is refused, so a page that
reaches this server cannot spend the key on other fal models.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, web

TARGET_HEADER = "x-fal-target-url"
WMA_HOST = "wma.fal.run"
WMA_APP_PATHS = {"/ice", "/session"}
WMA_SESSION_PATHS = {"/session/heartbeat"}
ALLOWED_APPS = ("fal-ai/abot-world-0",)
DROP_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection"}
LOCAL = ("127.0.0.1", "::1")


def fal_key() -> str | None:
    key = os.environ.get("FAL_KEY")
    if key:
        return key
    kid, secret = os.environ.get("FAL_KEY_ID"), os.environ.get("FAL_KEY_SECRET")
    return f"{kid}:{secret}" if kid and secret else None


def check_target(target: str, method: str, body: bytes) -> str | None:
    """Return a reason to refuse, or None if the request may be forwarded."""
    try:
        url = urlsplit(target)
    except ValueError:
        return "unparseable target"
    if url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
        return "target must be plain https"
    path = "/" + "/".join(p for p in url.path.split("/") if p)
    if method != "POST":
        return "only POST is forwarded"
    if url.hostname == WMA_HOST:
        if path in WMA_SESSION_PATHS:
            return None
        if path not in WMA_APP_PATHS:
            return "path not allowed"
        try:
            app = json.loads(body or b"{}").get("app_id")
        except (ValueError, AttributeError):
            return "body must be JSON"
        if body.count(b'"app_id"') > 1:
            return "duplicate app_id"
        return None if app in ALLOWED_APPS else "app not allowed"
    if url.hostname == "fal.run":
        if any(path == f"/{a}" or path.startswith(f"/{a}/") for a in ALLOWED_APPS):
            return None
        return "app not allowed"
    return "host not allowed"


class FalProxy:
    def __init__(self, rewrite: dict[str, str] | None = None):
        # `rewrite` maps an https origin to another base URL; tests use it to stand in for fal.
        self.rewrite = rewrite or {}
        self._http: ClientSession | None = None

    async def close(self) -> None:
        if self._http is not None:
            await self._http.close()

    async def handle(self, request: web.Request) -> web.StreamResponse:
        key = fal_key()
        if not key:
            raise web.HTTPNotFound(text="FAL_KEY is not set on the server")
        if request.remote not in LOCAL:
            raise web.HTTPForbidden(text="local players only")
        target = request.headers.get(TARGET_HEADER, "")
        body = await request.read()
        reason = check_target(target, request.method.upper(), body)
        if reason:
            raise web.HTTPBadRequest(text=f"refused: {reason}")
        url = target
        for origin, base in self.rewrite.items():
            if url.startswith(origin):
                url = base + url[len(origin):]
        headers = {k.lower(): v for k, v in request.headers.items() if k.lower().startswith("x-fal-")}
        headers.pop(TARGET_HEADER, None)
        headers.update({"authorization": f"Key {key}", "accept": "application/json",
                        "content-type": "application/json", "x-fal-client-proxy": "everfold/aiohttp"})
        if self._http is None:
            self._http = ClientSession(timeout=ClientTimeout(total=30))
        async with self._http.request(request.method, url, headers=headers, data=body or None) as up:
            payload = await up.read()
            resp = web.Response(status=up.status, body=payload)
            for k, v in up.headers.items():
                if k.lower() not in DROP_HEADERS:
                    resp.headers[k] = v
            return resp
