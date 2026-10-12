import asyncio
import json
import logging

import pytest

from solution import CorrelationMiddleware, JsonFormatter, bind_correlation_id, correlation_id, extract_correlation_id

CREATED = 1_700_000_000.25  # 2023-11-14T22:13:20.250Z


def make_record(msg="hello", *args, level=logging.INFO, exc_info=None, **extra):
    record = logging.LogRecord("app.orders", level, __file__, 10, msg, args, exc_info)
    record.created = CREATED
    for k, v in extra.items():
        setattr(record, k, v)
    return record


def fmt(record, service="orders-api"):
    line = JsonFormatter(service).format(record)
    assert "\n" not in line, "один запис = один рядок"
    return json.loads(line)


# ---------- JsonFormatter -----------------------------------------------------


def test_basic_fields():
    assert fmt(make_record("order %s created", 42)) == {
        "ts": "2023-11-14T22:13:20.250Z", "level": "INFO", "service": "orders-api", "logger": "app.orders", "message": "order 42 created"}


def test_level_names():
    assert fmt(make_record(level=logging.ERROR))["level"] == "ERROR"
    assert fmt(make_record(level=logging.WARNING))["level"] == "WARNING"


def test_correlation_id_is_added_only_when_bound():
    assert "correlation_id" not in fmt(make_record())
    with bind_correlation_id("req-12345678"):
        assert fmt(make_record())["correlation_id"] == "req-12345678"
    assert "correlation_id" not in fmt(make_record())


def test_extra_fields_are_included():
    data = fmt(make_record(order_id=7, amount=12.5, tags=["a", "b"]))
    assert data["order_id"] == 7 and data["amount"] == 12.5 and data["tags"] == ["a", "b"]


def test_extra_cannot_overwrite_reserved_keys():
    data = fmt(make_record("real", level=logging.INFO, service="evil", correlation_id="evil", ts="evil"))
    assert data["service"] == "orders-api" and data["ts"] == "2023-11-14T22:13:20.250Z"
    assert "correlation_id" not in data
    with bind_correlation_id("good-1234"):
        assert fmt(make_record(correlation_id="evil"))["correlation_id"] == "good-1234"


def test_exception_info():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        data = fmt(make_record("failed", exc_info=sys.exc_info()))
    assert data["exc"]["type"] == "ValueError" and data["exc"]["message"] == "boom"
    assert "Traceback" in data["exc"]["stack"] and "ValueError: boom" in data["exc"]["stack"]
    assert "exc" not in fmt(make_record())


def test_sensitive_keys_are_redacted_also_when_nested():
    data = fmt(make_record(password="hunter2", Authorization="Bearer abc", user={"name": "x", "api_key": "k", "profile": {"Session_Token": "t"}},
                           x_cookie="c", note="ok"))
    assert data["password"] == "***" and data["Authorization"] == "***" and data["x_cookie"] == "***"
    assert data["user"] == {"name": "x", "api_key": "***", "profile": {"Session_Token": "***"}}
    assert data["note"] == "ok"


def test_newlines_in_messages_cannot_forge_log_lines():
    line = JsonFormatter("s").format(make_record("login ok\n{\"level\": \"CRITICAL\"}"))
    assert "\n" not in line and len(line.splitlines()) == 1
    assert json.loads(line)["level"] == "INFO"


def test_unicode_stays_readable_and_unserializable_values_become_strings():
    line = JsonFormatter("s").format(make_record("замовлення", obj=object, path=__import__("pathlib").Path("x")))
    assert "замовлення" in line
    data = json.loads(line)
    assert data["path"] == "x" and isinstance(data["obj"], str)


def test_milliseconds_are_truncated_not_rounded():
    record = make_record()
    record.created = 1_700_000_000.75
    assert fmt(record)["ts"].endswith(":20.750Z")
    record.created = 1_700_000_000.0
    assert fmt(record)["ts"].endswith(":20.000Z")
    record.created = 1_700_000_000.9996
    assert fmt(record)["ts"].endswith(":20.999Z")


def test_works_with_a_real_logger():
    import io
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("svc"))
    log = logging.getLogger("t101-real")
    log.handlers[:] = [handler]
    log.propagate = False
    log.setLevel(logging.INFO)
    with bind_correlation_id("abcdefgh1"):
        log.info("paid", extra={"order_id": 5})
    data = json.loads(stream.getvalue())
    assert data["message"] == "paid" and data["order_id"] == 5 and data["correlation_id"] == "abcdefgh1" and data["logger"] == "t101-real"


# ---------- correlation id ----------------------------------------------------


def test_bind_restores_previous_value_even_after_exception():
    assert correlation_id.get() is None
    with bind_correlation_id("outer-1234"):
        with pytest.raises(RuntimeError):
            with bind_correlation_id("inner-1234"):
                assert correlation_id.get() == "inner-1234"
                raise RuntimeError
        assert correlation_id.get() == "outer-1234"
    assert correlation_id.get() is None


def gen():
    return "generated-0001"


@pytest.mark.parametrize("headers, expected", [
    ({"X-Request-ID": "abc-1234.def_5"}, "abc-1234.def_5"),
    ({"x-request-id": "abcdefgh"}, "abcdefgh"),
    ({"X-REQUEST-ID": "a" * 64}, "a" * 64),
    ({}, "generated-0001"),
    ({"X-Request-ID": ""}, "generated-0001"),
    ({"X-Request-ID": "short"}, "generated-0001"),
    ({"X-Request-ID": "a" * 65}, "generated-0001"),
    ({"X-Request-ID": "has space 12345"}, "generated-0001"),
    ({"X-Request-ID": "abcdefgh\nINFO fake"}, "generated-0001"),
    ({"X-Request-ID": "abcdefgh\n"}, "generated-0001"),
    ({"X-Request-ID": "<script>alert(1)</script>"}, "generated-0001"),
    ({"Other": "abcdefgh12"}, "generated-0001"),
])
def test_extract_correlation_id(headers, expected):
    assert extract_correlation_id(headers, gen) == expected


# ---------- middleware --------------------------------------------------------


def call(middleware, scope, after=None):
    sent = []
    after = {} if after is None else after

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    async def main():
        try:
            await middleware(scope, receive, send)
        finally:
            after["cid"] = correlation_id.get()  # той самий task: без reset значення б лишилось

    asyncio.run(main())
    return sent, after


def make_app(seen):
    async def app(scope, receive, send):
        seen["cid"] = correlation_id.get()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain"), (b"X-Request-ID", b"old")]})
        await send({"type": "http.response.body", "body": b"ok"})
    return app


def test_middleware_uses_incoming_id_and_echoes_it():
    seen = {}
    sent, _ = call(CorrelationMiddleware(make_app(seen), gen), {"type": "http", "headers": [(b"x-request-id", b"client-id-0001")]})
    assert seen["cid"] == "client-id-0001"
    start = sent[0]
    ids = [v for k, v in start["headers"] if k.lower() == b"x-request-id"]
    assert ids == [b"client-id-0001"], "старий заголовок замінено, а не дублюється"
    assert (b"content-type", b"text/plain") in start["headers"] and sent[1]["body"] == b"ok"


def test_middleware_generates_id_when_missing_or_invalid():
    for headers in ([], [(b"x-request-id", b"bad id!")]):
        seen = {}
        sent, _ = call(CorrelationMiddleware(make_app(seen), gen), {"type": "http", "headers": headers})
        assert seen["cid"] == "generated-0001"
        assert (b"x-request-id", b"generated-0001") in sent[0]["headers"]


def test_middleware_resets_the_context_afterwards_and_on_errors():
    seen = {}
    _, after = call(CorrelationMiddleware(make_app(seen), gen), {"type": "http", "headers": []})
    assert after["cid"] is None

    async def broken(scope, receive, send):
        raise RuntimeError("boom")

    after = {}
    with pytest.raises(RuntimeError):
        call(CorrelationMiddleware(broken, gen), {"type": "http", "headers": []}, after)
    assert after["cid"] is None


def test_non_http_scopes_pass_through():
    calls = []

    async def app(scope, receive, send):
        calls.append((scope["type"], correlation_id.get()))

    sent, _ = call(CorrelationMiddleware(app, gen), {"type": "lifespan"})
    assert calls == [("lifespan", None)] and sent == []


def test_logs_written_during_a_request_carry_its_id():
    import io
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter("svc"))
    log = logging.getLogger("t101-mw")
    log.handlers[:] = [handler]
    log.propagate = False
    log.setLevel(logging.INFO)

    async def app(scope, receive, send):
        log.info("handling")
        await send({"type": "http.response.start", "status": 204, "headers": []})

    call(CorrelationMiddleware(app, gen), {"type": "http", "headers": [(b"x-request-id", b"trace-abcdef1")]})
    assert json.loads(stream.getvalue())["correlation_id"] == "trace-abcdef1"
