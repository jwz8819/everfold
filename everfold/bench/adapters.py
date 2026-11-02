"""Renderer adapters for the benchmark. One adapter per world model.

An adapter turns each probe step into one image. Streaming models keep one session open per probe family, so
revisit and propagation are tested inside a single continuous session, the way a player would experience them.

Built in:
  reference  top-down control render of the true state (pipeline check, not a world model)
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
