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

    with (out / "verdicts.jsonl").open("w", encoding="utf-8") as f:
        for sid, v in verdicts.items():
            f.write(json.dumps({"id": sid, "verdicts": v}) + "\n")
    metrics = score(steps, verdicts)
    metrics["adapter"] = adapter.name
    metrics["seed"] = seed
    metrics["frames"] = sum(1 for s in steps if any((out / "frames").glob(f"{s.id}.*")))
    metrics["mean_frame_seconds"] = round(sum(latency.values()) / max(len(latency), 1), 3)
    if judge is not None:
        metrics["judge"] = {"model": judge.model, "usage": judge.usage, "failures": judge.failures}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (out / "report.md").write_text(report(metrics, steps, verdicts), encoding="utf-8")
    return metrics


def _rate(xs: list[bool]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def score(steps: list[ProbeStep], verdicts: dict[str, dict[str, str]]) -> dict:
    """Per-family scores. A fact counts as shown only when the judge says present."""
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
    # cross-view: did both players' frames show the shared landmark?
    cv = [s for s in steps if s.probe == "cross_view"]
    cross = None
    if len(cv) == 2 and all(s.id in verdicts for s in cv):
        shared = set(cv[0].must) & set(cv[1].must)
        cross = _rate([all(verdicts[s.id].get(m) == "present" for s in cv) for m in shared])
    # revisit: of the facts shown at the first pose, how many are shown again on return?
    retained = []
    for s in steps:
        if s.compare_to is None or s.id not in verdicts:
            continue
        first = idx.get(f"{s.probe}-{s.compare_to:02d}")
        if first is None or first.id not in verdicts:
            continue
        shown_first = {k for k, x in verdicts[first.id].items() if x == "present"}
        for k in shown_first:
            retained.append(verdicts[s.id].get(k) == "present")
    return {
        "fact_recall_by_kind": {k: _rate(v) for k, v in sorted(by_kind.items())},
        "required_facts_by_probe": {k: _rate(v) for k, v in sorted(must.items())},
        "cross_view_agreement": cross,
        "revisit_retention": _rate(retained),
        "propagation": _rate(must.get("propagation", [])),
        "identity_persistence": _rate(must.get("identity", [])),
        "shrine_state_change": _rate(must.get("shrine", [])),
        "frames_judged": len(verdicts),
        "steps": len(steps),
    }


def report(m: dict, steps: list[ProbeStep], verdicts: dict) -> str:
    fmt = lambda x: "n/a" if x is None else f"{x:.0%}"
    lines = [f"# Everfold probe report: {m['adapter']}, seed {m['seed']}", "",
             f"Frames judged: {m['frames_judged']} of {m['steps']} steps.", "",
             "| Measure | Score |", "|---|---|",
             f"| Cross-view agreement | {fmt(m['cross_view_agreement'])} |",
             f"| Revisit retention | {fmt(m['revisit_retention'])} |",
             f"| Cross-player state propagation | {fmt(m['propagation'])} |",
             f"| Identity persistence | {fmt(m['identity_persistence'])} |",
             f"| Shared structure state change | {fmt(m['shrine_state_change'])} |", ""]
    lines += ["## Fact recall by kind", "", "| Kind | Recall |", "|---|---|"]
    lines += [f"| {k} | {fmt(v)} |" for k, v in m["fact_recall_by_kind"].items()]
    lines += ["", "## Per step", ""]
    for s in steps:
        v = verdicts.get(s.id)
        if v is None:
            lines.append(f"- **{s.id}** {s.label}: no frame")
            continue
        missed = [f.text for f in s.view.facts if v.get(f.id) != "present"]
        lines.append(f"- **{s.id}** {s.label}: {sum(x == 'present' for x in v.values())}/{len(v)} shown"
                     + (f". Missing: {'; '.join(missed)}" if missed else ""))
    return "\n".join(lines) + "\n"
