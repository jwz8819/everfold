"""Human labels for calibrating the vision judge.

A person answers the same question the judge answers, frame by frame: does this image show each claim? They see
the frame and the claims only, never the prompt, the probe's purpose, which claims are true, or the judge's answer.
Comparing their answers with the judge's gives the agreement the paper must report before any judge number counts.

    labels/sample.json     the frames to label, drawn once and then fixed
    labels/labels.jsonl    one line per labelled frame (a later line for the same frame replaces an earlier one)
    labels/agreement.md    judge vs human, written by `everfold agreement`
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

from aiohttp import web

ANSWERS = ("present", "absent", "unclear")


def _frame(run: Path, sid: str) -> Path | None:
    return next(iter(sorted((run / "frames").glob(f"{sid}.*"))), None)


def _steps(run: Path) -> dict[str, dict]:
    return {d["id"]: d for d in map(json.loads, (run / "steps.jsonl").read_text(encoding="utf-8").splitlines())}


def _verdicts(run: Path) -> dict[str, dict[str, str]]:
    rows = map(json.loads, (run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines())
    return {r["id"]: r["verdicts"] for r in rows}


def judged_runs(runs: Path) -> list[Path]:
    """Finished, judged world-model runs. The reference renderer is a pipeline check, not a model, so it is left out."""
    return sorted(d for d in runs.iterdir() if d.is_dir() and not d.name.startswith("reference")
                  and (d / "verdicts.jsonl").exists() and (d / "steps.jsonl").exists())


def draw_sample(runs: Path, n: int = 100, seed: int = 0, exclude: list[dict] = (), focus: tuple[str, ...] = ()) -> list[dict]:
    """Up to n judged frames, spread evenly across runs, in a shuffled order so no run is labelled in one block.

    `exclude` lists frames labelled before (an older sample), which are never drawn again. When `focus` names step
    ids, half the sample is drawn from those steps first, so a change to a few claims gets enough labels."""
    rng = random.Random(seed)
    seen = {(e["run"], e["id"]) for e in exclude}
    pools = []
    # Interleave conditions (first seed of each, then the second, ...) so a sample smaller than the number of runs
    # still covers every condition rather than the alphabetically first ones.
    rank: dict[str, int] = defaultdict(int)
    order = []
    for run in judged_runs(runs):
        condition = run.name.rsplit("-seed", 1)[0]
        order.append((rank[condition], condition, run))
        rank[condition] += 1
    for *_, run in sorted(order, key=lambda t: t[:2]):
        verdicts = _verdicts(run)
        ids = [sid for sid in _steps(run) if sid in verdicts and _frame(run, sid) and (run.name, sid) not in seen]
        rng.shuffle(ids)
        pools.append([{"run": run.name, "id": sid} for sid in ids])
    picked: list[dict] = []

    def take(pools, limit):
        while len(picked) < limit and any(pools):
            for pool in pools:
                if pool and len(picked) < limit:
                    picked.append(pool.pop())

    if focus:
        take([[f for f in pool if f["id"] in focus] for pool in pools], n // 2)
        chosen = {(f["run"], f["id"]) for f in picked}
        pools = [[f for f in pool if (f["run"], f["id"]) not in chosen] for pool in pools]
    take(pools, n)
    rng.shuffle(picked)
    return picked


def claims(step: dict, key: str) -> list[dict]:
    """The step's true and stale claims in a fixed per-frame random order, without saying which is which."""
    items = [{"id": f["id"], "text": f["text"]} for f in step["facts"] + step.get("stale", [])]
    random.Random(hashlib.sha256(key.encode()).digest()).shuffle(items)
    return items


def load_labels(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            out[f"{row['run']}/{row['id']}"] = row
    return out


# agreement -------------------------------------------------------------------------------------------------------

def kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa between two raters over the same items."""
    if not pairs:
        return None
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else round((po - pe) / (1 - pe), 3)


def agreement(runs: Path, labels_dir: Path, against: Path | None = None) -> dict:
    """Agreement of the labels in `labels_dir` with the judge, or with another labeller's labels in `against`
    (then only frames both have labelled count)."""
    labels = load_labels(labels_dir / "labels.jsonl")
    other = load_labels(against / "labels.jsonl") if against else None
    if other is not None:
        labels = {k: v for k, v in labels.items() if k in other}
    pairs: list[tuple[str, str, str, str]] = []          # (this labeller, judge or other labeller, kind, run)
    cache: dict[str, tuple[dict, dict]] = {}
    for row in labels.values():
        run = runs / row["run"]
        if row["run"] not in cache:
            cache[row["run"]] = (_steps(run), _verdicts(run))
        steps, verdicts = cache[row["run"]]
        step = steps[row["id"]]
        kinds = {f["id"]: ("stale" if f in step.get("stale", []) else f["kind"])
                 for f in step["facts"] + step.get("stale", [])}
        for fid, human in row["answers"].items():
            judge = (other[f"{row['run']}/{row['id']}"]["answers"] if other is not None
                     else verdicts.get(row["id"], {})).get(fid)
            if judge in ANSWERS and human in ANSWERS:
                pairs.append((human, judge, kinds.get(fid, "?"), row["run"]))

    def summary(ps):
        three = [(h, j) for h, j, *_ in ps]
        binary = [(h == "present", j == "present") for h, j in three]
        return {"claims": len(ps), "agreement": round(sum(h == j for h, j in three) / len(ps), 3) if ps else None,
                "kappa": kappa(three), "present_kappa": kappa([(str(a), str(b)) for a, b in binary])}

    by_kind, by_run = defaultdict(list), defaultdict(list)
    for p in pairs:
        by_kind[p[2]].append(p)
        by_run[p[3]].append(p)
    confusion = Counter((h, j) for h, j, *_ in pairs)
    a, b = (next(iter(labels.values()))["labeler"] if labels else "human",
            next(iter(other.values()))["labeler"] if other else "judge")
    return {"frames": len(labels), "raters": [a, b], **summary(pairs),
            "by_kind": {k: summary(v) for k, v in sorted(by_kind.items())},
            "by_run": {k: summary(v) for k, v in sorted(by_run.items())},
            "confusion": {f"{a} {h} / {b} {j}": c for (h, j), c in sorted(confusion.items())}}


def agreement_report(a: dict) -> str:
    f = lambda x: "n/a" if x is None else f"{x:.2f}"
    a_name, b_name = a.get("raters", ["human", "judge"])
    lines = [f"# Agreement: {a_name} vs {b_name}", "",
             f"{a['frames']} frames, {a['claims']} claims. Agreement {f(a['agreement'])}, Cohen's kappa "
             f"{f(a['kappa'])} over present/absent/unclear, {f(a['present_kappa'])} on present vs not (the "
             "distinction the scores use).", "",
             "Rough reading of kappa: above 0.8 strong, 0.6-0.8 substantial, 0.4-0.6 moderate, below 0.4 weak.", "",
             "| Group | Claims | Agreement | Kappa | Present kappa |", "|---|---|---|---|---|"]
    for title, group in (("kind", a["by_kind"]), ("run", a["by_run"])):
        for k, s in group.items():
            lines.append(f"| {title}: {k} | {s['claims']} | {f(s['agreement'])} | {f(s['kappa'])} | "
                         f"{f(s['present_kappa'])} |")
    lines += ["", "## Confusion", ""] + [f"- {k}: {v}" for k, v in a["confusion"].items()]
    return "\n".join(lines) + "\n"


# labelling page ----------------------------------------------------------------------------------------------------

class LabelApp:
    def __init__(self, runs: Path, labels_dir: Path, labeler: str, n: int = 100, exclude: list[dict] = (),
                 focus: tuple[str, ...] = ()):
        self.runs, self.dir, self.labeler = runs, labels_dir, labeler
        self.dir.mkdir(parents=True, exist_ok=True)
        sample_file = self.dir / "sample.json"
        if not sample_file.exists():
            sample = draw_sample(runs, n, exclude=exclude, focus=focus)
            if not sample:
                raise RuntimeError(f"no judged runs under {runs}")
            sample_file.write_text(json.dumps(sample, indent=1), encoding="utf-8")
        self.sample = json.loads(sample_file.read_text(encoding="utf-8"))
        self.labels_file = self.dir / "labels.jsonl"
        self._steps: dict[str, dict] = {}

    def step(self, run: str, sid: str) -> dict:
        if run not in self._steps:
            self._steps[run] = _steps(self.runs / run)
        return self._steps[run][sid]

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", lambda r: web.Response(text=PAGE, content_type="text/html"))
        app.router.add_get("/api/next", self.next)
        app.router.add_post("/api/label", self.save)
        app.router.add_get("/frame/{i}", self.frame)
        return app

    async def next(self, request: web.Request) -> web.Response:
        done = load_labels(self.labels_file)
        for i, item in enumerate(self.sample):
            if f"{item['run']}/{item['id']}" in done:
                continue
            step = self.step(item["run"], item["id"])
            # opaque keys: a fact id such as "stale:..." would tell the labeller which claims are false
            shown = [{"id": f"c{k}", "text": c["text"]} for k, c in enumerate(claims(step, f"{item['run']}/{item['id']}"))]
            return web.json_response({"index": i, "done": len(done), "total": len(self.sample), "claims": shown})
        return web.json_response({"index": None, "done": len(done), "total": len(self.sample)})

    async def frame(self, request: web.Request) -> web.StreamResponse:
        i = int(request.match_info["i"])
        if not 0 <= i < len(self.sample):
            raise web.HTTPNotFound()
        item = self.sample[i]
        f = _frame(self.runs / item["run"], item["id"])
        if f is None:
            raise web.HTTPNotFound()
        return web.FileResponse(f, headers={"Cache-Control": "no-store"})

    async def save(self, request: web.Request) -> web.Response:
        body = await request.json()
        i = body.get("index")
        if not isinstance(i, int) or not 0 <= i < len(self.sample):
            raise web.HTTPBadRequest(text="bad index")
        item = self.sample[i]
        ids = [c["id"] for c in claims(self.step(item["run"], item["id"]), f"{item['run']}/{item['id']}")]
        answers = body.get("answers") or {}
        if set(answers) != {f"c{k}" for k in range(len(ids))} or any(a not in ANSWERS for a in answers.values()):
            raise web.HTTPBadRequest(text="answer every claim with present, absent or unclear")
        row = {"run": item["run"], "id": item["id"], "labeler": self.labeler,
               "answers": {ids[int(key[1:])]: a for key, a in answers.items()},
               "saved_at": round(time.time())}          # so time per frame can be reported
        with self.labels_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return web.json_response({"ok": True})


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Everfold labelling</title>
<style>
:root { --bg:#f6f4ef; --fg:#1d1d1b; --muted:#6b6a65; --card:#fff; --line:#dedbd2; --yes:#2f7d4a; --no:#b23b3b;
        --unc:#8a6d1c; --focus:#2b5fb4; }
@media (prefers-color-scheme: dark) { :root { --bg:#161614; --fg:#ecebe6; --muted:#a3a19a; --card:#22211f;
        --line:#3a3935; --yes:#5fbf80; --no:#e07a7a; --unc:#d9b75a; --focus:#7ea7ef; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; }
main { max-width:1180px; margin:0 auto; padding:16px; display:grid; gap:16px; grid-template-columns:1fr 400px; }
@media (max-width: 900px) { main { grid-template-columns:1fr; } }
header { grid-column:1/-1; display:flex; justify-content:space-between; align-items:baseline; gap:12px; flex-wrap:wrap; }
h1 { font-size:18px; margin:0; }
.progress { color:var(--muted); }
.bar { height:4px; background:var(--line); border-radius:2px; grid-column:1/-1; }
.bar > div { height:100%; background:var(--focus); border-radius:2px; width:0; }
img { width:100%; border-radius:8px; display:block; background:#000; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }
.claim { padding:10px; border-radius:8px; border:2px solid transparent; margin-bottom:8px; }
.claim.current { border-color:var(--focus); }
.claim p { margin:0 0 8px; }
.btns { display:flex; gap:6px; }
button { font:inherit; padding:6px 10px; border-radius:6px; border:1px solid var(--line); background:var(--bg);
         color:var(--fg); cursor:pointer; flex:1; }
button.on.present { background:var(--yes); color:#fff; border-color:var(--yes); }
button.on.absent { background:var(--no); color:#fff; border-color:var(--no); }
button.on.unclear { background:var(--unc); color:#fff; border-color:var(--unc); }
#next { width:100%; margin-top:8px; padding:10px; background:var(--focus); color:#fff; border:0; }
#next:disabled { opacity:.4; cursor:default; }
details { color:var(--muted); font-size:14px; }
kbd { border:1px solid var(--line); border-radius:4px; padding:0 4px; font-size:12px; }
</style></head><body>
<main>
<header><h1>Does the picture show it?</h1><span class="progress" id="progress"></span></header>
<div class="bar"><div id="bar"></div></div>
<div><img id="frame" alt="frame to label"></div>
<div class="card">
  <details open><summary>How to answer</summary>
  <p><b>Yes</b>: the picture clearly shows it. <b>No</b>: it clearly does not, or shows something that contradicts it.
  <b>Can't tell</b>: too blurry, dark or small to decide. Judge the thing, not the art style. A claim about a
  person's clothes or props is Yes only if a figure with those details is there. Don't be generous: a vaguely
  similar object is No.</p>
  <p>Keys: <kbd>1</kbd> Yes, <kbd>2</kbd> No, <kbd>3</kbd> Can't tell, <kbd>↑</kbd><kbd>↓</kbd> move,
  <kbd>Enter</kbd> save and next.</p></details>
  <div id="claims"></div>
  <button id="next" disabled>Save and next</button>
</div>
</main>
<script>
const LABELS = {present: "Yes", absent: "No", unclear: "Can't tell"};
let item = null, answers = {}, cur = 0;
async function load() {
  const r = await fetch("/api/next"); item = await r.json();
  document.getElementById("progress").textContent = `${item.done} of ${item.total} frames done`;
  document.getElementById("bar").style.width = `${100 * item.done / item.total}%`;
  if (item.index === null) {
    document.querySelector("main").innerHTML = "<header><h1>All done. Thank you!</h1></header>" +
      "<p>Tell Claude the labels are finished.</p>";
    return;
  }
  answers = {}; cur = 0;
  document.getElementById("frame").src = `/frame/${item.index}?t=${Date.now()}`;
  render();
}
function render() {
  const box = document.getElementById("claims"); box.innerHTML = "";
  item.claims.forEach((c, i) => {
    const d = document.createElement("div"); d.className = "claim" + (i === cur ? " current" : "");
    d.innerHTML = `<p>${i + 1}. ${c.text.replace(/</g, "&lt;")}</p>`;
    const b = document.createElement("div"); b.className = "btns";
    for (const a of ["present", "absent", "unclear"]) {
      const btn = document.createElement("button"); btn.textContent = LABELS[a];
      btn.className = a + (answers[c.id] === a ? " on" : "");
      btn.onclick = () => { answers[c.id] = a; cur = Math.min(i + 1, item.claims.length - 1); render(); };
      b.append(btn);
    }
    d.append(b); box.append(d);
  });
  document.getElementById("next").disabled = Object.keys(answers).length !== item.claims.length;
}
async function save() {
  if (Object.keys(answers).length !== item.claims.length) return;
  const r = await fetch("/api/label", {method: "POST", headers: {"Content-Type": "application/json"},
                                       body: JSON.stringify({index: item.index, answers})});
  if (!r.ok) { alert(await r.text()); return; }
  load();
}
document.getElementById("next").onclick = save;
document.addEventListener("keydown", (e) => {
  if (!item || item.index === null) return;
  const pick = {"1": "present", "2": "absent", "3": "unclear"}[e.key];
  if (pick) { answers[item.claims[cur].id] = pick; cur = Math.min(cur + 1, item.claims.length - 1); render(); }
  else if (e.key === "ArrowDown") { cur = Math.min(cur + 1, item.claims.length - 1); render(); e.preventDefault(); }
  else if (e.key === "ArrowUp") { cur = Math.max(cur - 1, 0); render(); e.preventDefault(); }
  else if (e.key === "Enter") save();
});
load();
</script></body></html>
"""
