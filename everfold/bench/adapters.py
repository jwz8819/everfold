"""Renderer adapters for the benchmark. One adapter per world model.

An adapter turns each probe step into one image. Streaming models keep one session open per probe family, so
revisit and propagation are tested inside a single continuous session, the way a player would experience them.

Built in:
  reference  top-down control render of the true state (pipeline check, not a world model)
  greybox    the engine's 3D render of the true state from the player's camera
  prompts    no images; writes prompts so a person can run a model by hand
  folder     reads frames a person captured by hand (web demos, research previews) from <frames>/<step id>.png
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .probes import ProbeStep


class Adapter(Protocol):
    name: str
    async def open(self, probe: str) -> None: ...
    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]: ...      # (image, seconds taken)
    async def close(self) -> None: ...


class ReferenceAdapter:
    """Returns the top-down render of the true state, captured when the probe step was taken."""
    name = "reference"

    async def open(self, probe: str) -> None:
        return None

    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]:
        return step.reference or None, 0.0

    async def close(self) -> None:
        return None


class GreyboxAdapter:
    """The engine's own 3D render of the true state (render/greybox.py): the ceiling for a renderer that draws
    from one shared world, and the input a restyling model is given."""
    name = "greybox"

    async def open(self, probe: str) -> None:
        return None

    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]:
        from ..render.greybox import FACING_HEADING, outfit_color, png, render

        v = step.view
        return png(render(step.scene, v.x, v.y, FACING_HEADING[v.facing], outfit_color(v.signature))), 0.0

    async def close(self) -> None:
        return None

    def stats(self) -> dict:
        return {"model": "greybox", "est_cost_usd": 0.0}


class PerPlayerAdapter:
    """One renderer session per player, the way a game would run one world-model stream per connected player.

    `make()` builds a fresh inner adapter. Within a probe family each player's steps go to that player's own
    session, opened on their first step; all of them stay open until the family ends, as connected players
    would. Only cross_view has two viewers; every other probe is rendered for one watcher, so per-player there
    is the same as one session."""

    def __init__(self, make, name: str):
        self.make, self.name = make, name
        self.live: dict[str, object] = {}
        self.all: list = []

    async def open(self, probe: str) -> None:
        self.live = {}

    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]:
        a = self.live.get(step.player)
        if a is None:
            a = self.live[step.player] = self.make()
            self.all.append(a)
            await a.open(step.probe)
        return await a.frame(step)

    async def close(self) -> None:
        for a in self.live.values():
            await a.close()
        self.live = {}

    async def aclose(self) -> None:
        for a in self.all:
            if hasattr(a, "aclose"):
                await a.aclose()

    @property
    def cost(self) -> float:
        return sum(getattr(a, "cost", 0.0) for a in self.all)

    def stats(self) -> dict:
        parts = [a.stats() for a in self.all if hasattr(a, "stats")]
        out = dict(parts[0]) if parts else {}
        for k in ("est_cost_usd", "session_seconds", "sessions", "responded_steps", "images"):
            if any(k in p for p in parts):
                out[k] = round(sum(p.get(k, 0) for p in parts), 4)
        for k in ("mean_ack_seconds", "mean_response_seconds", "mean_image_seconds"):
            xs = [p[k] for p in parts if p.get(k) is not None]
            if any(k in p for p in parts):
                out[k] = round(sum(xs) / len(xs), 3) if xs else None
        out["errors"] = [e for p in parts for e in p.get("errors", [])][:10]
        out["players"] = len(parts)
        return out


class PromptsAdapter:
    name = "prompts"

    async def open(self, probe: str) -> None:
        return None

    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]:
        return None, 0.0

    async def close(self) -> None:
        return None


class FolderAdapter:
    name = "folder"

    def __init__(self, frames: str | Path):
        self.dir = Path(frames)

    async def open(self, probe: str) -> None:
        return None

    async def frame(self, step: ProbeStep) -> tuple[bytes | None, float]:
        for ext in ("png", "jpg", "jpeg", "webp"):
            f = self.dir / f"{step.id}.{ext}"
            if f.exists():
                return f.read_bytes(), 0.0
        return None, 0.0

    async def close(self) -> None:
        return None
