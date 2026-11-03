import json

import pytest

from everfold.bench import adapters as A
from everfold.bench.judge import Judge
from everfold.bench.labels import LabelApp, agreement, draw_sample, kappa
from everfold.bench.run import run


@pytest.fixture
async def runs(tmp_path, fake_claude):
    """Two judged runs, so the sample has to spread across them."""
    def all_present(kw):
        n = kw["messages"][0]["content"][1]["text"].count("\n") + 1
        return {"verdicts": [{"n": i + 1, "verdict": "present", "why": ""} for i in range(n)]}

    root = tmp_path / "runs"
    for name in ("modela-image-seed42", "modelb-image-seed42"):
        await run(42, A.ReferenceAdapter(), root / name, Judge(fake_claude(*[all_present] * 5)),
                  ["shrine", "propagation"])
    await run(42, A.ReferenceAdapter(), root / "reference-seed42", None, ["shrine"])
    return root


def test_kappa():
    assert kappa([("a", "a"), ("b", "b")]) == 1.0
    assert kappa([("a", "b"), ("b", "a")]) == -1.0
    assert kappa([]) is None


async def test_sample_spreads_across_runs_and_skips_the_reference(runs):
    s = draw_sample(runs, n=6)
    assert len(s) == 6 and {x["run"] for x in s} == {"modela-image-seed42", "modelb-image-seed42"}
    assert sum(x["run"] == "modela-image-seed42" for x in s) == 3
    assert draw_sample(runs, n=6) == s, "the sample must be reproducible"


async def test_label_page_is_blind_validates_and_resumes(runs, tmp_path, aiohttp_client):
    app = LabelApp(runs, tmp_path / "labels", "tester", n=4)
    client = await aiohttp_client(app.app())
    assert "Does the picture show it?" in await (await client.get("/")).text()
    nxt = await (await client.get("/api/next")).json()
    assert nxt["done"] == 0 and nxt["total"] == 4
    item = app.sample[nxt["index"]]
    step = app.step(item["run"], item["id"])
    blob = json.dumps(nxt)
    assert step["prompt"] not in blob and step["label"] not in blob and "must" not in blob
    assert [c["id"] for c in nxt["claims"]] == [f"c{k}" for k in range(len(nxt["claims"]))]
    assert len(nxt["claims"]) == len(step["facts"]) + len(step.get("stale", []))
    assert (await client.get(f"/frame/{nxt['index']}")).status == 200
    assert (await client.get("/frame/99")).status == 404

    partial = {c["id"]: "present" for c in nxt["claims"][:-1]}
    assert (await client.post("/api/label", json={"index": nxt["index"], "answers": partial})).status == 400
    full = {c["id"]: "absent" for c in nxt["claims"]}
    assert (await client.post("/api/label", json={"index": nxt["index"], "answers": full})).status == 200
    saved = json.loads((tmp_path / "labels" / "labels.jsonl").read_text().splitlines()[-1])
    assert set(saved["answers"]) == {f["id"] for f in step["facts"] + step.get("stale", [])}
    again = await (await client.get("/api/next")).json()
    assert again["done"] == 1 and again["index"] != nxt["index"]

    # every remaining frame: nothing on the wire says which claims are stale, then the queue empties
    while again["index"] is not None:
        assert "stale" not in json.dumps(again)
        await client.post("/api/label", json={"index": again["index"],
                                              "answers": {c["id"]: "unclear" for c in again["claims"]}})
        again = await (await client.get("/api/next")).json()
    assert again["done"] == 4

    # a second launch keeps the same sample and progress
    app2 = LabelApp(runs, tmp_path / "labels", "tester", n=50)
    assert app2.sample == app.sample


async def test_agreement_compares_human_and_judge(runs, tmp_path):
    labels = tmp_path / "labels"
    app = LabelApp(runs, labels, "tester", n=2)
    rows = []
    for item in app.sample:
        step = app.step(item["run"], item["id"])
        ids = [f["id"] for f in step["facts"] + step.get("stale", [])]
        rows.append({"run": item["run"], "id": item["id"], "labeler": "tester",
                     "answers": {fid: "present" for fid in ids}})
    (labels / "labels.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    a = agreement(runs, labels)
    assert a["frames"] == 2 and a["agreement"] == 1.0          # the fake judge also said present to everything
    assert "stale" in a["by_kind"] or all(k != "stale" for k in a["by_kind"])
    assert a["confusion"] == {"human present / judge present": a["claims"]}
