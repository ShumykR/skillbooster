import pytest

from solution import KEEPALIVE, JobManager, TooManyJobs, format_sse, stream_chunks


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    clock = Clock()
    return clock, JobManager(clock, max_active_per_owner=2, max_events=50)


def kinds(manager, job_id, owner="ann", last=0):
    return [(e["id"], e["event"], e["data"]) for e in manager.events(job_id, owner, last)]


# ---------- lifecycle -------------------------------------------------------------------------------------------------------


def test_submit_creates_a_queued_job(env):
    clock, m = env
    assert m.submit("ann", "report", {"topic": "x"}) == "j1" and m.submit("ann", "report", {}) == "j2"
    assert m.get("j1", "ann") == {"id": "j1", "kind": "report", "status": "queued", "progress": 0, "result": None, "error": None,
                                  "created": 100.0, "finished": None}
    assert kinds(m, "j1") == [(1, "status", {"status": "queued"})]


def test_full_successful_run(env):
    clock, m = env
    j = m.submit("ann", "report", {})
    assert m.start(j) is True
    assert m.progress(j, 30, "Збираю дані") is True
    assert m.progress(j, 70, "Пишу текст") is True
    clock.now = 130.0
    assert m.complete(j, {"text": "готово"}) is True
    assert kinds(m, j) == [
        (1, "status", {"status": "queued"}), (2, "status", {"status": "running"}),
        (3, "progress", {"percent": 30, "message": "Збираю дані"}), (4, "progress", {"percent": 70, "message": "Пишу текст"}),
        (5, "result", {"result": {"text": "готово"}}), (6, "status", {"status": "succeeded"})]
    assert m.get(j, "ann") == {"id": j, "kind": "report", "status": "succeeded", "progress": 100, "result": {"text": "готово"}, "error": None,
                               "created": 100.0, "finished": 130.0}


def test_failure_records_the_error(env):
    clock, m = env
    j = m.submit("ann", "report", {})
    m.start(j)
    clock.now = 110
    assert m.fail(j, ValueError("LLM timeout")) is True
    assert kinds(m, j)[-2:] == [(3, "error", {"error": "LLM timeout"}), (4, "status", {"status": "failed"})]
    got = m.get(j, "ann")
    assert got["status"] == "failed" and got["error"] == "LLM timeout" and got["finished"] == 110 and got["progress"] == 0


def test_a_queued_job_can_fail(env):
    _, m = env
    j = m.submit("ann", "r", {})
    assert m.fail(j, "boom") is True and m.get(j, "ann")["status"] == "failed"


def test_invalid_transitions(env):
    _, m = env
    j = m.submit("ann", "r", {})
    with pytest.raises(ValueError):
        m.progress(j, 10)
    with pytest.raises(ValueError):
        m.complete(j, "x")
    m.start(j)
    with pytest.raises(ValueError):
        m.start(j)
    for bad in (-1, 101, 1.5, "10", True):
        with pytest.raises(ValueError):
            m.progress(j, bad)
    for call in (m.start, lambda i: m.progress(i, 5), lambda i: m.complete(i, 1), lambda i: m.fail(i, "e")):
        with pytest.raises(KeyError):
            call("nope")


# ---------- progress rules ---------------------------------------------------------------------------------------------------------


def test_progress_only_moves_forward(env):
    _, m = env
    j = m.submit("ann", "r", {})
    m.start(j)
    assert m.progress(j, 0, "start") is True, "перше значення будь-яке"
    assert m.progress(j, 40) is True
    assert m.progress(j, 40) is False and m.progress(j, 20) is False
    assert m.get(j, "ann")["progress"] == 40
    assert m.progress(j, 41) is True
    assert [e[1] for e in kinds(m, j)].count("progress") == 3


def test_message_only_progress_is_always_emitted(env):
    _, m = env
    j = m.submit("ann", "r", {})
    m.start(j)
    m.progress(j, 50)
    assert m.progress(j, None, "ще працюю") is True and m.progress(j, None, "ще працюю") is True
    assert m.get(j, "ann")["progress"] == 50
    assert kinds(m, j)[-1] == (5, "progress", {"percent": None, "message": "ще працюю"})


# ---------- cancellation -------------------------------------------------------------------------------------------------------------


def test_cancel_running_job_and_late_worker_calls_are_ignored(env):
    clock, m = env
    j = m.submit("ann", "r", {})
    m.start(j)
    clock.now = 120
    assert m.cancel(j, "ann") is True
    assert kinds(m, j)[-1] == (3, "status", {"status": "cancelled"}) and m.get(j, "ann")["finished"] == 120
    before = kinds(m, j)
    assert m.progress(j, 10) is False and m.complete(j, "late") is False and m.fail(j, "x") is False and m.start(j) is False
    assert kinds(m, j) == before and m.get(j, "ann")["result"] is None


def test_cancel_queued_and_finished(env):
    _, m = env
    j = m.submit("ann", "r", {})
    assert m.cancel(j, "ann") is True and m.cancel(j, "ann") is False
    j2 = m.submit("ann", "r", {})
    m.start(j2)
    m.complete(j2, "ok")
    assert m.cancel(j2, "ann") is False and m.get(j2, "ann")["status"] == "succeeded"


# ---------- ownership --------------------------------------------------------------------------------------------------------------------


def test_other_owners_see_nothing_not_even_that_the_job_exists(env):
    _, m = env
    j = m.submit("ann", "r", {})
    for call in (lambda: m.get(j, "bob"), lambda: m.events(j, "bob"), lambda: m.cancel(j, "bob"), lambda: stream_chunks(m, j, "bob")):
        with pytest.raises(KeyError):
            call()
    with pytest.raises(KeyError):
        m.get("j999", "ann")
    assert m.get(j, "ann")["status"] == "queued", "чужа спроба скасувати не діє"


# ---------- limits and idempotency -----------------------------------------------------------------------------------------------------------


def test_active_jobs_per_owner_are_limited(env):
    _, m = env
    a, b = m.submit("ann", "r", {}), m.submit("ann", "r", {})
    with pytest.raises(TooManyJobs):
        m.submit("ann", "r", {})
    assert m.submit("bob", "r", {}) == "j3", "ліміт на власника"
    m.start(a)
    m.complete(a, "ok")
    assert m.submit("ann", "r", {}) == "j4", "завершене звільняє місце"
    m.cancel(b, "ann")
    assert m.submit("ann", "r", {}) == "j5"


def test_idempotency_key():
    m = JobManager(Clock(), max_active_per_owner=2)
    a = m.submit("ann", "r", {}, key="k1")
    assert m.submit("ann", "r", {"other": 1}, key="k1") == a
    assert m.submit("bob", "r", {}, key="k1") != a, "ключ діє в межах власника"
    b = m.submit("ann", "r", {}, key="k2")
    assert b != a and m.get(a, "ann")["id"] == a
    with pytest.raises(TooManyJobs):
        m.submit("ann", "r", {}, key="k3")
    assert m.submit("ann", "r", {}, key="k1") == a, "повтор за ключем не підпадає під ліміт активних"
    assert m.submit("ann", "r", {}, key="k2") == b


# ---------- events and SSE ----------------------------------------------------------------------------------------------------------------


def test_events_resume_after_last_event_id(env):
    _, m = env
    j = m.submit("ann", "r", {})
    m.start(j)
    m.progress(j, 10)
    m.progress(j, 20)
    assert [e["id"] for e in m.events(j, "ann")] == [1, 2, 3, 4]
    assert [e["id"] for e in m.events(j, "ann", 2)] == [3, 4]
    assert m.events(j, "ann", 4) == [] and m.events(j, "ann", 99) == []


def test_event_retention_keeps_the_latest_and_does_not_renumber():
    clock = Clock()
    m = JobManager(clock, max_events=3)
    j = m.submit("ann", "r", {})
    m.start(j)
    for p in (10, 20, 30, 40):
        m.progress(j, p)
    assert [e["id"] for e in m.events(j, "ann")] == [4, 5, 6]


def test_events_are_copies(env):
    _, m = env
    j = m.submit("ann", "r", {})
    m.events(j, "ann")[0]["event"] = "hacked"
    assert m.events(j, "ann")[0]["event"] == "status"


def test_format_sse():
    assert format_sse({"id": 3, "event": "progress", "data": {"percent": 30, "message": "Збираю"}}) == (
        'id: 3\nevent: progress\ndata: {"message":"Збираю","percent":30}\n\n')
    assert format_sse({"id": 1, "event": "status", "data": {"status": "queued"}}) == 'id: 1\nevent: status\ndata: {"status":"queued"}\n\n'
    assert "\n" not in format_sse({"id": 1, "event": "e", "data": {"t": "a\nb"}}).split("data: ")[1].rstrip("\n"), "переноси екранує JSON"


def test_stream_chunks_with_resume_keepalive_and_finish(env):
    _, m = env
    j = m.submit("ann", "r", {})
    chunks, finished = stream_chunks(m, j, "ann")
    assert chunks == ['id: 1\nevent: status\ndata: {"status":"queued"}\n\n'] and finished is False
    assert stream_chunks(m, j, "ann", last_event_id=1) == ([KEEPALIVE], False)
    m.start(j)
    m.complete(j, "ok")
    chunks, finished = stream_chunks(m, j, "ann", last_event_id=2)
    assert [c.split("\n")[1] for c in chunks] == ["event: result", "event: status"] and finished is True
    assert stream_chunks(m, j, "ann", last_event_id=99) == ([], True), "завершене без нових подій: порожньо, без keepalive"


# ---------- purge --------------------------------------------------------------------------------------------------------------------------


def test_purge_removes_only_old_finished_jobs(env):
    clock, m = env
    done, active, recent = m.submit("ann", "r", {}), m.submit("bob", "r", {}), m.submit("cat", "r", {})
    m.start(done)
    m.complete(done, "ok")
    clock.now += 100
    m.start(recent)
    m.fail(recent, "x")
    clock.now += 50
    assert m.purge(120) == 1, "лише done завершене понад 120 с тому (150)"
    with pytest.raises(KeyError):
        m.get(done, "ann")
    assert m.get(active, "bob")["status"] == "queued" and m.get(recent, "cat")["status"] == "failed"
    clock.now += 71
    assert m.purge(120) == 1 and m.purge(120) == 0
    assert m.purge(1) == 0, "активні не чіпаємо"


def test_purge_boundary_is_strict(env):
    clock, m = env
    j = m.submit("ann", "r", {})
    m.start(j)
    m.complete(j, "ok")
    clock.now += 60
    assert m.purge(60) == 0
    clock.now += 0.5
    assert m.purge(60) == 1
