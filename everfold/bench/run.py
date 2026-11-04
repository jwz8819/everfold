"""Run the probes through one renderer, judge the frames, and write a report.

    runs/<run>/steps.jsonl       every probe step with its prompt and ground-truth facts
    runs/<run>/prompts.md        prompts in order, for running a model by hand
    runs/<run>/reference/        top-down truth renders
    runs/<run>/frames/           what the renderer produced
    runs/<run>/verdicts.jsonl    judge output per frame
    runs/<run>/report.md         the numbers that go in the paper
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .adapters import Adapter
from .judge import Judge, media_type
from .probes import ProbeStep, build


def _ext(img: bytes) -> str:
    return media_type(img).split("/")[1].replace("jpeg", "jpg")


def _frame_path(out: Path, sid: str) -> Path | None:
    return next(iter(sorted((out / "frames").glob(f"{sid}.*"))), None)


async def judge_pair(steps: list[ProbeStep], out: Path, judge: Judge) -> dict | None:
    """Show the judge both cross-view frames together: is the shared landmark recognisably the same structure?
    Presence alone cannot tell two players apart who each see a different tower. Saved to pair.json."""
    cv = [s for s in steps if s.probe == "cross_view"]
    frames = [_frame_path(out, s.id) for s in cv]
    if len(cv) != 2 or None in frames:
        return None
    shared = [f for f in cv[0].view.facts if f.id in set(cv[0].must) & set(cv[1].must)]
    if not shared:
        return None
    thing = shared[0].text.removesuffix(" is visible")
    pair = {"steps": [s.id for s in cv], "thing": thing,
            **await judge.same_object(frames[0].read_bytes(), frames[1].read_bytes(), thing)}
    (out / "pair.json").write_text(json.dumps(pair), encoding="utf-8")
    return pair


def apply_pair(pair: dict | None, metrics: dict) -> None:
    """Add cross-view consistency to the metrics. A second view the pair judge calls the same viewpoint (same
    background, the landmark at the same angle, things merely added in front) means the camera never really
    moved, so cross-view is not scored at all, exactly as for a frozen camera. Pixel similarity misses this: a
    model that drops props in the foreground changes the frame without moving the camera."""
    if pair is not None and pair.get("viewpoint") == "same":
        metrics["cross_view_agreement"] = None
    metrics["cross_view_same_viewpoint"] = None if pair is None else pair.get("viewpoint") == "same"
    metrics["cross_view_consistency"] = consistency(pair, metrics)


def consistency(pair: dict | None, metrics: dict) -> float | None:
    """1 when both players' frames show the shared landmark and it is the same structure. Not scored (None) when
    there is no pair or the cross-view camera never moved (cross-view agreement is n/a then too)."""
    if pair is None or metrics.get("cross_view_agreement") is None:
        return None
    return 1.0 if pair["a"] == "present" and pair["b"] == "present" and pair["same"] == "same" else 0.0


async def run(seed: int, adapter: Adapter, out: Path, judge: Judge | None, probes: list[str] | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    (out / "reference").mkdir(exist_ok=True)
    (out / "frames").mkdir(exist_ok=True)
    steps = build(seed, probes)
    with (out / "steps.jsonl").open("w", encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")
            (out / "reference" / f"{s.id}.png").write_bytes(s.reference)
    with (out / "prompts.md").open("w", encoding="utf-8") as f:
        f.write(f"# Probe prompts, seed {seed}\n\nRun each family as one continuous session, in order. "
                f"Save each frame as `frames/<id>.png`.\n\n")
        for s in steps:
            f.write(f"## {s.id}: {s.label}\n\n{s.prompt}\n\n")

    verdicts: dict[str, dict[str, str]] = {}
    latency: dict[str, float] = {}
    if hasattr(adapter, "prepare"):          # batch renderers (Lucy) make all their frames up front
        await adapter.prepare(steps)
    current = None
    for s in steps:
        if s.probe != current:
            if current is not None:
                await adapter.close()
            await adapter.open(s.probe)
            current = s.probe
        img, seconds = await adapter.frame(s)
        latency[s.id] = seconds
        if img is None:
            continue
        (out / "frames" / f"{s.id}.{_ext(img)}").write_bytes(img)
        if judge is not None:
            verdicts[s.id] = await judge.check(s, img)
    if current is not None:
        await adapter.close()
    if hasattr(adapter, "aclose"):
        await adapter.aclose()

    with (out / "verdicts.jsonl").open("w", encoding="utf-8") as f:
        for sid, v in verdicts.items():
            f.write(json.dumps({"id": sid, "verdicts": v}) + "\n")
    metrics = score(steps, verdicts, static_steps(steps, out / "frames"))
    pair = await judge_pair(steps, out, judge) if judge is not None else None
    apply_pair(pair, metrics)
    metrics["adapter"] = adapter.name
    metrics["seed"] = seed
    metrics["frames"] = sum(1 for s in steps if any((out / "frames").glob(f"{s.id}.*")))
    metrics["mean_frame_seconds"] = round(sum(latency.values()) / max(len(latency), 1), 3)
    if hasattr(adapter, "stats"):
        metrics["renderer"] = adapter.stats()
    if judge is not None:
        metrics["judge"] = {"model": judge.model, "usage": judge.usage, "failures": judge.failures}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out / "report.md").write_text(report(metrics, steps, verdicts), encoding="utf-8")
    return metrics


async def rescore(out: Path, judge: Judge | None = None) -> dict:
    """Recompute the scores of a finished run after the scoring changes, from its saved frames and verdicts.

    The steps are rebuilt from the seed (probes are deterministic). If they still match steps.jsonl the saved
    verdicts are reused. If the probes changed (new facts to check), a judge is required: every saved frame is
    judged again against the new steps, which costs judge calls but no world-model time. Run-time fields such as
    renderer stats are kept."""
    old = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    saved = [json.loads(line) for line in (out / "steps.jsonl").read_text(encoding="utf-8").splitlines()]
    steps = build(old["seed"], list(dict.fromkeys(s["probe"] for s in saved)))
    fresh = [json.loads(json.dumps(s.to_dict(), ensure_ascii=False)) for s in steps]
    # Facts and stale facts are the judge's claims about the world, not the world: when only they changed, the saved
    # frames still show the same steps and are judged again.
    same_world = lambda ds: [{k: v for k, v in d.items() if k not in ("facts", "stale")}
                             | {"view": {k: v for k, v in d["view"].items() if k != "facts"}} for d in ds]
    if same_world(fresh) != same_world(saved):
        raise RuntimeError(f"{out}: the probes now describe a different world; this run cannot be rescored")
    verdicts: dict[str, dict[str, str]] = {}
    if fresh == saved:
        with (out / "verdicts.jsonl").open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                verdicts[row["id"]] = row["verdicts"]
    else:
        if judge is None:
            raise RuntimeError(f"{out}: the judge's claims changed since this run; rescore with a judge to re-judge it")
        for s in steps:
            frame = _frame_path(out, s.id)
            if frame is not None:
                verdicts[s.id] = await judge.check(s, frame.read_bytes())
        with (out / "steps.jsonl").open("w", encoding="utf-8") as f:
            for d in fresh:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        with (out / "verdicts.jsonl").open("w", encoding="utf-8") as f:
            for sid, v in verdicts.items():
                f.write(json.dumps({"id": sid, "verdicts": v}) + "\n")
        old["judge"] = {"model": judge.model, "usage": judge.usage, "failures": judge.failures, "rejudged": True}
    metrics = {**old, **score(steps, verdicts, static_steps(steps, out / "frames"))}
    pair_file = out / "pair.json"
    pair = json.loads(pair_file.read_text(encoding="utf-8")) if pair_file.exists() else None
    if (pair is None or "viewpoint" not in pair) and judge is not None:
        pair = await judge_pair(steps, out, judge)
    apply_pair(pair, metrics)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out / "report.md").write_text(report(metrics, steps, verdicts), encoding="utf-8")
    return metrics


RETENTION_KINDS = {"landmark", "person", "feature"}


def _rate(xs: list[bool]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


# Two frames are the same picture when their normalised 32x18 grey images correlate above this. Measured on seed 42
# (2026-11-02): ABot frames that ignored a move scored 0.95-0.99 despite flicker and colour drift; frames after a
# real move (ABot driven, reference renderer) scored 0.50 or less.
STATIC_CORR = 0.9


def _moved(a: ProbeStep, b: ProbeStep) -> bool:
    return abs(a.view.x - b.view.x) + abs(a.view.y - b.view.y) > 0.5 or a.view.facing != b.view.facing


def _thumb(path: Path) -> list[float]:
    from PIL import Image

    px = list(Image.open(path).convert("L").resize((32, 18)).tobytes())
    mean = sum(px) / len(px)
    sd = (sum((p - mean) ** 2 for p in px) / len(px)) ** 0.5 or 1.0
    return [(p - mean) / sd for p in px]


def static_steps(steps: list[ProbeStep], frames: Path) -> list[str]:
    """Steps whose camera should have moved since the previous step of the family but whose frame did not change.
    A model that ignores movement would otherwise pass cross-view, revisit and identity by repeating one picture."""
    def thumb(s):
        f = next(iter(sorted(frames.glob(f"{s.id}.*"))), None)
        return _thumb(f) if f else None

    out = []
    for a, b in zip(steps, steps[1:]):
        if a.probe != b.probe or not _moved(a, b):
            continue
        ta, tb = thumb(a), thumb(b)
        if ta and tb and sum(x * y for x, y in zip(ta, tb)) / len(ta) > STATIC_CORR:
            out.append(b.id)
    return out


def _state_ok(s: ProbeStep, v: dict[str, str]) -> bool:
    """The frame shows the current state and not the stale one."""
    return all(v.get(m) == "present" for m in s.must) and all(v.get(f.id) == "absent" for f in s.stale)


def score(steps: list[ProbeStep], verdicts: dict[str, dict[str, str]], static: list[str] = ()) -> dict:
    """Per-family scores. A fact counts as shown only when the judge says present.

    State changes (propagation, shrine) are scored per transition: the frame before must show the old state and
    not the new one, and the frame after the reverse, so a picture that never changes cannot pass. Probes that need
    the camera to move are not scored (None) when a frame repeated the previous one; `static` lists those steps."""
    by_kind: dict[str, list[bool]] = defaultdict(list)
    must: dict[str, list[bool]] = defaultdict(list)
    for s in steps:
        v = verdicts.get(s.id)
        if v is None:
            continue
        for f in s.view.facts:
            by_kind[f.kind].append(v.get(f.id) == "present")
        for m in s.must:
            must[s.probe].append(v.get(m) == "present")

    idx = {s.id: s for s in steps}
    frozen = {idx[i].probe for i in static if i in idx}

    def changes(probe: str) -> float | None:
        fam = [s for s in steps if s.probe == probe]
        return _rate([_state_ok(a, verdicts[a.id]) and _state_ok(b, verdicts[b.id])
                      for a, b in zip(fam, fam[1:]) if a.id in verdicts and b.id in verdicts])

    # cross-view: did both players' frames show the shared landmark?
    cv = [s for s in steps if s.probe == "cross_view"]
    cross = None
    if len(cv) == 2 and all(s.id in verdicts for s in cv):
        shared = set(cv[0].must) & set(cv[1].must)
        cross = _rate([all(verdicts[s.id].get(m) == "present" for s in cv) for m in shared])
    # revisit: of the scene objects shown at the first pose, how many are shown again on return? Light, weather
    # and ground are left out: a frozen or generic picture keeps those for free.
    retained = []
    for s in steps:
        if s.compare_to is None or s.id not in verdicts:
            continue
        first = idx.get(f"{s.probe}-{s.compare_to:02d}")
        if first is None or first.id not in verdicts:
            continue
        objects = {f.id for f in first.view.facts if f.kind in RETENTION_KINDS}
        shown_first = {k for k, x in verdicts[first.id].items() if x == "present" and k in objects}
        for k in shown_first:
            retained.append(verdicts[s.id].get(k) == "present")
    return {
        "fact_recall_by_kind": {k: _rate(v) for k, v in sorted(by_kind.items())},
        "required_facts_by_probe": {k: _rate(v) for k, v in sorted(must.items())},
        "cross_view_agreement": None if "cross_view" in frozen else cross,
        "revisit_retention": None if "revisit" in frozen else _rate(retained),
        "propagation": changes("propagation"),
        "identity_persistence": None if "identity" in frozen else _rate(must.get("identity", [])),
        "shrine_state_change": changes("shrine"),
        "static_steps": sorted(static),
        "static_camera_rate": _rate([b.id in static for a, b in zip(steps, steps[1:])
                                     if a.probe == b.probe and _moved(a, b) and b.id in verdicts]),
        "frames_judged": len(verdicts),
        "steps": len(steps),
    }


def report(m: dict, steps: list[ProbeStep], verdicts: dict) -> str:
    fmt = lambda x: "n/a" if x is None else f"{x:.0%}"
    lines = [f"# Everfold probe report: {m['adapter']}, seed {m['seed']}", "",
             f"Frames judged: {m['frames_judged']} of {m['steps']} steps.", ""]
    if m.get("renderer"):
        lines += ["Renderer: " + ", ".join(f"{k} {v}" for k, v in m["renderer"].items() if v not in (None, [])), ""]
    lines += ["| Measure | Score |", "|---|---|",
             f"| Cross-view agreement | {fmt(m['cross_view_agreement'])} |",
             f"| Cross-view consistency (same structure in both views) | {fmt(m.get('cross_view_consistency'))} |",
             f"| Revisit retention | {fmt(m['revisit_retention'])} |",
             f"| Cross-player state propagation | {fmt(m['propagation'])} |",
             f"| Identity persistence | {fmt(m['identity_persistence'])} |",
             f"| Shared structure state change | {fmt(m['shrine_state_change'])} |",
             f"| Static camera (frame unchanged after a move) | {fmt(m.get('static_camera_rate'))} |", "",
             "n/a on a pose probe means its camera never moved, so the probe could not be tested.", ""]
    lines += ["## Fact recall by kind", "", "| Kind | Recall |", "|---|---|"]
    lines += [f"| {k} | {fmt(v)} |" for k, v in m["fact_recall_by_kind"].items()]
    lines += ["", "## Per step", ""]
    for s in steps:
        v = verdicts.get(s.id)
        if v is None:
            lines.append(f"- **{s.id}** {s.label}: no frame")
            continue
        missed = [f.text for f in s.view.facts if v.get(f.id) != "present"]
        wrong = [f.text for f in s.stale if v.get(f.id) == "present"]
        if wrong:
            missed.append("SHOWN BUT NO LONGER TRUE: " + ", ".join(wrong))
        if s.id in m.get("static_steps", []):
            missed.append("STATIC: same picture as the previous step although the camera moved")
        shown = sum(v.get(f.id) == "present" for f in s.view.facts)
        lines.append(f"- **{s.id}** {s.label}: {shown}/{len(s.view.facts)} shown"
                     + (f". Missing: {'; '.join(missed)}" if missed else ""))
    return "\n".join(lines) + "\n"
