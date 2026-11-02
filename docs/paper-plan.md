# Paper plan (working draft, 2026-11-01)

Internal codename: Project Hyrule. "Hyrule" and "Zelda" are Nintendo trademarks, so the public name of the
testbed and the paper must be original. The in-game world is already called the Everfold.

## Working title

**Who Holds the World? Evaluating Generative World Models as Renderers for Real-Time Multiplayer Open Worlds**

## The gap

Single-player world-model benchmarks (WorldRoamBench 2606.31672, WorldScore 2504.00983, MIND 2602.08025) test
action following, drift and revisit memory for one viewer. Multiplayer work is new and each system is evaluated
on its own game and its own terms:

| Work | What it does | What it leaves open |
|---|---|---|
| Agora-2 (Odyssey, Sep 2026, tech report) | learned simulation model + one renderer per player | its report says view agreement and latency were not measured |
| MASS (2608.06257) | learned logic engine holds state, separate rendering engine per player | evaluated on a Snake benchmark |
| Solaris (2602.22208) | open two-player Minecraft model with view consistency metrics | loses shared context when players leave each other's view |
| MultiGen (2603.06679) | shared editable memory, Doom | one game |
| WorldCast (2610.12412) | per-player generators that exchange state, Counter-Strike 2 | no hits or deaths modelled |
| Multiverse (Enigma Labs) | two-player split-screen racing | tiny resolution |

No benchmark compares heterogeneous world models (text-steered APIs, keyboard-driven open models, static 3D
generators, multiplayer-native models) on the same multiplayer properties against an authoritative ground truth.

## Contributions

1. **A taxonomy of integration patterns** for world models in multiplayer games, following the
   renderer / simulator / planner split (Fei-Fei 2026, as discussed in arXiv 2607.06401):
   - *engine-holds-state, model renders* (text- or state-conditioned rendering; this testbed, MASS, Agora-2's renderer)
   - *model holds state* (keyboard-driven models that invent their own world; Waypoint, Matrix-Game, ABot)
   - *model generates assets, engine renders* (static 3D: World Labs Marble)
   - *multiplayer-native* (Solaris, Multiverse, Agora)
2. **An open testbed** (this repository): a real-time multiplayer open world whose map, villagers and quests are
   generated on demand, with an authoritative server, persistence, and a pluggable renderer interface.
3. **Five multiplayer probes with ground truth** from the engine: cross-view agreement, revisit retention,
   cross-player state propagation, identity persistence, shared-structure state change.
4. **Grounded content generation**: quests written by an LLM are validated against real entities; the rejection
   rate measures how often the writer invents places, people or items.
5. **Results across models**, including cost per player-hour and latency, and which probes each integration
   pattern can even attempt.

## Model order

| Order | Model | Pattern | Access | What to run |
|---|---|---|---|---|
| 0 | Reference renderer | control | built in | calibrate the judge against 100+ human labels first |
| 1 | Odyssey-2 Pro | engine holds state, text-steered | self-serve API, free tier 5 streams | `hyrule bench --adapter odyssey` |
| 2 | Genie 3 (Project Genie) | text/image-steered | Google AI Ultra, 60 s sessions, no API | export prompts, capture frames by hand, `--adapter folder` |
| 3 | World Labs Marble | asset generator | paid API, about $1.20 per world | generate each landmark once, render in the engine |
| 4 | Waypoint-1.5, ABot-World-0, Matrix-Game 2.0 | model holds state | open weights, one rented GPU | action-driven adapter; only self-consistency probes apply |
| 5 | Solaris | multiplayer-native | open weights, 48 GB GPU | its own two-player cross-view run as the multiplayer baseline |
| 6 | Agora-2 | multiplayer-native | web demo only | qualitative only; its world is fixed |

## Venues

- **Main target: NeurIPS 2027 Datasets & Benchmarks** (deadline expected around May 2027, not yet announced).
- Earlier, smaller paper: IEEE CoG 2027 (expected around March 2027) with the testbed and first two models.
- arXiv preprint as soon as the Odyssey and Genie results are in.
- FDG 2027 full papers are due 11 January 2027 (unverified), which is too early for results.

## Before any number goes in the paper

- Human-label at least 100 frames and report judge agreement. Without that the judge numbers are not evidence.
- Run every probe on at least 20 seeds and report spread, not one run.
- Record cost and wall-clock per probe family per model.
- Keep the judge blind to the prompt (it already is) and fixed across models.
