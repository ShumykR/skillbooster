import random

import pytest

from solution import Timeline

STRATEGIES = ["push", "pull", "hybrid"]


def make(strategy, threshold=3):
    return Timeline(strategy, celebrity_threshold=threshold)


# ---------- behaviour shared by all strategies ----------------------------------------


@pytest.fixture(params=STRATEGIES)
def tl(request):
    return make(request.param)


def test_feed_has_followed_and_own_posts_newest_first(tl):
    tl.follow("ann", "bob")
    a = tl.post("bob", "b1")
    tl.post("zed", "not followed")
    b = tl.post("ann", "mine")
    c = tl.post("bob", "b2")
    assert tl.feed("ann")["posts"] == [c, b, a]
    assert tl.feed("bob")["posts"] == [c, a]
    assert tl.feed("zed")["posts"] == [2]
    assert tl.feed("nobody") == {"posts": [], "next_cursor": None}


def test_post_ids_and_get_post(tl):
    assert [tl.post("a", "x"), tl.post("b", "y")] == [1, 2]
    assert tl.get_post(2) == {"id": 2, "author": "b", "text": "y"}
    with pytest.raises(KeyError):
        tl.get_post(99)


def test_follow_applies_only_to_later_posts(tl):
    tl.post("bob", "old")
    tl.follow("ann", "bob")
    new = tl.post("bob", "new")
    assert tl.feed("ann")["posts"] == [new]


def test_unfollow_hides_posts_and_refollow_restarts(tl):
    tl.follow("ann", "bob")
    p1 = tl.post("bob", "1")
    tl.unfollow("ann", "bob")
    p2 = tl.post("bob", "2")
    assert tl.feed("ann")["posts"] == []
    tl.follow("ann", "bob")
    p3 = tl.post("bob", "3")
    assert tl.feed("ann")["posts"] == [p3], f"{p1} і {p2} не повертаються"


def test_repeated_follow_does_not_move_the_start(tl):
    tl.follow("ann", "bob")
    p1 = tl.post("bob", "1")
    tl.follow("ann", "bob")
    assert tl.feed("ann")["posts"] == [p1]
    tl.unfollow("ann", "ghost")


def test_pagination_with_cursor(tl):
    tl.follow("ann", "bob")
    ids = [tl.post("bob", str(i)) for i in range(5)]
    page1 = tl.feed("ann", limit=2)
    assert page1 == {"posts": [5, 4], "next_cursor": 4}
    page2 = tl.feed("ann", limit=2, cursor=page1["next_cursor"])
    assert page2 == {"posts": [3, 2], "next_cursor": 2}
    page3 = tl.feed("ann", limit=2, cursor=page2["next_cursor"])
    assert page3 == {"posts": [1], "next_cursor": None}
    assert ids == [1, 2, 3, 4, 5]


def test_last_full_page_has_no_cursor(tl):
    tl.follow("ann", "bob")
    tl.post("bob", "1")
    tl.post("bob", "2")
    assert tl.feed("ann", limit=2) == {"posts": [2, 1], "next_cursor": None}
    assert tl.feed("ann", limit=1) == {"posts": [2], "next_cursor": 2}


def test_cursor_beyond_the_range(tl):
    tl.follow("ann", "bob")
    tl.post("bob", "1")
    assert tl.feed("ann", cursor=1) == {"posts": [], "next_cursor": None}
    assert tl.feed("ann", cursor=1000)["posts"] == [1]


def test_validation(tl):
    with pytest.raises(ValueError):
        tl.follow("ann", "ann")
    with pytest.raises(ValueError):
        tl.feed("ann", limit=0)
    with pytest.raises(ValueError):
        Timeline("fanout")


# ---------- all strategies must agree ------------------------------------------------


def run_scenario(strategy, seed):
    rng = random.Random(seed)
    tl = make(strategy, threshold=3)
    users = [f"u{i}" for i in range(8)]
    outputs = []
    for _ in range(400):
        op = rng.choice(["post", "post", "follow", "follow", "unfollow", "feed", "feed"])
        u, v = rng.choice(users), rng.choice(users)
        if op == "post":
            outputs.append(("post", tl.post(u, "t")))
        elif op == "follow" and u != v:
            tl.follow(u, v)
        elif op == "unfollow":
            tl.unfollow(u, v)
        elif op == "feed":
            outputs.append((u, tl.feed(u, limit=rng.choice([1, 3, 50]), cursor=rng.choice([None, None, rng.randint(1, 120)]))))
    return outputs


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_all_strategies_return_identical_results(seed):
    results = [run_scenario(s, seed) for s in STRATEGIES]
    assert results[0] == results[1] == results[2]
    assert any(isinstance(o[1], dict) and o[1]["posts"] for o in results[0]), "сценарій не порожній"


# ---------- cost: fan-out writes -------------------------------------------------------


def popular_author(strategy, followers):
    tl = make(strategy, threshold=3)
    for i in range(followers):
        tl.follow(f"f{i}", "star")
    return tl


def test_push_writes_one_entry_per_follower_per_post():
    tl = popular_author("push", 3)
    tl.post("star", "a")
    tl.post("star", "b")
    assert tl.stats == {"fanout_writes": 6}
    tl.post("loner", "c")
    assert tl.stats["fanout_writes"] == 6


def test_pull_never_fans_out():
    tl = popular_author("pull", 50)
    for _ in range(10):
        tl.post("star", "x")
    assert tl.stats == {"fanout_writes": 0}


def test_hybrid_skips_fanout_for_celebrities_only():
    small = popular_author("hybrid", 2)
    small.post("star", "a")
    small.post("star", "b")
    assert small.stats == {"fanout_writes": 4}
    big = popular_author("hybrid", 3)
    big.post("star", "a")
    assert big.stats == {"fanout_writes": 0}, "поріг включно: 3 підписники = зірка"


def test_celebrity_status_is_sticky():
    tl = popular_author("hybrid", 3)
    tl.post("star", "a")
    for i in range(3):
        tl.unfollow(f"f{i}", "star")
    tl.follow("late", "star")
    tl.post("star", "b")
    assert tl.stats["fanout_writes"] == 0
    assert tl.feed("late")["posts"] == [2]


def test_hybrid_merges_pushed_and_pulled_posts_without_duplicates():
    tl = make("hybrid", threshold=2)
    tl.follow("ann", "star")
    tl.follow("bob", "star")
    first = tl.post("star", "became celebrity at this post")
    tl.follow("ann", "small")
    second = tl.post("small", "pushed")
    third = tl.post("star", "pulled")
    assert tl.feed("ann")["posts"] == [third, second, first]
    assert tl.stats["fanout_writes"] == 1, "лише пост small був розісланий"


def test_unfollowed_users_are_not_fanned_out_to():
    tl = popular_author("push", 3)
    tl.unfollow("f0", "star")
    tl.post("star", "a")
    assert tl.stats == {"fanout_writes": 2}
