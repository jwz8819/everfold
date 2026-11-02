# Project Hyrule (codename) · the Everfold

A real-time multiplayer open world that writes itself as players walk, built as a testbed for comparing
generative world models. The game server holds every fact. World models only draw what a player's camera sees,
and the benchmark grades their frames against the server's truth.

The research plan is in [docs/paper-plan.md](docs/paper-plan.md).

## Play

```bash
uv venv .venv && uv pip install -e ".[dev,claude]"
```

```bash
.venv/bin/python -m hyrule.cli serve
```

Open http://localhost:8765 in two browser windows to play together.

| Key | Does |
|---|---|
| WASD or arrows | walk |
| E | gather from a tree, bush, rock, flowers or chest |
| F | light a campfire (costs one wood) |
| T | talk to the nearest villager |
| G | hand items to a villager for a quest |
| Enter | chat with players near you |

Without `ANTHROPIC_API_KEY` villagers and quests are scripted. With it, Claude writes each villager the first time
someone comes near, voices them in conversation, and writes quests on the spot. Every quest is checked against
the real map before a player sees it.

## What is generated, and when

| Thing | When | How |
|---|---|---|
| Terrain, rivers, forests, peaks | the moment a chunk comes into range | seeded noise, identical every time |
| Villages, shrines, ruins, stables, towers | with their chunk | seeded placement |
| Villager names and personalities | first time a player comes within 12 tiles | Claude, or scripted |
| Dialogue | each conversation | Claude, with memory of each player and gossip about what other players did |
| Quests | when a villager decides to ask | Claude, validated against real places, people and items |

Shrines open only when two different players stand on both plates at once. Felled trees stay felled. Bushes,
chests and flowers regrow. Everything players change is saved to SQLite and survives a restart.

## Benchmark

```bash
.venv/bin/python -m hyrule.cli bench --adapter reference
```

| Adapter | Use |
|---|---|
| `reference` | top-down render of the true state; a pipeline check, not a world model |
| `prompts` | writes `prompts.md` so you can run any model by hand |
| `folder --frames DIR` | judges frames you captured by hand, named `<step id>.png` |
| `odyssey` | Odyssey-2 Pro through its Python SDK; needs `ODYSSEY_API_KEY` and `uv pip install -e ".[odyssey]"` |

The five probes are cross-view agreement, revisit retention, cross-player state propagation, identity
persistence, and shared-structure state change. A Claude vision judge marks each ground-truth fact present,
absent or unclear. It never sees the prompt. Results land in `runs/<adapter>-seed<n>/report.md`.

To watch Odyssey live in the game, set `ODYSSEY_API_KEY` before `serve`, install the Odyssey extra, and pick
"Odyssey-2 Pro (live)" in the World model view panel. The key stays on the server.

## Layout

| Path | Job |
|---|---|
| `hyrule/world.py` | chunked map generation and player changes |
| `hyrule/game.py` | the authoritative game: movement, gathering, shrines, villagers, quests, events |
| `hyrule/content/` | Claude calls with scripted fallbacks: villagers, dialogue, quests |
| `hyrule/render/` | camera view, prompt compiler, reference renderer |
| `hyrule/bench/` | probes, adapters, judge, scoring |
| `hyrule/server.py` | WebSocket server and static client |
| `client/` | browser client and live renderer plug-ins |

## Tests

```bash
.venv/bin/python -m pytest -q
```
