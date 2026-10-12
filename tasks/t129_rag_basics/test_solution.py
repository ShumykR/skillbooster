import hashlib
import math

import pytest

from solution import VectorIndex, build_prompt, check_citations, chunk_words, cosine, embed, evaluate, extract_citations

DOCS = {
    "refunds": "Refunds are issued within 14 days of purchase. To request a refund contact support with your order number.",
    "shipping": "Standard shipping takes 3 to 5 business days. Express shipping delivers the next day for an extra fee.",
    "passwords": "Reset your password from the login page by choosing forgot password and following the email link.",
    "billing": "Invoices are sent monthly. You can download invoices as PDF from the billing settings page.",
}
DATASET = [
    {"question": "how do I get a refund", "relevant": {"refunds"}},
    {"question": "how long does shipping take", "relevant": {"shipping"}},
    {"question": "I forgot my password", "relevant": {"passwords"}},
    {"question": "where to download invoices pdf", "relevant": {"billing"}},
]


@pytest.fixture
def index():
    idx = VectorIndex()
    for source, text in DOCS.items():
        idx.add_document(source, text)
    return idx


def words(n):
    return " ".join(f"w{i}" for i in range(n))


# ---------- chunk_words ---------------------------------------------------------------


@pytest.mark.parametrize("n, size, overlap, starts", [
    (25, 10, 2, [0, 8, 16]), (10, 10, 2, [0]), (18, 10, 2, [0, 8]), (17, 10, 2, [0, 8]), (19, 10, 2, [0, 8, 16]),
    (9, 10, 2, [0]), (6, 2, 0, [0, 2, 4]), (5, 1, 0, [0, 1, 2, 3, 4])])
def test_chunk_starts(n, size, overlap, starts):
    assert [c["start"] for c in chunk_words(words(n), size, overlap)] == starts


def test_chunk_content_and_overlap():
    chunks = chunk_words(words(12), 5, 2)
    assert [c["text"] for c in chunks] == ["w0 w1 w2 w3 w4", "w3 w4 w5 w6 w7", "w6 w7 w8 w9 w10", "w9 w10 w11"]
    assert chunk_words("", 5, 1) == [] and chunk_words("   \n ", 5, 1) == []


def test_chunk_whitespace_is_normalized():
    assert chunk_words("a  b\n\tc", 10, 0)[0]["text"] == "a b c"


@pytest.mark.parametrize("size, overlap", [(0, 0), (-1, 0), (5, 5), (5, -1), (5, 6)])
def test_chunk_validation(size, overlap):
    with pytest.raises(ValueError):
        chunk_words("a b c", size, overlap)


# ---------- embeddings ----------------------------------------------------------------------


def test_single_token_vector_follows_the_documented_hash():
    h = int(hashlib.md5(b"hello").hexdigest(), 16)
    vec = embed("Hello!", dim=64)
    nonzero = [(i, x) for i, x in enumerate(vec) if x]
    assert nonzero == [(h % 64, 1.0 if (h >> 64) & 1 == 0 else -1.0)]


def test_vectors_are_unit_length_and_deterministic():
    v = embed("The quick brown fox jumps over the lazy dog")
    assert len(v) == 256 and math.isclose(sum(x * x for x in v), 1.0)
    assert v == embed("the QUICK brown fox jumps over the lazy dog")
    assert len(embed("x", dim=32)) == 32


def test_empty_text_is_a_zero_vector():
    assert embed("") == [0.0] * 256 and embed("!!! ...") == [0.0] * 256
    assert cosine(embed(""), embed("anything")) == 0.0


def test_cosine():
    a = embed("refund policy for orders")
    assert cosine(a, a) == pytest.approx(1.0)
    assert cosine(a, embed("refund policy")) > cosine(a, embed("shipping carriers"))
    with pytest.raises(ValueError):
        cosine([1.0], [1.0, 2.0])


# ---------- index ---------------------------------------------------------------------------------


def test_chunk_ids_are_global_and_sources_kept():
    idx = VectorIndex()
    assert idx.add_document("a", words(25), size=10, overlap=2) == 3
    assert idx.add_document("b", words(5), size=10, overlap=2) == 1
    hits = idx.search("w0 w1 w2", k=10)
    assert sorted(h["chunk"]["id"] for h in hits) == sorted({h["chunk"]["id"] for h in hits})
    assert {h["chunk"]["source"] for h in hits} == {"a", "b"}
    assert max(h["chunk"]["id"] for h in hits) == 3


def test_search_finds_the_right_document_first(index):
    for item in DATASET:
        top = index.search(item["question"], k=1)[0]
        assert top["chunk"]["source"] in item["relevant"]


def test_search_result_shape_order_and_limits(index):
    hits = index.search("shipping days", k=3)
    assert hits[0]["chunk"]["source"] == "shipping"
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)
    assert all(h["score"] == round(h["score"], 4) and h["score"] > 0 for h in hits)
    assert len(index.search("shipping days", k=1)) == 1
    assert all(h["score"] > 0.3 for h in index.search("shipping days", k=3, min_score=0.3))
    assert index.search("zzzzzz qqqqqq") == [], "жодного спільного слова"


def test_ties_are_broken_by_chunk_id():
    idx = VectorIndex()
    idx.add_document("first", "alpha beta")
    idx.add_document("second", "alpha beta")
    assert [h["chunk"]["source"] for h in idx.search("alpha beta")] == ["first", "second"]


def test_empty_index_and_invalid_k():
    assert VectorIndex().search("anything") == []
    with pytest.raises(ValueError):
        VectorIndex().search("x", k=0)


# ---------- prompt and citations ------------------------------------------------------------------------


def test_build_prompt_format():
    hits = [{"score": 0.9, "chunk": {"source": "refunds", "text": "Refunds take 14 days."}},
            {"score": 0.5, "chunk": {"source": "billing", "text": "Invoices are monthly."}}]
    assert build_prompt("How long?", hits) == (
        'Answer using only the sources below. Cite sources as [1], [2]. If the answer is not in the sources, say "I don\'t know".\n'
        "\n"
        "[1] (refunds) Refunds take 14 days.\n"
        "[2] (billing) Invoices are monthly.\n"
        "\n"
        "Question: How long?")


def test_build_prompt_without_sources():
    assert build_prompt("Q?", []).endswith('"I don\'t know".\n\n\nQuestion: Q?')


@pytest.mark.parametrize("answer, cited", [
    ("Через 14 днів [1].", [1]), ("[2] і [1], знову [2]", [1, 2]), ("немає цитат", []), ("[a] [] [1.5] (3)", []), ("[10] та [3]", [3, 10]),
    ("[01]", [1])])
def test_extract_citations(answer, cited):
    assert extract_citations(answer) == cited


def test_check_citations_flags_invented_sources():
    assert check_citations("Так [1][2] і [5], а ще [0].", 3) == {"valid": [1, 2], "invalid": [0, 5]}
    assert check_citations("без цитат", 3) == {"valid": [], "invalid": []}
    assert check_citations("[1]", 0) == {"valid": [], "invalid": [1]}


# ---------- evaluation -------------------------------------------------------------------------------------


def test_evaluate_on_the_reference_set(index):
    r = evaluate(index, DATASET, k=3)
    assert r == {"recall": 1.0, "precision": 0.875, "mrr": 1.0}
    assert evaluate(index, DATASET, k=1) == {"recall": 1.0, "precision": 1.0, "mrr": 1.0}


def test_evaluate_penalises_misses_and_late_hits(index):
    wrong = [{"question": "how do I get a refund", "relevant": {"billing"}}]
    r = evaluate(index, wrong, k=1)
    assert r == {"recall": 0.0, "precision": 0.0, "mrr": 0.0}
    mixed = DATASET[:1] + wrong
    assert evaluate(index, mixed, k=1)["recall"] == 0.5


def test_evaluate_rank_of_the_first_relevant_hit(index):
    q = [{"question": "shipping days", "relevant": {"refunds"}}]
    assert [h["chunk"]["source"] for h in index.search("shipping days", k=3)] == ["shipping", "refunds"]
    assert evaluate(index, q, k=3) == {"recall": 1.0, "precision": 0.5, "mrr": 0.5}
    assert evaluate(index, q, k=1) == {"recall": 0.0, "precision": 0.0, "mrr": 0.0}


def test_evaluate_no_hits_counts_as_zero(index):
    r = evaluate(index, [{"question": "zzzzz qqqqq", "relevant": {"refunds"}}], k=3)
    assert r == {"recall": 0.0, "precision": 0.0, "mrr": 0.0}


def test_evaluate_empty_dataset(index):
    with pytest.raises(ValueError):
        evaluate(index, [])
