"""Deterministic integer hashing and value noise. No global RNG: every value is a function of (seed, coords)."""
from __future__ import annotations

import math
from functools import lru_cache

MASK = 0xFFFFFFFFFFFFFFFF


def hash64(*parts: int) -> int:
    """SplitMix64-style mix of integers. Stable across runs and platforms."""
    h = 0x9E3779B97F4A7C15
    for p in parts:
        h = (h ^ (p & MASK)) & MASK
        h = (h + 0x9E3779B97F4A7C15) & MASK
        z = h
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
        h = z ^ (z >> 31)
    return h


def rand01(*parts: int) -> float:
    return (hash64(*parts) >> 11) / float(1 << 53)


def _smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


@lru_cache(maxsize=1 << 18)
def _lattice(seed: int, x: int, y: int) -> float:
    return rand01(seed, x, y)


def value_noise(seed: int, x: float, y: float) -> float:
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = _smooth(x - x0), _smooth(y - y0)
    a = _lattice(seed, x0, y0)
    b = _lattice(seed, x0 + 1, y0)
    c = _lattice(seed, x0, y0 + 1)
    d = _lattice(seed, x0 + 1, y0 + 1)
    top = a + (b - a) * fx
    bottom = c + (d - c) * fx
    return top + (bottom - top) * fy


def fbm(seed: int, x: float, y: float, scale: float, octaves: int = 4) -> float:
    """Fractal noise in [0, 1]. `scale` is the size in tiles of the largest feature."""
    total, amp, norm, freq = 0.0, 1.0, 0.0, 1.0 / scale
    for o in range(octaves):
        total += amp * value_noise(seed + o * 1013, x * freq, y * freq)
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm
