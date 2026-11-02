"""Tuning constants for the testbed. Change numbers here, not in the engine."""

CHUNK = 32                  # tiles per chunk side
TICK_HZ = 10
PLAYER_SPEED = 4.5          # tiles per second
SLOW_TERRAIN_FACTOR = 0.5   # hills, sand, shallow river
VIEW_CHUNKS = 1             # a client receives chunks within this Chebyshev radius of its own

INTERACT_RANGE = 1.6        # tiles
TALK_RANGE = 2.5
GOTO_RADIUS = 3.0           # how close counts as "reached" for a quest step

DAY_SECONDS = 600           # one in-game day of wall-clock time
WEATHER_CELL = 96           # tiles per weather region
WEATHER_PERIOD = 180        # seconds a weather pattern holds

VIEW_RADIUS = 12            # tiles a world-model camera "sees" for prompt compilation
LANDMARK_RADIUS = 48        # towers and shrines are visible from further away
VIEW_PROMPT_EVERY = 3.0     # seconds between view prompts pushed to a client

NPC_WANDER = 4              # tiles from home an NPC strolls
NPC_THINK_TIMEOUT = 20.0    # seconds before an LLM call falls back to scripted content

MAX_ACTIVE_QUESTS = 3
SHRINE_PLATE_RADIUS = 0.8

# Every frame prompt ends with this. It is the drift lock for appearance across a session.
STYLE_ANCHOR = (
    "stylized hand-painted open-world adventure game, soft cel shading, warm afternoon palette, "
    "third-person camera, consistent art direction, no text, no UI"
)
