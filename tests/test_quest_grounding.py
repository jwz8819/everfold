"""Quest grounding batch: counts steps pointing at nothing real and names in the text that are not in the world."""
import json

from everfold.bench.quest_grounding import batch, names_in
from everfold.content.llm import LLM


def test_names_in_skips_sentence_starts():
    assert names_in("Bring wood to Mira. Then see Old Tobbe at Kestrel ford!") == ["Mira", "Old", "Tobbe", "Kestrel"]


async def test_batch_counts_invented_steps_and_names(tmp_path, fake_claude):
    def writer(kw):
        ctx = json.loads(kw["messages"][0]["content"])
        real = ctx["people"][0]["id"]
        return {"title": "Fish for Grandmother Ysolde", "summary": "Bring berries to me, then visit Tobbe at the mill.",
                "steps": [{"type": "gather", "item": "berries", "count": 3, "target": ""},
                          {"type": "talk", "target": "npc:invented:9", "item": "", "count": 0},
                          {"type": "deliver", "item": "berries", "count": 3, "target": real}],
                "reward_item": "wood", "reward_count": 1}

    s = await batch([1], LLM(fake_claude(writer, writer)), tmp_path, givers=2)
    assert s["written_by_model"] == 2 and s["fallback"] == 0
    assert s["steps_proposed"] == 6 and s["steps_rejected"] == 2 and s["step_rejection_rate"] == 0.333
    assert s["quests_with_unknown_names"] == 2
    rows = [json.loads(l) for l in (tmp_path / "quests.jsonl").read_text().splitlines()]
    assert {"Ysolde", "Tobbe"} <= set(rows[0]["unknown_names"])
    assert "Grandmother" not in rows[0]["unknown_names"] and "Fish" not in rows[0]["unknown_names"]
    assert "Quests with unknown names" in (tmp_path / "report.md").read_text()


async def test_a_failed_writer_falls_back_and_is_counted(tmp_path):
    s = await batch([1], LLM(None), tmp_path, givers=1)
    assert s["fallback"] == 1 and s["written_by_model"] == 0 and s["step_rejection_rate"] is None
