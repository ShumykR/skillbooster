import hashlib
import math
import re

import pytest

from solution import SemanticCache, cached_call, count_tokens, estimate_savings, order_for_cache, prefix_tokens


def embed(text, dim=4096):
    vec = [0.0] * dim
    for tok in re.findall(r"\w+", text.lower()):
        vec[int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make(**kw):
    clock = Clock()
    return clock, SemanticCache(embed, clock=clock, **kw)


Q1 = "what is the refund policy"
Q2 = "what is your refund policy"      # схожість 0.8 із Q1
Q3 = "how do I reset my password"


# ---------- SemanticCache -----------------------------------------------------------------------------------------


def test_exact_and_similar_hits_and_misses():
    _, c = make(threshold=0.75)
    c.put(Q1, "14 days")
    assert c.get(Q1) == "14 days"
    assert c.get(Q2) == "14 days", "схожість 0.8 >= 0.75"
    assert c.get(Q3) is None
    assert c.stats == {"hits": 2, "misses": 1, "evictions": 0, "expired": 0}


def test_threshold_controls_strictness():
    _, strict = make(threshold=0.9)
    strict.put(Q1, "14 days")
    assert strict.get(Q2) is None
    _, exact_only = make(threshold=1.0)
    exact_only.put(Q1, "14 days")
    assert exact_only.get(Q1) == "14 days" and exact_only.get(Q2) is None


def test_exact_text_always_hits_even_for_an_empty_embedding():
    _, c = make(threshold=0.9)
    c.put("!!!", "symbols")
    assert c.get("!!!") == "symbols"
    assert c.get("???") is None, "нульові вектори різних текстів не схожі"


def test_namespaces_are_isolated():
    _, c = make(threshold=0.75)
    c.put(Q1, "answer for tenant A", namespace="tenant-a")
    assert c.get(Q1, namespace="tenant-b") is None
    assert c.get(Q1) is None
    assert c.get(Q2, namespace="tenant-a") == "answer for tenant A"
    c.put(Q1, "answer for tenant B", namespace="tenant-b")
    assert c.get(Q1, namespace="tenant-a") == "answer for tenant A" and len(c) == 2


def test_best_match_wins_and_ties_go_to_the_oldest():
    clock, c = make(threshold=0.5)
    c.put("refund policy", "short")
    clock.now += 1
    c.put(Q1, "exact-ish")
    assert c.get("what is the refund policy please") == "exact-ish", "Q1 ближчий, ніж «refund policy»"
    _, tie = make(threshold=0.5)
    tie.put("alpha beta", "first")
    tie.put("beta alpha", "second")
    assert tie.get("alpha beta gamma") == "first"


def test_ttl_boundary_and_expired_counter():
    clock, c = make(ttl=100)
    c.put(Q1, "a")
    clock.now = 99.99
    assert c.get(Q1) == "a"
    clock.now = 100
    assert c.get(Q1) is None
    assert c.stats["expired"] == 1 and len(c) == 0 and c.stats["misses"] == 1


def test_ttl_is_counted_from_creation_not_from_last_use():
    clock, c = make(ttl=100)
    c.put(Q1, "a")
    clock.now = 60
    assert c.get(Q1) == "a"
    clock.now = 110
    assert c.get(Q1) is None


def test_put_again_refreshes_value_and_lifetime():
    clock, c = make(ttl=100)
    c.put(Q1, "old")
    clock.now = 90
    c.put(Q1, "new")
    clock.now = 150
    assert c.get(Q1) == "new" and len(c) == 1


def test_lru_eviction_uses_access_order():
    _, c = make(max_entries=2, threshold=1.0)
    c.put("a a", 1)
    c.put("b b", 2)
    assert c.get("a a") == 1
    c.put("c c", 3)
    assert c.get("b b") is None and c.get("a a") == 1 and c.get("c c") == 3
    assert c.stats["evictions"] == 1 and len(c) == 2


def test_overwriting_counts_as_use_and_does_not_evict():
    _, c = make(max_entries=2, threshold=1.0)
    c.put("a a", 1)
    c.put("b b", 2)
    c.put("a a", 10)
    assert len(c) == 2 and c.stats["evictions"] == 0
    c.put("c c", 3)
    assert c.get("b b") is None and c.get("a a") == 10


# ---------- cached_call -------------------------------------------------------------------------------------------------


class Counter:
    def __init__(self, reply="answer"):
        self.calls, self.reply = [], reply

    def __call__(self, prompt):
        self.calls.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_cached_call_saves_llm_calls():
    _, c = make(threshold=0.75)
    llm = Counter()
    assert cached_call(c, llm, Q1) == {"value": "answer", "cached": False}
    assert cached_call(c, llm, Q1) == {"value": "answer", "cached": True}
    assert cached_call(c, llm, Q2) == {"value": "answer", "cached": True}
    assert cached_call(c, llm, Q3)["cached"] is False
    assert llm.calls == [Q1, Q3]


def test_cached_call_respects_namespaces():
    _, c = make()
    llm = Counter()
    cached_call(c, llm, Q1, namespace="a")
    assert cached_call(c, llm, Q1, namespace="b")["cached"] is False and len(llm.calls) == 2


@pytest.mark.parametrize("reply", [None, "", "   \n", 42])
def test_empty_or_non_string_replies_are_not_cached(reply):
    _, c = make()
    llm = Counter(reply)
    assert cached_call(c, llm, Q1) == {"value": reply, "cached": False}
    assert len(c) == 0


def test_llm_errors_are_not_cached_or_swallowed():
    _, c = make()
    with pytest.raises(TimeoutError):
        cached_call(c, Counter(TimeoutError()), Q1)
    assert len(c) == 0


# ---------- prompt caching ---------------------------------------------------------------------------------------------------


def words(n):
    return " ".join(["w"] * n)


def test_count_tokens():
    assert count_tokens("a b  c\n d") == 4 and count_tokens("") == 0


def test_order_for_cache_puts_stable_parts_first():
    parts = [{"text": "sys", "stable": True}, {"text": "question", "stable": False}, {"text": "docs", "stable": True}, {"text": "time", "stable": False}]
    assert [p["text"] for p in order_for_cache(parts)] == ["sys", "docs", "question", "time"]
    assert order_for_cache([]) == []
    assert [p["text"] for p in parts] == ["sys", "question", "docs", "time"], "вхідний список не змінюється"


def test_reordering_enlarges_the_cacheable_prefix():
    parts = [{"text": words(900), "stable": True}, {"text": "user question", "stable": False}, {"text": words(300), "stable": True}]
    assert prefix_tokens(parts) == 0, "900 < 1024: стабільний префікс надто короткий, а документи після питання не рахуються"
    assert prefix_tokens(order_for_cache(parts)) == 1200


def test_prefix_threshold_and_custom_counter():
    assert prefix_tokens([{"text": words(1023), "stable": True}]) == 0
    assert prefix_tokens([{"text": words(1024), "stable": True}]) == 1024
    assert prefix_tokens([{"text": "abcd", "stable": True}], count=len, min_prefix=4) == 4
    assert prefix_tokens([{"text": "abc", "stable": True}], count=len, min_prefix=4) == 0
    assert prefix_tokens([{"text": "x", "stable": False}], min_prefix=0) == 0
    assert prefix_tokens([], min_prefix=0) == 0


def test_estimate_savings():
    r = estimate_savings(2000, 100, 10, 3.0)
    assert r == {"without": 0.063, "with": 0.0144, "saved": 0.0486, "saved_pct": 77.14}


def test_no_savings_below_the_minimum_prefix_or_with_a_single_call():
    assert estimate_savings(500, 100, 10, 3.0) == {"without": 0.018, "with": 0.018, "saved": 0.0, "saved_pct": 0.0}
    r = estimate_savings(2000, 100, 1, 3.0)
    assert r["saved"] == 0.0 and r["with"] == r["without"]
    assert estimate_savings(1024, 0, 2, 1.0)["saved"] > 0
    assert estimate_savings(1023, 0, 2, 1.0)["saved"] == 0.0


def test_discount_extremes():
    assert estimate_savings(2000, 100, 3, 1.0, cached_discount=0)["saved"] == 0.0
    r = estimate_savings(1000, 0, 11, 1.0, cached_discount=1.0, min_prefix=500)
    assert r["with"] == 0.001 and r["saved_pct"] == 90.91
    assert estimate_savings(0, 0, 5, 1.0, min_prefix=0) == {"without": 0.0, "with": 0.0, "saved": 0.0, "saved_pct": 0.0}


@pytest.mark.parametrize("args", [(100, 10, 0, 1.0), (-1, 10, 1, 1.0), (100, -1, 1, 1.0)])
def test_estimate_validation(args):
    with pytest.raises(ValueError):
        estimate_savings(*args)
    with pytest.raises(ValueError):
        estimate_savings(100, 10, 1, 1.0, cached_discount=1.5)
