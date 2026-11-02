from hyrule import config as C
from hyrule.game import Game
from hyrule.render.prompt import compile_prompt
from hyrule.render.reference import render_reference
from hyrule.render.view import view


def tower_game():
    g = Game(42)
    g.join("p_a", "Ash")
    g.ensure_around(0, 0, 3)
    t = next(p for p in g.world.pois.values() if p.kind == "tower")
    return g, t


def test_a_landmark_is_seen_only_when_facing_it():
    g, t = tower_game()
    g.teleport("p_a", t.x + 0.5, t.y + 9.5, "N")
    assert f"landmark:{t.id}" in {f.id for f in view(g, "p_a").facts}
    g.teleport("p_a", t.x + 0.5, t.y + 9.5, "S")
    assert f"landmark:{t.id}" not in {f.id for f in view(g, "p_a").facts}


def test_prompt_opens_with_identity_and_closes_with_the_style_lock():
    g, t = tower_game()
    g.teleport("p_a", t.x + 0.5, t.y + 9.5, "N")
    p = compile_prompt(view(g, "p_a"))
    assert p.lower().startswith(g.players["p_a"].signature.lower())
    assert p.endswith(f"Style: {C.STYLE_ANCHOR}.")
    assert "tower" in p and "facing north" in p


def test_other_players_appear_in_each_others_view():
    g, t = tower_game()
    g.join("p_b", "Briar")
    g.teleport("p_a", t.x + 0.5, t.y + 9.5, "N")
    g.teleport("p_b", t.x + 0.5, t.y + 6.5, "S")
    va, vb = view(g, "p_a"), view(g, "p_b")
    assert "person:p_b" in {f.id for f in va.facts} and "person:p_a" in {f.id for f in vb.facts}


def test_reference_render_is_a_png():
    g, t = tower_game()
    png = render_reference(g, view(g, "p_a"))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 1000
