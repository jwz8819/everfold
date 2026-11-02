"""Quests written on the spot, then checked against the real world before a player ever sees them.

The model may only point at places, people and items that exist. Anything else is thrown out and counted,
because "how often does the writer invent things" is one of the numbers the paper reports.
"""
from __future__ import annotations

import math

from ..entities import NPC, Quest, Step
from ..noise import hash64
from ..world import ITEM_LABELS, POI
from .llm import LLM
from .npcs import WORLD_LORE

MAX_STEPS = 4
GATHERABLE = ["wood", "berries", "stone", "herb", "mushroom", "relic"]
REWARDS = ["wood", "berries", "stone", "herb", "mushroom", "relic"]

QUEST_SYSTEM = WORLD_LORE + """

You write one small quest that a villager gives a player right now. You receive the villager, the real places and
people nearby with their ids, and the items that exist in this world.

Hard rules. A quest that breaks them is discarded.
- Use only ids from `places` and `people`. Never invent a place, person or item.
- 1 to 4 steps. Step types:
  goto    target = a place id. The player must walk there.
  talk    target = a person id (may be the giver). The player must speak to them.
  gather  item = an item, count = 1 to 5. The player must hold that many.
  deliver item, count, target = a person id. The player must hand them over.
  solve   target = a shrine place id. Opening a shrine needs two people standing on its plates at once,
          so this step makes the player find a partner.
- Leave unused fields as "" or 0.
- The quest should come from what the villager wants, use the land around them, and end back with a person.
- title: at most 6 words. summary: the villager's own words asking for help, at most 40 words.
Favour quests that make players meet each other or change the world in a way others will notice."""

QUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "steps": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["goto", "talk", "gather", "deliver", "solve"]},
                "target": {"type": "string"},
                "item": {"type": "string", "enum": [""] + GATHERABLE},
                "count": {"type": "integer"},
            },
            "required": ["type", "target", "item", "count"],
            "additionalProperties": False,
        }},
        "reward_item": {"type": "string", "enum": REWARDS},
        "reward_count": {"type": "integer"},
    },
    "required": ["title", "summary", "steps", "reward_item", "reward_count"],
    "additionalProperties": False,
}

DIRS8 = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]


def direction(dx: float, dy: float) -> str:
    return DIRS8[round(math.atan2(dy, dx) / (math.pi / 4)) % 8]


def context(giver: NPC, places: list[POI], people: list[NPC], player_name: str, past_titles: list[str]) -> dict:
    return {
        "giver": {"id": giver.id, "name": giver.name, "role": giver.role, "wants": giver.want},
        "player": player_name,
        "places": [{"id": p.id, "kind": p.kind, "name": p.name,
                    "distance_tiles": round(math.hypot(p.x - giver.x, p.y - giver.y)),
                    "direction": direction(p.x - giver.x, p.y - giver.y),
                    "solved": p.state.get("solved") if p.kind == "shrine" else None}
                   for p in places],
        "people": [{"id": n.id, "name": n.name or f"the {n.role}", "role": n.role} for n in [giver] + people],
        "items": GATHERABLE,
        "already_given_to_this_player": past_titles[-6:],
    }


def describe(step: Step, names: dict[str, str]) -> str:
    who = names.get(step.target, step.target)
    item = ITEM_LABELS.get(step.item, step.item)
    return {
        "goto": f"Travel to {who}",
        "talk": f"Speak with {who}",
        "gather": f"Collect {step.count} x {item}",
        "deliver": f"Bring {step.count} x {item} to {who}",
        "solve": f"Open {who} with a partner",
    }[step.type]


def validate(raw: dict, ctx: dict) -> tuple[list[Step], int]:
    """Keep only steps that point at real things. Returns (steps, number rejected)."""
    place_ids = {p["id"]: p for p in ctx["places"]}
    people_ids = {p["id"] for p in ctx["people"]}
    names = {p["id"]: p["name"] for p in ctx["places"] + ctx["people"]}
    steps, rejected = [], 0
    for s in (raw.get("steps") or [])[:MAX_STEPS + 2]:
        t, target, item = s.get("type"), str(s.get("target", "")), str(s.get("item", ""))
        try:
            count = int(s.get("count", 0))
        except (TypeError, ValueError):
            count = 0
        ok = (
            (t == "goto" and target in place_ids)
            or (t == "talk" and target in people_ids)
            or (t == "gather" and item in GATHERABLE and 1 <= count <= 5)
            or (t == "deliver" and item in GATHERABLE and 1 <= count <= 5 and target in people_ids)
            or (t == "solve" and target in place_ids and place_ids[target]["kind"] == "shrine")
        )
        if not ok or len(steps) >= MAX_STEPS:
            rejected += 1
            continue
        if t == "gather" and item == "relic":
            count = 1          # one relic per ruin chest, keep it achievable
        if t in ("goto", "talk", "solve"):
            item, count = "", 0
        if t == "gather":
            target = ""
        step = Step(t, target, item, count)
        step.text = describe(step, names)
        steps.append(step)
    return steps, rejected


def scripted(ctx: dict, salt: int) -> dict:
    """A plain quest built from the same context. Used when the model is off or fails."""
    g = ctx["giver"]["id"]
    shrines = [p for p in ctx["places"] if p["kind"] == "shrine" and not p.get("solved")]
    ruins = [p for p in ctx["places"] if p["kind"] == "ruins"]
    others = [p for p in ctx["people"] if p["id"] != g]
    far = [p for p in ctx["places"] if p["kind"] in ("tower", "stable", "village")]
    h = hash64(*map(ord, g), salt)
    options = [
        {"title": "A basket for the village", "summary": "Could you bring me a few berries? The festival is close.",
         "steps": [{"type": "gather", "item": "berries", "count": 3, "target": ""},
                   {"type": "deliver", "item": "berries", "count": 3, "target": g}]},
        {"title": "Wood before the cold", "summary": "My fence is falling apart. Some wood would save me.",
         "steps": [{"type": "gather", "item": "wood", "count": 4, "target": ""},
                   {"type": "deliver", "item": "wood", "count": 4, "target": g}]},
    ]
    if shrines:
        s = shrines[h % len(shrines)]
        options.append({"title": f"Two at {s['name']}", "summary": f"The {s['name']} shrine needs two people. "
                        "Find a partner, open it, and tell me what is inside.",
                        "steps": [{"type": "solve", "target": s["id"], "item": "", "count": 0},
                                  {"type": "talk", "target": g, "item": "", "count": 0}]})
    if ruins:
        r = ruins[h % len(ruins)]
        options.append({"title": "Something old", "summary": f"They say the ruins of {r['name']} still hold a relic. "
                        "Bring it to me?",
                        "steps": [{"type": "goto", "target": r["id"], "item": "", "count": 0},
                                  {"type": "gather", "item": "relic", "count": 1, "target": ""},
                                  {"type": "deliver", "item": "relic", "count": 1, "target": g}]})
    if others:
        o = others[h % len(others)]
        options.append({"title": "A word for a neighbour", "summary": f"Tell {o['name']} I am sorry. Then come back.",
                        "steps": [{"type": "talk", "target": o["id"], "item": "", "count": 0},
                                  {"type": "talk", "target": g, "item": "", "count": 0}]})
    if far:
        f = far[h % len(far)]
        options.append({"title": f"Eyes on {f['name']}", "summary": f"Go and look at {f['name']} for me. "
                        "I need to know it is still standing.",
                        "steps": [{"type": "goto", "target": f["id"], "item": "", "count": 0},
                                  {"type": "talk", "target": g, "item": "", "count": 0}]})
    pick = options[h % len(options)]
    return {**pick, "reward_item": REWARDS[(h >> 8) % len(REWARDS)], "reward_count": 1 + (h >> 16) % 2}


async def write(quest_id: str, giver: NPC, owner: str, ctx: dict, llm: LLM, salt: int) -> Quest:
    raw = await llm.json(QUEST_SYSTEM, ctx, QUEST_SCHEMA, max_tokens=4000)
    by = "claude"
    steps, rejected = validate(raw, ctx) if raw else ([], 0)
    if not steps:
        raw, by = scripted(ctx, salt), "scripted"
        steps, _ = validate(raw, ctx)
    reward_item = raw.get("reward_item") if raw.get("reward_item") in REWARDS else "berries"
    try:
        reward_count = min(max(int(raw.get("reward_count", 1)), 1), 3)
    except (TypeError, ValueError):
        reward_count = 1
    return Quest(id=quest_id, giver=giver.id, owner=owner, title=str(raw.get("title", "A favour"))[:60],
                 summary=str(raw.get("summary", ""))[:300], steps=steps, reward={reward_item: reward_count},
                 generated_by=by, rejected_steps=rejected)
