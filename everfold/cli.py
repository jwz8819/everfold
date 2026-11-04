"""Command line.

    everfold serve [--seed 42] [--port 8765]           play in the browser; open two windows for multiplayer
    everfold bench --adapter reference                 run the probes through the control renderer
    everfold bench --adapter prompts                   export probe prompts to run a model by hand
    everfold bench --adapter folder --frames DIR       judge frames captured by hand from any model
    everfold bench --adapter abot|lingbot|eden [--start image] [--drive]
                                                       a realtime world model on fal, headless (billed per second)
    everfold bench --adapter flux-oracle               the ceiling: every frame drawn fresh from the true state
    everfold bench --adapter greybox                   the engine's own 3D render of the true state (free)
    everfold bench --adapter lucy [--per-player]       Decart Lucy restyles the greybox on fal (billed per second)
    everfold rescore runs/<run> ...                    re-score finished runs after a scoring change
    everfold sweep abot-image-drive:20 ... --budget 20 many seeds under a fal budget, resumable
    everfold aggregate                                 means and 95% intervals across seeds
    everfold quests                                    quest grounding: how often the quest writer invents things
    everfold label                                     label judged frames by hand in the browser
    everfold agreement                                 judge vs human agreement from those labels
    everfold agreement --labels A --against B          two labellers on the same frames
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path


def load_env(path: Path = Path(__file__).resolve().parent.parent / ".env") -> None:
    """Read KEY=value lines from a local .env without overriding variables already set."""
    import os

    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.removeprefix("export ").strip(), v.strip().strip("'\"")
        if k and k not in os.environ:
            os.environ[k] = v


def cmd_serve(args) -> None:
    from aiohttp import web

    from .content.llm import LLM, make_client
    from .game import Game
    from .server import Server
    from .store import Store

    client = None if args.scripted else make_client()
    llm = LLM(client, model=args.model) if client else LLM(None)
    store = Store(Path(args.data) / f"world-{args.seed}.sqlite")
    game = Game(args.seed, llm, store)
    import os

    mode = f"Claude ({llm.model})" if llm.enabled else "scripted (set ANTHROPIC_API_KEY for Claude villagers)"
    models = [n for n, k in (("ABot-World-0 via fal", "FAL_KEY"), ("Odyssey", "ODYSSEY_API_KEY")) if os.environ.get(k)]
    print(f"Everfold seed {args.seed} on http://localhost:{args.port}  ·  villagers and quests: {mode}")
    print(f"World models available in the panel: {', '.join(models) or 'none (add keys to .env)'}")
    web.run_app(Server(game).app(), host=args.host, port=args.port, print=None)


def cmd_bench(args) -> None:
    from .bench import adapters as A
    from .bench.judge import Judge
    from .bench.run import run
    from .content.llm import make_client

    if args.adapter == "reference":
        adapter = A.ReferenceAdapter()
    elif args.adapter == "greybox":
        adapter = A.GreyboxAdapter()
    elif args.adapter == "lucy":
        from .bench.lucy_adapter import LucyAdapter
        try:
            adapter = LucyAdapter(per_player=args.per_player)
        except RuntimeError as e:
            sys.exit(str(e))
    elif args.adapter == "prompts":
        adapter = A.PromptsAdapter()
    elif args.adapter == "odyssey":
        from .bench.odyssey_adapter import OdysseyAdapter
        try:
            adapter = OdysseyAdapter(settle_s=args.settle)
        except RuntimeError as e:
            sys.exit(str(e))
    elif args.adapter in ("abot", "lingbot", "eden"):
        from .bench.fal_adapter import FalWorldAdapter
        try:
            make = lambda: FalWorldAdapter(args.adapter, settle_s=args.settle, start=args.start, drive=args.drive,
                                           tile_s=args.tile_s, turn_s=args.turn_s)
            adapter = make()
        except RuntimeError as e:
            sys.exit(str(e))
        if args.per_player:
            adapter = A.PerPlayerAdapter(make, f"{args.adapter}-{args.start}-2p")
    elif args.adapter == "flux-oracle":
        from .bench.oracle_adapter import FluxOracleAdapter
        try:
            adapter = FluxOracleAdapter()
        except RuntimeError as e:
            sys.exit(str(e))
    elif args.adapter == "folder":
        if not args.frames:
            sys.exit("--frames is required with --adapter folder")
        adapter = A.FolderAdapter(args.frames)
    else:
        sys.exit(f"unknown adapter {args.adapter}")
    judge = None
    if not args.no_judge and args.adapter != "prompts":
        client = make_client()
        if client is None:
            print("No ANTHROPIC_API_KEY: frames are saved but not judged.")
        else:
            judge = Judge(client, args.judge_model)
    out = Path(args.out) / f"{adapter.name}-seed{args.seed}"
    m = asyncio.run(run(args.seed, adapter, out, judge, args.probes or None))
    print(json.dumps({k: v for k, v in m.items() if k != "judge"}, indent=2))
    print(f"Wrote {out}")


def cmd_rescore(args) -> None:
    from .bench.judge import Judge
    from .bench.run import rescore
    from .content.llm import make_client

    async def go():
        client = make_client()
        for d in args.runs:
            judge = Judge(client, args.judge_model) if client is not None else None
            try:
                m = await rescore(Path(d), judge)
            except (OSError, RuntimeError, KeyError, ValueError) as e:
                sys.exit(f"{d}: {e}")
            keys = ("cross_view_agreement", "cross_view_consistency", "revisit_retention", "propagation", "identity_persistence",
                    "shrine_state_change", "static_camera_rate")
            print(d, json.dumps({k: m.get(k) for k in keys}))

    asyncio.run(go())


def cmd_sweep(args) -> None:
    from .bench.judge import Judge
    from .bench.sweep import parse_plan, schedule, sweep
    from .content.llm import make_client

    try:
        plan = parse_plan(args.conditions)
    except ValueError as e:
        sys.exit(str(e))
    client = make_client()
    if client is None and not args.dry_run:
        sys.exit("A sweep needs ANTHROPIC_API_KEY: its runs are judged as they finish.")
    runs = Path(args.out)
    runs.mkdir(parents=True, exist_ok=True)
    print(f"{len(schedule(plan))} runs planned for tag {args.tag!r}, budget ${args.budget:.2f}")
    result = asyncio.run(sweep(plan, args.budget, args.tag, runs, lambda: Judge(client, args.judge_model),
                               settle_s=args.settle, dry_run=args.dry_run, log=lambda m: print(m, flush=True)))
    print(json.dumps(result, indent=2))


def cmd_aggregate(args) -> None:
    from .bench.sweep import aggregate, aggregate_report

    report = aggregate_report(aggregate(Path(args.runs)))
    (Path(args.runs) / "aggregate.md").write_text(report, encoding="utf-8")
    print(report)


def cmd_quests(args) -> None:
    from .bench.quest_grounding import batch
    from .content.llm import LLM, make_client

    client = make_client()
    if client is None:
        sys.exit("Quest grounding needs ANTHROPIC_API_KEY: the writer under test is Claude.")
    seeds = list(range(1, args.worlds + 1))
    s = asyncio.run(batch(seeds, LLM(client, model=args.model, effort=args.effort, timeout=60.0), Path(args.out),
                          args.givers, args.personas))
    print((Path(args.out) / "report.md").read_text(encoding="utf-8"))
    print(json.dumps(s["writer"], indent=2))


def cmd_label(args) -> None:
    from aiohttp import web

    from .bench.labels import LabelApp

    exclude = []
    for f in args.exclude or []:
        exclude += json.loads(Path(f).read_text(encoding="utf-8"))
    try:
        app = LabelApp(Path(args.runs), Path(args.labels), args.labeler, args.n, exclude, tuple(args.focus or ()))
    except (OSError, RuntimeError) as e:
        sys.exit(str(e))
    print(f"Labelling {len(app.sample)} frames. Open http://127.0.0.1:{args.port} in your browser.")
    print("Answers save after every frame; stop with Ctrl+C and run this again to resume.")
    web.run_app(app.app(), host="127.0.0.1", port=args.port, print=None)


def cmd_agreement(args) -> None:
    from .bench.labels import agreement, agreement_report

    against = Path(args.against) if args.against else None
    a = agreement(Path(args.runs), Path(args.labels), against)
    if not a["claims"]:
        sys.exit("No labels yet (or none on the same frames). Run `everfold label` first.")
    report = agreement_report(a)
    name = f"agreement-vs-{against.name}.md" if against else "agreement.md"
    (Path(args.labels) / name).write_text(report, encoding="utf-8")
    print(report)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    load_env()
    p = argparse.ArgumentParser(prog="everfold")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the multiplayer game server")
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--data", default="data")
    s.add_argument("--model", default="claude-opus-5-5")
    s.add_argument("--scripted", action="store_true", help="never call Claude")
    s.set_defaults(fn=cmd_serve)
    b = sub.add_parser("bench", help="run the multiplayer world-model probes")
    b.add_argument("--seed", type=int, default=42)
    b.add_argument("--adapter", default="reference", choices=["reference", "greybox", "lucy", "prompts", "folder", "odyssey",
                                                         "abot", "lingbot", "eden", "flux-oracle"])
    b.add_argument("--start", default="preset", choices=["preset", "image"],
                   help="fal models: start from the model's own world, or an image generated from the first prompt")
    b.add_argument("--drive", action="store_true", help="fal models: walk the avatar between probe poses")
    b.add_argument("--per-player", action="store_true",
                   help="fal models: one session per player (use with --probes cross_view; other probes have one viewer)")
    b.add_argument("--tile-s", type=float, default=None, help="fal models with --drive: seconds of forward per tile")
    b.add_argument("--turn-s", type=float, default=None, help="fal models with --drive: seconds of look per 90 degrees")
    b.add_argument("--settle", type=float, default=5.0, help="seconds to let a streaming model respond per step")
    b.add_argument("--frames", help="folder of hand-captured frames named <step id>.png")
    b.add_argument("--probes", nargs="*", choices=["cross_view", "revisit", "propagation", "identity", "shrine"])
    b.add_argument("--judge-model", default="claude-opus-5-5")
    b.add_argument("--no-judge", action="store_true")
    b.add_argument("--out", default="runs")
    b.set_defaults(fn=cmd_bench)

    r = sub.add_parser("rescore", help="recompute scores of finished runs from their saved verdicts")
    r.add_argument("runs", nargs="+", help="run folders, e.g. runs/abot-preset-seed42")
    r.add_argument("--judge-model", default="claude-opus-5-5", help="used only if the probes gained facts")
    r.set_defaults(fn=cmd_rescore)

    sw = sub.add_parser("sweep", help="run fal conditions over many seeds under a budget (resumable)")
    sw.add_argument("conditions", nargs="+", help="e.g. abot-image-drive:20 lingbot-image:8")
    sw.add_argument("--budget", type=float, required=True, help="USD cap on fal spend for this tag")
    sw.add_argument("--tag", default="sweep1", help="ledger tag; reuse it to resume under the same budget")
    sw.add_argument("--settle", type=float, default=5.0)
    sw.add_argument("--judge-model", default="claude-opus-5-5")
    sw.add_argument("--out", default="runs")
    sw.add_argument("--dry-run", action="store_true", help="print what would run and the predicted cost")
    sw.set_defaults(fn=cmd_sweep)

    agg = sub.add_parser("aggregate", help="per-condition means and 95% intervals across seeds")
    agg.add_argument("--runs", default="runs")
    agg.set_defaults(fn=cmd_aggregate)

    qg = sub.add_parser("quests", help="quest grounding: how often the quest writer invents things")
    qg.add_argument("--worlds", type=int, default=20, help="world seeds 1..N")
    qg.add_argument("--givers", type=int, default=2, help="villagers asked for a quest per world")
    qg.add_argument("--model", default="claude-opus-5-5")
    qg.add_argument("--effort", default="low", help="the game's own setting is low")
    qg.add_argument("--personas", default="claude", choices=["claude", "scripted"],
                    help="who writes the quest-givers' personalities: Claude as in play, or the fixed scripted ones")
    qg.add_argument("--out", default="runs/quests")
    qg.set_defaults(fn=cmd_quests)

    lb = sub.add_parser("label", help="label judged frames by hand to calibrate the judge")
    lb.add_argument("--runs", default="runs")
    lb.add_argument("--labels", default="labels")
    lb.add_argument("--labeler", default="human1", help="a name for whoever is labelling (no real names needed)")
    lb.add_argument("--n", type=int, default=100, help="frames to sample the first time")
    lb.add_argument("--exclude", nargs="*", help="sample.json files of earlier rounds: their frames are not drawn again")
    lb.add_argument("--focus", nargs="*", help="step ids (e.g. shrine-00) that fill half the sample")
    lb.add_argument("--port", type=int, default=8770)
    lb.set_defaults(fn=cmd_label)

    ag = sub.add_parser("agreement", help="compare human labels with the judge")
    ag.add_argument("--runs", default="runs")
    ag.add_argument("--labels", default="labels")
    ag.add_argument("--against", help="another labeller's folder: compare the two people instead of person vs judge")
    ag.set_defaults(fn=cmd_agreement)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
