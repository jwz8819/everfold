"""Command line.

    everfold serve [--seed 42] [--port 8765]           play in the browser; open two windows for multiplayer
    everfold bench --adapter reference                 run the probes through the control renderer
    everfold bench --adapter prompts                   export probe prompts to run a model by hand
    everfold bench --adapter folder --frames DIR       judge frames captured by hand from any model
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
    elif args.adapter == "prompts":
        adapter = A.PromptsAdapter()
    elif args.adapter == "odyssey":
        from .bench.odyssey_adapter import OdysseyAdapter
        try:
            adapter = OdysseyAdapter(settle_s=args.settle)
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
    out = Path(args.out) / f"{args.adapter}-seed{args.seed}"
    m = asyncio.run(run(args.seed, adapter, out, judge, args.probes or None))
    print(json.dumps({k: v for k, v in m.items() if k != "judge"}, indent=2))
    print(f"Wrote {out}")


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
    b.add_argument("--adapter", default="reference", choices=["reference", "prompts", "folder", "odyssey"])
    b.add_argument("--settle", type=float, default=5.0, help="seconds to let a streaming model respond per step")
    b.add_argument("--frames", help="folder of hand-captured frames named <step id>.png")
    b.add_argument("--probes", nargs="*", choices=["cross_view", "revisit", "propagation", "identity", "shrine"])
    b.add_argument("--judge-model", default="claude-opus-5-5")
    b.add_argument("--no-judge", action="store_true")
    b.add_argument("--out", default="runs")
    b.set_defaults(fn=cmd_bench)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
