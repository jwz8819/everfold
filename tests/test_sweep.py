import json

import pytest

from everfold.bench import adapters as A
from everfold.bench import sweep as S
from everfold.bench.run import run


def test_plan_and_seed_major_schedule():
    plan = S.parse_plan(["abot-image-drive:3", "lingbot-image:2"])
    assert S.schedule(plan) == [("abot-image-drive", 42), ("lingbot-image", 42), ("abot-image-drive", 1),
                                ("lingbot-image", 1), ("abot-image-drive", 2)]
    for bad in ("eden:3", "abot-image-drive", "abot-image-drive:0", "abot-drive:2"):
        with pytest.raises(ValueError):
            S.parse_plan([bad])


class CheapAdapter(A.ReferenceAdapter):
    """Stands in for a fal model: the reference renderer, with a cost."""
    def __init__(self, model, settle_s=5.0, start="preset", drive=False):
        self.name, self.cost = f"{model}-{start}" + ("-drive" if drive else ""), 0.0

    async def frame(self, step):
        self.cost += 0.01
        return await super().frame(step)

    async def aclose(self):
        return None

    def stats(self):
        return {"est_cost_usd": round(self.cost, 4)}


async def test_sweep_respects_budget_resumes_and_logs(tmp_path, monkeypatch):
    import everfold.bench.fal_adapter as F

    monkeypatch.setattr(F, "FalWorldAdapter", CheapAdapter)
    monkeypatch.setattr(S, "FALLBACK_COST", {"abot": 0.14, "lingbot": 0.14, "eden": 1.0})
    plan = S.parse_plan(["abot-image-drive:3"])
    # 14 steps x $0.01 = $0.14 per run; predicted 0.14 * 1.15 = 0.161, so $0.40 allows two runs
    r = await S.sweep(plan, 0.40, "t", tmp_path, lambda: None, log=lambda m: None)
    assert r["done"] == ["abot-image-drive-seed42", "abot-image-drive-seed1"]
    assert r["skipped_for_budget"] == ["abot-image-drive-seed2"]
    assert S.ledger_total(tmp_path, "t") == pytest.approx(0.28)
    # resume with a bigger budget: only the missing run happens, and the ledger keeps counting
    r2 = await S.sweep(plan, 1.0, "t", tmp_path, lambda: None, log=lambda m: None)
    assert r2["done"] == ["abot-image-drive-seed2"] and S.ledger_total(tmp_path, "t") == pytest.approx(0.42)
    dry = await S.sweep(S.parse_plan(["abot-image-drive:5"]), 1.0, "t", tmp_path, lambda: None,
                        log=lambda m: None, dry_run=True)
    assert dry["done"] == ["abot-image-drive-seed3", "abot-image-drive-seed4"]
    assert S.ledger_total(tmp_path, "t") == pytest.approx(0.42), "a dry run spends nothing"


async def test_aggregate_means_intervals_and_na(tmp_path):
    for seed in (42, 1, 2):
        await run(seed, A.ReferenceAdapter(), tmp_path / f"abot-image-drive-seed{seed}", None, ["shrine"])
        m = json.loads((tmp_path / f"abot-image-drive-seed{seed}" / "metrics.json").read_text())
        m["shrine_state_change"] = {42: 1.0, 1: 0.0, 2: 0.0}[seed]
        m["cross_view_agreement"] = None
        m["renderer"] = {"est_cost_usd": 0.3}
        (tmp_path / f"abot-image-drive-seed{seed}" / "metrics.json").write_text(json.dumps(m))
    a = S.aggregate(tmp_path)["abot-image-drive"]
    assert a["seeds"] == 3 and a["usd_per_run"] == 0.3
    assert a["shrine_state_change"]["mean"] == pytest.approx(0.333) and a["shrine_state_change"]["n"] == 3
    lo, hi = a["shrine_state_change"]["ci95"]
    assert lo == 0.0 and hi == 1.0
    assert a["cross_view_agreement"] == {"n": 0, "mean": None, "ci95": None}
    assert "abot-image-drive | 3 |" in S.aggregate_report(S.aggregate(tmp_path))
