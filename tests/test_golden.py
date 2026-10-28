from collections import Counter
from events_agent import golden, kb


def test_groups():
    tasks = golden.tasks()
    assert len({t["id"] for t in tasks}) == 67
    assert Counter(t["group"] for t in tasks) == {golden.IN_BASE: 27, golden.SEARCH_ONLY: 30, golden.NO_ANSWER: 10}


def test_held_out_pages_are_not_in_eval_base():
    held = golden.held_out_pages()
    pages = {c["page"] for c in kb.corpus_chunks(held)}
    assert not pages & held
    assert {t["page"] for t in golden.tasks() if t["group"] == golden.IN_BASE} <= pages
    assert {t["page"] for t in golden.tasks() if t["group"] == golden.SEARCH_ONLY} <= held
