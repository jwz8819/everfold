"""Multi-seed runs under a budget, and the across-seed numbers that go in the paper.

A condition is a fal model, a start and optionally drive, written the way run folders are named:
`abot-image-drive`, `lingbot-image`; or `flux-oracle`, the ceiling (oracle_adapter.py). `sweep` runs each condition on its first N seeds (42, then 1, 2, 3, ...),
seed by seed across conditions so a sweep cut short by the budget is still balanced. It resumes: a run folder
with metrics.json is never run again. Every finished run's cost goes into runs/ledger.jsonl under the sweep's tag,
and a run is not started if the tag's total plus that run's predicted cost would pass the budget.

`aggregate` reads every run folder and reports, per condition, each probe score as the mean over seeds with a 95%
bootstrap interval (seed is the unit), how many seeds could be scored (n/a seeds are left out), and the cost.
"""
from __future__ import annotations

import json
import random
import re
import time
from collections import defaultdict
from pathlib import Path

SEEDS = [42] + [s for s in range(1, 200) if s != 42]
PROBE_KEYS = ("cross_view_agreement", "cross_view_consistency", "revisit_retention", "propagation", "identity_persistence",
              "shrine_state_change", "static_camera_rate")
# Cost of one run before any of the condition has been run (seed 42, 2026-11-02), padded by MARGIN when predicting.
FALLBACK_COST = {"abot": 0.35, "lingbot": 0.70, "eden": 2.70, "flux": 0.05}
MARGIN = 1.15
# -drive walks one session's avatar between poses; -2p gives each player their own session (cross_view only: it
# is the one probe with two viewers, see PerPlayerAdapter)
CONDITION = re.compile(r"^(?:(abot|lingbot|eden)-(preset|image)(-drive|-2p)?|flux-oracle)$")


def parse_plan(items: list[str]) -> list[tuple[str, int]]:
    """["abot-image-drive:20", ...] -> [("abot-image-drive", 20), ...]"""
    plan = []
    for item in items:
        name, _, n = item.partition(":")
        if not CONDITION.match(name) or not n.isdigit() or int(n) < 1:
            raise ValueError(f"bad condition {item!r}; write it like abot-image-drive:20")
        plan.append((name, int(n)))
    return plan


def schedule(plan: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """(condition, seed) pairs, seed-major so every condition advances together."""
    out = []
    for i in range(max(n for _, n in plan)):
        out += [(name, SEEDS[i]) for name, n in plan if i < n]
    return out


def make_adapter(condition: str, settle_s: float):
    if condition == "flux-oracle":
        from .oracle_adapter import FluxOracleAdapter
        return FluxOracleAdapter()
    from .fal_adapter import FalWorldAdapter

    model, start, mode = CONDITION.match(condition).groups()
    if mode == "-2p":
        from .adapters import PerPlayerAdapter
        return PerPlayerAdapter(lambda: FalWorldAdapter(model, settle_s=settle_s, start=start), condition)
    return FalWorldAdapter(model, settle_s=settle_s, start=start, drive=mode == "-drive")


def probes_for(condition: str) -> list[str] | None:
    return ["cross_view"] if condition.endswith("-2p") else None


def run_dir(runs: Path, condition: str, seed: int) -> Path:
    return runs / f"{condition}-seed{seed}"


def ledger_total(runs: Path, tag: str) -> float:
    f = runs / "ledger.jsonl"
    if not f.exists():
        return 0.0
    return sum(r["usd"] for r in map(json.loads, f.read_text(encoding="utf-8").splitlines()) if r["tag"] == tag)


def predicted_cost(runs: Path, condition: str) -> float:
    costs = [m["renderer"]["est_cost_usd"] for m in _metrics(runs, condition) if m.get("renderer")]
    # a -2p run renders only the two cross_view steps, about a third of a full run's session time
    base = max(costs) if costs else FALLBACK_COST[condition.split("-")[0]] * (0.35 if condition.endswith("-2p") else 1)
    return round(base * MARGIN, 4)


async def sweep(plan: list[tuple[str, int]], budget: float, tag: str, runs: Path, judge_factory,
                settle_s: float = 5.0, log=print, dry_run: bool = False) -> dict:
    from .run import run

    todo = [(c, s) for c, s in schedule(plan) if not (run_dir(runs, c, s) / "metrics.json").exists()]
    spent = ledger_total(runs, tag)
    done, skipped = [], []
    for condition, seed in todo:
        need = predicted_cost(runs, condition)
        if spent + need > budget:
            skipped.append(f"{condition}-seed{seed}")
            continue
        if dry_run:
            log(f"would run {condition} seed {seed} (about ${need:.2f})")
            spent += need
            done.append(f"{condition}-seed{seed}")
            continue
        adapter = make_adapter(condition, settle_s)
        out = run_dir(runs, condition, seed)
        t0 = time.monotonic()
        log(f"{condition} seed {seed}: running (spent ${spent:.2f} of ${budget:.2f})")
        try:
            await run(seed, adapter, out, judge_factory(), probes_for(condition))
        except Exception as e:          # noqa: BLE001 - one failed run must not end an overnight sweep
            log(f"{condition} seed {seed}: FAILED {type(e).__name__}: {e}")
            await adapter.aclose()
            usd = round(adapter.cost, 4)     # partial sessions are still billed
        else:
            usd = adapter.stats()["est_cost_usd"]
            done.append(out.name)
        spent += usd
        with (runs / "ledger.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"tag": tag, "run": out.name, "usd": usd,
                                "minutes": round((time.monotonic() - t0) / 60, 1)}) + "\n")
        log(f"{condition} seed {seed}: ${usd:.3f}, total ${spent:.2f}")
    return {"done": done, "skipped_for_budget": skipped, "spent": round(spent, 2)}


# aggregate ---------------------------------------------------------------------------------------------------------

def _metrics(runs: Path, condition: str) -> list[dict]:
    out = []
    for d in sorted(runs.glob(f"{condition}-seed*")):
        if re.fullmatch(rf"{re.escape(condition)}-seed\d+", d.name) and (d / "metrics.json").exists():
            out.append(json.loads((d / "metrics.json").read_text(encoding="utf-8")))
    return out


def bootstrap(xs: list[float], reps: int = 4000, seed: int = 0) -> tuple[float, float] | None:
    if not xs:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(reps))
    return round(means[int(0.025 * reps)], 3), round(means[int(0.975 * reps) - 1], 3)


def aggregate(runs: Path) -> dict:
    conditions = sorted({re.sub(r"-seed\d+$", "", d.name) for d in runs.iterdir()
                         if d.is_dir() and re.search(r"-seed\d+$", d.name)})
    out = {}
    for c in conditions:
        ms = _metrics(runs, c)
        if not ms:
            continue
        row = {"seeds": len(ms)}
        for k in PROBE_KEYS:
            xs = [m[k] for m in ms if m.get(k) is not None]
            row[k] = {"n": len(xs), "mean": round(sum(xs) / len(xs), 3) if xs else None, "ci95": bootstrap(xs)}
        kinds = defaultdict(list)
        for m in ms:
            for kind, v in m["fact_recall_by_kind"].items():
                if v is not None:
                    kinds[kind].append(v)
        row["fact_recall_by_kind"] = {k: round(sum(v) / len(v), 3) for k, v in sorted(kinds.items())}
        costs = [m["renderer"]["est_cost_usd"] for m in ms if m.get("renderer")]
        row["usd_per_run"] = round(sum(costs) / len(costs), 3) if costs else None
        row["cost"] = _cost(c, ms)
        out[c] = row
    return out


def _mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def _cost(condition: str, ms: list[dict]) -> dict:
    """Cost and latency from the renderer stats every run records. A realtime model is billed per second of an open
    session, so one player costs price x 3600 an hour whatever they do; the oracle is billed per image and is not
    realtime (each frame takes over a second), so it has no per-hour price."""
    from .fal_adapter import IMAGE_PRICE, MODELS

    r = [m["renderer"] for m in ms if m.get("renderer")]
    model = MODELS.get(condition.split("-")[0])
    steps = sum(m["steps"] for m in ms if m.get("renderer"))
    responded = [x.get("responded_steps") for x in r if "responded_steps" in x]
    return {"usd_per_player_hour": round(model.price_per_s * 3600, 2) if model else None,
            "usd_per_image": IMAGE_PRICE if condition == "flux-oracle" else None,
            "session_s_per_run": _mean([x.get("session_seconds") for x in r]),
            "ack_s": _mean([x.get("mean_ack_seconds") for x in r]),
            "response_s": _mean([x.get("mean_response_seconds") for x in r]),
            "frame_s": _mean([m.get("mean_frame_seconds") for m in ms]),
            "response_rate": round(sum(responded) / steps, 3) if responded and steps else None,
            "errors_per_run": _mean([len(x.get("errors", [])) for x in r])}


def aggregate_report(a: dict) -> str:
    def cell(x):
        if x["mean"] is None:
            return "n/a"
        lo, hi = x["ci95"]
        return f"{x['mean']:.0%} [{lo:.0%}, {hi:.0%}] n={x['n']}"

    names = {"cross_view_agreement": "Cross-view", "cross_view_consistency": "Same tower", "revisit_retention": "Revisit", "propagation": "Propagation",
             "identity_persistence": "Identity", "shrine_state_change": "Shrine", "static_camera_rate": "Static camera"}
    lines = ["# Everfold results across seeds", "",
             "Mean over seeds with a 95% bootstrap interval (seed is the unit); n = seeds where the probe could be "
             "scored. n/a: the camera never moved, so the probe could not be tested.", "",
             "| Condition | Seeds | " + " | ".join(names.values()) + " | $/run |",
             "|---|---|" + "---|" * len(names) + "---|"]
    for c, row in a.items():
        usd = "n/a" if row["usd_per_run"] is None else f"{row['usd_per_run']:.2f}"
        lines.append(f"| {c} | {row['seeds']} | " + " | ".join(cell(row[k]) for k in names) + f" | {usd} |")
    lines += ["", "## Fact recall by kind (mean over seeds)", "",
              "| Condition | " + " | ".join(sorted({k for r in a.values() for k in r["fact_recall_by_kind"]})) + " |"]
    kinds = sorted({k for r in a.values() for k in r["fact_recall_by_kind"]})
    lines.append("|---|" + "---|" * len(kinds))
    for c, row in a.items():
        lines.append(f"| {c} | " + " | ".join(
            "n/a" if row["fact_recall_by_kind"].get(k) is None else f"{row['fact_recall_by_kind'][k]:.0%}"
            for k in kinds) + " |")
    num = lambda x, fmt: "n/a" if x is None else format(x, fmt)
    lines += ["", "## Cost and latency (mean over seeds)", "",
              "Player-hour: what one player's open session costs for an hour (fal list price per second x 3600). "
              "Ack: prompt sent to model confirms it. Response: prompt sent to the picture visibly changing (mean "
              "absolute pixel change of 12 or more). Responded: share of steps where the picture changed at all. "
              "Errors: moderation refusals and prompts never confirmed, per run.", "",
              "| Condition | $/player-hour | $/run | Session s/run | Ack s | Response s | Frame s | Responded | "
              "Errors/run |", "|---|---|---|---|---|---|---|---|---|"]
    for c, row in a.items():
        k = row.get("cost") or {}
        hour = (f"${k['usd_per_player_hour']:.2f}" if k.get("usd_per_player_hour") is not None
                else f"${k['usd_per_image']}/image" if k.get("usd_per_image") else "n/a")
        lines.append(f"| {c} | {hour} | {num(row['usd_per_run'], '.2f')} | {num(k.get('session_s_per_run'), '.0f')} | "
                     f"{num(k.get('ack_s'), '.1f')} | {num(k.get('response_s'), '.1f')} | {num(k.get('frame_s'), '.1f')} | "
                     f"{num(k.get('response_rate'), '.0%')} | {num(k.get('errors_per_run'), '.1f')} |")
    return "\n".join(lines) + "\n"
