from events_agent.grading import is_correct, is_refusal, score


def test_is_correct_from_stage_3():
    assert is_correct({"answer": "15 March"}, "Нашёл.\nFINAL: March 15, 2026")
    assert not is_correct({"answer": "Charles H. Bennett, Gilles Brassard"}, "FINAL: Charles H. Bennett")


def test_numbers_and_scales():
    assert is_correct({"answer": "43"}, "FINAL: 43 people")
    assert not is_correct({"answer": "43"}, "FINAL: 143")
    assert is_correct({"answer": "$400 million"}, "FINAL: $400M")


def test_refusal():
    assert is_refusal("Nothing in the sources.\nFINAL: NOT_FOUND")
    assert not is_refusal("FINAL: Felix Rosenqvist")


def test_score_no_answer_needs_refusal():
    task = {"kind": "no_answer", "answer": "something"}
    assert score(task, "FINAL: NOT_FOUND")
    assert not score(task, "FINAL: something")
