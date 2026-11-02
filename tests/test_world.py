from hyrule.config import CHUNK
from hyrule.world import GROUND, World


def test_same_seed_same_world_different_seed_different_world():
    a, b, c = World(42), World(42), World(43)
    for w in (a, b, c):
        for cx in range(-1, 2):
            w.chunk(cx, 0)
    assert a.chunk(1, 0).ground == b.chunk(1, 0).ground
    assert a.chunk(1, 0).ground != c.chunk(1, 0).ground


def test_terrain_is_continuous_across_chunk_edges():
    w = World(7)
    jumps = 0
    for y in range(0, 4 * CHUNK):
        x = CHUNK - 1
        e1, e2 = w._fields(x, y)[0], w._fields(x + 1, y)[0]
        jumps += abs(e1 - e2) > 0.05
    assert jumps == 0


def test_spawn_has_a_village_and_a_coop_shrine():
    w = World(42)
    w.chunk(0, 0), w.chunk(1, 0)
    v, s = w.pois["village:0:0"], w.pois["shrine:1:0"]
    assert len(v.slots) == 3 and w.feature_code(v.x, v.y) == "w"
    assert len(s.slots) == 2 and all(w.feature_code(x, y) == "o" for x, y in s.slots)
    assert w.feature_code(s.x, s.y - 2) == "g" and s.state == {"solved": False}


def test_every_seed_gets_a_reachable_spawn_village():
    for seed in (1, 2, 3, 99, 2026):
        w = World(seed)
        v = w.chunk(0, 0) and w.pois["village:0:0"]
        assert GROUND[w.chunk(0, 0).ground[0]] is not None
        assert w.ground(v.x, v.y).code == "P"


def test_player_changes_override_generation_and_reach_clients():
    w = World(42)
    w.chunk(0, 0)
    w.set_feature(3, 4, "x")
    assert w.feature_code(3, 4) == "x"
    payload = w.chunk_payload(0, 0)
    assert payload["feature"][4 * CHUNK + 3] == "x"
    assert len(payload["ground"]) == CHUNK * CHUNK and len(payload["feature"]) == CHUNK * CHUNK


def test_pois_near_sorted_by_distance():
    w = World(42)
    for cx in range(-2, 3):
        for cy in range(-2, 3):
            w.chunk(cx, cy)
    near = w.pois_near(16, 16, 120)
    d = [((p.x - 16) ** 2 + (p.y - 16) ** 2) for p in near]
    assert d == sorted(d) and near[0].id == "village:0:0"
