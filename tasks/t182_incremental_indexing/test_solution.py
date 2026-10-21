import hashlib

import pytest

from solution import IncrementalIndex, content_hash, split_chunks

WORDS = ["cat", "dog", "fish", "bird"]


class Embedder:
    """Мок-embeddings: вектор це кількість слів зі словника; рахує виклики. scale/shift відрізняють «моделі»."""

    def __init__(self, scale=1.0, words=WORDS, fail_on=None):
        self.scale = scale
        self.words = words
        self.fail_on = fail_on
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("embedding service down")
        low = text.lower()
        return [self.scale * low.count(w) for w in self.words]


def make(**kw):
    emb = Embedder(**kw)
    return IncrementalIndex(emb), emb


# --- split_chunks / content_hash ---------------------------------------------------------------

def test_split_chunks():
    assert split_chunks("one\n\ntwo\n  \n\nthree") == ["one", "two", "three"]
    assert split_chunks("  a b  \n\n\n\n  c  ") == ["a b", "c"]
    assert split_chunks("") == [] and split_chunks("\n\n   \n\n") == []
    assert split_chunks("same\n\nsame") == ["same", "same"]       # дублікати й порядок зберігаються
    assert split_chunks("line1\nline2\n\nnext") == ["line1\nline2", "next"]


def test_content_hash():
    assert content_hash("abc") == hashlib.sha256(b"abc").hexdigest()
    assert content_hash("Київ") == hashlib.sha256("Київ".encode("utf-8")).hexdigest()
    assert content_hash("a") != content_hash("A")


# --- upsert: інкрементальність -----------------------------------------------------------------

def test_first_upsert_embeds_each_chunk_once_in_order():
    idx, emb = make()
    res = idx.upsert("d1", "cat story\n\ndog story\n\nfish story", ["alice"])
    assert res == {"added": 3, "removed": 0, "unchanged": 0}
    assert emb.calls == ["cat story", "dog story", "fish story"]
    assert idx.stats() == {"docs": 1, "chunks": 3, "model": "v1"}


def test_duplicate_paragraphs_inside_one_document_are_one_chunk():
    idx, emb = make()
    res = idx.upsert("d1", "cat\n\ncat\n\ndog", ["alice"])
    assert res == {"added": 2, "removed": 0, "unchanged": 0}
    assert emb.calls == ["cat", "dog"]
    assert idx.stats()["chunks"] == 2


def test_unchanged_text_calls_embed_zero_times():
    idx, emb = make()
    idx.upsert("d1", "cat\n\ndog", ["alice"])
    emb.calls.clear()
    assert idx.upsert("d1", "cat\n\ndog", ["alice"]) == {"added": 0, "removed": 0, "unchanged": 2}
    assert emb.calls == []


def test_changed_paragraph_only_that_chunk_is_reembedded_and_old_one_disappears():
    idx, emb = make()
    idx.upsert("d1", "cat tale\n\ndog tale\n\nfish tale", ["alice"])
    emb.calls.clear()
    res = idx.upsert("d1", "cat tale\n\ndog tale CHANGED\n\nfish tale", ["alice"])
    assert res == {"added": 1, "removed": 1, "unchanged": 2}
    assert emb.calls == ["dog tale CHANGED"]
    texts = [r["chunk"] for r in idx.search("dog", ["alice"], k=10)]
    assert texts == ["dog tale CHANGED"]
    assert idx.stats()["chunks"] == 3


def test_reordering_and_insert_at_start_do_not_reembed_the_rest():
    idx, emb = make()
    idx.upsert("d1", "cat tale\n\ndog tale\n\nfish tale", ["alice"])
    emb.calls.clear()
    assert idx.upsert("d1", "fish tale\n\ncat tale\n\ndog tale", ["alice"]) == {"added": 0, "removed": 0, "unchanged": 3}
    assert emb.calls == []
    res = idx.upsert("d1", "bird intro\n\nfish tale\n\ncat tale\n\ndog tale", ["alice"])
    assert res == {"added": 1, "removed": 0, "unchanged": 3}
    assert emb.calls == ["bird intro"]


def test_removing_paragraphs_and_emptying_the_document():
    idx, emb = make()
    idx.upsert("d1", "cat\n\ndog\n\nfish", ["alice"])
    assert idx.upsert("d1", "cat", ["alice"]) == {"added": 0, "removed": 2, "unchanged": 1}
    assert idx.stats()["chunks"] == 1
    assert idx.upsert("d1", "\n\n  \n", ["alice"]) == {"added": 0, "removed": 1, "unchanged": 0}
    assert idx.stats() == {"docs": 1, "chunks": 0, "model": "v1"}
    assert idx.search("cat dog", ["alice"]) == []


def test_same_paragraph_in_different_documents_are_separate_chunks():
    idx, emb = make()
    idx.upsert("d1", "cat tale", ["alice"])
    res = idx.upsert("d2", "cat tale", ["bob"])
    assert res == {"added": 1, "removed": 0, "unchanged": 0}
    assert emb.calls == ["cat tale", "cat tale"]
    assert idx.stats()["chunks"] == 2
    assert {r["doc_id"] for r in idx.search("cat", ["alice", "bob"])} == {"d1", "d2"}
    assert idx.delete("d1") == 1
    assert [r["doc_id"] for r in idx.search("cat", ["alice", "bob"])] == ["d2"]


# --- upsert: валідація та атомарність ----------------------------------------------------------

@pytest.mark.parametrize("acl", [None, "alice", b"alice", 5, [1], [""], [None], {"a": 1}.items(), ["ok", ""]])
def test_bad_acl_is_rejected_and_nothing_changes(acl):
    idx, emb = make()
    with pytest.raises(ValueError):
        idx.upsert("d1", "cat", acl)
    assert idx.stats()["docs"] == 0 and emb.calls == []


@pytest.mark.parametrize("doc_id, text", [("", "x"), (None, "x"), (5, "x"), ("d", None), ("d", 5), ("d", b"x")])
def test_bad_doc_id_or_text(doc_id, text):
    idx, _ = make()
    with pytest.raises(ValueError):
        idx.upsert(doc_id, text, ["a"])


@pytest.mark.parametrize("acl", [["alice"], ("alice",), {"alice"}, frozenset({"alice"})])
def test_acl_accepts_collections(acl):
    idx, _ = make()
    idx.upsert("d1", "cat", acl)
    assert len(idx.search("cat", ["alice"])) == 1


def test_empty_acl_means_nobody_can_read():
    idx, _ = make()
    idx.upsert("d1", "cat", [])
    assert idx.search("cat", ["alice", "admins", "everyone"]) == []
    assert idx.stats()["chunks"] == 1


def test_embed_failure_is_atomic_for_text_and_acl():
    idx, emb = make(fail_on="BOOM")
    idx.upsert("d1", "cat tale\n\ndog tale", ["alice"])
    before = idx.search("cat dog", ["alice", "bob"], k=10)
    with pytest.raises(RuntimeError):
        idx.upsert("d1", "cat tale\n\nfish tale\n\nBOOM bird", ["bob"])      # новий acl теж не має застосуватись
    assert idx.stats() == {"docs": 1, "chunks": 2, "model": "v1"}
    assert idx.search("cat dog", ["alice", "bob"], k=10) == before
    assert idx.search("cat", ["bob"]) == []                                   # bob так і не отримав доступ
    with pytest.raises(RuntimeError):
        idx.upsert("new", "BOOM cat", ["alice"])
    assert idx.stats()["docs"] == 1                                           # новий документ не зʼявився


def test_acl_change_applies_without_embedding_and_revocation_is_immediate():
    idx, emb = make()
    idx.upsert("d1", "cat tale", ["alice"])
    emb.calls.clear()
    assert idx.upsert("d1", "cat tale", ["bob"]) == {"added": 0, "removed": 0, "unchanged": 1}
    assert emb.calls == []
    assert idx.search("cat", ["alice"]) == []
    assert len(idx.search("cat", ["bob"])) == 1


# --- delete ------------------------------------------------------------------------------------

def test_delete():
    idx, _ = make()
    idx.upsert("d1", "cat\n\ndog\n\ncat", ["alice"])
    assert idx.delete("d1") == 2
    assert idx.delete("d1") == 0 and idx.delete("missing") == 0
    assert idx.stats() == {"docs": 0, "chunks": 0, "model": "v1"}
    assert idx.search("cat dog", ["alice"]) == []


# --- search ------------------------------------------------------------------------------------

def test_search_result_shape_score_is_dot_product_and_only_positive():
    idx, _ = make()
    idx.upsert("d1", "cat cat dog\n\nfish only\n\nnothing here", ["alice"])
    res = idx.search("cat dog dog", ["alice"], k=10)
    assert res == [{"doc_id": "d1", "chunk": "cat cat dog", "score": 2 * 1 + 1 * 2}]   # (2,1,0,0)·(1,2,0,0)
    assert idx.search("bird", ["alice"]) == []


def test_acl_filter_is_applied_before_top_k():
    idx, _ = make()
    idx.upsert("secret", "cat cat cat cat", ["boss"])
    idx.upsert("a", "cat cat", ["alice"])
    idx.upsert("b", "cat", ["alice"])
    idx.upsert("c", "cat dog", ["alice"])
    res = idx.search("cat", ["alice"], k=2)
    assert [r["doc_id"] for r in res] == ["a", "b"]          # b і c мають рівний score 1: за doc_id
    assert all(r["doc_id"] != "secret" for r in res)
    assert [r["doc_id"] for r in idx.search("cat", ["boss", "alice"], k=2)] == ["secret", "a"]


def test_group_principals_any_match_is_enough():
    idx, _ = make()
    idx.upsert("d1", "cat", ["team-a", "alice"])
    idx.upsert("d2", "cat cat", ["team-b"])
    assert [r["doc_id"] for r in idx.search("cat", ["bob", "team-b"])] == ["d2"]
    assert [r["doc_id"] for r in idx.search("cat", ["bob", "team-a", "team-b"])] == ["d2", "d1"]
    assert idx.search("cat", []) == []
    assert idx.search("cat", set()) == []


def test_ties_are_broken_by_doc_id_then_chunk_position_following_current_text():
    idx, _ = make()
    idx.upsert("b", "cat first\n\ncat second", ["u"])
    idx.upsert("a", "cat only", ["u"])
    got = [(r["doc_id"], r["chunk"]) for r in idx.search("cat", ["u"], k=10)]
    assert got == [("a", "cat only"), ("b", "cat first"), ("b", "cat second")]
    idx.upsert("b", "cat second\n\ncat first", ["u"])                            # позиція береться з ПОТОЧНОГО тексту
    got = [(r["doc_id"], r["chunk"]) for r in idx.search("cat", ["u"], k=10)]
    assert got == [("a", "cat only"), ("b", "cat second"), ("b", "cat first")]


def test_search_orders_by_score_desc():
    idx, _ = make()
    idx.upsert("d1", "cat\n\ncat cat cat\n\ncat cat", ["u"])
    assert [r["chunk"] for r in idx.search("cat", ["u"], k=3)] == ["cat cat cat", "cat cat", "cat"]
    assert [r["score"] for r in idx.search("cat", ["u"], k=2)] == [3, 2]


def test_search_embeds_the_query_exactly_once():
    idx, emb = make()
    idx.upsert("d1", "cat\n\ndog", ["u"])
    emb.calls.clear()
    idx.search("cat dog", ["u"])
    assert emb.calls == ["cat dog"]
    idx.search("cat", ["nobody"])
    assert emb.calls == ["cat dog", "cat"]


@pytest.mark.parametrize("principals", [None, "alice", b"a", 5, [1], [""]])
def test_search_rejects_bad_principals(principals):
    idx, _ = make()
    with pytest.raises(ValueError):
        idx.search("cat", principals)


@pytest.mark.parametrize("k", [0, -1, 1.5, "3", None])
def test_search_rejects_bad_k(k):
    idx, _ = make()
    with pytest.raises(ValueError):
        idx.search("cat", ["a"], k=k)


# --- reindex -----------------------------------------------------------------------------------

def test_reindex_same_model_is_a_noop():
    idx, emb = make()
    idx.upsert("d1", "cat\n\ndog", ["u"])
    other = Embedder(scale=9)
    assert idx.reindex(other, "v1") == 0
    assert other.calls == [] and idx.stats()["model"] == "v1"
    assert idx.search("cat", ["u"])[0]["score"] == 1          # досі стара embed


def test_reindex_recomputes_every_chunk_once_and_switches_everything():
    idx, emb = make()
    idx.upsert("d1", "cat\n\ndog", ["u"])
    idx.upsert("d2", "cat\n\nfish", ["u"])
    new = Embedder(scale=10)
    assert idx.reindex(new, "v2") == 4
    assert sorted(new.calls) == ["cat", "cat", "dog", "fish"]
    assert idx.stats() == {"docs": 2, "chunks": 4, "model": "v2"}
    new.calls.clear()
    res = idx.search("cat", ["u"])
    assert new.calls == ["cat"] and [r["score"] for r in res] == [100, 100]   # і запит, і чанки з новою embed
    new.calls.clear()
    idx.upsert("d3", "bird", ["u"])
    assert new.calls == ["bird"]
    assert idx.search("bird", ["u"])[0]["score"] == 100


def test_reindex_failure_keeps_old_model_completely():
    idx, emb = make()
    idx.upsert("d1", "cat\n\ndog\n\nBOOM fish", ["u"])
    broken = Embedder(scale=10, fail_on="BOOM")
    with pytest.raises(RuntimeError):
        idx.reindex(broken, "v2")
    assert idx.stats() == {"docs": 1, "chunks": 3, "model": "v1"}
    emb.calls.clear()
    assert idx.search("cat", ["u"])[0]["score"] == 1 and emb.calls == ["cat"]
    assert idx.reindex(Embedder(scale=10), "v2") == 3                       # повторна спроба проходить


def test_reindex_on_empty_index_and_embed_exceptions_in_init_state():
    idx, _ = make()
    assert idx.reindex(Embedder(scale=2), "v2") == 0
    assert idx.stats() == {"docs": 0, "chunks": 0, "model": "v2"}


def test_unchanged_chunks_are_not_recomputed_after_reindex_either():
    idx, _ = make()
    idx.upsert("d1", "cat tale\n\ndog tale", ["u"])
    new = Embedder(scale=3)
    idx.reindex(new, "v2")
    new.calls.clear()
    assert idx.upsert("d1", "cat tale\n\ndog tale\n\nfish tale", ["u"]) == {"added": 1, "removed": 0, "unchanged": 2}
    assert new.calls == ["fish tale"]
