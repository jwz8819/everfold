# Interactive world models an independent researcher can test (checked 2026-11-01)

Compiled from official pages, GitHub, Hugging Face and arXiv. Items marked UNVERIFIED came from secondary sources.

## Models

| Model | Org | Type | Access | Controls | Output | Session | Multiplayer | Cost / hardware | License |
|---|---|---|---|---|---|---|---|---|---|
| Odyssey-2 Pro | Odyssey | frame-by-frame video | self-serve API, JS + Python SDKs | text prompt, optional start image, mid-stream text. No keyboard, mouse or camera input | 1280×704, 22 fps, frame every 50 ms | 150 s per stream, 60 min per connection | broadcast only (one shared stream) | price not published; free tier 5 concurrent streams | Odyssey API licence |
| Odyssey-3 / 3 Pro | Odyssey | frame-by-frame | web research preview; developers asked to get in touch | movement, camera, text events | 480p / 720p | n/p | no | n/p | proprietary |
| Agora-1 | Odyssey | multiplayer shared state | web preview | GoldenEye-style actions | n/p | n/p | 4 players | n/a | proprietary |
| Agora-2 | Odyssey | multiplayer: learned simulation + per-player renderer + authoritative server | web preview + tech report, no API or weights | movement, attack | 640×480; latency not measured in report | n/p | 4 humans + agents | 4× RTX PRO 4500 per 4-player session | proprietary |
| Genie 3 / Project Genie | Google DeepMind | frame-by-frame | Google AI Ultra subscribers, no API | text, image, camera | 720p, 24 fps | 60 s per generation | no | Ultra subscription | proprietary |
| Genie 4 | Google DeepMind | frame-by-frame with audio | trusted testers, waitlist; Gemini API early access "coming soon" | keyboard, camera, text | n/p | short sessions | n/p | n/p | proprietary |
| Marble (World API) | World Labs | static 3D (Gaussian splats + mesh) | self-serve paid API | text, images, video | about 5 min per world | static | via your engine | about $1.20–1.28 per world; drafts $0.12–0.20 | proprietary |
| Waypoint-1.5 | Overworld | frame-by-frame | open weights | keyboard, mouse, text, image | 720p, 56 fps on RTX 5090 | context about 10 s | no | RTX 30-series or newer | Apache 2.0 |
| Waypoint-2 | Overworld | frame-by-frame | invite beta, not on Hugging Face | text, keyboard, mouse | 720p, 75 fps on RTX 5090 | n/p | no | n/p | n/p |
| Oasis 3 Preview | Decart | frame-by-frame, driving only | self-serve API | text + throttle/steering | 3 camera streams | n/p | no | $0.02 per second | proprietary |
| Matrix-Game 2.0 | Skywork | frame-by-frame | open weights | keyboard, mouse | 25 fps on one H100 | long | no | 1× H100 | MIT |
| Matrix-Game 3.0 | Skywork | frame-by-frame | open weights | keyboard, mouse | 720p, up to 40 fps on 8+1 GPUs | minute-long | no | multi-GPU | Apache-2.0 vs MIT conflict |
| HY-World 1.5 WorldPlay | Tencent | frame-by-frame | open weights + training code | WASD + rotation | 480p, 24 fps claimed | memory module | no | 72 GB on one GPU for 8B | Tencent licence (UNVERIFIED) |
| ABot-World-0 | Alibaba AMAP | frame-by-frame, third-person | open weights | raw keyboard | 720p, 16 fps, 1.2 s action-to-frame | very long | no | 1× RTX 5090, about 19 GB | Apache 2.0 |
| WHAM / Muse | Microsoft | frame-by-frame | open weights, research only | controller | 300×180, not real-time | 10 frames | trained on 4v4 play | A6000 | Microsoft Research licence |
| Cosmos 3 | NVIDIA | action-to-video for robots and cars | open weights | camera, robot, vehicle actions | not real-time | n/a | no | H100 | OpenMDW 1.1 |
| GWM-1 Worlds | Runway | frame-by-frame | no Worlds API | actions, camera | 720p | 2 min | no | n/a | proprietary |
| Multiverse | Enigma Labs | multiplayer split-screen | open weights | two players' keyboards | 48×64 per player | n/p | 2 players | consumer GPU | MIT |
| Solaris | NYU | multiplayer multi-view | open weights | Minecraft actions | n/p | n/p | 2 players | at least 48 GB GPU | Apache 2.0 |

Not usable today: Lucid (shut down), General Intuition (waitlist), MineWorld (checkpoints withdrawn),
DreamForge-World (no release), Mirage 2 (browser demo only, details UNVERIFIED).

## Odyssey SDK facts used by this repo

Docs index: https://documentation.api.odyssey.ml/llms.txt

- JS: `npm install @odysseyml/odyssey`. Python 3.12+: `pip install git+https://github.com/odysseyml/odyssey-python.git`.
- Python: `Odyssey(api_key=...)`, `await connect(on_video_frame=...)`, `await start_stream(prompt, portrait=...)`,
  `await interact(prompt)`, `await end_stream()`, `await disconnect()`. Frames are RGB uint8 numpy arrays.
- Browser without exposing the key: the server calls `create_client_credentials()`, the browser calls
  `connectWithCredentials(credentialsFromDict(...))`.
- Limits: 150 s per stream, 60 min per connection, 15 min idle, 5 concurrent streams on the free tier,
  10 queued simulation jobs.

## Papers to cite

- Solaris (2602.22208), MultiGen (2603.06679), MASS (2608.06257), WorldCast (2610.12412), Agora-2 tech report:
  multiplayer and shared state.
- MIND (2602.08025), DreamX-World 1.0 (2606.16993), Latent Spatial Memory (2606.09828): revisit and persistence.
- WorldRoamBench (2606.31672; shares authors with ABot-World-0), WorldScore (2504.00983): evaluation.
- minWM (2605.30263), ABot-World-0 (2607.19191), Matrix-Game 2.0 (2508.13009): runnable systems.
- A Definition and Roadmap for World Models (2607.06401) and World Models: A Comprehensive Survey (2606.00133):
  framing and taxonomy. HAI issue brief (July 2026): the evaluation gap.
