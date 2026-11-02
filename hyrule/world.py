"""The map: an endless grid of chunks generated on demand from a seed, plus the changes players make to it.

Generation is pure: chunk (cx, cy) under seed s is always the same. Player changes live in
`World.overrides` and are persisted separately, so the world remembers without storing terrain.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import CHUNK
from .noise import fbm, hash64, rand01


@dataclass(frozen=True)
class Ground:
    code: str
    label: str          # drawable phrase for frame prompts
    color: tuple[int, int, int]
    walkable: bool
    speed: float


GROUND: dict[str, Ground] = {g.code: g for g in [
    Ground("D", "deep blue water", (38, 84, 140), False, 0.0),
    Ground("W", "a clear lake", (64, 128, 186), False, 0.0),
    Ground("R", "a shallow river", (92, 160, 205), True, 0.5),
    Ground("S", "a sandy shore", (226, 210, 150), True, 0.8),
    Ground("G", "a rolling green meadow", (122, 186, 96), True, 1.0),
    Ground("F", "a mossy forest floor", (72, 132, 74), True, 0.9),
    Ground("H", "grassy hills", (150, 170, 98), True, 0.7),
    Ground("M", "a rocky mountainside", (138, 128, 118), True, 0.5),
    Ground("N", "a snowy peak", (236, 240, 246), True, 0.45),
    Ground("P", "a packed-dirt village square", (196, 170, 120), True, 1.0),
    Ground("T", "an ancient stone platform", (170, 168, 160), True, 1.0),
]}


@dataclass(frozen=True)
class Feature:
    code: str
    label: str
    color: tuple[int, int, int]
    blocks: bool
    yields: str | None = None       # item gained by interacting
    becomes: str = ""               # feature left behind after interacting


FEATURES: dict[str, Feature] = {f.code: f for f in [
    Feature("t", "a broad oak tree", (40, 100, 48), True, "wood", "x"),
    Feature("p", "a tall pine tree", (30, 80, 52), True, "wood", "x"),
    Feature("b", "a berry bush", (60, 140, 70), True, "berries", "e"),
    Feature("e", "a picked-over bush", (90, 130, 80), True),
    Feature("r", "a mossy boulder", (120, 120, 116), True, "stone", "q"),
    Feature("q", "a pile of rubble", (150, 146, 140), False),
    Feature("f", "a patch of wildflowers", (230, 170, 200), False, "herb", ""),
    Feature("m", "a cluster of mushrooms", (210, 90, 70), False, "mushroom", ""),
    Feature("x", "a fresh tree stump", (120, 90, 60), False),
    Feature("C", "a crackling campfire", (250, 140, 40), True),
    Feature("h", "a timber house with a thatched roof", (150, 96, 60), True),
    Feature("w", "a stone well", (110, 110, 130), True),
    Feature("s", "a large wooden stable", (160, 110, 70), True),
    Feature("u", "a crumbling stone pillar", (160, 156, 140), True),
    Feature("c", "an old treasure chest", (200, 160, 40), True, "relic", "k"),
    Feature("k", "an empty open chest", (150, 120, 60), True),
    Feature("o", "a glowing pressure plate", (90, 200, 220), False),
    Feature("g", "a sealed stone gate", (100, 96, 120), True),
    Feature("G", "an open stone gate", (140, 200, 210), False),
    Feature("O", "a floating spirit orb", (170, 240, 255), True, "spirit_orb", ""),
    Feature("T", "a tall stone watchtower with a blue flame at its top", (90, 100, 150), True),
]}

ITEM_LABELS = {
    "wood": "a bundle of wood", "berries": "a handful of berries", "stone": "a chunk of stone",
    "herb": "a sprig of wild herb", "mushroom": "a forest mushroom", "relic": "an ancient relic",
    "spirit_orb": "a spirit orb",
}


@dataclass
class POI:
    id: str
    kind: str                   # village | shrine | ruins | stable | tower
    name: str
    x: int
    y: int
    chunk: tuple[int, int]
    slots: list[tuple[int, int]] = field(default_factory=list)   # NPC homes, shrine plates
    state: dict = field(default_factory=dict)

    def label(self) -> str:
        return {
            "village": f"the village of {self.name}, a cluster of thatched timber houses around a stone well",
            "shrine": f"the {self.name} shrine, a stone platform with two glowing plates and "
                      + ("an open gate" if self.state.get("solved") else "a sealed gate"),
            "ruins": f"the ruins of {self.name}, broken stone pillars half swallowed by grass",
            "stable": f"{self.name} stable, a big wooden barn with a painted horse-head sign",
            "tower": f"{self.name} tower, a tall stone watchtower crowned with a blue flame",
        }[self.kind]


@dataclass
class Chunk:
    cx: int
    cy: int
    ground: list[str]            # CHUNK*CHUNK codes, row-major
    feature: list[str]
    pois: list[POI]

    def idx(self, lx: int, ly: int) -> int:
        return ly * CHUNK + lx


SYLLABLES = ["ka", "ri", "lo", "ve", "an", "tor", "mi", "sa", "dun", "el", "or", "wyn", "bra", "ith", "ku",
             "ra", "zel", "mo", "ha", "nae", "fel", "gro", "lu", "tam", "vi", "sor"]
POI_ODDS = [("village", 0.10), ("shrine", 0.13), ("ruins", 0.11), ("stable", 0.05)]


def place_name(seed: int, *parts: int) -> str:
    n = 2 + hash64(seed, *parts, 7) % 2
    s = "".join(SYLLABLES[hash64(seed, *parts, i) % len(SYLLABLES)] for i in range(n))
    return s.capitalize()


def chunk_of(x: float, y: float) -> tuple[int, int]:
    return math.floor(x) // CHUNK, math.floor(y) // CHUNK


class World:
    def __init__(self, seed: int):
        self.seed = seed
        self.chunks: dict[tuple[int, int], Chunk] = {}
        self.overrides: dict[tuple[int, int], str] = {}     # (x, y) -> feature code after player changes
        self.pois: dict[str, POI] = {}

    # ------------------------------------------------------------------ sampling
    def _fields(self, x: int, y: int) -> tuple[float, float, float]:
        s = self.seed
        elev = fbm(s, x, y, 96, 5)
        # a broad continental bias keeps the spawn area mostly land
        elev = 0.55 * elev + 0.45 * fbm(s + 11, x, y, 400, 2) + 0.06
        # the land around the spawn village is always walkable lowland, whatever the seed
        k = max(0.0, 1.0 - math.hypot(x - 16, y - 16) / 110.0) * 0.75
        elev = elev * (1 - k) + 0.5 * k
        moist = fbm(s + 29, x, y, 70, 4)
        river = fbm(s + 53, x, y, 90, 2)
        return elev, moist, river

    def _base(self, x: int, y: int) -> tuple[str, str]:
        elev, moist, river = self._fields(x, y)
        r = rand01(self.seed, x, y, 991)
        if elev < 0.30:
            return "D", ""
        if elev < 0.35:
            return "W", ""
        if abs(river - 0.5) < 0.007 and 0.38 < elev < 0.70:
            return "R", ""
        if elev < 0.38:
            return "S", ""
        if elev > 0.80:
            return "N", ""
        if elev > 0.70:
            return "M", "r" if r < 0.10 else ""
        if elev > 0.62:
            return "H", "r" if r < 0.04 else ("p" if r < 0.10 else "")
        if moist > 0.56:
            if r < 0.22:
                return "F", "p" if moist > 0.64 else "t"
            if r < 0.27:
                return "F", "m"
            if r < 0.31:
                return "F", "b"
            return "F", ""
        if r < 0.03:
            return "G", "t"
        if r < 0.07:
            return "G", "f"
        if r < 0.09:
            return "G", "b"
        if r < 0.10:
            return "G", "r"
        return "G", ""

    # ------------------------------------------------------------------ chunks
    def chunk(self, cx: int, cy: int) -> Chunk:
        key = (cx, cy)
        if key not in self.chunks:
            self.chunks[key] = self._generate(cx, cy)
            for p in self.chunks[key].pois:
                self.pois[p.id] = p
        return self.chunks[key]

    def _generate(self, cx: int, cy: int) -> Chunk:
        ground, feature = [], []
        for ly in range(CHUNK):
            for lx in range(CHUNK):
                g, f = self._base(cx * CHUNK + lx, cy * CHUNK + ly)
                ground.append(g)
                feature.append(f)
        ch = Chunk(cx, cy, ground, feature, [])
        kind = self._poi_kind(cx, cy)
        if kind:
            self._place(ch, kind, 16, 16, force=(cx, cy) in ((0, 0), (1, 0)))
        if self._has_tower(cx, cy):
            self._place(ch, "tower", 6 + hash64(self.seed, cx, cy, 5) % 4, 6 + hash64(self.seed, cx, cy, 6) % 4)
        return ch

    def _poi_kind(self, cx: int, cy: int) -> str | None:
        if (cx, cy) == (0, 0):
            return "village"
        if (cx, cy) == (1, 0):
            return "shrine"
        roll = rand01(self.seed, cx, cy, 401)
        acc = 0.0
        for kind, odds in POI_ODDS:
            acc += odds
            if roll < acc:
                return kind
        return None

    def _has_tower(self, cx: int, cy: int) -> bool:
        rx, ry = math.floor(cx / 3), math.floor(cy / 3)
        pick = hash64(self.seed, rx, ry, 77) % 9
        return (cx - rx * 3) * 3 + (cy - ry * 3) == pick

    def _land_spot(self, ch: Chunk, ax: int, ay: int, radius: int) -> tuple[int, int] | None:
        """Nearest local spot whose surrounding square is dry land."""
        for d in range(0, 9):
            for lx in range(ax - d, ax + d + 1):
                for ly in range(ay - d, ay + d + 1):
                    if max(abs(lx - ax), abs(ly - ay)) != d:
                        continue
                    if not (radius <= lx < CHUNK - radius and radius <= ly < CHUNK - radius):
                        continue
                    ok = all(ch.ground[ch.idx(x, y)] in "GFHSP"
                             for x in range(lx - radius, lx + radius + 1)
                             for y in range(ly - radius, ly + radius + 1))
                    if ok:
                        return lx, ly
        return None

    def _set(self, ch: Chunk, lx: int, ly: int, g: str | None = None, f: str | None = None) -> None:
        if 0 <= lx < CHUNK and 0 <= ly < CHUNK:
            i = ch.idx(lx, ly)
            if g is not None:
                ch.ground[i] = g
            if f is not None:
                ch.feature[i] = f

    def _place(self, ch: Chunk, kind: str, ax: int, ay: int, force: bool = False) -> None:
        radius = {"village": 6, "shrine": 4, "ruins": 3, "stable": 3, "tower": 2}[kind]
        spot = self._land_spot(ch, ax, ay, radius)
        if spot is None:
            if not force:
                return
            spot = (ax, ay)
            for x in range(ax - radius - 1, ax + radius + 2):
                for y in range(ay - radius - 1, ay + radius + 2):
                    self._set(ch, x, y, "G", "")
        lx, ly = spot
        cx, cy = ch.cx, ch.cy
        wx, wy = cx * CHUNK + lx, cy * CHUNK + ly
        poi = POI(f"{kind}:{cx}:{cy}", kind, place_name(self.seed, cx, cy, len(kind)), wx, wy, (cx, cy))
        if kind == "village":
            for x in range(lx - 5, lx + 6):
                for y in range(ly - 5, ly + 6):
                    if (x - lx) ** 2 + (y - ly) ** 2 <= 30:
                        self._set(ch, x, y, "P", "")
            self._set(ch, lx, ly, f="w")
            houses = [(-4, -3), (3, -4), (-3, 3), (4, 2)]
            for i, (dx, dy) in enumerate(houses):
                self._set(ch, lx + dx, ly + dy, f="h")
                self._set(ch, lx + dx + 1, ly + dy, f="h")
                if i < 3:
                    poi.slots.append((wx + dx, wy + dy + 1))
        elif kind == "shrine":
            for x in range(lx - 3, lx + 4):
                for y in range(ly - 3, ly + 4):
                    self._set(ch, x, y, "T", "")
            self._set(ch, lx - 2, ly + 2, f="o")
            self._set(ch, lx + 2, ly + 2, f="o")
            self._set(ch, lx, ly - 2, f="g")
            poi.slots = [(wx - 2, wy + 2), (wx + 2, wy + 2)]
            poi.state = {"solved": False}
        elif kind == "ruins":
            for i, (dx, dy) in enumerate([(-2, -2), (2, -2), (-2, 2), (2, 2), (0, -3)]):
                if rand01(self.seed, cx, cy, i, 3) < 0.8:
                    self._set(ch, lx + dx, ly + dy, "T", "u")
            self._set(ch, lx, ly, "T", "c")
        elif kind == "stable":
            for x in range(lx - 3, lx + 4):
                for y in range(ly - 3, ly + 4):
                    self._set(ch, x, y, "P", "")
            self._set(ch, lx, ly - 1, f="s")
            self._set(ch, lx + 1, ly - 1, f="s")
            poi.slots.append((wx, wy + 1))
        elif kind == "tower":
            for x in range(lx - 1, lx + 2):
                for y in range(ly - 1, ly + 2):
                    self._set(ch, x, y, "T", "")
            self._set(ch, lx, ly, f="T")
        ch.pois.append(poi)

    # ------------------------------------------------------------------ queries
    def ground(self, x: int, y: int) -> Ground:
        ch = self.chunk(*chunk_of(x, y))
        return GROUND[ch.ground[ch.idx(x - ch.cx * CHUNK, y - ch.cy * CHUNK)]]

    def feature_code(self, x: int, y: int) -> str:
        if (x, y) in self.overrides:
            return self.overrides[(x, y)]
        ch = self.chunk(*chunk_of(x, y))
        return ch.feature[ch.idx(x - ch.cx * CHUNK, y - ch.cy * CHUNK)]

    def feature(self, x: int, y: int) -> Feature | None:
        code = self.feature_code(x, y)
        return FEATURES.get(code) if code else None

    def set_feature(self, x: int, y: int, code: str) -> None:
        self.overrides[(x, y)] = code

    def walkable(self, x: int, y: int) -> bool:
        g = self.ground(x, y)
        f = self.feature(x, y)
        return g.walkable and not (f and f.blocks)

    def pois_near(self, x: float, y: float, radius: float, kinds: tuple[str, ...] | None = None) -> list[POI]:
        c0x, c0y = chunk_of(x - radius, y - radius)
        c1x, c1y = chunk_of(x + radius, y + radius)
        out = []
        for cx in range(c0x, c1x + 1):
            for cy in range(c0y, c1y + 1):
                for p in self.chunk(cx, cy).pois:
                    if (kinds is None or p.kind in kinds) and math.hypot(p.x - x, p.y - y) <= radius:
                        out.append(p)
        return sorted(out, key=lambda p: math.hypot(p.x - x, p.y - y))

    def chunk_payload(self, cx: int, cy: int) -> dict:
        """What a client needs to draw a chunk, with player changes applied."""
        ch = self.chunk(cx, cy)
        feats = list(ch.feature)
        for (x, y), code in self.overrides.items():
            if chunk_of(x, y) == (cx, cy):
                feats[ch.idx(x - cx * CHUNK, y - cy * CHUNK)] = code
        return {"cx": cx, "cy": cy, "ground": "".join(ch.ground), "feature": "".join(f or "." for f in feats),
                "pois": [{"id": p.id, "kind": p.kind, "name": p.name, "x": p.x, "y": p.y, "state": p.state}
                         for p in ch.pois]}
