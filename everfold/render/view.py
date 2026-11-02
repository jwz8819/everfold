"""What one player's camera sees, computed from the authoritative state.

A ViewSpec is renderer-neutral. Text-conditioned world models get it as a prompt; the benchmark keeps its
`facts` as ground truth and asks a judge whether a rendered frame shows them.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .. import config as C
from ..game import FACING, Game
from ..world import FEATURES, GROUND

CONE_DEGREES = 50          # half-angle of the camera cone
NOTABLE = set("CxkGOThswcogu")        # features worth naming individually


@dataclass
class Seen:
    kind: str                 # landmark | person | feature
    id: str                   # poi id, player/npc id, or feature@x,y
    label: str
    side: str                 # left | ahead | right
    distance: float

    @property
    def band(self) -> str:
        return "close by" if self.distance <= 4 else "a little way off" if self.distance <= 12 else "in the distance"


@dataclass
class Fact:
    id: str
    text: str
    kind: str                 # ground | landmark | person | feature | atmosphere


@dataclass
class ViewSpec:
    player: str
    x: float
    y: float
    facing: str
    signature: str
    ground_here: str
    ahead: list[str]
    seen: list[Seen]
    time_of_day: str
    weather: str
    facts: list[Fact] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["seen"] = [asdict(s) | {"band": s.band} for s in self.seen]
        return d


def _bearing(facing: str, dx: float, dy: float) -> tuple[float, str]:
    fx, fy = FACING[facing]
    dot = fx * dx + fy * dy
    cross = fx * dy - fy * dx
    ang = math.degrees(math.atan2(cross, dot))
    side = "left" if ang < -18 else "right" if ang > 18 else "ahead"
    return ang, side


def view(game: Game, pid: str) -> ViewSpec:
    p = game.players[pid]
    w = game.world
    seen: list[Seen] = []
    ground_counts: dict[str, int] = {}
    feature_counts: dict[str, int] = {}
    px, py = math.floor(p.x), math.floor(p.y)
    for dx in range(-C.VIEW_RADIUS, C.VIEW_RADIUS + 1):
        for dy in range(-C.VIEW_RADIUS, C.VIEW_RADIUS + 1):
            dist = math.hypot(dx, dy)
            if dist > C.VIEW_RADIUS or dist < 0.5:
                continue
            ang, side = _bearing(p.facing, dx, dy)
            if abs(ang) > CONE_DEGREES:
                continue
            x, y = px + dx, py + dy
            g = w.ground(x, y)
            ground_counts[g.code] = ground_counts.get(g.code, 0) + 1
            code = w.feature_code(x, y)
            if not code:
                continue
            feature_counts[code] = feature_counts.get(code, 0) + 1
            if code in NOTABLE and code not in "hT":      # houses and towers are described by their landmark
                seen.append(Seen("feature", f"{code}@{x},{y}", FEATURES[code].label, side, dist))
    for poi in w.pois_near(p.x, p.y, C.LANDMARK_RADIUS):
        dx, dy = poi.x + 0.5 - p.x, poi.y + 0.5 - p.y
        ang, side = _bearing(p.facing, dx, dy)
        reach = C.LANDMARK_RADIUS if poi.kind == "tower" else C.VIEW_RADIUS * 2
        if abs(ang) <= CONE_DEGREES + 10 and math.hypot(dx, dy) <= reach:
            seen.append(Seen("landmark", poi.id, poi.label(), side, math.hypot(dx, dy)))
    people = [(o.id, o.signature, o.x, o.y) for o in game.players.values() if o.online and o.id != pid]
    people += [(n.id, n.signature, n.x, n.y) for n in game.npcs.values()]
    for oid, sig, ox, oy in people:
        dx, dy = ox - p.x, oy - p.y
        dist = math.hypot(dx, dy)
        ang, side = _bearing(p.facing, dx, dy)
        if dist <= C.VIEW_RADIUS and abs(ang) <= CONE_DEGREES:
            seen.append(Seen("person", oid, sig, side, dist))
    seen.sort(key=lambda s: ({"landmark": 0, "person": 1, "feature": 2}[s.kind], s.distance))

    ahead = [GROUND[k].label for k in sorted(ground_counts, key=lambda k: -ground_counts[k])[:2]]
    for code in sorted(feature_counts, key=lambda k: -feature_counts[k]):
        if code not in NOTABLE and feature_counts[code] >= 3:
            ahead.append(f"{'many' if feature_counts[code] >= 8 else 'several'} {FEATURES[code].label[2:]}s")
            if len(ahead) >= 4:
                break

    v = ViewSpec(pid, round(p.x, 2), round(p.y, 2), p.facing, p.signature, w.ground(px, py).label, ahead, seen,
                 game.time_of_day(), game.weather_at(p.x, p.y))
    v.facts = facts_for(v)
    return v


def facts_for(v: ViewSpec) -> list[Fact]:
    """Checkable claims about the frame. Kept short and visual so a judge can verify them from pixels."""
    facts = [Fact("self", f"{v.signature} is visible in the foreground", "person"),
             Fact("ground", f"the ground is {v.ground_here}", "ground")]
    named = set()
    for s in v.seen:
        if s.kind == "feature":
            if s.label in named or s.distance > 9:
                continue
            named.add(s.label)
            facts.append(Fact(f"feature:{s.label}", f"{s.label} is visible", "feature"))
        else:
            facts.append(Fact(f"{s.kind}:{s.id}", f"{s.label} is visible", s.kind))
    facts.append(Fact("time", {"dawn": "it is dawn", "day": "it is daytime", "dusk": "it is dusk",
                               "night": "it is night"}[v.time_of_day], "atmosphere"))
    return facts
