"""Two-player condition: one session per player, and a pair judge that asks whether both saw the same tower."""
import json

from everfold.bench import adapters as A
from everfold.bench import sweep as S
from everfold.bench.judge import Judge
from everfold.bench.probes import build
from everfold.bench.run import consistency, rescore, run


class Session(A.ReferenceAdapter):
    """A stand-in session that records which player it rendered for."""
    made = []

    def __init__(self):
        self.players, self.cost, self.closed = [], 0.01, False
        Session.made.append(self)

    async def frame(self, step):
        self.players.append(step.player)
        return await super().frame(step)

    async def close(self):
        self.closed = True

    def stats(self):
        return {"est_cost_usd": self.cost, "sessions": 1, "errors": []}


async def test_each_player_gets_their_own_session():
    Session.made = []
    pp = A.PerPlayerAdapter(Session, "x-image-2p")
    steps = build(42, ["cross_view"])
    await pp.open("cross_view")
    for s in steps:
        await pp.frame(s)
    await pp.close()
    assert len(Session.made) == 2 and [m.players for m in Session.made] == [[steps[0].player], [steps[1].player]]
    assert all(m.closed for m in Session.made)
    assert pp.stats()["players"] == 2 and pp.stats()["est_cost_usd"] == 0.02 and pp.cost == 0.02


def test_2p_conditions_run_only_cross_view():
    assert S.parse_plan(["abot-image-2p:5"]) == [("abot-image-2p", 5)]
    assert S.probes_for("abot-image-2p") == ["cross_view"] and S.probes_for("abot-image-drive") is None
    a = S.make_adapter("abot-image-2p", 5.0)        # sessions are made lazily, so no fal key is needed here
    assert isinstance(a, A.PerPlayerAdapter) and a.name == "abot-image-2p"


def test_consistency_needs_both_present_and_same():
    m = {"cross_view_agreement": 1.0}
    assert consistency({"a": "present", "b": "present", "same": "same"}, m) == 1.0
    assert consistency({"a": "present", "b": "present", "same": "different"}, m) == 0.0
    assert consistency({"a": "present", "b": "absent", "same": "unclear"}, m) == 0.0
    assert consistency(None, m) is None
    assert consistency({"a": "present", "b": "present", "same": "same"}, {"cross_view_agreement": None}) is None


async def test_run_judges_the_pair_and_rescore_backfills_it(tmp_path, fake_claude):
    def present(kw):
        n = kw["messages"][0]["content"][1]["text"].count("\n")
        return {"verdicts": [{"n": i + 1, "verdict": "present", "why": ""} for i in range(n)]}

    pair = {"a": "present", "b": "present", "same": "different", "why": "one tower is round, one square"}
    m = await run(42, A.ReferenceAdapter(), tmp_path, Judge(fake_claude(present, present, pair)), ["cross_view"])
    assert m["cross_view_consistency"] == 0.0
    saved = json.loads((tmp_path / "pair.json").read_text())
    assert saved["same"] == "different" and "tower" in saved["thing"]
    # an older run without a pair: rescore asks the judge once, for the pair only
    (tmp_path / "pair.json").unlink()
    j = Judge(fake_claude(dict(pair, same="same")))
    m2 = await rescore(tmp_path, j)
    assert len(j.client.calls) == 1 and m2["cross_view_consistency"] == 1.0
