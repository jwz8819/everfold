"""Ground-truth picture of a view: a top-down map crop drawn straight from the game state.

It is not a world model. It is the control: what the state actually is, shown next to each model's frame.
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw

from ..game import FACING, Game
from ..world import FEATURES
from .view import CONE_DEGREES, ViewSpec

TILE = 14
SPAN = 13      # tiles each side of the player


def render_reference(game: Game, v: ViewSpec) -> bytes:
    size = (2 * SPAN + 1) * TILE
    img = Image.new("RGB", (size, size), (20, 24, 30))
    d = ImageDraw.Draw(img)
    cx, cy = math.floor(v.x), math.floor(v.y)
    for dy in range(-SPAN, SPAN + 1):
        for dx in range(-SPAN, SPAN + 1):
            x, y = cx + dx, cy + dy
            px, py = (dx + SPAN) * TILE, (dy + SPAN) * TILE
            d.rectangle([px, py, px + TILE - 1, py + TILE - 1], fill=game.world.ground(x, y).color)
            code = game.world.feature_code(x, y)
            if code:
                f = FEATURES[code]
                pad = 2 if f.blocks else 4
                d.ellipse([px + pad, py + pad, px + TILE - 1 - pad, py + TILE - 1 - pad], fill=f.color)
    # camera cone
    fx, fy = FACING[v.facing]
    base = math.atan2(fy, fx)
    o = (SPAN * TILE + TILE / 2, SPAN * TILE + TILE / 2)
    r = 12 * TILE
    for a in (base - math.radians(CONE_DEGREES), base + math.radians(CONE_DEGREES)):
        d.line([o, (o[0] + r * math.cos(a), o[1] + r * math.sin(a))], fill=(255, 255, 255), width=1)
    # people
    for s in v.seen:
        if s.kind != "person":
            continue
        who = game.players.get(s.id) or game.npcs.get(s.id)
        if who is None:
            continue
        px, py = (who.x - cx + SPAN) * TILE, (who.y - cy + SPAN) * TILE
        color = (240, 80, 80) if s.id in game.players else (250, 230, 120)
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=color, outline=(0, 0, 0))
    me = game.players[v.player]
    px, py = (me.x - cx + SPAN) * TILE, (me.y - cy + SPAN) * TILE
    d.ellipse([px - 6, py - 6, px + 6, py + 6], fill=(255, 255, 255), outline=(0, 0, 0), width=2)
    d.line([(px, py), (px + fx * 12, py + fy * 12)], fill=(0, 0, 0), width=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
