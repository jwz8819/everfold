"""Villagers. Their bodies are placed by the map; their minds are written the first time a player comes near."""
from __future__ import annotations

from ..entities import NPC, ROLES, npc_signature
from ..noise import hash64
from ..world import POI, SYLLABLES
from .llm import LLM

WORLD_LORE = """The world is the Everfold: an endless, sunlit wilderness of meadows, forests, rivers and snowy peaks.
Small villages and stables dot the land. Ancient stone shrines, each with two pressure plates, only open when two
people stand on the plates at once, so strangers must cooperate. Blue-flamed watchtowers mark every region.
Ruins of an older people hold relics. Travellers (real players) arrive from everywhere and nobody knows why.
There is no combat yet. Life here is about exploring, gathering, trading favours and helping one another."""

VILLAGE_ROLES = ["elder", "fisher", "smith", "herbalist", "merchant", "guard", "cartographer", "baker", "child"]

PERSONA_SYSTEM = WORLD_LORE + """

You write one villager for this world. You are given their role, their village, the land around it, and who else
lives there. Return a person a player would remember after one conversation.

- name: one or two words, invented, pronounceable, not from any existing game or book.
- persona: two sentences. Who they are and the one thing about them that surprises people.
- voice: how they talk, in one sentence, concrete enough to imitate.
- want: something they want this week that a stranger could help with, grounded in the land described.
- secret: one thing they will only tell someone who has helped them.
Keep it gentle and all-ages. No real people, brands, or other games' characters."""

PERSONA_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("name", "persona", "voice", "want", "secret")},
    "required": ["name", "persona", "voice", "want", "secret"],
    "additionalProperties": False,
}

FALLBACK = {
    "elder": ("Has watched the tower flame for sixty years and swears it once burned green.",
              "Slow and warm, ends every thought with a question.", "news of what lies past the river"),
    "fisher": ("Knows every bend of the river and names the fish she lets go.",
               "Short sentences, weather first, feelings last.", "fresh herbs to keep the catch from spoiling"),
    "smith": ("Can fix anything except his own roof.", "Loud, blunt, laughs at his own jokes.",
              "good stone from the hills"),
    "herbalist": ("Talks to her plants and believes they answer.", "Soft and quick, full of plant names.",
                  "wild herbs and mushrooms from the forest"),
    "merchant": ("Has traded with every village and trusts none of them.", "Friendly, always counting.",
                 "a relic from the old ruins to sell"),
    "guard": ("Guards a village that has never been attacked and is a little disappointed.",
              "Formal, then suddenly gossipy.", "someone to check on the nearest shrine"),
    "cartographer": ("Maps the Everfold and keeps finding it larger than yesterday.",
                     "Precise, excitable about distances.", "a report from the nearest watchtower"),
    "baker": ("Bakes for travellers she will never see again.", "Bright and motherly.", "berries for a festival pie"),
    "child": ("Wants to be a traveller and follows real ones around.", "Breathless, asks three questions at once.",
              "someone to open a shrine with"),
    "stablehand": ("Can tell a traveller's mood from how they walk.", "Drawling and patient.",
                   "a bundle of wood to mend the fence"),
}


def npc_name(seed: int, npc_id: str) -> str:
    h = hash64(seed, *map(ord, npc_id), 3)
    parts = [SYLLABLES[(h >> (i * 8)) % len(SYLLABLES)] for i in range(2)]
    return "".join(parts).capitalize()


def populate(seed: int, poi: POI) -> list[NPC]:
    """Deterministic villagers for a POI. Same seed, same people."""
    out = []
    for i, (hx, hy) in enumerate(poi.slots if poi.kind in ("village", "stable") else []):
        if poi.kind == "stable":
            role = "stablehand"
        else:
            role = VILLAGE_ROLES[hash64(seed, *map(ord, poi.id), i) % len(VILLAGE_ROLES)]
            if i == 0:
                role = "elder"
        nid = f"npc:{poi.id}:{i}"
        out.append(NPC(id=nid, role=role, home=(hx, hy), poi_id=poi.id, signature=npc_signature(seed, nid, role),
                       x=hx + 0.5, y=hy + 0.5))
    return out


def scripted_mind(seed: int, npc: NPC, poi: POI) -> dict:
    persona, voice, want = FALLBACK[npc.role]
    return {"name": npc_name(seed, npc.id), "persona": persona, "voice": voice, "want": want,
            "secret": f"they once saw the gate of a shrine near {poi.name} open on its own"}


async def awaken(npc: NPC, poi: POI, neighbours: list[NPC], land: str, seed: int, llm: LLM) -> NPC:
    """Fill in name and personality. Idempotent: a villager is only written once."""
    if npc.ready:
        return npc
    payload = {"role": npc.role, "looks": npc.signature, "village": poi.name, "village_kind": poi.kind,
               "land_around": land, "neighbours": [{"role": n.role, "name": n.name or "unnamed"} for n in neighbours]}
    out = await llm.json(PERSONA_SYSTEM, payload, PERSONA_SCHEMA, max_tokens=3000)
    if out and all(isinstance(out.get(k), str) and out[k].strip() for k in PERSONA_SCHEMA["required"]):
        mind, npc.generated_by = out, "claude"
    else:
        mind, npc.generated_by = scripted_mind(seed, npc, poi), "scripted"
    npc.name = mind["name"].strip()[:24]
    npc.persona, npc.voice = mind["persona"][:400], mind["voice"][:200]
    npc.want, npc.secret = mind["want"][:200], mind["secret"][:200]
    return npc


assert set(FALLBACK) == set(ROLES)
