import asyncio

import pytest

from solution import DataLoader, DataLoaderError, posts_with_authors


def run(coro):
    # таймаут: невиконана Future у завантажувачі інакше вішає тест назавжди
    return asyncio.run(asyncio.wait_for(coro, timeout=5))


class Batches:
    """batch_fn, що записує, які пакети йому прийшли."""

    def __init__(self, fn=None):
        self.calls = []
        self.fn = fn or (lambda keys: [f"v{k}" for k in keys])

    async def __call__(self, keys):
        self.calls.append(list(keys))
        await asyncio.sleep(0)
        result = self.fn(keys)
        return result


async def many(loader, keys):
    return await asyncio.gather(*(loader.load(k) for k in keys))


# ---------- пакетування -------------------------------------------------------


def test_loads_in_same_tick_become_one_batch():
    b = Batches()
    result = run(many(DataLoader(b), [1, 2, 3]))
    assert result == ["v1", "v2", "v3"]
    assert b.calls == [[1, 2, 3]]


def test_duplicate_keys_in_a_batch_are_requested_once_but_all_callers_get_values():
    b = Batches()
    result = run(many(DataLoader(b), [1, 2, 1, 2, 1]))
    assert result == ["v1", "v2", "v1", "v2", "v1"]
    assert b.calls == [[1, 2]]


def test_loads_in_different_ticks_make_separate_batches():
    b = Batches()

    async def main():
        loader = DataLoader(b)
        first = await loader.load(1)
        second = await loader.load(2)
        return [first, second]

    assert run(main()) == ["v1", "v2"]
    assert b.calls == [[1], [2]]


def test_max_batch_size_splits_batches_preserving_order():
    b = Batches()
    result = run(many(DataLoader(b, max_batch_size=2), [1, 2, 3, 4, 5]))
    assert result == ["v1", "v2", "v3", "v4", "v5"]
    assert b.calls == [[1, 2], [3, 4], [5]]


def test_load_many_keeps_key_order():
    b = Batches()

    async def main():
        return await DataLoader(b).load_many([3, 1, 2])

    assert run(main()) == ["v3", "v1", "v2"]
    assert b.calls == [[3, 1, 2]]


def test_empty_load_many_does_not_call_batch_fn():
    b = Batches()

    async def main():
        return await DataLoader(b).load_many([])

    assert run(main()) == [] and b.calls == []


# ---------- кеш ---------------------------------------------------------------


def test_cache_hits_across_batches():
    b = Batches()

    async def main():
        loader = DataLoader(b)
        await loader.load(1)
        return [await loader.load(1), await loader.load(2)]

    assert run(main()) == ["v1", "v2"]
    assert b.calls == [[1], [2]]


def test_second_load_of_inflight_key_shares_the_first_request():
    b = Batches()

    async def main():
        loader = DataLoader(b)
        t1 = asyncio.create_task(loader.load(1))
        await asyncio.sleep(0)
        t2 = asyncio.create_task(loader.load(1))
        return await asyncio.gather(t1, t2)

    assert run(main()) == ["v1", "v1"]
    assert b.calls == [[1]]


def test_cache_disabled_still_dedups_within_a_batch_but_not_between_batches():
    b = Batches()

    async def main():
        loader = DataLoader(b, cache=False)
        await many(loader, [1, 1])
        await loader.load(1)

    run(main())
    assert b.calls == [[1], [1]]


def test_clear_one_key_and_all():
    b = Batches()

    async def main():
        loader = DataLoader(b)
        await many(loader, [1, 2])
        loader.clear(1)
        await many(loader, [1, 2])
        loader.clear()
        await many(loader, [1, 2])

    run(main())
    assert b.calls == [[1, 2], [1], [1, 2]]


def test_prime_does_not_overwrite_and_avoids_fetch():
    b = Batches()

    async def main():
        loader = DataLoader(b)
        loader.prime(1, "primed")
        loader.prime(1, "ignored")
        return await many(loader, [1, 2])

    assert run(main()) == ["primed", "v2"]
    assert b.calls == [[2]]


# ---------- помилки -----------------------------------------------------------


def test_per_key_exception_fails_only_that_key():
    b = Batches(lambda keys: [ValueError(f"bad {k}") if k == 2 else f"v{k}" for k in keys])

    async def shared():
        loader = DataLoader(b)
        return await asyncio.gather(*(loader.load(k) for k in [1, 2, 3]), return_exceptions=True)

    first, second, third = run(shared())
    assert first == "v1" and third == "v3"
    assert isinstance(second, ValueError) and str(second) == "bad 2"


def test_failed_key_is_not_cached():
    attempts = []

    def fn(keys):
        attempts.append(list(keys))
        return [ValueError("flaky") if len(attempts) == 1 else "ok" for _ in keys]

    async def main():
        loader = DataLoader(Batches(fn))
        with pytest.raises(ValueError):
            await loader.load(1)
        return await loader.load(1)

    assert run(main()) == "ok"


def test_batch_fn_exception_reaches_every_key_and_is_not_cached():
    calls = []

    async def boom(keys):
        calls.append(list(keys))
        if len(calls) == 1:
            raise RuntimeError("db down")
        return ["ok" for _ in keys]

    async def main():
        loader = DataLoader(boom)
        results = await asyncio.gather(*(loader.load(k) for k in [1, 2]), return_exceptions=True)
        assert all(isinstance(r, RuntimeError) for r in results)
        return await loader.load_many([1, 2])

    assert run(main()) == ["ok", "ok"]


def test_wrong_result_length_is_an_error_for_all_keys():
    async def short(keys):
        return ["only-one"]

    async def main():
        loader = DataLoader(short)
        return await asyncio.gather(*(loader.load(k) for k in [1, 2, 3]), return_exceptions=True)

    assert all(isinstance(r, DataLoaderError) for r in run(main()))


# ---------- N+1 на прикладі «дописи й автори» ---------------------------------


class FakeDB:
    def __init__(self, posts, users):
        self.posts, self.users = posts, {u["id"]: u for u in users}
        self.queries = []

    async def list_posts(self):
        self.queries.append("posts")
        await asyncio.sleep(0)
        return [dict(p) for p in self.posts]

    async def get_user(self, user_id):
        self.queries.append(f"user:{user_id}")
        await asyncio.sleep(0)
        return self.users.get(user_id)

    async def users_by_ids(self, ids):
        self.queries.append(f"users:{sorted(ids)}")
        await asyncio.sleep(0)
        return [self.users.get(i) for i in ids]


def make_db(n_posts=50, n_authors=7):
    users = [{"id": i, "name": f"user{i}"} for i in range(1, n_authors + 1)]
    posts = [{"id": p, "author_id": (p % n_authors) + 1} for p in range(n_posts)]
    return FakeDB(posts, users)


def test_posts_with_authors_returns_correct_authors():
    db = make_db()
    posts = run(posts_with_authors(db))
    assert len(posts) == 50
    assert all(p["author"] == {"id": p["author_id"], "name": f"user{p['author_id']}"} for p in posts)


def test_posts_with_authors_does_exactly_two_queries_for_any_size():
    for n_posts in (1, 50, 400):
        db = make_db(n_posts=n_posts)
        run(posts_with_authors(db))
        assert len(db.queries) == 2, f"{n_posts} дописів: запитів {len(db.queries)}"
        assert db.queries[0] == "posts" and db.queries[1].startswith("users:")


def test_posts_with_authors_asks_each_author_once():
    db = make_db(n_posts=50, n_authors=7)
    run(posts_with_authors(db))
    assert db.queries[1] == "users:[1, 2, 3, 4, 5, 6, 7]"


def test_missing_author_is_none_without_breaking_the_others():
    db = make_db(n_posts=6, n_authors=3)
    db.posts.append({"id": 99, "author_id": 12345})
    posts = run(posts_with_authors(db))
    assert posts[-1]["author"] is None
    assert all(p["author"] is not None for p in posts[:-1])
    assert len(db.queries) == 2
