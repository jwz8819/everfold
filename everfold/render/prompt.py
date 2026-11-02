"""Compile a ViewSpec into a frame prompt for text-conditioned world models.

Fixed order: who (signature first, the identity lock), where, what is ahead, who else, what changed,
light and weather, camera, then the season-long style anchor (the look lock).
"""
from __future__ import annotations

from .. import config as C
from .view import ViewSpec

COMPASS = {"N": "north", "E": "east", "S": "south", "W": "west"}
# Things players changed come first, so a state change is never crowded out of the prompt.
FEATURE_PRIORITY = {"an open stone gate": 0, "a floating spirit orb": 0, "a crackling campfire": 0,
                    "a fresh tree stump": 1, "an empty open chest": 1, "a sealed stone gate": 2,
                    "an old treasure chest": 2}
LIGHT = {"dawn": "pale dawn light", "day": "bright daylight", "dusk": "golden dusk light", "night": "moonlit night"}


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _place(side: str, band: str) -> str:
    where = {"left": "to the left", "right": "to the right", "ahead": "straight ahead"}[side]
    return f"{where}, {band}"


def compile_prompt(v: ViewSpec, max_people: int = 3, max_features: int = 3) -> str:
    parts = [f"{_cap(v.signature)}, seen from behind, stands on {v.ground_here}."]
    if v.ahead:
        parts.append(f"Ahead the land is {', '.join(v.ahead[:3])}.")
    for s in [s for s in v.seen if s.kind == "landmark"][:2]:
        parts.append(f"{_cap(s.label)} rises {_place(s.side, s.band)}.")
    people = [s for s in v.seen if s.kind == "person"][:max_people]
    for s in people:
        parts.append(f"{_cap(s.label)} stands {_place(s.side, s.band)}.")
    feats = sorted((s for s in v.seen if s.kind == "feature" and s.distance <= 9),
                   key=lambda s: (FEATURE_PRIORITY.get(s.label, 3), s.distance))[:max_features]
    for s in feats:
        parts.append(f"{_cap(s.label)} is {_place(s.side, s.band)}.")
    parts.append(f"{_cap(LIGHT[v.time_of_day])}, {v.weather}.")
    parts.append(f"Camera: third-person over-the-shoulder, facing {COMPASS[v.facing]}.")
    parts.append(f"Style: {C.STYLE_ANCHOR}.")
    return " ".join(parts)
