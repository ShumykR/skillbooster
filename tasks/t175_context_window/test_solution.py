import copy

import pytest

from solution import assemble


def count(s):
    return len(s.split())


def w(n, tag):
    return " ".join(f"{tag}{i}" for i in range(n))


class Summarizer:
    def __init__(self, text="SUMMARY of earlier talk"):
        self.text = text
        self.calls = []

    def __call__(self, turns):
        self.calls.append(list(turns))
        return self.text


def turn(role, n, tag):
    return {"role": role, "content": w(n, tag)}


def texts(res, section=None):
    return [m["text"] for m in res["messages"] if section is None or m["section"] == section]


def sections(res):
    return [m["section"] for m in res["messages"]]


def docs(*pairs):
    return [{"text": t, "score": s} for t, s in pairs]


# --- без обрізання -----------------------------------------------------------------------------

def test_everything_fits_order_and_shape():
    res = assemble("SYS rules", ["m1 fact", "m2 fact"], docs(("d1 text", 0.9)),
                   [{"role": "user", "content": "hi there"}, {"role": "assistant", "content": "hello"}],
                   budget=100, count_tokens=count)
    assert sections(res) == ["instructions", "memory", "memory", "documents", "history", "history"]
    assert [m["role"] for m in res["messages"]] == ["system", "system", "system", "system", "user", "assistant"]
    assert texts(res) == ["SYS rules", "m1 fact", "m2 fact", "d1 text", "hi there", "hello"]
    assert res["tokens"] == 2 + 2 + 2 + 2 + 2 + 1
    assert res["dropped"] == {"documents": 0, "memory": 0, "history": 0}
    assert res["compacted"] is False and res["compacted_turns"] == 0


def test_empty_optional_sections():
    res = assemble("SYS", [], [], [], budget=5, count_tokens=count)
    assert texts(res) == ["SYS"] and res["tokens"] == 1


def test_documents_best_at_the_edges_lost_in_the_middle():
    ds = docs(("d3", 0.3), ("d1", 0.9), ("d5", 0.1), ("d2", 0.8), ("d4", 0.2))
    res = assemble("S", [], ds, [], budget=50, count_tokens=count)
    assert texts(res, "documents") == ["d1", "d3", "d5", "d4", "d2"]


def test_documents_two_three_and_one():
    assert texts(assemble("S", [], docs(("a", 0.1), ("b", 0.5)), [], 50, count), "documents") == ["b", "a"]
    assert texts(assemble("S", [], docs(("a", 0.1), ("b", 0.5), ("c", 0.3)), [], 50, count), "documents") == ["b", "a", "c"]
    assert texts(assemble("S", [], docs(("a", 0.1)), [], 50, count), "documents") == ["a"]


def test_equal_scores_keep_input_order():
    ds = docs(("a", 0.5), ("b", 0.5), ("c", 0.5), ("d", 0.5))
    assert texts(assemble("S", [], ds, [], 50, count), "documents") == ["a", "c", "d", "b"]


def test_inputs_are_not_mutated():
    mem = ["m1 x", "m2 x"]
    ds = docs(("d1 t", 0.9), ("d2 t", 0.1))
    hist = [turn("user", 5, "u"), turn("assistant", 5, "a"), turn("user", 5, "v"), turn("assistant", 5, "b")]
    snapshot = copy.deepcopy((mem, ds, hist))
    assemble("SYS", mem, ds, hist, budget=12, count_tokens=count, summarize=Summarizer())
    assert (mem, ds, hist) == snapshot


# --- бюджет і порядок відкидання ----------------------------------------------------------------

def test_budget_is_never_exceeded_and_instructions_always_first():
    mem = [w(3, "m"), w(3, "n")]
    ds = docs((w(6, "a"), 0.9), (w(6, "b"), 0.5), (w(6, "c"), 0.1))
    hist = [turn("user", 4, "u"), turn("assistant", 4, "a"), turn("user", 4, "v")]
    instr = w(5, "i")
    for budget in range(9, 60):
        res = assemble(instr, mem, ds, hist, budget=budget, count_tokens=count)
        assert res["tokens"] <= budget
        assert res["tokens"] == sum(count(t) for t in texts(res))
        assert res["messages"][0] == {"section": "instructions", "role": "system", "text": instr}
        assert res["messages"][-1]["text"] == hist[-1]["content"]


def test_budget_exactly_filled_is_allowed():
    res = assemble("a b", [], [], [{"role": "user", "content": "c d e"}], budget=5, count_tokens=count)
    assert res["tokens"] == 5 and res["dropped"]["history"] == 0


def test_documents_dropped_first_lowest_score_first():
    mem = ["mem " + w(2, "m")]
    ds = docs((w(4, "a"), 0.9), (w(4, "b"), 0.2), (w(4, "c"), 0.5))
    hist = [turn("user", 3, "u")]
    # 2 + 3 + 12 + 3 = 20
    res = assemble(w(2, "i"), mem, ds, hist, budget=20, count_tokens=count)
    assert res["dropped"] == {"documents": 0, "memory": 0, "history": 0}
    res = assemble(w(2, "i"), mem, ds, hist, budget=19, count_tokens=count)
    assert res["dropped"] == {"documents": 1, "memory": 0, "history": 0}
    kept = texts(res, "documents")
    assert w(4, "b") not in kept and len(kept) == 2
    res = assemble(w(2, "i"), mem, ds, hist, budget=12, count_tokens=count)
    assert res["dropped"]["documents"] == 2 and texts(res, "documents") == [w(4, "a")]


def test_equal_score_documents_drop_the_later_one_first():
    ds = docs(("a1 a2", 0.5), ("b1 b2", 0.5))
    res = assemble("S", [], ds, [], budget=3, count_tokens=count)
    assert texts(res, "documents") == ["a1 a2"]


def test_memory_dropped_after_documents_from_the_end():
    mem = [w(3, "x"), w(3, "y"), w(3, "z")]
    ds = docs((w(4, "d"), 0.9))
    hist = [turn("user", 2, "u")]
    # 1 + 9 + 4 + 2 = 16; без документів 12
    res = assemble("S", mem, ds, hist, budget=12, count_tokens=count)
    assert res["dropped"] == {"documents": 1, "memory": 0, "history": 0}
    res = assemble("S", mem, ds, hist, budget=11, count_tokens=count)
    assert res["dropped"] == {"documents": 1, "memory": 1, "history": 0}
    assert texts(res, "memory") == [w(3, "x"), w(3, "y")]
    res = assemble("S", mem, ds, hist, budget=6, count_tokens=count)
    assert res["dropped"] == {"documents": 1, "memory": 2, "history": 0}
    assert texts(res, "memory") == [w(3, "x")]
    res = assemble("S", mem, ds, hist, budget=5, count_tokens=count)
    assert res["dropped"] == {"documents": 1, "memory": 3, "history": 0}
    assert texts(res, "memory") == []


def test_history_dropped_oldest_first_after_documents_and_memory():
    hist = [turn("user", 3, "a"), turn("assistant", 3, "b"), turn("user", 3, "c"), turn("assistant", 3, "d")]
    res = assemble("S", ["mm"], docs(("dd", 0.5)), hist, budget=100, count_tokens=count)
    assert res["dropped"]["history"] == 0
    res = assemble("S", ["mm"], docs(("dd", 0.5)), hist, budget=9, count_tokens=count)
    assert res["dropped"] == {"documents": 1, "memory": 1, "history": 2}
    assert texts(res, "history") == [w(3, "c"), w(3, "d")]
    res = assemble("S", ["mm"], docs(("dd", 0.5)), hist, budget=4, count_tokens=count)
    assert texts(res, "history") == [w(3, "d")]
    assert res["dropped"]["history"] == 3


def test_instructions_are_never_truncated():
    big = w(10, "i")
    with pytest.raises(ValueError):
        assemble(big, [], [], [], budget=9, count_tokens=count)
    res = assemble(big, ["m"], docs(("d", 1.0)), [turn("user", 1, "u")], budget=11, count_tokens=count)
    assert res["messages"][0]["text"] == big
    assert texts(res, "history") == ["u0"]


def test_last_turn_must_fit_otherwise_value_error():
    with pytest.raises(ValueError):
        assemble("S", [], [], [turn("user", 5, "u")], budget=5, count_tokens=count)
    assert assemble("S", [], [], [turn("user", 4, "u")], budget=5, count_tokens=count)["tokens"] == 5


# --- компактизація -------------------------------------------------------------------------------

def long_history():
    return [turn("user", 10, "a"), turn("assistant", 10, "b"), turn("user", 10, "c"),
            turn("assistant", 10, "d"), turn("user", 10, "e")]


def test_compaction_not_triggered_below_threshold():
    s = Summarizer()
    # усього 1 + 50 = 51 токен, бюджет 100: поріг 80
    res = assemble("S", [], [], long_history(), budget=100, count_tokens=count, summarize=s)
    assert s.calls == [] and res["compacted"] is False and len(texts(res, "history")) == 5


def test_compaction_threshold_is_strict():
    s = Summarizer()
    hist = long_history()  # 50 токенів + інструкції
    res = assemble(w(30, "i"), [], [], hist, budget=100, count_tokens=count, summarize=s)  # рівно 80
    assert s.calls == [] and res["tokens"] == 80
    res = assemble(w(31, "i"), [], [], hist, budget=100, count_tokens=count, summarize=s)  # 81 > 80
    assert len(s.calls) == 1


def test_compaction_summarizes_old_turns_and_keeps_recent_verbatim():
    s = Summarizer("short summary")
    hist = long_history()
    res = assemble(w(35, "i"), [], [], hist, budget=100, count_tokens=count, summarize=s, keep_recent=2)
    assert len(s.calls) == 1
    assert s.calls[0] == [f"user: {w(10, 'a')}", f"assistant: {w(10, 'b')}", f"user: {w(10, 'c')}"]
    assert res["compacted"] is True and res["compacted_turns"] == 3
    assert sections(res) == ["instructions", "summary", "history", "history"]
    assert texts(res, "summary") == ["short summary"]
    assert texts(res, "history") == [w(10, "d"), w(10, "e")]
    assert res["tokens"] == 35 + 2 + 20
    assert res["dropped"]["history"] == 0


def test_summary_sits_between_documents_and_history():
    s = Summarizer()
    res = assemble("S", ["mem"], docs(("doc", 1.0)), long_history(), budget=60, count_tokens=count, summarize=s)
    assert sections(res) == ["instructions", "memory", "documents", "summary", "history", "history"]


def test_compaction_called_once_per_assemble():
    s = Summarizer()
    assemble("S", [], [], long_history(), budget=30, count_tokens=count, summarize=s)
    assert len(s.calls) == 1


def test_no_compaction_when_not_enough_old_turns():
    s = Summarizer()
    hist = [turn("user", 40, "a"), turn("assistant", 40, "b")]
    assemble("S", [], [], hist, budget=90, count_tokens=count, summarize=s, keep_recent=2)
    assert s.calls == []


def test_keep_recent_is_configurable():
    s = Summarizer()
    res = assemble(w(40, "i"), [], [], long_history(), budget=100, count_tokens=count, summarize=s, keep_recent=4)
    assert s.calls == [[f"user: {w(10, 'a')}"]]
    assert len(texts(res, "history")) == 4


def test_summary_that_is_not_shorter_is_discarded():
    s = Summarizer(w(40, "long"))  # довше, ніж 3 старі ходи по 10
    hist = long_history()
    res = assemble(w(35, "i"), [], [], hist, budget=100, count_tokens=count, summarize=s)
    assert len(s.calls) == 1
    assert res["compacted"] is False and "summary" not in sections(res)
    assert len(texts(res, "history")) == 5


def test_summarize_none_only_trims():
    res = assemble(w(35, "i"), [], [], long_history(), budget=60, count_tokens=count, summarize=None)
    assert res["compacted"] is False
    assert texts(res, "history") == [w(10, "d"), w(10, "e")] and res["dropped"]["history"] == 3


def test_summary_is_dropped_before_recent_history_when_still_too_big():
    s = Summarizer(w(10, "sum"))
    hist = long_history()
    # інструкції 5, summary 10, останні два ходи по 10 = 35 > 30 → summary відкидається
    res = assemble(w(5, "i"), [], [], hist, budget=30, count_tokens=count, summarize=s)
    assert res["compacted"] is False and res["compacted_turns"] == 0
    assert "summary" not in sections(res)
    assert texts(res, "history") == [w(10, "d"), w(10, "e")]
    assert res["dropped"]["history"] == 3
    assert res["tokens"] == 25


def test_documents_are_dropped_before_the_summary_is_touched():
    s = Summarizer(w(4, "sum"))
    res = assemble("S", [], docs((w(10, "d"), 0.5)), long_history(), budget=30, count_tokens=count, summarize=s)
    assert res["dropped"]["documents"] == 1
    assert res["compacted"] is True and res["tokens"] == 1 + 4 + 20


# --- валідація ------------------------------------------------------------------------------------

@pytest.mark.parametrize("kw", [{"budget": 0}, {"budget": -1}, {"budget": 5.5}, {"keep_recent": 0},
                                {"compact_at": 0}, {"compact_at": 1.1}, {"compact_at": -0.5}])
def test_invalid_parameters(kw):
    args = {"budget": 50, "count_tokens": count}
    args.update(kw)
    with pytest.raises(ValueError):
        assemble("S", [], [], [], **args)
