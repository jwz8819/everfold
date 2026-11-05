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
- Refused prompts (checked 2026-11-03). fal's realtime models refused or never confirmed 56 of 714 prompt
  updates (7.8%), about 2 per ABot/LingBot run. Many came with "content moderation failed".
  - Every probe family is affected, including 9 ABot-drive propagation steps.
  - Rescoring only runs where the probe had no refused prompt leaves every conclusion the same: ABot-drive
    propagation 0% (13 runs), shrine 0% everywhere, cross-view 0% (ABot) and 11% (LingBot).
  - Report both, as-run (what a deployment gets) and refusal-free (capability), and give the refusal rate in
    the cost table.
  - Triggers are only weakly identifiable: the blacksmith NPC description, "small hand drum", and generated
    place names such as "Zeldun" (close to a trademark). Prompts stay fixed for comparability; note it as a
    limitation of hosted models.
- Quest grounding (contribution 4), run 2026-11-03 with `everfold quests`. 20 worlds, up to 4 quest-givers
  each (one per role), Claude Opus 5.5 at the game's own low effort. Results are in docs/results-quests.md.
  - Steps: 0 of 200 proposed steps pointed at a place, person or item that does not exist (scripted-persona
    control: 0 of 215). With the ids listed and items enumerated in the schema, structural invention does
    not occur. The validator stays as a guard.
  - Text, Claude-written personalities (as in play): no invented places or people. One vague "Gran"; one
    real villager ("Rari") named from outside the area the writer was shown.
  - Invented items: 28 of 57 quests (49%) ask for an item variety that does not exist ("glowcap moss",
    "silverbell", "honeyclover"), which the step quietly maps to the generic herb or mushroom. All 28 trace
    to the villager's own want, written by the persona generator: invention enters one stage earlier and
    propagates. A fix to test is to give the persona writer the item list too.
  - Variety: with the fixed scripted personalities, 34 distinct titles in 60 quests, one repeated 19 times;
    with Claude personalities, 57 of 57 distinct. Grounding and variety trade off through the persona stage.
  - Method caveat: invented names were found by a heuristic (capitalised non-dictionary words, checked
    against the context), then classified by hand by Claude. A person should confirm the 30-word list
    before publication. Names that are also English words ("Wren", "Love") cannot be caught this way.
- Two-player condition and cross-view consistency (2026-11-03, commit 54aef19).
  - Condition `<model>-image-2p`: one fal session per player (PerPlayerAdapter), as a game running one
    world-model stream per player would. It renders only cross_view, the one probe with two viewers.
    About $0.10 per seed.
  - New score, "same tower" (cross_view_consistency). A pair judge sees both players' frames and the
    landmark description, and decides whether each shows it and whether it is recognisably the same
    structure. Presence alone passes two players who each see a different tower.
  - Pair-judge controls on the 20 oracle towers:
    - Each tower vs a mirrored, cropped copy of itself: judged same 20/20.
    - The two independently drawn oracle frames: same 2/20.
    - So the oracle is a ceiling for presence (95%) but not for consistency (10%). Independent frames don't
      share a world.
  - Seed 42: ABot-2p and LingBot-2p show the tower to both players (cross-view 100%), but a different tower
    each time (same tower 0%). Each session starts from its own FLUX image of that player's view, so the
    worlds disagree from the first frame. That is the point: per-player renderers share nothing unless the
    engine supplies it.
  - 20 seeds each (tag twoplayer1, $2.96, 0 failures):

    | Condition | Cross-view (tower shown) | Same tower |
    |---|---|---|
    | ABot, one session per player | 75% [55, 90] | 5% [0, 15] |
    | LingBot, one session per player | 80% [60, 95] | 0% |
    | ABot, one session walked between players | 0% | 0% |
    | LingBot, one session walked between players | 8% [0, 25] | 0% |
    | FLUX oracle | 95% [85, 100] | 10% [0, 25] |

    Per-player sessions show each player the landmark (they draw from their own start image), but almost
    never the same landmark. The single walked session loses it. Neither architecture gives two players one
    world.
  - Viewpoint check (2026-11-04). Eden's "100% same tower" came from a camera that never left: its second
    view showed the same background with props (chests, stone blocks) added in front. Whole-frame pixel
    similarity missed it because the foreground changed. The pair judge now also answers whether B was
    really taken from elsewhere. If it says "same spot", cross-view and same tower are n/a, as for a frozen
    camera, for every model.
    - Validation: the image-only runs, whose cameras never move, are judged same spot on 15 of 16 pairs;
      two-player pairs are judged different on 40 of 40.
    - Eden drive: same spot on 2 of 3 seeds. Its one valid pair kept the tower (n=1, inconclusive).
    - All pairs were re-judged with the new question. Re-asking moved some calls: LingBot-2p same tower went
      from 0/20 to 2/20 and the oracle from 2/20 to 3/19. That is judge noise within the intervals; report it.
- Eden is game-bound (calibration 2026-11-04, scripts/eden_calibrate.py, docs/eden-games.jpg, $0.64).
  - Eden Live 14B Game always runs one of 12 built-in games (/info lists them). Our image and prompt only
    replace the opening frame; the game's own rules run underneath.
  - Default game "freeze" (a lava crossing): the first forward command drops the game's props (a frozen
    block, a rock ledge) into our scene, then the camera stops responding. Turn and forward change the view
    by almost nothing (frame correlation 0.98-0.99). This explains the same-spot cross-view frames.
  - Game "drone" (free flight in a forest): the camera moves on every command (correlation -0.19 to 0.42),
    but within 4 s the scene becomes the game's own forest. The tower, river and avatar are gone, and a drone
    appears.
  - So neither game can carry the probes. Eden belongs in the taxonomy as a game-locked model: a text or
    image start conditions only the first frames, and the game decides what persists. Report seeds 42, 1, 2
    and this calibration qualitatively. Don't buy more Eden seeds.
- Drive-speed sensitivity (tag sens1, 2026-11-04, $3.48). ABot drive with the seconds per tile and per
  quarter turn (calibrated by eye) scaled x0.5 and x1.5, on the same 5 seeds as the base speed:

  | Drive speed | Seeds | Cross-view | Same tower | Revisit | Propagation | Identity | Shrine | Static camera | $/run |
  |---|---|---|---|---|---|---|---|---|---|
  | x0.5 | 5 | 20% [0%, 60%] | 0% [0%, 0%] | 20% [0%, 60%] | 0% [0%, 0%] | 27% [13%, 33%] | 0% [0%, 0%] | 0% [0%, 0%] | 0.28 |
  | x1 (calibrated) | 5 | 0% [0%, 0%] | 0% [0%, 0%] | 14% [4%, 24%] | 0% [0%, 0%] | 13% [0%, 27%] | 0% [0%, 0%] | 0% [0%, 0%] | 0.38 |
  | x1.5 | 5 | 0% [0%, 0%] | 0% [0%, 0%] | 5% [0%, 15%] | 0% [0%, 0%] | 20% [0%, 47%] | 0% [0%, 0%] | 0% [0%, 0%] | 0.41 |

  - State changes (propagation, shrine) and same tower are 0% at every speed, so the headline results do not
    depend on the calibration.
  - The pose probes move within noise (overlapping intervals). Shorter walks (x0.5) score slightly higher on
    cross-view, revisit and identity, consistent with less time to drift. That is worth one sentence, not a
    claim.
  - One x0.5 run failed to connect (WebRTC timeout) and was rerun.
- Engine renders, model restyles (2026-11-04). This is the second integration pattern.
  - Greybox: the engine's own 3D render of the true state (render/greybox.py). High chase camera over the
    shoulder, with tall occluders faded in the line of sight, as games do. Free.
  - Lucy: Decart Lucy Restyle on fal (`decart/lucy-restyle`, $0.01/s) restyles one greybox clip per probe
    family (hold at each pose, walk between them). One clip per player for the 2p variant.
  - Prompt: art direction plus the people and landmarks true for the whole clip, never a state change.
  - 20 seeds each:

    | Condition | Cross-view | Same tower | Revisit | Propagation | Identity | Shrine |
    |---|---|---|---|---|---|---|
    | Greybox (engine render) | 100% | 100% | 99% [97, 100] | 0% | 70% [57, 83] | 20% [5, 40] |
    | Lucy, one clip | 40% [20, 60] | 10% [0, 25] | 0% (n=6) | 0% | 10% [3, 18] | 0% |
    | Lucy, clip per player | 80% [60, 95] | 35% [15, 55] | n/a | n/a | n/a | n/a |

  - Greybox: perfect cross-view consistency, by construction from one shared state, the only renderer with it.
    Its propagation is 0% because the player who fells the tree stands between the watcher and the stump: the
    probes' text truth has no occlusion, a true 3D camera does. Its shrine is 20% because a small glowing box
    rarely reads as a "floating spirit orb". It is the ceiling for consistency, not for legibility.
  - Lucy keeps the layout, but recolours freely (purple trees), invents effects (fire, glows), and drifts
    over a clip (the 19 s revisit clip ends in a purple sky). Revisit is scorable on only 6 of 20 seeds,
    because its first frame showed nothing the judge recognised.
  - Restyling one shared geometry per player (35% same tower) beats per-player world-model sessions (5-10%)
    but falls far short of the engine's own render (100%). The restyler's freedom costs most of the
    consistency the engine provides.
  - Cost: $0.49 per seed (49 s of clip) for one clip; $0.06 per seed for 2p.
  - fal quirks found: Lucy fails fast (HTTP 500 on the result) when the prompt is over ~900 characters.
    11 of 40 runs hit it; those clips were redone with a 895-character cap (whole villager descriptions
    dropped from the end), and every prompt that had worked is byte-identical under the cap. Clips are now
    uploaded to fal storage rather than sent inline. Lucy returns the clip at half speed (2x duration);
    frames are sampled on the stretched timeline.
  - The "same spot" viewpoint rule applies only to models that move their own camera. For greybox and Lucy
    the engine places the camera, and Lucy's repainting made the pair judge call 10 of 20 one-clip pairs the
    same spot; those are scored rather than hidden as n/a.
- Run every probe on at least 20 seeds and report spread, not one run.
- Record cost and wall-clock per probe family per model.
- Keep the judge blind to the prompt (it already is) and fixed across models.
