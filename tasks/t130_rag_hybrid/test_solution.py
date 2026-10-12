import math

import pytest

from solution import BM25, HybridIndex, evaluate_ranking, rerank, rewrite_query, rrf, tokenize

CONCEPTS = [("car", "automobile", "vehicle"), ("refund", "reimbursement"), ("password", "passcode"), ("invoice", "bill")]


def concept_embed(text):
    """Підроблена «семантична» модель: синоніми з однієї групи дають одну вісь."""
    words = tokenize(text, drop_stopwords=False)
    vec = [float(sum(1 for w in words if w in group)) for group in CONCEPTS]
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


DOCS = {
    "rental": "Our vehicle rental policy: you can cancel a car booking free of charge.",
    "refunds": "Reimbursement is processed within 14 days.",
    "locked": "Passcode reset instructions for locked accounts.",
    "gateway": "ERR-4012 means the payment gateway timed out; retry in a minute.",
    "billing": "Invoice and bill history is in the billing page.",
}
DATASET = [
    {"question": "automobile cancellation", "relevant": {"rental"}},
    {"question": "refund", "relevant": {"refunds"}},
    {"question": "ERR-4012", "relevant": {"gateway"}},
    {"question": "passcode", "relevant": {"locked"}},
]


@pytest.fixture
def index():
    idx = HybridIndex(concept_embed)
    for doc_id, text in DOCS.items():
        idx.add(doc_id, text)
    return idx


# ---------- tokenize and BM25 -------------------------------------------------------------------------


def test_tokenize():
    assert tokenize("How do I reset the Password? ERR-4012!") == ["reset", "password", "err", "4012"]
    assert tokenize("How do I reset", drop_stopwords=False) == ["how", "do", "i", "reset"]
    assert tokenize("") == [] and tokenize("the a an") == []


def test_bm25_known_values():
    bm = BM25(["apple banana", "apple apple cherry", "banana cherry date"])
    assert bm.scores("apple") == pytest.approx([0.5295815540797021, 0.6454985466035854, 0.0])
    assert bm.scores("apple cherry") == pytest.approx([0.5295815540797021, 1.0904723967770629, 0.4449738501734775])
    assert bm.scores("zzz") == [0.0, 0.0, 0.0]


def test_bm25_parameters_and_stopwords_in_documents():
    assert BM25(["a b c d", "a"], k1=1.2, b=0.5).scores("b a") == pytest.approx([0.5446156418685285, 0.0])


def test_bm25_uses_unique_query_tokens_and_rewards_rare_terms():
    bm = BM25(["common rare", "common", "common other"])
    assert bm.scores("rare rare rare") == bm.scores("rare")
    assert bm.scores("rare")[0] > bm.scores("common")[0]


def test_bm25_empty_inputs():
    assert BM25([]).scores("x") == []
    assert BM25(["the a", ""]).scores("x") == [0.0, 0.0]


# ---------- rrf ------------------------------------------------------------------------------------------


def test_rrf_scores_and_order():
    got = rrf([["a", "b", "c"], ["b", "c", "d"]])
    assert [d for d, _ in got] == ["b", "c", "a", "d"]
    scores = dict(got)
    assert scores["a"] == pytest.approx(1 / 61) and scores["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["d"] == pytest.approx(1 / 63)


def test_rrf_custom_k_ties_and_duplicates():
    assert rrf([["x", "y"]], k=1) == [("x", 0.5), ("y", 1 / 3)]
    assert [d for d, _ in rrf([["b"], ["a"]])] == ["a", "b"], "рівні score за id"
    assert [d for d, _ in rrf([[10], [9]])] == [9, 10], "числові id порівнюються як числа"
    dup = dict(rrf([["a", "a", "b"]]))
    assert dup["a"] == pytest.approx(1 / 61) and dup["b"] == pytest.approx(1 / 63)
    assert rrf([]) == [] and rrf([[], []]) == []


# ---------- HybridIndex -------------------------------------------------------------------------------------


def test_bm25_finds_exact_terms_but_not_synonyms(index):
    assert index.search("ERR-4012", method="bm25") == ["gateway"]
    assert index.search("automobile", method="bm25") == []


def test_vector_finds_synonyms_but_not_rare_codes(index):
    assert index.search("automobile", method="vector") == ["rental"]
    assert index.search("refund", method="vector") == ["refunds"]
    assert index.search("ERR-4012", method="vector") == []


def test_hybrid_gets_both(index):
    assert index.search("ERR-4012") == ["gateway"]
    assert index.search("automobile") == ["rental"]
    assert index.search("passcode") == ["locked"]


def test_documents_found_by_both_methods_beat_those_found_by_one():
    idx = HybridIndex(concept_embed)
    idx.add("d1", "car")
    idx.add("d2", "automobile vehicle")
    idx.add("d3", "car repair car shop")
    assert idx.search("car", method="bm25") == ["d1", "d3"]
    assert idx.search("car", method="vector") == ["d1", "d2", "d3"]
    assert idx.search("car", method="hybrid") == ["d1", "d3", "d2"], "d3 є в обох списках, d2 лише у векторному"


def test_pool_and_k_limit_results(index):
    idx = HybridIndex(concept_embed)
    for i in range(5):
        idx.add(i, "car")
    assert idx.search("car", k=2, method="vector") == [0, 1]
    assert idx.search("car", k=10, method="vector", pool=3) == [0, 1, 2]
    assert idx.search("car", k=10, method="bm25", pool=4) == [0, 1, 2, 3]
    assert idx.search("car", k=10, pool=2) == [0, 1]


def test_stopword_only_query_finds_nothing(index):
    assert index.search("how do I") == [] and index.search("") == []


def test_index_validation(index):
    with pytest.raises(ValueError):
        index.add("rental", "again")
    with pytest.raises(ValueError):
        index.search("x", method="magic")
    with pytest.raises(ValueError):
        index.search("x", k=0)


def test_metrics_improve_with_hybrid(index):
    bm25 = evaluate_ranking(lambda q: index.search(q, method="bm25"), DATASET)
    vector = evaluate_ranking(lambda q: index.search(q, method="vector"), DATASET)
    hybrid = evaluate_ranking(lambda q: index.search(q, method="hybrid"), DATASET)
    assert bm25 == {"recall": 0.5, "mrr": 0.5} and vector == {"recall": 0.75, "mrr": 0.75}
    assert hybrid == {"recall": 1.0, "mrr": 1.0}


# ---------- evaluate_ranking --------------------------------------------------------------------------------


def test_evaluate_ranking_positions_and_cutoff():
    data = [{"question": "q1", "relevant": {"x"}}, {"question": "q2", "relevant": {"y"}}, {"question": "q3", "relevant": {"z"}}]
    results = {"q1": ["a", "x"], "q2": ["a", "b", "c", "y"], "q3": []}
    assert evaluate_ranking(lambda q: results[q], data, k=3) == {"recall": 0.3333, "mrr": 0.1667}
    assert evaluate_ranking(lambda q: results[q], data, k=4) == {"recall": 0.6667, "mrr": 0.2500}
    with pytest.raises(ValueError):
        evaluate_ranking(lambda q: [], [])


# ---------- rewrite_query -----------------------------------------------------------------------------------


HISTORY = [{"role": "user", "content": "Tell me about the Pro plan"}, {"role": "assistant", "content": "It costs $20."}]


def test_rewrite_prompt_and_cleanup():
    seen = []

    def llm(prompt):
        seen.append(prompt)
        return '\n  "Pro plan price per month"  \nignored second line'

    assert rewrite_query(llm, "and per year?", HISTORY) == "Pro plan price per month"
    assert seen[0] == ("Rewrite the last question as a standalone search query. Reply with the query only.\n"
                       "History:\nuser: Tell me about the Pro plan\nassistant: It costs $20.\nQuestion: and per year?\nQuery:")


def test_rewrite_without_history_and_single_quotes():
    prompts = []

    def llm(prompt):
        prompts.append(prompt)
        return "'refund policy'"

    assert rewrite_query(llm, "refunds?", []) == "refund policy"
    assert prompts[0].splitlines()[1:3] == ["History:", "Question: refunds?"]


@pytest.mark.parametrize("reply", ["", "   \n  ", "x" * 201, '""'])
def test_rewrite_falls_back_to_the_original_question(reply):
    assert rewrite_query(lambda p: reply, "original?", HISTORY) == "original?"


def test_rewrite_survives_llm_errors():
    def broken(prompt):
        raise ConnectionError("down")

    assert rewrite_query(broken, "original?", HISTORY) == "original?"
    assert rewrite_query(lambda p: "y" * 200, "q", []) == "y" * 200


# ---------- rerank ---------------------------------------------------------------------------------------------


def test_rerank_orders_by_score_and_is_stable():
    cands = [("a", "one"), ("b", "three words here"), ("c", "two words"), ("d", "also two")]
    calls = []

    def scorer(query, text):
        calls.append((query, text))
        return len(text.split())

    assert rerank(scorer, "q", cands) == ["b", "c", "d", "a"]
    assert {c[0] for c in calls} == {"q"} and {c[1] for c in calls} == {t for _, t in cands}
    assert rerank(scorer, "q", cands, top=2) == ["b", "c"]
    assert rerank(scorer, "q", []) == []
    assert rerank(lambda q, t: 0, "q", cands) == ["a", "b", "c", "d"]
