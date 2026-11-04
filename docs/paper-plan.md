# Paper plan (working draft, 2026-11-01)

The testbed, the benchmark and the in-game world are all named **Everfold**. The paper is written in English.

## Working title

**Everfold: Benchmarking Generative World Models as Renderers for Real-Time Multiplayer Open Worlds**

Alternative: *Who Holds the World? Evaluating Generative World Models in Real-Time Multiplayer Open Worlds*

## The gap

Single-player world-model benchmarks (WorldRoamBench 2606.31672, WorldScore 2504.00983, MIND 2602.08025) test
action following, drift and revisit memory for one viewer. Multiplayer work is new and each system is evaluated
on its own game and its own terms:

| Work | What it does | What it leaves open |
|---|---|---|
| PROWL-2 (Odyssey, Oct 2026, paper) | multi-agent RL inside a world model; a "fidelity gate" replays states and withholds rollouts that diverge from real trajectories | fidelity is checked against recorded trajectories in StarCraft and quadrupeds, not against a live multiplayer server |
| MIRA (General Intuition, Kyutai, Epic) | 5B multiplayer model, Rocket League 2v2 with four synchronised views | code open, weights not released; one game |
| Agora-2 (Odyssey, Sep 2026, tech report) | learned simulation model + one renderer per player | its report says view agreement and latency were not measured |
| MASS (2608.06257) | learned logic engine holds state, separate rendering engine per player | evaluated on a Snake benchmark |
| Solaris (2602.22208) | open two-player Minecraft model with view consistency metrics | loses shared context when players leave each other's view |
| MultiGen (2603.06679) | shared editable memory, Doom | one game |
| WorldCast (2610.12412) | per-player generators that exchange state, Counter-Strike 2 | no hits or deaths modelled |
| Multiverse (Enigma Labs) | two-player split-screen racing | tiny resolution |

### Live single-player worlds

Live worlds such as Google DeepMind's Genie 4 and Runway's GWM-1 Worlds generate frames in real time as the user
steers. Genie 4 (research preview to trusted testers, 27 Oct 2026) also generates sound natively, including
characters who converse and react in real time, and creatives already test it as a "draft mode" for
previsualisation. DeepMind's own post says visual details and object permanence can still drift over time,
particularly in longer sessions and after multiple complex prompt edits; press coverage puts consistent scenes at
about two minutes. GWM-1 Worlds (11 Dec 2025) turns a still image and a prompt into an explorable space and claims
that returning to an earlier position restores the same view, which is exactly what our revisit probe measures.
Neither describes a world shared by several players.

Use in the paper: (1) motivation, since live worlds are already used as production tools while their drift is
documented only in vendors' own words; (2) the vendor claims (DeepMind's drift caveat, Runway's revisit claim)
become hypotheses Everfold tests against engine truth; (3) the gap, since all of these are single-viewer.

Sources: https://deepmind.google/blog/genie-4-a-new-generation-of-world-simulation/ ,
https://blog.google/innovation-and-ai/models-and-research/google-deepmind/introducing-genie-4/ ,
https://runway.com/research/introducing-runway-gwm-1 . The two-minute figure is from press reports
(e.g. https://northeasttimes.com/2026/10/27/google-deepmind-opens-genie-4-preview-to-testers-with-audio-and-two-minute/ ),
not from DeepMind; cite it as such or leave it out.

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
| 1 | ABot-World-0 on fal.ai | model holds state, steered by keys and prompts | self-serve fal account | new adapter: player keys become model commands, the view prompt steers the scene |
| 1b | Odyssey-2 Pro | engine holds state, text-steered | existing users only; request access | `everfold bench --adapter odyssey` once a key arrives |
| 1c | Decart Lucy Restyle 2 | engine renders geometry, model restyles | Decart platform | restyle a simple third-person render of the true state |
| 2 | Genie 3 (Project Genie) | text/image-steered | Google AI Ultra, 60 s sessions, no API | export prompts, capture frames by hand, `--adapter folder` |
| 2b | Genie 4 | live world with audio and talking characters | trusted testers now; "coming soon" to AI Ultra (Project Genie) and Gemini API early access | same as Genie 3 once in Project Genie; API adapter when the Gemini API opens. Test DeepMind's drift-after-edits caveat directly: propagation and shrine are prompt edits |
| 2c | Runway GWM-1 Worlds | live world from a still image | early-access form on Runway's GWM-1 page | apply now; revisit probe tests Runway's "returning restores the same view" claim |
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
  - Done 2026-11-03 for seed 42: 98 frames (all 7 runs), 609 claims, one labeller (the author, labeller id
    human1). Judge vs human: agreement 0.81, Cohen's kappa 0.66 over three classes, 0.74 on present vs not.
    Stale facts (state-change checks) 0.98 agreement, present-kappa 1.00; landmarks 0.81; people 0.62; ground 0.47.
    The judge is stricter than the human (44 human-yes/judge-no vs 13 the other way), mostly on ground type and on
    other people's clothing, so fact recall by kind is a lower bound. Re-scoring all seven runs with the human
    labels instead of the judge gives identical probe scores on every probe. Atmosphere kappa (0.27) is low only
    because almost every frame is daytime (95% raw agreement); report raw agreement there.
  - Still needed: a second, independent labeller on an overlapping subset (30-50 frames) for human-human agreement;
    the first labeller knows the study design. Any change to the judge prompt must be checked on labels it was not
    tuned on.
- Ceiling: the FLUX oracle (`flux-oracle`) draws every frame fresh from the true-state prompt. Over 20 seeds with
  the original claim wording (v1) it scored cross-view 95%, revisit 89%, propagation 30%, identity 20%, shrine 0%.
- Claim wording v2 (2026-11-03, commit c3744f7). Three changes, justified only by the oracle's v1 failures:
  - Propagation: a tree stump, not a fresh tree stump. Clearly drawn, weathered stumps were rejected.
  - Shrine: the landmark is only "a stone shrine platform". The compound "two glowing plates and a sealed gate"
    failed whenever any part was missing, and the gate and plates are already separate facts.
  - People: checked by outfit (colour and garment) alone, not the full signature.

  Prompts are unchanged, so every saved frame was re-judged with no new renders. v1 verdicts are kept in each run's
  `v1/` folder. Report both versions. The human labels (human1) were collected against the v1 wording, so the
  judge-human agreement figures above are v1; v2 claims need their own agreement check.
  - Done 2026-11-03 (labels-v2/, labeller human1). 50 new frames, none from round 1. Half come from identity,
    propagation and shrine steps, across the five swept conditions.
    - Overall: 319 claims, agreement 0.79, kappa 0.60 over three classes, 0.66 on present vs not (v1: 0.74).
    - The changed claims agree well: tree stump 7/8, shrine platform 6/6, gate/orb/plate 13/16, stale facts
      16/16 (kappa 1.00).
    - People are the weak kind: other people present-kappa 0.43, self 0.54. Disagreements run both ways
      (15 human-yes/judge-no vs 12 the reverse), so the judge is noisy on outfit colour and garment, not biased.
    - Probe-level check: of the 46 sampled frames carrying probe requirements, judge and human give the same
      pass/fail on 41. All 7 cross-view and all 6 shrine frames match. The 5 that differ split 3 to 2.
  - Second labeller (labels-v2-human2/, labeller human2), same 50 frames, labelled independently from the
    README brief. The brief doesn't mention the study's purpose, the judge or human1's answers.

    | Pair | Agreement | Kappa (3 classes) | Present kappa | People present kappa | Probe pass/fail same |
    |---|---|---|---|---|---|
    | human1 vs human2 | 0.91 | 0.81 | 0.82 | 0.71 | 41/46 |
    | human1 vs judge | 0.79 | 0.60 | 0.66 | 0.53 | 41/46 |
    | human2 vs judge | 0.78 | 0.59 | 0.65 | 0.58 | 42/46 |

    - The judge agrees with each person about equally (0.65–0.66), but less than the two people agree with
      each other (0.82). So the judge is the noisiest rater on single claims.
    - On people specifically, humans reach 0.71. The outfit claims are fairly clear to people, and the
      judge's 0.53–0.58 is the judge's own weakness, not ambiguous wording.
    - Grounds and atmosphere are weak for the judge (ground present-kappa 0.32–0.44), so ground recall
      should not be headlined.
    - At the level the scores use, probe pass/fail, the judge matches each human as often as the humans match
      each other (41–42 of 46), so probe scores are as reliable as a second human rater.
    - These labels have no timestamps, so time per frame can't be reported; rows saved from now on carry
      `saved_at`.
- Run every probe on at least 20 seeds and report spread, not one run.
- Record cost and wall-clock per probe family per model.
- Keep the judge blind to the prompt (it already is) and fixed across models.
