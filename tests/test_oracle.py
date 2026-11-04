"""The FLUX oracle against a stand-in fal endpoint: one fresh image per step, drawn from that step's own prompt."""
from aiohttp import web

from everfold.bench import sweep as S
from everfold.bench.fal_adapter import IMAGE_APP
from everfold.bench.oracle_adapter import FluxOracleAdapter
from everfold.bench.probes import build

PNG = b"\x89PNG fake"


async def test_each_step_is_drawn_fresh_from_its_prompt(aiohttp_server):
    asked = []

    async def image(request):
        assert request.headers["authorization"] == "Key test-key"
        asked.append(await request.json())
        return web.json_response({"images": [{"url": str(request.url.with_path("/img.png"))}]})

    app = web.Application()
    app.router.add_post(f"/{IMAGE_APP}", image)
    async def png(request):
        return web.Response(body=PNG)

    app.router.add_get("/img.png", png)
    server = await aiohttp_server(app)
    steps = build(42, ["propagation"])
    a = FluxOracleAdapter(api_key="test-key", run_url=str(server.make_url("")))
    await a.open("propagation")
    frames = [await a.frame(s) for s in steps]
    await a.aclose()
    assert [f for f, _ in frames] == [PNG] * len(steps)
    assert [b["prompt"] for b in asked] == [s.prompt for s in steps]
    assert len({b["seed"] for b in asked}) == len(steps), "different prompts, different image seeds"
    assert a.stats()["images"] == len(steps) and a.stats()["est_cost_usd"] > 0


async def test_a_failed_image_is_a_missing_frame_not_a_crash(aiohttp_server):
    async def boom(request):
        return web.Response(status=500, text="boom")

    app = web.Application()
    app.router.add_post(f"/{IMAGE_APP}", boom)
    server = await aiohttp_server(app)
    a = FluxOracleAdapter(api_key="test-key", run_url=str(server.make_url("")))
    await a.open("shrine")
    image, _ = await a.frame(build(42, ["shrine"])[0])
    await a.aclose()
    assert image is None and a.stats()["errors"] and a.cost == 0


def test_sweep_accepts_the_oracle():
    assert S.parse_plan(["flux-oracle:20"]) == [("flux-oracle", 20)]
