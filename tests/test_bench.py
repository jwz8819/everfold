import json

import pytest

from hyrule.bench import adapters as A
from hyrule.bench.judge import Judge
from hyrule.bench.probes import PROBES, build
from hyrule.bench.run import run, score


@pytest.mark.parametrize("seed", [42, 7, 2026, 31337])
def test_every_probe_builds_on_several_worlds(seed):
    steps = build(seed)
    assert {s.probe for s in steps} == set(PROBES)
    assert all(s.prompt and s.view.facts and s.reference for s in steps)


def all_verdicts(steps, value):
    return {s.id: {f.id: value for f in s.view.facts} for s in steps}


def test_a_perfect_renderer_scores_full_marks_and_a_blank_one_zero():
    steps = build(42)
    good, bad = score(steps, all_verdicts(steps, "present")), score(steps, all_verdicts(steps, "absent"))
    for k in ("cross_view_agreement", "propagation", "identity_persistence", "shrine_state_change"):
        assert good[k] == 1.0 and bad[k] == 0.0
    assert good["revisit_retention"] == 1.0 and bad["revisit_retention"] is None


def test_revisit_only_counts_what_was_shown_the_first_time():
    steps = [s for s in build(42, ["revisit"])]
    v = all_verdicts(steps, "present")
    last = steps[-1]
    landmark = next(f.id for f in last.view.facts if f.kind == "landmark")
    v[last.id][landmark] = "absent"
    m = score(steps, v)
    shown_first = len(steps[0].view.facts)
    assert m["revisit_retention"] == pytest.approx(round((shown_first - 1) / shown_first, 3))


async def test_judge_reads_verdicts_and_survives_bad_output(fake_claude):
    steps = build(42, ["shrine"])
    s = steps[-1]
    n = len(s.view.facts)
    reply = {"verdicts": [{"n": i + 1, "verdict": "present" if i % 2 == 0 else "absent", "why": ""} for i in range(n)]
             + [{"n": 99, "verdict": "present", "why": "ignored"}]}
    j = Judge(fake_claude(reply))
    out = await j.check(s, s.reference)
    assert [out[f.id] for f in s.view.facts] == ["present" if i % 2 == 0 else "absent" for i in range(n)]
    content = j.client.calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    assert s.prompt not in json.dumps(content), "the judge must not see the prompt"
    j2 = Judge(fake_claude(reply, stop_reason="refusal"))
    assert set((await j2.check(s, s.reference)).values()) == {"unclear"} and j2.failures == 1


async def test_full_run_with_reference_renderer_and_fake_judge(tmp_path, fake_claude):
    def all_present(kw):
        n = kw["messages"][0]["content"][1]["text"].count("\n")
        return {"verdicts": [{"n": i + 1, "verdict": "present", "why": ""} for i in range(n)]}

    steps = len(build(42))
    m = await run(42, A.ReferenceAdapter(), tmp_path, Judge(fake_claude(*[all_present] * steps)))
    assert m["frames_judged"] == steps and m["cross_view_agreement"] == 1.0
    for name in ("steps.jsonl", "prompts.md", "verdicts.jsonl", "metrics.json", "report.md"):
        assert (tmp_path / name).exists()
    assert len(list((tmp_path / "frames").glob("*.png"))) == steps


async def test_folder_adapter_reads_hand_captured_frames(tmp_path):
    steps = build(42, ["identity"])
    (tmp_path / f"{steps[1].id}.png").write_bytes(steps[1].reference)
    ad = A.FolderAdapter(tmp_path)
    assert (await ad.frame(steps[0]))[0] is None
    assert (await ad.frame(steps[1]))[0] == steps[1].reference
