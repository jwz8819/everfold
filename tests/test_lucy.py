"""Greybox render and the Lucy restyle adapter against a stand-in fal queue."""
import base64
import json

import pytest

pytest.importorskip("av")
from aiohttp import web

from everfold.bench import sweep as S
from everfold.bench.adapters import GreyboxAdapter
from everfold.bench.lucy_adapter import APP, FPS, LucyAdapter, decode, encode, plan_clip, prompt_for
from everfold.bench.probes import build
from everfold.render.greybox import FACING_HEADING, H, W, outfit_color, render


def test_greybox_draws_the_shared_tower_from_both_sides():
    a, b = build(42, ["cross_view"])
    imgs = [render(s.scene, s.view.x, s.view.y, FACING_HEADING[s.view.facing], outfit_color(s.view.signature))
            for s in (a, b)]
    assert all(im.size == (W, H) for im in imgs)
    def blue(im):
        px = im.tobytes()
        return sum(1 for i in range(0, len(px), 3) if px[i + 2] > 200 and px[i] < 110 and px[i + 1] < 180)
    assert all(blue(im) > 20 for im in imgs), "the tower's blue flame is in both players' frames"


def test_greybox_shows_the_state_change():
    s0, s1 = build(42, ["shrine"])
    frames = [render(s.scene, s.view.x, s.view.y, FACING_HEADING[s.view.facing]) for s in (s0, s1)]
    assert frames[0].tobytes() != frames[1].tobytes()


def test_clip_holds_at_each_pose_and_samples_inside_the_hold():
    steps = build(42, ["cross_view"])
    frames, sample = plan_clip(steps)
    assert set(sample) == {s.id for s in steps}
    for s in steps:
        i = round(sample[s.id] * FPS)
        assert frames[i][0] is s and (frames[i][1], frames[i][2]) == (s.view.x, s.view.y)
    assert sample[steps[1].id] > sample[steps[0].id] + 1.0, "the camera walks between the two poses"


def test_prompt_never_states_a_state_change():
    steps = build(42, ["shrine", "propagation"])
    for probe in ("shrine", "propagation"):
        p = prompt_for([s for s in steps if s.probe == probe])
        for word in ("sealed", "open gate", "stump", "campfire", "orb"):
            assert word not in p, (probe, word)


def test_encode_decode_round_trip():
    frames, _ = plan_clip(build(42, ["shrine"]))
    out = decode(encode(frames))
    assert len(out) == len(frames) and out[0][1].size == (W, H)


async def test_adapter_restyles_one_clip_per_family_and_samples_steps(aiohttp_server):
    seen = []

    async def submit(request):
        body = await request.json()
        seen.append(body)
        assert body["video_url"].startswith("data:video/mp4;base64,") and not body["enhance_prompt"]   # no upload in tests
        n = len(seen)
        base = str(request.url.with_path(""))
        return web.json_response({"request_id": str(n), "status_url": f"{base}/status/{n}",
                                  "response_url": f"{base}/result/{n}"})

    async def status(request):
        return web.json_response({"status": "COMPLETED"})

    async def result(request):
        n = int(request.match_info["n"])
        return web.json_response({"video": {"url": str(request.url.with_path(f"/video/{n}"))}})

    async def video(request):          # "restyled" = the input clip itself
        n = int(request.match_info["n"])
        return web.Response(body=base64.b64decode(seen[n - 1]["video_url"].split(",", 1)[1]))

    app = web.Application()
    app.router.add_post(f"/{APP}", submit)
    app.router.add_get("/status/{n}", status)
    app.router.add_get("/result/{n}", result)
    app.router.add_get("/video/{n}", video)
    server = await aiohttp_server(app)
    steps = build(42, ["cross_view", "shrine"])
    a = LucyAdapter(api_key="k", queue_url=str(server.make_url("")), upload_url=None, poll_s=0.01)
    await a.prepare(steps)
    frames = [await a.frame(s) for s in steps]
    await a.aclose()
    assert len(seen) == 2 and all(img for img, _ in frames)
    assert a.stats()["clips"] == 2 and a.stats()["est_cost_usd"] > 0
    pp = LucyAdapter(api_key="k", per_player=True)
    assert pp.name == "lucy-greybox-2p"


def test_conditions():
    assert S.parse_plan(["greybox:3", "lucy-greybox:2", "lucy-greybox-2p:2"])
    assert isinstance(S.make_adapter("greybox", 5.0), GreyboxAdapter)


def test_greybox_reports_zero_cost_for_the_sweep_ledger():
    assert GreyboxAdapter().stats()["est_cost_usd"] == 0.0


def test_prompts_stay_under_lucys_limit():
    from everfold.bench.lucy_adapter import MAX_PROMPT_CHARS

    for seed in (10, 4, 18):
        for probe in ("revisit", "identity"):
            assert len(prompt_for([s for s in build(seed) if s.probe == probe])) <= MAX_PROMPT_CHARS
