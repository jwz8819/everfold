"""Quest grounding: how often the quest writer points at things that do not exist.

For each world seed, the villagers around spawn get their scripted personalities (no model, so every quest writer
sees the same fixed context), then the writer is asked for a quest from a few of them, exactly as the game asks
when a villager offers one. Two measures:

  step grounding   steps whose target or item is not a real place, person or item (rejected by quests.validate,
                   which the game applies before a player sees the quest), over all steps proposed
  text grounding   capitalised names in the title and summary that are not a real place, person, the player or a
                   world word. A heuristic: it misses lowercase inventions ("the old mill") and can flag a proper
                   word the list lacks, so every flagged quest is written out for a person to check.

Also recorded: how often the writer failed outright and the scripted fallback was used.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from ..content import quests as questmod
from ..content.llm import LLM
from ..game import Game

WORLD_WORDS = {"Everfold", "I", "I'm", "I'll", "I've", "I'd", "Thank", "Thanks", "Please", "Bring", "Find", "Go", "Tell",
               "Help", "Come", "Could", "Would", "Will", "Can", "If", "When", "My", "The", "A", "An", "And", "But", "So",
               "Then", "Take", "Speak", "Ask", "Travel", "Meet", "Gather", "Collect", "Deliver", "Open", "Two", "One"}
PLAYER = "Ash"


def names_in(text: str) -> list[str]:
    """Capitalised words that are not the first word of a sentence."""
    out = []
    for sentence in re.split(r"(?<=[.!?:])\s+|\n", text):
        words = re.findall(r"[A-Za-z][\w'-]*", sentence)
        out += [w for w in words[1:] if w[0].isupper()]
    return out


_DICTIONARY: set[str] | None = None


def english(word: str) -> bool:
    """In the system word list (macOS /usr/share/dict/words). Titles are in title case, so a capitalised English
    word ("River", "Beyond") is not a name; an invented name that happens to be a dictionary word is missed."""
    global _DICTIONARY
    if _DICTIONARY is None:
        f = Path("/usr/share/dict/words")
        _DICTIONARY = {w.strip().lower() for w in f.read_text().splitlines()} if f.exists() else set()
    w = word.lower()
    # the word list has few plurals: "Herbs", "Berries", "Hills" are English too
    return any(x in _DICTIONARY for x in (w, w.removesuffix("s"), w.removesuffix("es"), w[:-3] + "y" if w.endswith("ies") else w))


def unknown_names(quest: dict, ctx: dict) -> list[str]:
    known = set(WORLD_WORDS) | {PLAYER}
    for p in ctx["places"] + ctx["people"]:
        known |= set(re.findall(r"[A-Za-z][\w'-]*", p["name"]))
    title = re.findall(r"[A-Za-z][\w'-]*", quest.get("title", ""))
    words = [w for w in title if w[0].isupper()] + names_in(quest.get("summary", ""))
    words = [w.removesuffix("'s") for w in words]
    return sorted({w for w in words if w not in known and not english(w)})


async def run_world(seed: int, writer: LLM, givers: int, personas: str = "scripted") -> list[dict]:
    """personas: "scripted" gives every villager its role's fixed personality (the same context for any writer, but
    every baker wants the same thing); "claude" has the writer give the quest-givers their personalities first, as
    the game does in play. Other villagers are scripted either way: the quest context shows only their names."""
    game = Game(seed, LLM(None))
    game.ensure_around(0, 0, 3)
    for npc in list(game.npcs.values()):
        await game.awaken(npc)
    pid = "p_quest"
    game.join(pid, PLAYER)
    home = sorted((n for n in game.npcs.values() if n.poi_id == "village:0:0"), key=lambda n: n.id)
    by_role: dict[str, object] = {}
    for n in home:                                   # one giver per role, so one village gives varied quests
        by_role.setdefault(n.role, n)
    chosen = list(by_role.values())[:givers]
    if personas == "claude":
        game.llm = writer
        for npc in chosen:
            npc.name = ""
            await game.awaken(npc)
        game.llm = LLM(None)
    out = []
    for i, npc in enumerate(chosen):
        # the same context Game.offer_quest builds, written by the writer under test
        people = [n for n in game.npcs.values() if n.id != npc.id and math.hypot(n.x - npc.x, n.y - npc.y) <= 140]
        ctx = questmod.context(npc, game.world.pois_near(npc.x, npc.y, 140), people, PLAYER, [])
        failures = writer.failures
        quest = await questmod.write(f"q:{seed}:{i}", npc, pid, ctx, writer, salt=i)
        q = quest.to_dict()
        out.append({"seed": seed, "giver": npc.id, "role": npc.role, "persona_by": npc.generated_by,
                    "want": npc.want, "generated_by": quest.generated_by,
                    "writer_failed": writer.failures > failures, "kept_steps": len(quest.steps),
                    "rejected_steps": quest.rejected_steps,
                    "unknown_names": unknown_names(q, ctx) if quest.generated_by == "claude" else [],
                    "title": q["title"], "summary": q["summary"], "steps": [s["text"] for s in q["steps"]]})
    return out


async def batch(seeds: list[int], writer: LLM, out: Path, givers: int = 2, personas: str = "scripted") -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in seeds:
        rows += await run_world(seed, writer, givers, personas)
    with (out / "quests.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarize(rows)
    summary["personas"] = personas
    summary["writer"] = {"model": writer.model, "effort": writer.effort, "calls": writer.calls, "usage": writer.usage}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "report.md").write_text(report(summary, rows), encoding="utf-8")
    return summary


def summarize(rows: list[dict]) -> dict:
    claude = [r for r in rows if r["generated_by"] == "claude"]
    titles = [r["title"] for r in rows]
    proposed = sum(r["kept_steps"] + r["rejected_steps"] for r in claude)
    rejected = sum(r["rejected_steps"] for r in claude)
    return {"quests": len(rows), "written_by_model": len(claude), "fallback": len(rows) - len(claude),
            "steps_proposed": proposed, "steps_rejected": rejected,
            "step_rejection_rate": round(rejected / proposed, 3) if proposed else None,
            "quests_with_a_rejected_step": sum(r["rejected_steps"] > 0 for r in claude),
            "quests_with_unknown_names": sum(bool(r["unknown_names"]) for r in claude),
            "distinct_titles": len(set(titles)),
            "most_repeated_title": max(set(titles), key=titles.count) if titles else None,
            "most_repeated_count": max(map(titles.count, set(titles))) if titles else 0}


def report(s: dict, rows: list[dict]) -> str:
    lines = ["# Quest grounding", "",
             f"{s['quests']} quests asked for; {s['written_by_model']} written by the model, {s['fallback']} fell back "
             "to the scripted writer.", "",
             f"- Steps: {s['steps_rejected']} of {s['steps_proposed']} proposed steps pointed at something that does "
             f"not exist (rate {s['step_rejection_rate']}); {s['quests_with_a_rejected_step']} quests had at least one.",
             f"- Text: {s['quests_with_unknown_names']} quests name something in the title or summary that is not in "
             "the world (heuristic; check the list below).",
             f"- Variety: {s['distinct_titles']} distinct titles; the most repeated, \"{s['most_repeated_title']}\", "
             f"appears {s['most_repeated_count']} times.", "", "## Quests with unknown names", ""]
    for r in rows:
        if r["unknown_names"]:
            lines.append(f"- seed {r['seed']}, {r['role']}: **{', '.join(r['unknown_names'])}**. "
                         f"\"{r['title']}\": {r['summary']}")
    return "\n".join(lines) + "\n"
