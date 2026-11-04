"""Greybox: a plain 3D picture of a player's view, drawn straight from the game state.

The engine's own render of the truth, the way a game draws its blockout pass: flat ground tiles, boxes for trees,
houses and people, a stone column with a blue flame for a tower. It is what a restyling model (Decart Lucy) is
fed, and a control in its own right: every frame is computed from one shared state, so two players looking at the
same tower see the same geometry from two sides.

A Scene is captured when a probe step is taken (the world as it is then, minus the viewer, who is drawn as the
avatar wherever the camera is). `render(scene, x, y, heading)` draws it from any camera pose, so a clip can walk
between probe poses. Units are tiles; z is up; the game's y axis points south.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from ..entities import COLORS
from ..game import Game

W, H = 640, 360
SUPERSAMPLE = 2
FOV = math.radians(90)
# A high chase camera, as in top-down-leaning adventure games: the probes' notion of "in view" ignores walls,
# so the camera looks over houses rather than letting one hide what the step says is ahead.
EYE_BACK, EYE_UP, PITCH = 4.6, 4.5, math.radians(20)
SHOULDER = 1.0     # over the right shoulder, so what is straight ahead of the player is not hidden behind them
NEAR = 0.15
CLEAR = 3.0        # objects closer to the camera than this (the avatar is ~6.6 ahead) are not drawn, as third-person
                   # cameras do, so a tree behind the player never fills the screen
# Occluder fade, as games do: a tall object (house, tree) standing close in front of the player, within a narrow
# corridor along the line of sight, is not drawn, so it cannot hide what the probe step says is ahead. People and
# anything beyond FADE_AHEAD tiles are always drawn.
# The corridor runs from the camera (behind the player) to FADE_AHEAD tiles in front; it is wider behind the player,
# where the over-the-shoulder camera sits to one side. Only things taller than a person fade (houses, trees, rocks
# stay if low; a campfire or stump never fades).
FADE_AHEAD, FADE_HALF_WIDTH, FADE_MIN_HEIGHT = 5.5, 1.1, 1.6
GROUND_RADIUS, OBJECT_RADIUS, LANDMARK_RADIUS = 30, 30, 48
SKY_TOP, SKY_HORIZON = (120, 170, 225), (200, 222, 240)
LIGHT = (0.35, 0.55, 0.76)
SKIN = (226, 190, 160)
OUTFIT = {"crimson": (176, 32, 52), "teal": (20, 128, 128), "amber": (228, 160, 36), "violet": (138, 82, 196),
          "forest-green": (40, 110, 52), "sky-blue": (112, 178, 232), "rust-orange": (190, 92, 40),
          "ivory": (238, 232, 212), "plum": (120, 52, 102), "navy": (34, 44, 104)}
assert set(OUTFIT) == set(COLORS)

Face = tuple[list[tuple[float, float, float]], tuple[int, int, int], bool]     # points, colour, glows


@dataclass
class Obj:
    x: float
    y: float
    height: float
    person: bool
    faces: list[Face]


@dataclass
class Scene:
    ground: list[tuple[int, int, tuple[int, int, int], float]] = field(default_factory=list)   # x, y, colour, z
    objects: list[Obj] = field(default_factory=list)

    def add(self, x: float, y: float, faces: list[Face], person: bool = False) -> None:
        if faces:
            self.objects.append(Obj(x, y, max(p[2] for f in faces for p in f[0]), person, faces))


def outfit_color(signature: str) -> tuple[int, int, int]:
    words = signature.split(" in ", 1)[-1]
    return next((OUTFIT[c] for c in sorted(OUTFIT, key=len, reverse=True) if c in words), (150, 150, 150))


# shapes ------------------------------------------------------------------------------------------------------------

def box(cx: float, cy: float, w: float, d: float, z0: float, z1: float, color, glow: bool = False) -> list[Face]:
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2
    return [([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], color, glow),     # top
            ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], color, glow),     # north (y0)
            ([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], color, glow),     # south
            ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], color, glow),     # east
            ([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], color, glow)]     # west


def roof(cx: float, cy: float, w: float, d: float, z0: float, z1: float, color) -> list[Face]:
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2
    return [([(x0, y0, z0), (x1, y0, z0), (x1, cy, z1), (x0, cy, z1)], color, False),
            ([(x1, y1, z0), (x0, y1, z0), (x0, cy, z1), (x1, cy, z1)], color, False),
            ([(x1, y0, z0), (x1, y1, z0), (x1, cy, z1)], color, False),
            ([(x0, y1, z0), (x0, y0, z0), (x0, cy, z1)], color, False)]


def person(x: float, y: float, color) -> list[Face]:
    return box(x, y, 0.5, 0.36, 0.0, 1.1, color) + box(x, y, 0.3, 0.3, 1.1, 1.45, SKIN)


def feature_faces(code: str, x: float, y: float) -> list[Face]:
    """One tile's feature, centred on the tile."""
    cx, cy = x + 0.5, y + 0.5
    trunk = (110, 78, 48)
    shapes = {
        "t": lambda: box(cx, cy, 0.25, 0.25, 0, 1.3, trunk) + box(cx, cy, 1.5, 1.5, 1.1, 2.7, (52, 120, 56)),
        "p": lambda: box(cx, cy, 0.22, 0.22, 0, 1.0, trunk) + box(cx, cy, 1.3, 1.3, 0.9, 1.9, (32, 86, 52))
        + box(cx, cy, 0.9, 0.9, 1.9, 2.8, (32, 86, 52)) + box(cx, cy, 0.45, 0.45, 2.8, 3.5, (32, 86, 52)),
        "b": lambda: box(cx, cy, 0.8, 0.8, 0, 0.6, (60, 140, 70)) + box(cx, cy, 0.5, 0.5, 0.6, 0.7, (190, 40, 70)),
        "e": lambda: box(cx, cy, 0.8, 0.8, 0, 0.55, (96, 132, 82)),
        "r": lambda: box(cx, cy, 0.9, 0.8, 0, 0.75, (124, 122, 116)),
        "q": lambda: box(cx - 0.2, cy, 0.4, 0.4, 0, 0.25, (150, 146, 140)) + box(cx + 0.2, cy + 0.1, 0.35, 0.35, 0, 0.2,
                                                                                (140, 136, 130)),
        "f": lambda: box(cx, cy, 0.7, 0.7, 0, 0.12, (232, 168, 204)),
        "m": lambda: box(cx - 0.15, cy, 0.18, 0.18, 0, 0.25, (214, 88, 70)) + box(cx + 0.18, cy + 0.1, 0.15, 0.15, 0, 0.2,
                                                                                 (214, 88, 70)),
        "x": lambda: box(cx, cy, 0.55, 0.55, 0, 0.4, (150, 112, 70)) + box(cx, cy, 0.45, 0.45, 0.4, 0.42, (214, 184, 132)),
        "C": lambda: box(cx, cy, 0.8, 0.25, 0, 0.18, (90, 60, 36)) + box(cx, cy, 0.25, 0.8, 0, 0.18, (90, 60, 36))
        + box(cx, cy, 0.4, 0.4, 0.18, 0.75, (250, 150, 40), True) + box(cx, cy, 0.2, 0.2, 0.75, 1.0, (255, 220, 90), True),
        "h": lambda: box(cx, cy, 1.0, 1.0, 0, 1.5, (196, 168, 128)) + roof(cx, cy, 1.15, 1.15, 1.5, 2.3, (176, 132, 64))
        + box(cx, cy + 0.51, 0.3, 0.02, 0, 0.8, (96, 64, 40)),
        "w": lambda: box(cx, cy, 0.9, 0.9, 0, 0.6, (128, 128, 140)) + box(cx, cy, 0.6, 0.6, 0.6, 0.62, (30, 40, 60))
        + box(cx, cy, 0.9, 0.08, 1.3, 1.4, (110, 80, 50)),
        "s": lambda: box(cx, cy, 1.0, 1.4, 0, 1.9, (164, 110, 70)) + roof(cx, cy, 1.15, 1.55, 1.9, 2.8, (120, 70, 44)),
        "u": lambda: box(cx, cy, 0.45, 0.45, 0, 2.2, (168, 164, 150)),
        "c": lambda: box(cx, cy, 0.7, 0.5, 0, 0.45, (204, 160, 44)),
        "k": lambda: box(cx, cy, 0.7, 0.5, 0, 0.3, (150, 120, 60)),
        "o": lambda: box(cx, cy, 0.8, 0.8, 0, 0.08, (100, 220, 235), True),
        "g": lambda: box(cx, cy, 1.6, 0.35, 0, 2.3, (104, 100, 124)),
        "G": lambda: box(cx - 0.7, cy, 0.25, 0.35, 0, 2.3, (150, 200, 210)) + box(cx + 0.7, cy, 0.25, 0.35, 0, 2.3,
                                                                                 (150, 200, 210))
        + box(cx, cy, 1.65, 0.35, 2.3, 2.6, (150, 200, 210)),
        "O": lambda: box(cx, cy, 0.45, 0.45, 1.1, 1.55, (180, 245, 255), True),
        # kept short enough that its flame is in frame from the probes' 9-tile viewing distance
        "T": lambda: box(cx, cy, 1.5, 1.5, 0, 5.2, (120, 124, 136)) + box(cx, cy, 1.9, 1.9, 5.2, 5.6, (104, 108, 120))
        + box(cx, cy, 0.7, 0.7, 5.6, 6.5, (70, 150, 255), True),
    }
    make = shapes.get(code)
    return make() if make else []


# capture -------------------------------------------------------------------------------------------------------------

def capture(game: Game, x: float, y: float, exclude: str) -> Scene:
    """The world around (x, y) as it is now, without the viewer (drawn as the avatar at render time)."""
    w, sc = game.world, Scene()
    cx, cy = math.floor(x), math.floor(y)
    for dy in range(-GROUND_RADIUS, GROUND_RADIUS + 1):
        for dx in range(-GROUND_RADIUS, GROUND_RADIUS + 1):
            if dx * dx + dy * dy > GROUND_RADIUS ** 2:
                continue
            gx, gy = cx + dx, cy + dy
            g = w.ground(gx, gy)
            sc.ground.append((gx, gy, g.color, -0.12 if g.code in "DWR" else 0.0))
            code = w.feature_code(gx, gy)
            if code and code != "T" and dx * dx + dy * dy <= OBJECT_RADIUS ** 2:
                sc.add(gx + 0.5, gy + 0.5, feature_faces(code, gx, gy))
    for poi in w.pois_near(x, y, LANDMARK_RADIUS, ("tower",)):
        sc.add(poi.x + 0.5, poi.y + 0.5, feature_faces("T", poi.x, poi.y))
    people = [(p.id, p.signature, p.x, p.y) for p in game.players.values() if p.online]
    people += [(n.id, n.signature, n.x, n.y) for n in game.npcs.values()]
    for pid, sig, px, py in people:
        if pid != exclude and math.hypot(px - x, py - y) <= OBJECT_RADIUS:
            sc.add(px, py, person(px, py, outfit_color(sig)), person=True)
    return sc


# render --------------------------------------------------------------------------------------------------------------

def _camera(x: float, y: float, heading: float):
    fx, fy = math.cos(heading), math.sin(heading)
    eye = (x - fx * EYE_BACK - fy * SHOULDER, y - fy * EYE_BACK + fx * SHOULDER, EYE_UP)
    c, s = math.cos(PITCH), math.sin(PITCH)
    fwd = (fx * c, fy * c, -s)
    up = (fx * s, fy * s, c)
    right = (-fy, fx, 0.0)
    return eye, fwd, up, right


def _to_cam(p, cam):
    eye, fwd, up, right = cam
    d = (p[0] - eye[0], p[1] - eye[1], p[2] - eye[2])
    return (d[0] * right[0] + d[1] * right[1], d[0] * up[0] + d[1] * up[1] + d[2] * up[2],
            d[0] * fwd[0] + d[1] * fwd[1] + d[2] * fwd[2])


def _clip(poly):
    """Clip a camera-space polygon to z >= NEAR."""
    out = []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        if a[2] >= NEAR:
            out.append(a)
        if (a[2] >= NEAR) != (b[2] >= NEAR):
            t = (NEAR - a[2]) / (b[2] - a[2])
            out.append(tuple(a[k] + t * (b[k] - a[k]) for k in range(3)))
    return out


def _shade(color, normal, depth, glow):
    if glow:
        lit = 1.0
    else:
        lit = 0.55 + 0.45 * max(0.0, sum(n * l for n, l in zip(normal, LIGHT)))
    fog = min(max((depth - 14) / 45, 0.0), 0.65)
    return tuple(int(c * lit * (1 - fog) + h * fog) for c, h in zip(color, SKY_HORIZON))


def _normal(p):
    ax, ay, az = (p[1][k] - p[0][k] for k in range(3))
    bx, by, bz = (p[2][k] - p[0][k] for k in range(3))
    n = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
    m = math.sqrt(sum(c * c for c in n)) or 1.0
    return tuple(c / m for c in n)


def render(scene: Scene, x: float, y: float, heading: float, avatar=None) -> Image.Image:
    """The view from a third-person camera behind (x, y), looking along `heading` (radians, 0 = east, pi/2 = south).
    `avatar` is the viewer's outfit colour, drawn at (x, y)."""
    S = SUPERSAMPLE
    w, h = W * S, H * S
    f = (w / 2) / math.tan(FOV / 2)
    cam = _camera(x, y, heading)
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for row in range(h):                                     # sky gradient, then the far ground as a band
        t = min(row / (h * 0.5), 1.0)
        d.line([(0, row), (w, row)], fill=tuple(int(a + (b - a) * t) for a, b in zip(SKY_TOP, SKY_HORIZON)))
    horizon = min(max(h / 2 - math.tan(PITCH) * f, 0), h)      # the camera looks down, so the horizon rises
    if scene.ground:
        avg = tuple(sum(g[2][k] for g in scene.ground) // len(scene.ground) for k in range(3))
        d.rectangle([0, horizon, w, h], fill=_shade(avg, (0, 0, 1), 60, False))

    def project(poly3):
        cam_pts = _clip([_to_cam(p, cam) for p in poly3])
        if len(cam_pts) < 3:
            return None, 0.0
        pts = [(w / 2 + px / pz * f, h / 2 - py / pz * f) for px, py, pz in cam_pts]
        return pts, sum(p[2] for p in cam_pts) / len(cam_pts)

    eye = cam[0]
    tiles = []
    for gx, gy, color, z in scene.ground:
        poly = [(gx, gy, z), (gx + 1, gy, z), (gx + 1, gy + 1, z), (gx, gy + 1, z)]
        pts, depth = project(poly)
        if pts:
            tiles.append((depth, pts, _shade(color, (0, 0, 1), depth, False)))
    for depth, pts, color in sorted(tiles, key=lambda t: -t[0]):
        d.polygon(pts, fill=color)

    hx, hy = math.cos(heading), math.sin(heading)
    faces: list[tuple[Face, bool]] = []
    for o in scene.objects:
        ahead, side = (o.x - x) * hx + (o.y - y) * hy, -(o.x - x) * hy + (o.y - y) * hx
        width = FADE_HALF_WIDTH if ahead >= 0 else FADE_HALF_WIDTH + SHOULDER
        if not o.person and o.height >= FADE_MIN_HEIGHT and -EYE_BACK - 0.5 < ahead < FADE_AHEAD and abs(side) < width:
            continue
        faces += [(fc, True) for fc in o.faces]
    faces += [(fc, False) for fc in (person(x, y, avatar) if avatar else [])]
    drawn = []
    for (poly, color, glow), scenery in faces:
        n = _normal(poly)
        centre = [sum(p[k] for p in poly) / len(poly) for k in range(3)]
        if sum(n[k] * (eye[k] - centre[k]) for k in range(3)) <= 0:      # facing away
            continue
        if scenery and _to_cam(centre, cam)[2] < CLEAR:
            continue
        pts, depth = project(poly)
        if pts:
            dist = math.dist(eye, centre)
            drawn.append((dist, pts, _shade(color, n, depth, glow)))
    for _, pts, color in sorted(drawn, key=lambda t: -t[0]):
        d.polygon(pts, fill=color)
    return img.resize((W, H), Image.LANCZOS)


FACING_HEADING = {"E": 0.0, "S": math.pi / 2, "W": math.pi, "N": -math.pi / 2}


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
