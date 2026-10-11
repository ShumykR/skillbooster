import asyncio
import time

from solution import fetch_dashboard


def run(coro):
    return asyncio.run(coro)


def make(delay, result="ok", exc=None, log=None):
    async def svc(user_id):
        if log is not None:
            log["active"] += 1
            log["peak"] = max(log["peak"], log["active"])
        try:
            await asyncio.sleep(delay)
            if exc:
                raise exc
            return f"{result}:{user_id}"
        finally:
            if log is not None:
                log["active"] -= 1
    return svc


def test_runs_in_parallel():
    services = {n: make(0.2, n) for n in ("a", "b", "c")}
    start = time.perf_counter()
    res = run(fetch_dashboard(7, services, timeout=1, max_concurrency=3))
    elapsed = time.perf_counter() - start
    assert res["data"] == {"a": "a:7", "b": "b:7", "c": "c:7"}
    assert res["errors"] == {}
    assert elapsed < 0.45, f"сервіси викликаються послідовно: {elapsed:.2f}s"


def test_partial_failure_and_timeout():
    services = {
        "good": make(0.01, "good"),
        "boom": make(0.01, exc=ValueError("x")),
        "slow": make(5),
    }
    start = time.perf_counter()
    res = run(fetch_dashboard(1, services, timeout=0.1, max_concurrency=3))
    assert time.perf_counter() - start < 1
    assert res["data"] == {"good": "good:1"}
    assert res["errors"] == {"boom": "error", "slow": "timeout"}


def test_respects_max_concurrency():
    log = {"active": 0, "peak": 0}
    services = {f"s{i}": make(0.05, log=log) for i in range(6)}
    res = run(fetch_dashboard(1, services, timeout=1, max_concurrency=2))
    assert len(res["data"]) == 6
    assert log["peak"] == 2


def test_slow_service_is_cancelled():
    state = {"cancelled": False}

    async def slow(user_id):
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    res = run(fetch_dashboard(1, {"slow": slow}, timeout=0.05))
    assert res["errors"] == {"slow": "timeout"}
    assert state["cancelled"], "після таймауту завдання має бути скасоване"


def test_timeout_does_not_include_waiting_for_semaphore():
    # 4 сервіси по 0.15с, concurrency=1, timeout=0.3: черга триває ~0.6с,
    # але кожен сервіс окремо вкладається в таймаут.
    services = {f"s{i}": make(0.15) for i in range(4)}
    res = run(fetch_dashboard(1, services, timeout=0.3, max_concurrency=1))
    assert len(res["data"]) == 4
    assert res["errors"] == {}
