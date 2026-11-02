"""The authoritative game. One instance per world. It owns every fact; renderers and models only describe it.

Messages to players go into `outbox` as (player_id, message) pairs; the server delivers them.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import asdict

from . import config as C
from .content import dialogue, npcs as npcmod, quests as questmod
from .content.llm import LLM
from .entities import NPC, Player, Quest, Step, player_signature
from .noise import hash64
from .store import Store
from .world import FEATURES, ITEM_LABELS, POI, World, chunk_of

FACING = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
REGROW = {"e": ("b", 300.0), "k": ("c", 600.0), "q": ("r", 900.0), "f": ("f", 240.0), "m": ("m", 240.0)}
CAMPFIRE_SECONDS = 300.0
GOSSIP_RADIUS = 160
GOSSIP_WINDOW = 1800.0


class Game:
    def __init__(self, seed: int, llm: LLM | None = None, store: Store | None = None):
        self.seed = seed
        self.llm = llm or LLM(None)
        self.store = store
        self.world = World(seed)
        self.t = 0.0
        self.players: dict[str, Player] = {}
        self.npcs: dict[str, NPC] = {}
        self.quests: dict[str, Quest] = {}
        self.events: list[dict] = []
        self.timers: list[tuple[float, int, int, str]] = []     # (at, x, y, code to set)
        self.offers: dict[str, dict] = {}                        # player id -> pending quest offer
        self.outbox: list[tuple[str, dict]] = []
        self._tasks: set[asyncio.Task] = set()
        self._awakening: set[str] = set()
        self._seq = 0
        self._saved_npc: dict[str, dict] = {}
        if store is not None:
            self._restore(store)

    # ------------------------------------------------------------ persistence
    def _restore(self, store: Store) -> None:
        saved_seed = store.get_meta("seed")
        if saved_seed is not None and int(saved_seed) != self.seed:
            raise ValueError(f"store belongs to seed {saved_seed}, not {self.seed}")
        store.set_meta("seed", str(self.seed))
        data = store.load()
        self.t = data["clock"]
        self.world.overrides.update(data["overrides"])
        self._poi_state = data["poi_state"]
        self._saved_npc = data["npcs"]
        for pid, d in data["players"].items():
            d["move"] = (0.0, 0.0)
            d["online"] = False
            self.players[pid] = Player(**d)
        for qid, d in data["quests"].items():
            d["steps"] = [Step(**s) for s in d["steps"]]
            self.quests[qid] = Quest(**d)
        self.events = data["events"]
        self._seq = max((e["seq"] for e in self.events), default=0)
        self.timers = data["timers"]

    def save(self) -> None:
        if self.store is None:
            return
        self.store.set_meta("clock", str(self.t))
        self.store.save(
            overrides=self.world.overrides,
            poi_state={p.id: p.state for p in self.world.pois.values() if p.state},
            npcs={n.id: self._npc_record(n) for n in self.npcs.values() if n.ready},
            players={p.id: {k: v for k, v in asdict(p).items() if k not in ("move", "online")}
                     for p in self.players.values()},
            quests={q.id: q.to_dict() for q in self.quests.values()},
            events=self.events[-500:],
            timers=self.timers,
        )

    @staticmethod
    def _npc_record(n: NPC) -> dict:
        return {k: getattr(n, k) for k in ("name", "persona", "voice", "want", "secret", "generated_by", "memory")}

    # ------------------------------------------------------------------ world
    def ensure_chunk(self, cx: int, cy: int) -> None:
        if (cx, cy) in self.world.chunks:
            return
        ch = self.world.chunk(cx, cy)
        for poi in ch.pois:
            saved = getattr(self, "_poi_state", {}).get(poi.id)
            if saved:
                poi.state.update(saved)
            for n in npcmod.populate(self.seed, poi):
                rec = self._saved_npc.get(n.id)
                if rec:
                    for k, v in rec.items():
                        setattr(n, k, v)
                self.npcs[n.id] = n

    def ensure_around(self, x: float, y: float, radius: int = C.VIEW_CHUNKS) -> list[tuple[int, int]]:
        cx, cy = chunk_of(x, y)
        keys = [(cx + dx, cy + dy) for dy in range(-radius, radius + 1) for dx in range(-radius, radius + 1)]
        for k in keys:
            self.ensure_chunk(*k)
        return keys

    def poi(self, poi_id: str) -> POI | None:
        return self.world.pois.get(poi_id)

    # ----------------------------------------------------------------- events
    def emit(self, kind: str, text: str, actor: str | None = None, target: str | None = None,
             x: float | None = None, y: float | None = None, **data) -> dict:
        self._seq += 1
        ev = {"seq": self._seq, "t": round(self.t, 2), "kind": kind, "text": text, "actor": actor, "target": target,
              "x": x, "y": y, **data}
        self.events.append(ev)
        if len(self.events) > 2000:
            self.events = self.events[-1500:]
        if x is not None:
            for p in self.players.values():
                if p.online and math.hypot(p.x - x, p.y - y) <= 60:
                    self.outbox.append((p.id, {"type": "event", "event": ev}))
        return ev

    def gossip_near(self, x: float, y: float) -> list[str]:
        cutoff = self.t - GOSSIP_WINDOW
        out = [e["text"] for e in self.events
               if e["t"] >= cutoff and e.get("x") is not None and e["kind"] in GOSSIP_KINDS
               and math.hypot(e["x"] - x, e["y"] - y) <= GOSSIP_RADIUS]
        return out[-6:]

    # ---------------------------------------------------------------- players
    def spawn_point(self, pid: str = "") -> tuple[float, float]:
        """A free spot in the village square. Different players land on different tiles."""
        self.ensure_chunk(0, 0)
        v = self.world.pois["village:0:0"]
        taken = {(math.floor(p.x), math.floor(p.y)) for p in self.players.values() if p.online}
        taken |= {(math.floor(n.x), math.floor(n.y)) for n in self.npcs.values()}
        spots = [(v.x + dx, v.y + dy) for r in range(2, 6) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                 if max(abs(dx), abs(dy)) == r and self.world.walkable(v.x + dx, v.y + dy)
                 and (v.x + dx, v.y + dy) not in taken]
        if not spots:
            return v.x + 0.5, v.y + 2.5
        x, y = spots[hash64(self.seed, *map(ord, pid)) % min(len(spots), 16)]
        return x + 0.5, y + 0.5

    def join(self, pid: str, name: str) -> Player:
        p = self.players.get(pid)
        if p is None:
            x, y = self.spawn_point(pid)
            p = Player(pid, name[:20] or "Traveller", x, y, player_signature(self.seed, pid))
            self.players[pid] = p
        p.online, p.move = True, (0.0, 0.0)
        p.name = name[:20] or p.name
        self.ensure_around(p.x, p.y)
        self.emit("arrive", f"{p.name} arrived in the Everfold.", p.id, x=p.x, y=p.y)
        return p

    def leave(self, pid: str) -> None:
        p = self.players.get(pid)
        if p:
            p.online, p.move = False, (0.0, 0.0)
            self.emit("depart", f"{p.name} left.", p.id, x=p.x, y=p.y)

    def set_move(self, pid: str, dx: float, dy: float) -> None:
        p = self.players.get(pid)
        if not p:
            return
        dx, dy = max(-1.0, min(1.0, float(dx))), max(-1.0, min(1.0, float(dy)))
        p.move = (dx, dy)
        if abs(dx) > abs(dy) and dx:
            p.facing = "E" if dx > 0 else "W"
        elif dy:
            p.facing = "S" if dy > 0 else "N"

    def teleport(self, pid: str, x: float, y: float, facing: str | None = None) -> None:
        """For scripted benchmark players and tests."""
        p = self.players[pid]
        p.x, p.y = x, y
        if facing:
            p.facing = facing
        self.ensure_around(x, y)

    def _give(self, p: Player, item: str, n: int = 1) -> None:
        p.inventory[item] = p.inventory.get(item, 0) + n
        self.outbox.append((p.id, {"type": "inventory", "inventory": p.inventory}))

    def _take(self, p: Player, item: str, n: int) -> bool:
        if p.inventory.get(item, 0) < n:
            return False
        p.inventory[item] -= n
        if p.inventory[item] == 0:
            del p.inventory[item]
        self.outbox.append((p.id, {"type": "inventory", "inventory": p.inventory}))
        return True

    def _set_tile(self, x: int, y: int, code: str) -> None:
        self.world.set_feature(x, y, code)
        for p in self.players.values():
            if p.online and math.hypot(p.x - x, p.y - y) <= C.CHUNK * (C.VIEW_CHUNKS + 1.5):
                self.outbox.append((p.id, {"type": "tile", "x": x, "y": y, "code": code or "."}))

    def facing_tile(self, p: Player) -> tuple[int, int]:
        fx, fy = FACING[p.facing]
        return math.floor(p.x + fx * 0.9), math.floor(p.y + fy * 0.9)

    def _interact_target(self, p: Player) -> tuple[int, int] | None:
        tx, ty = self.facing_tile(p)
        cands = [(tx, ty)] + [(math.floor(p.x) + dx, math.floor(p.y) + dy)
                              for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        for x, y in cands:
            f = self.world.feature(x, y)
            if f and f.yields and math.hypot(x + 0.5 - p.x, y + 0.5 - p.y) <= C.INTERACT_RANGE + 0.5:
                return x, y
        return None

    def interact(self, pid: str) -> dict | None:
        p = self.players.get(pid)
        if not p:
            return None
        spot = self._interact_target(p)
        if spot is None:
            return None
        x, y = spot
        f = self.world.feature(x, y)
        self._give(p, f.yields)
        self._set_tile(x, y, f.becomes)
        regrow = REGROW.get(f.becomes) or (REGROW.get(f.code) if not f.becomes else None)
        if regrow:
            self.timers.append((self.t + regrow[1], x, y, regrow[0]))
        verb = {"wood": "felled", "berries": "picked", "stone": "broke", "herb": "gathered", "mushroom": "gathered",
                "relic": "opened", "spirit_orb": "claimed"}[f.yields]
        return self.emit("change", f"{p.name} {verb} {f.label} and got {ITEM_LABELS[f.yields]}.", p.id,
                         x=x + 0.5, y=y + 0.5, tile=[x, y], before=f.code, after=f.becomes, item=f.yields)

    def campfire(self, pid: str) -> dict | None:
        p = self.players.get(pid)
        if not p:
            return None
        x, y = self.facing_tile(p)
        if self.world.feature_code(x, y) or not self.world.ground(x, y).walkable or not self._take(p, "wood", 1):
            return None
        self._set_tile(x, y, "C")
        self.timers.append((self.t + CAMPFIRE_SECONDS, x, y, ""))
        return self.emit("change", f"{p.name} lit a campfire.", p.id, x=x + 0.5, y=y + 0.5, tile=[x, y],
                         before="", after="C")

    def chat(self, pid: str, text: str) -> None:
        p = self.players.get(pid)
        text = dialogue.clean_player_text(text)
        if not p or not text:
            return
        msg = {"type": "chat", "from": p.name, "id": p.id, "text": text}
        for o in self.players.values():
            if o.online and math.hypot(o.x - p.x, o.y - p.y) <= 40:
                self.outbox.append((o.id, msg))

    # ---------------------------------------------------------------- villagers
    def npc_land(self, poi: POI) -> str:
        counts: dict[str, int] = {}
        for dx in range(-20, 21, 4):
            for dy in range(-20, 21, 4):
                g = self.world.ground(poi.x + dx, poi.y + dy).label
                counts[g] = counts.get(g, 0) + 1
        return ", ".join(sorted(counts, key=lambda k: -counts[k])[:3])

    async def awaken(self, npc: NPC) -> NPC:
        if npc.ready:
            return npc
        poi = self.world.pois[npc.poi_id]
        neighbours = [n for n in self.npcs.values() if n.poi_id == npc.poi_id and n.id != npc.id]
        await npcmod.awaken(npc, poi, neighbours, self.npc_land(poi), self.seed, self.llm)
        self.emit("npc_awake", f"{npc.name} the {npc.role} of {poi.name}.", npc.id, x=npc.x, y=npc.y,
                  generated_by=npc.generated_by)
        return npc

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def idle(self) -> None:
        """Wait for background model calls. Used by tests and the benchmark."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def nearest_npc(self, p: Player, radius: float = C.TALK_RANGE) -> NPC | None:
        best = min(self.npcs.values(), key=lambda n: math.hypot(n.x - p.x, n.y - p.y), default=None)
        return best if best and math.hypot(best.x - p.x, best.y - p.y) <= radius else None

    async def talk(self, pid: str, npc_id: str, said: str = "") -> dict | None:
        p, npc = self.players.get(pid), self.npcs.get(npc_id)
        if not p or not npc or math.hypot(npc.x - p.x, npc.y - p.y) > C.TALK_RANGE + 1:
            return None
        await self.awaken(npc)
        self._advance(p, "talk", npc.id)
        mine = [self.quests[q] for q in p.quests if self.quests[q].giver == npc.id]
        between = ({"title": mine[0].title, "next_step": mine[0].current.text if mine[0].current else "done"}
                   if mine else None)
        may_offer = not mine and len(p.quests) < C.MAX_ACTIVE_QUESTS and pid not in self.offers
        out = await dialogue.talk(npc, p, said, self.gossip_near(npc.x, npc.y), between, may_offer, self.llm)
        msg = {"type": "say", "npc": npc.public(), "text": out["reply"], "mood": out.get("mood", ""),
               "generated_by": out["generated_by"]}
        self.outbox.append((pid, msg))
        self.emit("talk", f"{p.name} talked with {npc.name}.", pid, npc.id, x=npc.x, y=npc.y, private=True)
        if out.get("offer_quest"):
            await self.offer_quest(pid, npc.id)
        return msg

    async def offer_quest(self, pid: str, npc_id: str) -> Quest | None:
        p, npc = self.players[pid], self.npcs[npc_id]
        places = self.world.pois_near(npc.x, npc.y, 140)
        people = [n for n in self.npcs.values()
                  if n.id != npc.id and math.hypot(n.x - npc.x, n.y - npc.y) <= 140]
        past = [self.quests[q].title for q in p.quests + p.done_quests if q in self.quests]
        ctx = questmod.context(npc, places, people, p.name, past)
        qid = f"q:{pid}:{len(p.quests) + len(p.done_quests) + len(self.offers)}:{int(self.t)}"
        quest = await questmod.write(qid, npc, pid, ctx, self.llm, salt=len(past))
        self.offers[pid] = {"quest": quest}
        self.outbox.append((pid, {"type": "offer", "quest": quest.to_dict(), "giver": npc.public()}))
        return quest

    def accept(self, pid: str) -> Quest | None:
        offer = self.offers.pop(pid, None)
        p = self.players.get(pid)
        if not offer or not p:
            return None
        q: Quest = offer["quest"]
        self.quests[q.id] = q
        p.quests.append(q.id)
        giver = self.npcs[q.giver]
        self.emit("quest_start", f"{p.name} agreed to help {giver.name}: {q.title}.", pid, giver.id,
                  x=giver.x, y=giver.y, quest=q.id, generated_by=q.generated_by, rejected_steps=q.rejected_steps)
        self._send_quests(p)
        self._advance(p)
        return q

    def decline(self, pid: str) -> None:
        self.offers.pop(pid, None)

    def give(self, pid: str, npc_id: str) -> bool:
        p, npc = self.players.get(pid), self.npcs.get(npc_id)
        if not p or not npc or math.hypot(npc.x - p.x, npc.y - p.y) > C.TALK_RANGE + 1:
            return False
        return self._advance(p, "deliver", npc.id)

    # ----------------------------------------------------------------- quests
    def _send_quests(self, p: Player) -> None:
        self.outbox.append((p.id, {"type": "quests", "quests": [self.quests[q].to_dict() for q in p.quests]}))

    def _step_met(self, p: Player, step: Step, trigger: str | None, target: str | None) -> bool:
        if step.type == "goto":
            poi = self.poi(step.target)
            return bool(poi) and math.hypot(poi.x + 0.5 - p.x, poi.y + 0.5 - p.y) <= C.GOTO_RADIUS + 2
        if step.type == "gather":
            return p.inventory.get(step.item, 0) >= step.count
        if step.type == "talk":
            return trigger == "talk" and target == step.target
        if step.type == "deliver":
            return trigger == "deliver" and target == step.target and self._take(p, step.item, step.count)
        if step.type == "solve":
            poi = self.poi(step.target)
            return bool(poi) and poi.state.get("solved", False)
        return False

    def _advance(self, p: Player, trigger: str | None = None, target: str | None = None) -> bool:
        moved = False
        for qid in list(p.quests):
            q = self.quests[qid]
            while q.current and self._step_met(p, q.current, trigger, target):
                q.step += 1
                moved = True
                trigger = None          # one talk or delivery satisfies one step
            if q.status == "active" and q.step >= len(q.steps):
                q.status = "done"
                p.quests.remove(qid)
                p.done_quests.append(qid)
                for item, n in q.reward.items():
                    self._give(p, item, n)
                giver = self.npcs.get(q.giver)
                if giver:
                    giver.memory.setdefault(p.id, []).append(f"{p.name} finished my request: {q.title}")
                self.emit("quest_done", f"{p.name} finished \"{q.title}\" for {giver.name if giver else 'someone'}.",
                          p.id, q.giver, x=p.x, y=p.y, quest=qid)
        if moved:
            self._send_quests(p)
        return moved

    # ------------------------------------------------------------------- tick
    def step(self, dt: float) -> None:
        self.t += dt
        for p in self.players.values():
            if p.online and p.move != (0.0, 0.0):
                self._move(p, dt)
        self._shrines()
        self._npcs(dt)
        for p in self.players.values():
            if p.online:
                self._advance(p)
        self._timers()

    def _move(self, p: Player, dt: float) -> None:
        dx, dy = p.move
        norm = math.hypot(dx, dy) or 1.0
        speed = C.PLAYER_SPEED * self.world.ground(math.floor(p.x), math.floor(p.y)).speed * dt / norm
        before = chunk_of(p.x, p.y)
        nx = p.x + dx * speed
        if self.world.walkable(math.floor(nx), math.floor(p.y)):
            p.x = nx
        ny = p.y + dy * speed
        if self.world.walkable(math.floor(p.x), math.floor(ny)):
            p.y = ny
        if chunk_of(p.x, p.y) != before:
            self.ensure_around(p.x, p.y)
            self.outbox.append((p.id, {"type": "need_chunks"}))

    def _shrines(self) -> None:
        online = [p for p in self.players.values() if p.online]
        if len(online) < 2:
            return
        for poi in self.world.pois.values():
            if poi.kind != "shrine" or poi.state.get("solved"):
                continue
            on = []
            for px, py in poi.slots:
                who = [p for p in online if math.hypot(p.x - (px + 0.5), p.y - (py + 0.5)) <= C.SHRINE_PLATE_RADIUS]
                on.append(who)
            if all(on) and len({w.id for ws in on for w in ws}) >= 2:
                names = sorted({w.name for ws in on for w in ws})
                poi.state["solved"] = True
                poi.state["by"] = names
                gx, gy = poi.x, poi.y - 2
                self._set_tile(gx, gy, "G")
                self._set_tile(poi.x, poi.y, "O")
                self.emit("shrine_open", f"{' and '.join(names)} opened the {poi.name} shrine together.",
                          target=poi.id, x=poi.x + 0.5, y=poi.y + 0.5, tile=[gx, gy], players=names)

    def _npcs(self, dt: float) -> None:
        for n in self.npcs.values():
            near = any(p.online and math.hypot(p.x - n.x, p.y - n.y) <= 12 for p in self.players.values())
            if near and not n.ready and n.id not in self._awakening:
                self._awakening.add(n.id)
                try:
                    asyncio.get_running_loop()
                    self._spawn(self.awaken(n))
                except RuntimeError:
                    # headless use (benchmark, scripts): no event loop, so write the villager without a model
                    poi = self.world.pois[n.poi_id]
                    mind = npcmod.scripted_mind(self.seed, n, poi)
                    n.name, n.persona, n.voice, n.want, n.secret = (mind[k] for k in
                                                                    ("name", "persona", "voice", "want", "secret"))
                    n.generated_by = "scripted"
            if near and self.t >= n.busy_until:
                h = hash64(self.seed, *map(ord, n.id), int(self.t // 6))
                tx = n.home[0] + 0.5 + (h % (2 * C.NPC_WANDER + 1)) - C.NPC_WANDER
                ty = n.home[1] + 0.5 + ((h >> 8) % (2 * C.NPC_WANDER + 1)) - C.NPC_WANDER
                if self.world.walkable(math.floor(tx), math.floor(ty)):
                    n.x, n.y = tx, ty
                n.busy_until = self.t + 6

    def _timers(self) -> None:
        due = [t for t in self.timers if t[0] <= self.t]
        if not due:
            return
        self.timers = [t for t in self.timers if t[0] > self.t]
        for _, x, y, code in due:
            self._set_tile(x, y, code)

    # ------------------------------------------------------------ observation
    def time_of_day(self) -> str:
        phase = (self.t % C.DAY_SECONDS) / C.DAY_SECONDS
        return "dawn" if phase < 0.15 else "day" if phase < 0.6 else "dusk" if phase < 0.75 else "night"

    def weather_at(self, x: float, y: float) -> str:
        h = hash64(self.seed, math.floor(x / C.WEATHER_CELL), math.floor(y / C.WEATHER_CELL),
                   int(self.t // C.WEATHER_PERIOD))
        return ["clear", "clear", "clear", "drifting clouds", "light rain", "morning mist"][h % 6]

    def snapshot(self, pid: str) -> dict:
        p = self.players[pid]
        near = lambda e: math.hypot(e.x - p.x, e.y - p.y) <= C.CHUNK * 1.5
        return {"type": "snapshot", "t": round(self.t, 2), "time_of_day": self.time_of_day(),
                "weather": self.weather_at(p.x, p.y),
                "you": p.public() | {"inventory": p.inventory},
                "players": [o.public() for o in self.players.values() if o.online and o.id != pid and near(o)],
                "npcs": [n.public() for n in self.npcs.values() if near(n)]}


GOSSIP_KINDS = {"change", "shrine_open", "quest_done", "quest_start", "arrive"}
FEATURE_LABEL = {k: v.label for k, v in FEATURES.items()}
