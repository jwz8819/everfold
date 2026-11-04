"""People and quests. Positions are in tiles (floats for people)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .noise import hash64

COLORS = ["crimson", "teal", "amber", "violet", "forest-green", "sky-blue", "rust-orange", "ivory", "plum", "navy"]
GARMENTS = ["hooded cloak", "padded tunic", "patchwork poncho", "long travel coat", "quilted vest"]
PROPS = ["a lantern on a pole", "a rolled map", "a wooden shield", "a fishing rod", "a satchel of herbs",
         "a feathered hat", "a carved walking staff", "a small hand drum"]

ROLES = {
    "elder": ("a stooped", "with a long braided white beard"),
    "fisher": ("a weathered", "with a net slung over one shoulder"),
    "smith": ("a broad-shouldered", "with soot on the forearms and a hammer at the belt"),
    "herbalist": ("a wiry", "with dried flowers tucked into the hair"),
    "merchant": ("a round-faced", "with a huge overstuffed backpack"),
    "guard": ("a tall", "with a spear and a dented helmet"),
    "cartographer": ("a bespectacled", "with ink-stained fingers and a roll of maps"),
    "baker": ("a cheerful", "with a flour-dusted apron"),
    "child": ("a small", "with a wooden toy sword"),
    "stablehand": ("a sunburned", "with a coil of rope and a straw hat"),
}


def _a(word: str) -> str:
    return ("an " if word[0] in "aeiou" else "a ") + word


def npc_signature(seed: int, npc_id: str, role: str) -> str:
    h = hash64(seed, *map(ord, npc_id))
    adj, extra = ROLES[role]
    color = COLORS[h % len(COLORS)]
    garment = GARMENTS[(h >> 8) % len(GARMENTS)]
    return f"{adj} {role} in {_a(color)} {garment}, {extra}"


def outfit(signature: str) -> str:
    """The colour and garment of a signature ("a young traveller in an ivory padded tunic, carrying ..." ->
    "an ivory padded tunic"): the one feature of a person the judge checks."""
    return signature.split(" in ", 1)[1].split(",", 1)[0]


def player_signature(seed: int, player_id: str) -> str:
    h = hash64(seed, *map(ord, player_id), 99)
    color = COLORS[h % len(COLORS)]
    garment = GARMENTS[(h >> 8) % len(GARMENTS)]
    prop = PROPS[(h >> 16) % len(PROPS)]
    return f"a young traveller in {_a(color)} {garment}, carrying {prop}"


@dataclass
class Player:
    id: str
    name: str
    x: float
    y: float
    signature: str
    facing: str = "S"                   # N E S W
    move: tuple[float, float] = (0.0, 0.0)
    inventory: dict[str, int] = field(default_factory=dict)
    quests: list[str] = field(default_factory=list)       # active quest ids
    done_quests: list[str] = field(default_factory=list)
    online: bool = True

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "x": round(self.x, 2), "y": round(self.y, 2),
                "facing": self.facing, "signature": self.signature, "online": self.online}


@dataclass
class NPC:
    id: str
    role: str
    home: tuple[int, int]
    poi_id: str
    signature: str
    x: float
    y: float
    name: str = ""
    persona: str = ""
    voice: str = ""
    want: str = ""
    secret: str = ""
    generated_by: str = ""                       # claude | scripted, recorded for the paper
    memory: dict[str, list[str]] = field(default_factory=dict)   # player id -> notes
    busy_until: float = 0.0

    @property
    def ready(self) -> bool:
        return bool(self.name)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name or f"a {self.role}", "role": self.role, "x": round(self.x, 2),
                "y": round(self.y, 2), "signature": self.signature}


STEP_TYPES = ("goto", "talk", "gather", "deliver", "solve")


@dataclass
class Step:
    type: str                 # goto | talk | gather | deliver | solve
    target: str = ""          # poi id or npc id
    item: str = ""
    count: int = 0
    text: str = ""            # how the log describes it

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Quest:
    id: str
    giver: str
    owner: str                 # player id
    title: str
    summary: str
    steps: list[Step]
    reward: dict[str, int]
    step: int = 0
    status: str = "active"     # active | done
    generated_by: str = ""     # claude | scripted
    rejected_steps: int = 0    # steps the validator threw out, for measuring hallucination

    @property
    def current(self) -> Step | None:
        return self.steps[self.step] if self.status == "active" and self.step < len(self.steps) else None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d
