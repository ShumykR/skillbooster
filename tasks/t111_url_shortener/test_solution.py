import hashlib

import pytest

from solution import (AliasTaken, ClickCounter, Expired, NotFound, ShardRing, Shortener, decode_base62, encode_base62,
                      normalize_url)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# ---------- base62 ---------------------------------------------------------------


@pytest.mark.parametrize("n, s", [(0, "0"), (9, "9"), (10, "A"), (35, "Z"), (36, "a"), (61, "z"), (62, "10"), (125, "21"), (3843, "zz"), (3844, "100")])
def test_base62_known_values(n, s):
    assert encode_base62(n) == s
    assert decode_base62(s) == n


def test_base62_roundtrip():
    for n in (0, 1, 61, 62, 12345, 2**40, 2**63 - 1):
        assert decode_base62(encode_base62(n)) == n


@pytest.mark.parametrize("call", [lambda: encode_base62(-1), lambda: decode_base62(""), lambda: decode_base62("ab-c"), lambda: decode_base62("a b")])
def test_base62_errors(call):
    with pytest.raises(ValueError):
        call()


# ---------- normalize_url --------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [
    ("  HTTP://Example.COM/Path?q=1#frag ", "http://example.com/Path?q=1"),
    ("https://example.com", "https://example.com"),
    ("http://EXAMPLE.com:8080/x", "http://example.com:8080/x"),
    ("https://example.com/A/B?X=Y", "https://example.com/A/B?X=Y"),
])
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("bad", [
    "javascript:alert(1)", "ftp://example.com/f", "data:text/html,hi", "example.com", "http:///path", "http://",
    "http://user:pw@example.com/", "http://user@example.com/", "http://exa mple.com", "http://example.com/a\nb", "http://example.com/\x00",
    "https://example.com/" + "a" * 2050, "",
])
def test_normalize_url_rejects(bad):
    with pytest.raises(ValueError):
        normalize_url(bad)


def test_url_at_the_length_limit():
    ok = "https://e.com/" + "a" * (2048 - len("https://e.com/"))
    assert normalize_url(ok) == ok
    with pytest.raises(ValueError):
        normalize_url(ok + "a")


# ---------- Shortener ------------------------------------------------------------


@pytest.fixture
def clock():
    return Clock()


def test_auto_codes_are_sequential_base62(clock):
    s = Shortener(clock=clock, start_id=3843)
    assert [s.create(f"https://e.com/{i}") for i in range(3)] == ["zz", "100", "101"]
    assert s.resolve("100") == "https://e.com/1"


def test_same_url_gets_the_same_code_without_burning_ids(clock):
    s = Shortener(clock=clock)
    a = s.create("https://Example.com/x#top")
    assert s.create("https://example.com/x") == a
    assert s.create("https://e.com/other") != a
    assert s.create("https://e.com/third") == encode_base62(3), "id 2 не витрачено на дубль"


def test_custom_alias(clock):
    s = Shortener(clock=clock)
    assert s.create("https://e.com/a", alias="my-link_1") == "my-link_1"
    assert s.resolve("my-link_1") == "https://e.com/a"
    with pytest.raises(AliasTaken):
        s.create("https://e.com/b", alias="my-link_1")
    assert s.create("https://e.com/b", alias="My-Link_1") == "My-Link_1", "регістр значущий"


@pytest.mark.parametrize("alias", ["ab", "a" * 33, "has space", "dot.dot", "слово", "api", "Admin", "HEALTH", "static", "docs", ""])
def test_invalid_or_reserved_aliases(clock, alias):
    with pytest.raises(ValueError):
        Shortener(clock=clock).create("https://e.com/", alias=alias)


def test_alias_length_boundaries(clock):
    s = Shortener(clock=clock)
    assert s.create("https://e.com/", alias="abc") == "abc"
    assert s.create("https://e.com/", alias="a" * 32) == "a" * 32


def test_auto_code_skips_codes_taken_by_aliases(clock):
    s = Shortener(clock=clock, start_id=3844)
    s.create("https://e.com/x", alias="100")
    assert s.create("https://e.com/y") == "101"
    with pytest.raises(AliasTaken):
        s.create("https://e.com/z", alias="101")


def test_alias_does_not_hijack_dedupe(clock):
    s = Shortener(clock=clock)
    s.create("https://e.com/x", alias="custom")
    auto = s.create("https://e.com/x")
    assert auto != "custom" and s.resolve(auto) == "https://e.com/x"


def test_ttl_expiry_boundary(clock):
    s = Shortener(clock=clock)
    code = s.create("https://e.com/temp", ttl=10)
    clock.now += 9.99
    assert s.resolve(code) == "https://e.com/temp"
    clock.now += 0.01
    with pytest.raises(Expired):
        s.resolve(code)
    with pytest.raises(NotFound):
        s.resolve(code)
    with pytest.raises(KeyError):
        s.resolve(code)


def test_ttl_links_are_not_deduplicated(clock):
    s = Shortener(clock=clock)
    permanent = s.create("https://e.com/x")
    temp = s.create("https://e.com/x", ttl=5)
    assert temp != permanent
    assert s.create("https://e.com/x") == permanent
    assert s.create("https://e.com/x", ttl=5) not in (temp, permanent)


@pytest.mark.parametrize("ttl", [0, -1])
def test_invalid_ttl(clock, ttl):
    with pytest.raises(ValueError):
        Shortener(clock=clock).create("https://e.com/", ttl=ttl)


def test_unknown_code_and_invalid_url(clock):
    s = Shortener(clock=clock)
    with pytest.raises(NotFound):
        s.resolve("nope")
    with pytest.raises(ValueError):
        s.create("javascript:alert(1)")


# ---------- ClickCounter ---------------------------------------------------------


def test_clicks_are_batched_and_flushed_when_full():
    batches = []
    c = ClickCounter(batches.append, flush_every=4)
    for code in ("a", "b", "a"):
        c.hit(code)
    assert batches == [] and c.pending == 3
    c.hit("a")
    assert batches == [{"a": 3, "b": 1}] and c.pending == 0


def test_manual_flush_and_empty_flush():
    batches = []
    c = ClickCounter(batches.append, flush_every=100)
    c.flush()
    assert batches == []
    c.hit("x")
    c.flush()
    c.flush()
    assert batches == [{"x": 1}]


def test_no_clicks_are_lost_or_duplicated():
    total = {}

    def sink(batch):
        for k, v in batch.items():
            total[k] = total.get(k, 0) + v

    c = ClickCounter(sink, flush_every=7)
    for i in range(100):
        c.hit("a" if i % 3 else "b")
    c.flush()
    assert total == {"a": 66, "b": 34}


def test_flush_every_validation():
    with pytest.raises(ValueError):
        ClickCounter(lambda b: None, flush_every=0)
    batches = []
    c = ClickCounter(batches.append, flush_every=1)
    c.hit("a")
    c.hit("a")
    assert batches == [{"a": 1}, {"a": 1}]


# ---------- ShardRing ------------------------------------------------------------


def pos(text):
    return int.from_bytes(hashlib.md5(text.encode()).digest()[:8], "big")


def naive_shard(shards, vnodes, key):
    points = sorted((pos(f"{s}#{i}"), s) for s in shards for i in range(vnodes))
    k = pos(key)
    for p, s in points:
        if p >= k:
            return s
    return points[0][1]


def test_mapping_follows_the_documented_algorithm():
    ring = ShardRing(["a", "b", "c"], vnodes=8)
    for i in range(200):
        assert ring.shard_for(f"key{i}") == naive_shard(["a", "b", "c"], 8, f"key{i}")


def test_wraps_around_the_ring():
    ring = ShardRing(["only"], vnodes=4)
    assert {ring.shard_for(f"k{i}") for i in range(50)} == {"only"}
    ring2 = ShardRing(["a", "b"], vnodes=1)
    top = max(pos("a#0"), pos("b#0"))
    wrapping = [k for k in (f"x{i}" for i in range(500)) if pos(k) > top]
    assert wrapping, "для тесту потрібен ключ за останньою точкою"
    first = min((pos("a#0"), "a"), (pos("b#0"), "b"))[1]
    assert ring2.shard_for(wrapping[0]) == first


def test_keys_are_spread_reasonably():
    ring = ShardRing(["a", "b", "c"], vnodes=128)
    counts = {"a": 0, "b": 0, "c": 0}
    for i in range(6000):
        counts[ring.shard_for(f"code{i}")] += 1
    assert all(0.2 * 6000 < n < 0.47 * 6000 for n in counts.values()), counts


def test_removing_a_shard_moves_only_its_keys():
    ring = ShardRing(["a", "b", "c"], vnodes=64)
    keys = [f"k{i}" for i in range(2000)]
    before = {k: ring.shard_for(k) for k in keys}
    ring.remove("b")
    after = {k: ring.shard_for(k) for k in keys}
    for k in keys:
        if before[k] != "b":
            assert after[k] == before[k]
        else:
            assert after[k] in ("a", "c")


def test_adding_a_shard_steals_keys_only_for_itself():
    ring = ShardRing(["a", "b", "c"], vnodes=64)
    keys = [f"k{i}" for i in range(2000)]
    before = {k: ring.shard_for(k) for k in keys}
    ring.add("d")
    moved = [k for k in keys if ring.shard_for(k) != before[k]]
    assert moved and all(ring.shard_for(k) == "d" for k in moved)
    assert len(moved) < 0.4 * len(keys)


def test_add_after_remove_restores_the_original_mapping():
    ring = ShardRing(["a", "b", "c"])
    keys = [f"k{i}" for i in range(300)]
    before = [ring.shard_for(k) for k in keys]
    ring.remove("c")
    ring.add("c")
    assert [ring.shard_for(k) for k in keys] == before


def test_ring_errors():
    with pytest.raises(LookupError):
        ShardRing().shard_for("x")
    ring = ShardRing(["a"])
    with pytest.raises(ValueError):
        ring.add("a")
    with pytest.raises(ValueError):
        ring.remove("zzz")
    ring.remove("a")
    with pytest.raises(LookupError):
        ring.shard_for("x")
