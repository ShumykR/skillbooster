import asyncio
import threading
import time

from solution import build_reports


async def load_user(user_id):
    await asyncio.sleep(0)
    return {"id": user_id}


def run(coro):
    return asyncio.run(coro)


def test_event_loop_stays_free_while_rendering():
    # render_pdf чекає, поки ІНША корутина (на тому самому loop) подасть сигнал.
    # Якщо рендер іде в потоці loop, ця корутина не отримає керування: рендер впаде за таймаутом.
    release = threading.Event()

    def render(user):
        return b"ok" if release.wait(2) else b"BLOCKED"

    async def other_requests():
        for _ in range(20):
            await asyncio.sleep(0)
        release.set()

    async def main():
        reports, _ = await asyncio.gather(build_reports([1, 2], load_user, render), other_requests())
        return reports

    reports = run(main())
    assert [r["pdf"] for r in reports] == [b"ok", b"ok"], "event loop заблоковано: render_pdf виконується в його потоці"


def test_results_keep_input_order():
    def render(user):
        time.sleep(0.03 if user["id"] == 1 else 0.0)  # перший завершується останнім
        return f"pdf{user['id']}".encode()

    reports = run(build_reports([1, 2, 3], load_user, render))
    assert reports == [{"user_id": i, "pdf": f"pdf{i}".encode()} for i in (1, 2, 3)]


def test_renders_in_parallel_but_not_more_than_limit():
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    def render(user):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.03)
        with lock:
            state["active"] -= 1
        return b"x"

    run(build_reports(list(range(8)), load_user, render, max_parallel=3))
    assert 2 <= state["peak"] <= 3, f"піково одночасних рендерів: {state['peak']}, очікувалось 2..3"


def test_one_failure_does_not_break_the_rest():
    def render(user):
        if user["id"] == 2:
            raise RuntimeError("font missing")
        return b"ok"

    reports = run(build_reports([1, 2, 3], load_user, render))
    assert reports[0] == {"user_id": 1, "pdf": b"ok"}
    assert reports[1] == {"user_id": 2, "error": "font missing"}
    assert reports[2] == {"user_id": 3, "pdf": b"ok"}


def test_empty_input():
    assert run(build_reports([], load_user, lambda u: b"")) == []
