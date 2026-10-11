import asyncio

import pytest

from solution import SingleFlightCache


class Counter:
    def __init__(self, delay=0.02, fail_first=False):
        self.calls = {}
        self.delay = delay
        self.fail_first = fail_first

    async def load(self, key):
        n = self.calls.get(key, 0) + 1
        self.calls[key] = n
        await asyncio.sleep(self.delay)
        if self.fail_first and n == 1:
            raise RuntimeError("db down")
        return f"{key}-v{n}"


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_stampede_single_load():
    async def main():
        c = Counter()
        cache = SingleFlightCache(c.load, ttl=10)
        results = await asyncio.gather(*(cache.get("k") for _ in range(1000)))
        return c, results

    c, results = asyncio.run(main())
    assert c.calls == {"k": 1}
    assert set(results) == {"k-v1"}


def test_ttl_expiry_reloads():
    async def main():
        c, clock = Counter(delay=0), FakeClock()
        cache = SingleFlightCache(c.load, ttl=10, clock=clock)
        a = await cache.get("k")
        clock.t = 9.9
        b = await cache.get("k")
        clock.t = 10.1
        d = await cache.get("k")
        return a, b, d, c

    a, b, d, c = asyncio.run(main())
    assert (a, b, d) == ("k-v1", "k-v1", "k-v2")
    assert c.calls["k"] == 2


def test_different_keys_are_independent():
    async def main():
        c = Counter()
        cache = SingleFlightCache(c.load, ttl=10)
        await asyncio.gather(cache.get("a"), cache.get("b"), cache.get("a"))
        return c

    assert asyncio.run(main()).calls == {"a": 1, "b": 1}


def test_error_goes_to_all_waiters_and_is_not_cached():
    async def main():
        c = Counter(fail_first=True)
        cache = SingleFlightCache(c.load, ttl=10)
        res = await asyncio.gather(*(cache.get("k") for _ in range(5)), return_exceptions=True)
        again = await cache.get("k")
        return c, res, again

    c, res, again = asyncio.run(main())
    assert all(isinstance(r, RuntimeError) for r in res)
    assert c.calls["k"] == 2, "після помилки наступний запит має спробувати знову"
    assert again == "k-v2"


def test_one_waiter_cancelled_does_not_break_others():
    async def main():
        c = Counter(delay=0.05)
        cache = SingleFlightCache(c.load, ttl=10)
        t1 = asyncio.create_task(cache.get("k"))
        t2 = asyncio.create_task(cache.get("k"))
        await asyncio.sleep(0.01)
        t1.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t1
        return await t2, c

    value, c = asyncio.run(main())
    assert value == "k-v1"
    assert c.calls["k"] == 1
