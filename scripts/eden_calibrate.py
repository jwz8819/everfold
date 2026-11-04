"""Does Eden's camera move on our commands? One short session per game, same start scene and command script.

    .venv/bin/python scripts/eden_calibrate.py freeze drone        (about $0.35 per game on fal)
"""
import asyncio, dataclasses, io, json, sys, time
from pathlib import Path
from PIL import Image
from everfold.cli import load_env
load_env()
from everfold.bench.fal_adapter import FalWorldAdapter, COMMAND_EVERY_S
from everfold.bench.probes import build

OUT = Path(__file__).resolve().parent.parent / "runs" / "eden-calibration"
OUT.mkdir(parents=True, exist_ok=True)
SCRIPT = [("forward", 4.0), ("look_right", 4.0), ("forward", 4.0)]

def thumb(im, top=1.0):
    g = im.convert("L"); w, h = g.size
    px = list(g.crop((0, 0, w, int(h * top))).resize((32, 18)).tobytes()); n = len(px); m = sum(px) / n
    sd = (sum((p - m) ** 2 for p in px) / n) ** .5 or 1
    return [(p - m) / sd for p in px]

corr = lambda a, b: round(sum(x * y for x, y in zip(a, b)) / len(a), 2)

async def calibrate(game):
    a = FalWorldAdapter("eden", start="image", settle_s=5.0)
    a.spec = dataclasses.replace(a.spec, configure={**a.spec.configure, "game": game})
    step = build(42, ["cross_view"])[0]
    await a.open("cross_view")
    await a.frame(step)
    shots = [("start", Image.fromarray(a.latest))]
    for cmd, secs in SCRIPT:
        first, end = True, time.monotonic() + secs
        while time.monotonic() < end:
            a._send({"type": "commands", "active": [cmd], "activated": [cmd] if first else []})
            first = False
            await asyncio.sleep(COMMAND_EVERY_S)
        a._send({"type": "commands", "active": [], "activated": []})
        await asyncio.sleep(1.5)
        shots.append((f"after {cmd} {secs:.0f}s", Image.fromarray(a.latest)))
    await a.aclose()
    rows = []
    for (l0, i0), (l1, i1) in zip(shots, shots[1:]):
        rows.append({"step": l1, "full_corr": corr(thumb(i0), thumb(i1)), "top_corr": corr(thumb(i0, .5), thumb(i1, .5))})
    for i, (label, im) in enumerate(shots):
        im.save(OUT / f"{game}-{i}.jpg", quality=85)
    return {"game": game, "steps": rows, "usd": round(a.cost, 3), "errors": a.errors}

async def main():
    res = [await calibrate(g) for g in sys.argv[1:]]
    (OUT / "result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))

asyncio.run(main())
