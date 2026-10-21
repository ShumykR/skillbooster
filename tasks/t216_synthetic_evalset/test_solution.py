import copy
import json
import random
import re

import pytest

from solution import TYPES, generate_dataset

CORPUS = [
    {"id": "c1", "text": "Python 3.12 removed distutils from the standard library."},
    {"id": "c2", "text": "Rust 1.75 stabilized async fn in traits."},
    {"id": "c3", "text": "PostgreSQL 16 added logical replication from standby servers."},
    {"id": "c4", "text": "Redis 7.2 introduced client-side caching improvements."},
]

GEN_HEAD = "You write evaluation questions for a RAG system."
GEN_TAIL = 'Reply with JSON only: {"question": "...", "answer": "..."} (answer null if the chunks do not contain it).'
JUDGE_HEAD = "You verify evaluation questions."
JUDGE_TAIL = "Can the question be answered from the SOURCE alone? Reply YES or NO."

SCRIPT = {
    ("fact", "c1"): ("Which module did Python 3.12 remove from the standard library?", "distutils"),
    ("fact", "c2"): ("What did Rust 1.75 stabilize for traits?", "async fn"),
    ("fact", "c3"): ("Where can PostgreSQL 16 replicate logically from?", "standby servers"),
    ("fact", "c4"): ("What did Redis 7.2 improve regarding caching?", "client-side caching"),
    ("comparison", "c1,c2"): ("Compare the removal in Python 3.12 against the stabilization in Rust 1.75.", "One removes, one adds"),
    ("comparison", "c2,c3"): ("How does Rust trait support differ from database replication?", "Different domains"),
    ("comparison", "c3,c4"): ("Contrast standby replication with client caching.", "Replication vs caching"),
    ("multi_hop", "c1,c2"): ("Which language lost distutils and which one gained async traits?", "Python and Rust"),
    ("multi_hop", "c2,c3"): ("Name the two tools shipping async traits and logical standby replication.", "Rust and PostgreSQL"),
    ("multi_hop", "c3,c4"): ("Which servers can feed replicas and what accelerates client reads?", "standby, caching"),
    ("no_answer", "c1"): ("What is the release date of Python 3.12?", None),
    ("no_answer", "c2"): ("Who wrote the Rust 1.75 changelog?", None),
    ("no_answer", "c3"): ("How many contributors worked on PostgreSQL 16?", None),
    ("no_answer", "c4"): ("What does Redis 7.2 cost per month?", None),
}


def scripted(t, ids):
    q, a = SCRIPT[(t, ids)]
    return json.dumps({"question": q, "answer": a})


class Mock:
    """Мок-LLM: відповідає на генерацію за SCRIPT, на перевірку за правилами; усе записує."""

    def __init__(self, gen=scripted, verdict=None):
        self.gen, self.verdict, self.calls = gen, verdict, []

    def __call__(self, prompt):
        self.calls.append(prompt)
        if prompt.startswith(GEN_HEAD):
            t = re.search(r"^TYPE: (\w+)$", prompt, re.M).group(1)
            ids = re.search(r"^CHUNK_IDS: (.*)$", prompt, re.M).group(1)
            r = self.gen(t, ids)
        else:
            assert prompt.startswith(JUDGE_HEAD), prompt
            q = re.search(r"^QUESTION: (.*)$", prompt, re.M).group(1)
            default = "NO" if "ANSWER: (none)" in prompt else "YES"
            r = self.verdict(q, prompt, default) if self.verdict else default
        if isinstance(r, Exception):
            raise r
        return r

    def generation_calls(self):
        return [c for c in self.calls if c.startswith(GEN_HEAD)]

    def judge_calls(self):
        return [c for c in self.calls if c.startswith(JUDGE_HEAD)]


def make_corpus(n):
    return [{"id": f"d{i}", "text": f"Document number {i} talks about topic {i}."} for i in range(1, n + 1)]


def generic_gen(t, ids):
    answer = None if t == "no_answer" else "some answer"
    return json.dumps({"question": f"{t} item about {ids.replace(',', ' plus ')} please", "answer": answer})


# ---------- повний конвеєр ---------------------------------------------------------------------------------


def test_full_pipeline_happy_path():
    llm = Mock()
    result = generate_dataset(CORPUS, llm)
    items = result["items"]
    assert [i["id"] for i in items] == [
        "fact:c1", "fact:c2", "fact:c3", "fact:c4",
        "comparison:c1+c2", "comparison:c2+c3", "comparison:c3+c4",
        "multi_hop:c1+c2", "multi_hop:c2+c3", "multi_hop:c3+c4",
        "no_answer:c1", "no_answer:c2", "no_answer:c3", "no_answer:c4",
    ]
    first = items[0]
    assert first == {"id": "fact:c1", "type": "fact", "question": SCRIPT[("fact", "c1")][0], "answer": "distutils",
                     "sources": ["c1"], "answerable": True}
    assert items[4]["sources"] == ["c1", "c2"] and items[4]["answerable"] is True
    assert items[10]["answer"] is None and items[10]["answerable"] is False and items[10]["sources"] == ["c1"]
    report = result["report"]
    assert report["generated"] == 14
    assert report["rejected"] == {"llm_error": 0, "bad_json": 0, "invalid": 0, "duplicate": 0, "unanswerable": 0, "answerable_leak": 0}
    assert report["by_type"] == {"fact": 4, "comparison": 3, "multi_hop": 3, "no_answer": 4}
    assert report["dropped_by_stratification"] == 0
    assert report["short_types"] == []
    assert len(llm.generation_calls()) == 14 and len(llm.judge_calls()) == 14


def test_types_default_constant():
    assert TYPES == ("fact", "comparison", "multi_hop", "no_answer")


def test_exact_generation_prompts_and_call_order():
    llm = Mock()
    generate_dataset(CORPUS, llm)
    gens = llm.generation_calls()
    assert gens[0] == "\n".join([GEN_HEAD, "TYPE: fact", "CHUNK_IDS: c1", f"CHUNK[c1]: {CORPUS[0]['text']}", GEN_TAIL])
    pair = next(c for c in gens if "TYPE: multi_hop" in c and "CHUNK_IDS: c2,c3" in c)
    assert pair == "\n".join([GEN_HEAD, "TYPE: multi_hop", "CHUNK_IDS: c2,c3", f"CHUNK[c2]: {CORPUS[1]['text']}",
                              f"CHUNK[c3]: {CORPUS[2]['text']}", GEN_TAIL])
    types_in_order = [re.search(r"^TYPE: (\w+)$", c, re.M).group(1) for c in gens]
    assert types_in_order == ["fact"] * 4 + ["comparison"] * 3 + ["multi_hop"] * 3 + ["no_answer"] * 4
    # усі виклики генерації йдуть перед усіма викликами перевірки
    kinds = ["g" if c.startswith(GEN_HEAD) else "j" for c in llm.calls]
    assert kinds == ["g"] * 14 + ["j"] * 14


def test_exact_judge_prompts():
    llm = Mock()
    generate_dataset(CORPUS, llm)
    judges = llm.judge_calls()
    q, a = SCRIPT[("fact", "c2")]
    assert judges[1] == "\n".join([JUDGE_HEAD, f"QUESTION: {q}", f"ANSWER: {a}", f"SOURCE[c2]: {CORPUS[1]['text']}", JUDGE_TAIL])
    qn = SCRIPT[("no_answer", "c3")][0]
    assert judges[12] == "\n".join([JUDGE_HEAD, f"QUESTION: {qn}", "ANSWER: (none)", f"SOURCE[c3]: {CORPUS[2]['text']}", JUDGE_TAIL])
    qc, ac = SCRIPT[("comparison", "c1,c2")]
    assert judges[4] == "\n".join([JUDGE_HEAD, f"QUESTION: {qc}", f"ANSWER: {ac}", f"SOURCE[c1]: {CORPUS[0]['text']}",
                                   f"SOURCE[c2]: {CORPUS[1]['text']}", JUDGE_TAIL])


def test_single_chunk_corpus_has_no_pair_units():
    llm = Mock()
    result = generate_dataset(CORPUS[:1], llm)
    assert [i["id"] for i in result["items"]] == ["fact:c1", "no_answer:c1"]
    assert len(llm.generation_calls()) == 2 and len(llm.judge_calls()) == 2
    assert result["report"]["by_type"] == {"fact": 1, "comparison": 0, "multi_hop": 0, "no_answer": 1}


def test_types_subset_and_order_follow_argument():
    llm = Mock()
    result = generate_dataset(CORPUS, llm, types=("no_answer", "fact"))
    assert [i["type"] for i in result["items"]] == ["no_answer"] * 4 + ["fact"] * 4
    assert list(result["report"]["by_type"]) == ["no_answer", "fact"]
    assert len(llm.generation_calls()) == 8 and len(llm.judge_calls()) == 8
    types_in_order = [re.search(r"^TYPE: (\w+)$", c, re.M).group(1) for c in llm.generation_calls()]
    assert types_in_order == ["no_answer"] * 4 + ["fact"] * 4


def test_corpus_not_mutated_and_result_is_deterministic():
    corpus = copy.deepcopy(CORPUS)
    a = generate_dataset(corpus, Mock(), per_type=2, seed=7)
    b = generate_dataset(corpus, Mock(), per_type=2, seed=7)
    assert corpus == CORPUS
    assert a == b


# ---------- розбір відповіді генерації ---------------------------------------------------------------------


@pytest.mark.parametrize("wrap", ["```json\n{}\n```", "```\n{}\n```", "  \n{}\n  ", "```JSON\n{}\n```", "```json{}```"])
def test_fenced_json_is_accepted(wrap):
    def gen(t, ids):
        return wrap.replace("{}", scripted(t, ids))

    result = generate_dataset(CORPUS, Mock(gen=gen))
    assert len(result["items"]) == 14
    assert result["report"]["rejected"]["bad_json"] == 0


@pytest.mark.parametrize("bad", ["not json at all", "", "[1, 2]", "null", '"text"', "42", "{broken", None, 5, ["q"]])
def test_bad_json_is_counted_and_skipped(bad):
    def gen(t, ids):
        return bad if (t, ids) == ("fact", "c2") else scripted(t, ids)

    llm = Mock(gen=gen)
    result = generate_dataset(CORPUS, llm)
    assert "fact:c2" not in [i["id"] for i in result["items"]]
    assert result["report"]["rejected"]["bad_json"] == 1
    assert result["report"]["generated"] == 13
    assert len(llm.judge_calls()) == 13


@pytest.mark.parametrize("payload", [
    {"answer": "x"},
    {"question": "", "answer": "x"},
    {"question": "   ", "answer": "x"},
    {"question": "???", "answer": "x"},
    {"question": 42, "answer": "x"},
    {"question": ["a"], "answer": "x"},
    {"question": "What is it?", "answer": None},
    {"question": "What is it?"},
    {"question": "What is it?", "answer": ""},
    {"question": "What is it?", "answer": "   \n"},
    {"question": "What is it?", "answer": 5},
])
def test_invalid_fact_candidates(payload):
    def gen(t, ids):
        return json.dumps(payload) if (t, ids) == ("fact", "c3") else scripted(t, ids)

    llm = Mock(gen=gen)
    result = generate_dataset(CORPUS, llm)
    assert "fact:c3" not in [i["id"] for i in result["items"]]
    assert result["report"]["rejected"]["invalid"] == 1
    assert result["report"]["generated"] == 14
    assert len(llm.judge_calls()) == 13


@pytest.mark.parametrize("answer", ["actually there is an answer", "", 0, False, []])
def test_no_answer_candidate_must_have_null_answer(answer):
    def gen(t, ids):
        if (t, ids) == ("no_answer", "c1"):
            return json.dumps({"question": "What is the release date of Python 3.12?", "answer": answer})
        return scripted(t, ids)

    result = generate_dataset(CORPUS, Mock(gen=gen))
    assert "no_answer:c1" not in [i["id"] for i in result["items"]]
    assert result["report"]["rejected"]["invalid"] == 1


def test_generation_exception_is_counted_and_does_not_stop_the_run():
    def gen(t, ids):
        if (t, ids) in (("fact", "c1"), ("multi_hop", "c2,c3")):
            return RuntimeError("provider down")
        return scripted(t, ids)

    llm = Mock(gen=gen)
    result = generate_dataset(CORPUS, llm)
    assert result["report"]["rejected"]["llm_error"] == 2
    assert result["report"]["generated"] == 12
    assert len(result["items"]) == 12
    assert len(llm.judge_calls()) == 12


# ---------- перевірка відповідності джерелу ----------------------------------------------------------------


def test_unanswerable_questions_are_filtered_by_the_judge():
    bad_q = SCRIPT[("fact", "c2")][0]
    bad_pair = SCRIPT[("comparison", "c3,c4")][0]

    def verdict(q, prompt, default):
        return "NO" if q in (bad_q, bad_pair) else default

    result = generate_dataset(CORPUS, Mock(verdict=verdict))
    ids = [i["id"] for i in result["items"]]
    assert "fact:c2" not in ids and "comparison:c3+c4" not in ids
    assert len(ids) == 12
    assert result["report"]["rejected"]["unanswerable"] == 2
    assert result["report"]["by_type"]["fact"] == 3 and result["report"]["by_type"]["comparison"] == 2


@pytest.mark.parametrize("reply, kept", [
    ("YES", True), ("yes", True), ("Yes.", True), ("  YES, it is stated directly\n", True),
    ("NO", False), ("no", False), ("", False), ("maybe", False), ("unclear", False), ("It can be answered", False),
    (None, False), (1, False),
])
def test_judge_reply_for_answerable_types_fail_closed(reply, kept):
    target = SCRIPT[("fact", "c1")][0]

    def verdict(q, prompt, default):
        return reply if q == target else default

    result = generate_dataset(CORPUS, Mock(verdict=verdict))
    assert ("fact:c1" in [i["id"] for i in result["items"]]) is kept
    assert result["report"]["rejected"]["unanswerable"] == (0 if kept else 1)


@pytest.mark.parametrize("reply, kept", [
    ("NO", True), ("no", True), ("No, the chunk does not say.", True),
    ("YES", False), ("yes", False), ("", False), ("maybe", False), ("Perhaps", False), (None, False),
])
def test_judge_reply_for_no_answer_questions(reply, kept):
    target = SCRIPT[("no_answer", "c2")][0]

    def verdict(q, prompt, default):
        return reply if q == target else default

    result = generate_dataset(CORPUS, Mock(verdict=verdict))
    assert ("no_answer:c2" in [i["id"] for i in result["items"]]) is kept
    assert result["report"]["rejected"]["answerable_leak"] == (0 if kept else 1)


def test_judge_exception_rejects_candidate():
    target = SCRIPT[("fact", "c4")][0]

    def verdict(q, prompt, default):
        return TimeoutError("judge timeout") if q == target else default

    result = generate_dataset(CORPUS, Mock(verdict=verdict))
    assert "fact:c4" not in [i["id"] for i in result["items"]]
    assert result["report"]["rejected"]["llm_error"] == 1
    assert len(result["items"]) == 13


# ---------- дедуплікація -----------------------------------------------------------------------------------


def make_dup_gen(questions):
    def gen(t, ids):
        return json.dumps({"question": questions[(t, ids)], "answer": None if t == "no_answer" else "a"})

    return gen


def test_paraphrase_duplicates_are_dropped_before_judging_and_first_wins():
    questions = {
        ("fact", "c1"): "What did Rust 1.75 stabilize for traits?",
        ("fact", "c2"): "what did rust 1.75 stabilize for TRAITS ??",
        ("fact", "c3"): "Where can PostgreSQL 16 replicate logically from?",
        ("fact", "c4"): "Which Redis 7.2 feature speeds up caching?",
    }
    llm = Mock(gen=make_dup_gen(questions))
    result = generate_dataset(CORPUS, llm, types=("fact",))
    assert [i["id"] for i in result["items"]] == ["fact:c1", "fact:c3", "fact:c4"]
    assert result["report"]["rejected"]["duplicate"] == 1
    assert result["report"]["generated"] == 4
    judged = [re.search(r"^QUESTION: (.*)$", c, re.M).group(1) for c in llm.judge_calls()]
    assert len(judged) == 3 and questions[("fact", "c2")] not in judged


def test_duplicate_threshold_is_inclusive_and_configurable():
    questions = {
        ("fact", "c1"): "alpha beta gamma delta",
        ("fact", "c2"): "alpha beta gamma delta epsilon",   # Jaccard = 4/5 = 0.8
        ("fact", "c3"): "totally unrelated words appear here",
        ("fact", "c4"): "another question about cats",
    }
    at = generate_dataset(CORPUS, Mock(gen=make_dup_gen(questions)), types=("fact",), dedup_threshold=0.8)
    assert [i["id"] for i in at["items"]] == ["fact:c1", "fact:c3", "fact:c4"]
    above = generate_dataset(CORPUS, Mock(gen=make_dup_gen(questions)), types=("fact",), dedup_threshold=0.81)
    assert [i["id"] for i in above["items"]] == ["fact:c1", "fact:c2", "fact:c3", "fact:c4"]



def test_default_threshold_keeps_similar_but_different_questions():
    questions = {
        ("fact", "c1"): "alpha beta gamma delta",
        ("fact", "c2"): "alpha beta gamma epsilon zeta",   # 3/6 = 0.5
        ("fact", "c3"): "one two three four five",
        ("fact", "c4"): "red green blue black white",
    }
    result = generate_dataset(CORPUS, Mock(gen=make_dup_gen(questions)), types=("fact",))
    assert len(result["items"]) == 4 and result["report"]["rejected"]["duplicate"] == 0


def test_duplicates_are_detected_across_types_and_earlier_type_wins():
    questions = {
        ("fact", "c1"): "What is the release date of Python 3.12?",
        ("fact", "c2"): "Which keyword did Rust 1.75 stabilize in traits?",
        ("no_answer", "c1"): "what is the release date of python 3.12",
        ("no_answer", "c2"): "Who maintains the Rust 1.75 changelog every week?",
    }
    result = generate_dataset(CORPUS[:2], Mock(gen=make_dup_gen(questions)), types=("fact", "no_answer"))
    assert [i["id"] for i in result["items"]] == ["fact:c1", "fact:c2", "no_answer:c2"]
    assert result["report"]["rejected"]["duplicate"] == 1


def test_duplicate_of_a_later_rejected_candidate_is_still_a_duplicate():
    questions = {
        ("fact", "c1"): "What did Rust 1.75 stabilize for traits?",
        ("fact", "c2"): "What did Rust 1.75 stabilize for traits?",
    }

    def verdict(q, prompt, default):
        return "NO"  # перший кандидат не пройде перевірку

    llm = Mock(gen=make_dup_gen(questions), verdict=verdict)
    result = generate_dataset(CORPUS[:2], llm, types=("fact",))
    assert result["items"] == []
    assert result["report"]["rejected"]["duplicate"] == 1
    assert result["report"]["rejected"]["unanswerable"] == 1
    assert len(llm.judge_calls()) == 1


def test_invalid_candidates_do_not_take_part_in_dedup():
    def gen(t, ids):
        if ids == "c1":
            return json.dumps({"question": "What did Rust 1.75 stabilize for traits?", "answer": None})  # invalid
        return json.dumps({"question": "What did Rust 1.75 stabilize for traits?", "answer": "async fn"})

    result = generate_dataset(CORPUS[:2], Mock(gen=gen), types=("fact",))
    assert [i["id"] for i in result["items"]] == ["fact:c2"]
    assert result["report"]["rejected"]["invalid"] == 1 and result["report"]["rejected"]["duplicate"] == 0


# ---------- стратифікація ----------------------------------------------------------------------------------


def candidate_ids(corpus, t):
    return sorted(f"{t}:{c['id']}" for c in corpus)


def test_per_type_limits_every_type_and_reports_dropped():
    corpus = make_corpus(6)
    result = generate_dataset(corpus, Mock(gen=generic_gen), per_type=3, seed=5)
    by_type = result["report"]["by_type"]
    assert by_type == {"fact": 3, "comparison": 3, "multi_hop": 3, "no_answer": 3}
    assert result["report"]["dropped_by_stratification"] == 3 + 2 + 2 + 3
    assert result["report"]["short_types"] == []
    ids = [i["id"] for i in result["items"]]
    assert ids == sorted(ids, key=lambda x: (TYPES.index(x.split(":")[0]), x))
    assert len(result["items"]) == 12


@pytest.mark.parametrize("seed", [0, 1, 7, 42])
def test_sampling_is_exactly_random_sample_of_sorted_ids(seed):
    corpus = make_corpus(6)
    result = generate_dataset(corpus, Mock(gen=generic_gen), types=("fact",), per_type=3, seed=seed)
    expected = sorted(random.Random(seed).sample(candidate_ids(corpus, "fact"), 3))
    assert [i["id"] for i in result["items"]] == expected


def test_different_seeds_give_different_samples():
    corpus = make_corpus(6)
    seen = set()
    for seed in range(12):
        r = generate_dataset(corpus, Mock(gen=generic_gen), types=("fact",), per_type=3, seed=seed)
        seen.add(tuple(i["id"] for i in r["items"]))
    assert len(seen) > 1


def test_short_types_when_fewer_candidates_than_per_type():
    corpus = make_corpus(3)
    result = generate_dataset(corpus, Mock(gen=generic_gen), per_type=3)
    assert result["report"]["by_type"] == {"fact": 3, "comparison": 2, "multi_hop": 2, "no_answer": 3}
    assert result["report"]["short_types"] == ["comparison", "multi_hop"]
    assert result["report"]["dropped_by_stratification"] == 0


def test_per_type_larger_than_everything_changes_nothing():
    corpus = make_corpus(3)
    full = generate_dataset(corpus, Mock(gen=generic_gen))
    limited = generate_dataset(corpus, Mock(gen=generic_gen), per_type=50)
    assert full["items"] == limited["items"]
    assert full["report"]["short_types"] == []
    assert set(limited["report"]["short_types"]) == {"fact", "comparison", "multi_hop", "no_answer"}


def test_stratification_happens_after_filtering():
    corpus = make_corpus(4)

    def verdict(q, prompt, default):
        return "NO" if "d1" in q or "d2" in q else default

    result = generate_dataset(corpus, Mock(gen=generic_gen, verdict=verdict), types=("fact",), per_type=3, seed=1)
    ids = [i["id"] for i in result["items"]]
    assert ids == ["fact:d3", "fact:d4"]
    assert result["report"]["dropped_by_stratification"] == 0
    assert result["report"]["short_types"] == ["fact"]


# ---------- валідація входу --------------------------------------------------------------------------------


@pytest.mark.parametrize("corpus", [
    [], None, "text", [{"id": "a"}], [{"text": "x"}], [{"id": "", "text": "x"}], [{"id": 1, "text": "x"}], [{"id": "a", "text": 5}],
    [{"id": "a", "text": "x"}, {"id": "a", "text": "y"}], ["a"],
])
def test_bad_corpus(corpus):
    llm = Mock()
    with pytest.raises(ValueError):
        generate_dataset(corpus, llm)
    assert llm.calls == []


@pytest.mark.parametrize("kw", [
    dict(types=()), dict(types=("fact", "fact")), dict(types=("fact", "joke")), dict(types=("FACT",)),
    dict(per_type=0), dict(per_type=-1), dict(per_type=True), dict(per_type="3"), dict(per_type=1.5),
    dict(dedup_threshold=0), dict(dedup_threshold=1.5), dict(dedup_threshold=-0.1), dict(dedup_threshold=True),
])
def test_bad_options_fail_before_any_llm_call(kw):
    llm = Mock()
    with pytest.raises(ValueError):
        generate_dataset(CORPUS, llm, **kw)
    assert llm.calls == []


def test_threshold_one_means_only_identical_word_sets_are_duplicates():
    questions = {
        ("fact", "c1"): "alpha beta gamma",
        ("fact", "c2"): "Gamma, BETA alpha!",
        ("fact", "c3"): "alpha beta gamma delta",
        ("fact", "c4"): "something else entirely",
    }
    result = generate_dataset(CORPUS, Mock(gen=make_dup_gen(questions)), types=("fact",), dedup_threshold=1)
    assert [i["id"] for i in result["items"]] == ["fact:c1", "fact:c3", "fact:c4"]
