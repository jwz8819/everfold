"""Multiplayer probes. Each one scripts real players through the real engine and records, per camera view,
what is true. Those truths are what a world model's frames are graded against.

Five probe families, each targeting a property single-player world-model benchmarks do not test:
  cross_view   two players look at the same landmark from different sides
  revisit      a player looks, walks away, comes back to the same pose
  propagation  one player changes the world, another player must see the change
  identity     the same player is seen by someone else from several poses
  shrine       two players cooperate to change a structure, a third watches
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..game import Game
from ..render.prompt import compile_prompt
from ..render.reference import render_reference
from ..render.view import Fact, ViewSpec, view


@dataclass
class ProbeStep:
    probe: str
    index: int
    player: str
    label: str
    view: ViewSpec
    prompt: str
    must: list[str] = field(default_factory=list)          # fact ids that must be visible in this frame
    compare_to: int | None = None                          # revisit: index whose facts should reappear
    reference: bytes = b""                                 # top-down render of the true state at capture time
    stale: list[Fact] = field(default_factory=list)        # false now: the other side of a state change

    @property
    def id(self) -> str:
        return f"{self.probe}-{self.index:02d}"

    def to_dict(self) -> dict:
        return {"id": self.id, "probe": self.probe, "index": self.index, "player": self.player, "label": self.label,
                "prompt": self.prompt, "must": self.must, "compare_to": self.compare_to, "view": self.view.to_dict(),
                "facts": [{"id": f.id, "text": f.text, "kind": f.kind} for f in self.view.facts],
                "stale": [{"id": f.id, "text": f.text, "kind": f.kind} for f in self.stale]}

    @property
    def claims(self) -> list[Fact]:
        """Everything the judge is asked about: the true facts plus the stale ones, unmarked."""
        return self.view.facts + self.stale


def stale(label: str) -> Fact:
    """A feature that must NOT be visible: the state before a change, or the one it replaced."""
    return Fact(f"stale:feature:{label}", f"{label} is visible", "feature")


def _snap(game: Game, probe: str, steps: list[ProbeStep], pid: str, label: str, must=(), compare_to=None,
          gone=()) -> ProbeStep:
    v = view(game, pid)
    ids = {f.id for f in v.facts}
    missing = [m for m in must if m not in ids]
    if missing:
        raise RuntimeError(f"{probe}: expected {missing} in view, scene setup is wrong")
    s = ProbeStep(probe, len(steps), pid, label, v, compile_prompt(v), list(must), compare_to,
                  render_reference(game, v), [stale(g) for g in gone])
    steps.append(s)
    return s


def _free(game: Game, x: int, y: int, r: int = 12) -> tuple[float, float]:
    """Nearest walkable tile centre to (x, y)."""
    for d in range(r + 1):
        for dx in range(-d, d + 1):
            for dy in range(-d, d + 1):
                if max(abs(dx), abs(dy)) == d and game.world.walkable(x + dx, y + dy):
                    return x + dx + 0.5, y + dy + 0.5
    raise RuntimeError(f"no walkable tile near {x},{y}")


def _bench_players(game: Game, n: int) -> list[str]:
    ids = []
    for i in range(n):
        pid = f"p_bench{i}"
        game.join(pid, ["Ash", "Briar", "Cove"][i])
        ids.append(pid)
    return ids


def cross_view(game: Game) -> list[ProbeStep]:
    a, b = _bench_players(game, 2)
    game.ensure_around(0, 0, 3)
    tower = next(p for p in game.world.pois.values() if p.kind == "tower")
    steps: list[ProbeStep] = []
    game.teleport(a, *_free(game, tower.x, tower.y + 9), "N")
    game.teleport(b, *_free(game, tower.x - 9, tower.y), "E")
    must = [f"landmark:{tower.id}"]
    _snap(game, "cross_view", steps, a, f"{tower.name} tower from the south", must)
    _snap(game, "cross_view", steps, b, f"{tower.name} tower from the west", must)
    return steps


def revisit(game: Game) -> list[ProbeStep]:
    a, = _bench_players(game, 1)
    village = game.world.pois["village:0:0"]
    sx, sy = _free(game, village.x, village.y + 8)
    steps: list[ProbeStep] = []
    game.teleport(a, sx, sy, "N")
    first = _snap(game, "revisit", steps, a, "village from the south", [f"landmark:{village.id}"])
    game.teleport(a, *_free(game, int(sx), int(sy) + 12), "S")
    _snap(game, "revisit", steps, a, "walked away, facing the other way")
    game.teleport(a, *_free(game, int(sx) + 12, int(sy) + 12), "E")
    _snap(game, "revisit", steps, a, "further away, facing east")
    game.teleport(a, sx, sy, "N")
    _snap(game, "revisit", steps, a, "back at the first pose", [f"landmark:{village.id}"], compare_to=first.index)
    return steps


def propagation(game: Game) -> list[ProbeStep]:
    a, b = _bench_players(game, 2)
    village = game.world.pois["village:0:0"]
    tree = None
    for r in range(4, 48):
        for dx in range(-r, r + 1):
            for dy in (-r, r):
                x, y = village.x + dx, village.y + dy
                if game.world.feature_code(x, y) in ("t", "p") and game.world.walkable(x, y + 1) \
                        and all(game.world.walkable(x + k, y + 1) for k in range(-1, 2)):
                    tree = (x, y)
                    break
            if tree:
                break
        if tree:
            break
    if tree is None:
        raise RuntimeError("no tree near spawn for the propagation probe")
    tx, ty = tree
    steps: list[ProbeStep] = []
    game.teleport(a, tx + 0.5, ty + 1.5, "N")                       # the cutter stands just south
    game.teleport(b, *_free(game, tx, ty + 6), "N")                 # the watcher looks north at it
    _snap(game, "propagation", steps, b, "the tree before anyone touches it",
          gone=["a fresh tree stump", "a crackling campfire"])
    ev = game.interact(a)
    if not ev or ev.get("after") != "x":
        raise RuntimeError("could not fell the tree")
    _snap(game, "propagation", steps, b, f"after {game.players[a].name} fells it",
          ["feature:a fresh tree stump"], gone=["a crackling campfire"])
    game.players[a].inventory["wood"] = game.players[a].inventory.get("wood", 0) + 1
    lit = False
    for fx, fy in [(tx + dx, ty + dy) for dy in (1, 2, 3, 0) for dx in (-1, 1, -2, 2, 0)]:
        if game.world.feature_code(fx, fy) or not game.world.walkable(fx, fy):
            continue
        for facing, (sx, sy) in {"N": (0, 1), "S": (0, -1), "E": (-1, 0), "W": (1, 0)}.items():
            stand = (fx + sx, fy + sy)
            if stand != (tx, ty) and game.world.walkable(*stand):
                game.teleport(a, stand[0] + 0.5, stand[1] + 0.5, facing)
                if game.facing_tile(game.players[a]) == (fx, fy) and game.campfire(a):
                    lit = True
                    break
        if lit:
            break
    if not lit:
        raise RuntimeError("could not light the campfire")
    _snap(game, "propagation", steps, b, f"after {game.players[a].name} lights a campfire",
          ["feature:a crackling campfire"])
    return steps


def identity(game: Game) -> list[ProbeStep]:
    a, b = _bench_players(game, 2)
    village = game.world.pois["village:0:0"]
    ax, ay = _free(game, village.x + 2, village.y + 6)
    game.teleport(a, ax, ay, "S")
    steps: list[ProbeStep] = []
    for i, (dx, dy, facing) in enumerate([(0, -5, "S"), (5, 0, "W"), (0, 5, "N")]):
        game.teleport(b, *_free(game, int(ax) + dx, int(ay) + dy, 3), facing)
        game.step(30.0)                                         # time passes between sightings
        _snap(game, "identity", steps, b, f"sighting {i + 1} of {game.players[a].name}", [f"person:{a}"])
    return steps


def shrine(game: Game) -> list[ProbeStep]:
    a, b, c = _bench_players(game, 3)
    game.ensure_chunk(1, 0)
    sh = game.world.pois["shrine:1:0"]
    steps: list[ProbeStep] = []
    game.teleport(c, *_free(game, sh.x, sh.y + 6), "N")
    game.teleport(a, *_free(game, sh.x - 8, sh.y), "E")
    game.teleport(b, *_free(game, sh.x + 8, sh.y), "W")
    _snap(game, "shrine", steps, c, "sealed shrine", [f"landmark:{sh.id}", "feature:a sealed stone gate"],
          gone=["an open stone gate", "a floating spirit orb"])
    (p1x, p1y), (p2x, p2y) = sh.slots
    game.teleport(a, p1x + 0.5, p1y + 0.5, "N")
    game.teleport(b, p2x + 0.5, p2y + 0.5, "N")
    game.step(0.1)
    if not sh.state.get("solved"):
        raise RuntimeError("shrine did not open with two players on the plates")
    game.teleport(a, *_free(game, sh.x - 5, sh.y + 4), "E")
    game.teleport(b, *_free(game, sh.x + 5, sh.y + 4), "W")
    _snap(game, "shrine", steps, c, "after two players open it",
          [f"landmark:{sh.id}", "feature:an open stone gate", "feature:a floating spirit orb"],
          gone=["a sealed stone gate"])
    return steps


PROBES = {"cross_view": cross_view, "revisit": revisit, "propagation": propagation, "identity": identity,
          "shrine": shrine}


def build(seed: int, names: list[str] | None = None) -> list[ProbeStep]:
    """Each probe family runs in a fresh world so they cannot contaminate each other."""
    out = []
    for name in names or list(PROBES):
        game = Game(seed)
        game.t = 200.0          # daytime
        out.extend(PROBES[name](game))
    return out


def distance(a: ViewSpec, b: ViewSpec) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)
