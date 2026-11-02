"""SQLite persistence. The terrain is regenerated from the seed; only what players changed is stored."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS overrides (x INTEGER, y INTEGER, code TEXT, PRIMARY KEY (x, y));
CREATE TABLE IF NOT EXISTS poi_state (id TEXT PRIMARY KEY, state TEXT);
CREATE TABLE IF NOT EXISTS npcs (id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS players (id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS quests (id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, t REAL, data TEXT);
CREATE TABLE IF NOT EXISTS timers (x INTEGER, y INTEGER, at REAL, code TEXT, PRIMARY KEY (x, y));
"""


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def save(self, *, overrides: dict, poi_state: dict, npcs: dict, players: dict, quests: dict,
             events: list[dict], timers: list[tuple]) -> None:
        cur = self.db.cursor()
        cur.executemany("INSERT OR REPLACE INTO overrides VALUES (?, ?, ?)",
                        [(x, y, c) for (x, y), c in overrides.items()])
        cur.executemany("INSERT OR REPLACE INTO poi_state VALUES (?, ?)",
                        [(k, json.dumps(v)) for k, v in poi_state.items()])
        cur.executemany("INSERT OR REPLACE INTO npcs VALUES (?, ?)", [(k, json.dumps(v)) for k, v in npcs.items()])
        cur.executemany("INSERT OR REPLACE INTO players VALUES (?, ?)",
                        [(k, json.dumps(v)) for k, v in players.items()])
        cur.executemany("INSERT OR REPLACE INTO quests VALUES (?, ?)", [(k, json.dumps(v)) for k, v in quests.items()])
        cur.executemany("INSERT OR IGNORE INTO events VALUES (?, ?, ?)",
                        [(e["seq"], e["t"], json.dumps(e)) for e in events])
        cur.execute("DELETE FROM timers")
        cur.executemany("INSERT OR REPLACE INTO timers VALUES (?, ?, ?, ?)", [(x, y, at, c) for at, x, y, c in timers])
        self.db.commit()

    def load(self) -> dict:
        q = self.db.execute
        return {
            "overrides": {(x, y): c for x, y, c in q("SELECT x, y, code FROM overrides")},
            "poi_state": {k: json.loads(v) for k, v in q("SELECT id, state FROM poi_state")},
            "npcs": {k: json.loads(v) for k, v in q("SELECT id, data FROM npcs")},
            "players": {k: json.loads(v) for k, v in q("SELECT id, data FROM players")},
            "quests": {k: json.loads(v) for k, v in q("SELECT id, data FROM quests")},
            "events": [json.loads(v) for (v,) in q("SELECT data FROM events ORDER BY seq DESC LIMIT 2000")][::-1],
            "timers": [(at, x, y, c) for x, y, at, c in q("SELECT x, y, at, code FROM timers")],
            "clock": float(self.get_meta("clock") or 0.0),
        }

    def close(self) -> None:
        self.db.close()
