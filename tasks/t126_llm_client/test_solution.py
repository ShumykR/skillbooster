import json

import pytest

from solution import (AuthError, BadRequest, BadResponse, LLMError, RateLimited, ServerError, StreamError, Timeout, build_request,
                      classify_response, complete, iter_sse_events, stream_text)


def chunk(text=None, finish=None, **extra):
    delta = {} if text is None else {"content": text}
    return "data: " + json.dumps({"choices": [{"delta": delta, "finish_reason": finish}], **extra})


# ---------- build_request ------------------------------------------------------------


def test_build_request_minimal_and_full():
    assert build_request("m", "hi") == {"model": "m", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 512, "temperature": 0.2}
    full = build_request("m", "hi", system="be brief", max_tokens=50, temperature=0, stream=True)
    assert full["messages"] == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]
    assert full["stream"] is True and full["stream_options"] == {"include_usage": True} and full["temperature"] == 0
    assert "stream" not in build_request("m", "hi") and "stream_options" not in build_request("m", "hi")


@pytest.mark.parametrize("kwargs", [dict(model=""), dict(user="   "), dict(max_tokens=0), dict(temperature=-0.1), dict(temperature=2.1)])
def test_build_request_validation(kwargs):
    args = {"model": "m", "user": "hi", **kwargs}
    with pytest.raises(ValueError):
        build_request(args.pop("model"), args.pop("user"), **args)


def test_empty_system_prompt_is_still_sent_but_none_is_not():
    assert build_request("m", "hi", system="")["messages"][0] == {"role": "system", "content": ""}
    assert len(build_request("m", "hi", system=None)["messages"]) == 1


# ---------- classify_response -------------------------------------------------------------


def test_success_codes_pass():
    for status in (200, 201, 204):
        assert classify_response(status, {}, {}) is None


@pytest.mark.parametrize("status, error, retryable", [
    (401, AuthError, False), (403, AuthError, False), (400, BadRequest, False), (404, BadRequest, False), (413, BadRequest, False),
    (422, BadRequest, False), (418, BadRequest, False), (429, RateLimited, True), (500, ServerError, True), (503, ServerError, True),
])
def test_status_classification(status, error, retryable):
    with pytest.raises(error) as info:
        classify_response(status, {}, {"error": {"message": "nope"}})
    assert info.value.retryable is retryable and str(info.value) == "nope" and isinstance(info.value, LLMError)


def test_message_fallbacks():
    with pytest.raises(ServerError) as info:
        classify_response(502, {}, "x" * 500)
    assert str(info.value) == "x" * 200
    with pytest.raises(BadRequest) as info:
        classify_response(400, {}, {"detail": "other"})
    assert "other" in str(info.value)


@pytest.mark.parametrize("headers, expected", [
    ({"Retry-After": "7"}, 7.0), ({"retry-after": "2.5"}, 2.5), ({"RETRY-AFTER": "0"}, 0.0),
    ({"Retry-After": "-3"}, None), ({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, None), ({}, None)])
def test_retry_after_header(headers, expected):
    with pytest.raises(RateLimited) as info:
        classify_response(429, headers, {})
    assert info.value.retry_after == expected


# ---------- SSE parsing ---------------------------------------------------------------------


def test_events_are_separated_by_blank_lines():
    lines = ["data: one", "", "data: two", "", ""]
    assert list(iter_sse_events(iter(lines))) == ["one", "two"]


def test_multiline_data_comments_and_other_fields():
    lines = [": keep-alive", "event: message", "id: 7", "data: a", "data:b", "retry: 100", "", "event: ping", "", "data:  spaced", ""]
    assert list(iter_sse_events(iter(lines))) == ["a\nb", " spaced"]


def test_last_event_without_blank_line_is_delivered():
    assert list(iter_sse_events(iter(["data: x", "", "data: tail"]))) == ["x", "tail"]
    assert list(iter_sse_events(iter([]))) == []


def test_stream_text_joins_deltas_and_stops_at_done():
    lines = [chunk("Hel"), "", chunk("lo"), "", chunk(""), "", chunk(None), "", "data: [DONE]", "", chunk("never"), ""]
    assert "".join(stream_text(iter(lines))) == "Hello"


def test_stream_ends_at_finish_reason_without_done():
    lines = [chunk("a"), "", chunk("b", finish="stop"), "", chunk("late"), ""]
    assert list(stream_text(iter(lines))) == ["a", "b"]


def test_usage_chunk_without_choices_is_skipped():
    lines = [chunk("a"), "", 'data: {"usage": {"total_tokens": 5}, "choices": []}', "", chunk("b"), "", "data: [DONE]", ""]
    assert list(stream_text(iter(lines))) == ["a", "b"]


def test_stream_errors():
    with pytest.raises(StreamError):
        list(stream_text(iter(['data: {"error": {"message": "overloaded"}}', ""])))
    with pytest.raises(StreamError):
        list(stream_text(iter(["data: {broken", ""])))
    with pytest.raises(StreamError):
        list(stream_text(iter(["data: [1, 2]", ""])))


def test_interrupted_stream_raises_after_yielding_what_arrived():
    gen = stream_text(iter([chunk("par"), "", chunk("tial"), ""]))
    got = [next(gen), next(gen)]
    assert got == ["par", "tial"]
    with pytest.raises(StreamError, match="interrupted"):
        next(gen)
    with pytest.raises(StreamError, match="interrupted"):
        list(stream_text(iter([])))


# ---------- complete ----------------------------------------------------------------------------


OK = (200, {}, {"choices": [{"message": {"content": "hi there"}}], "usage": {"total_tokens": 9}})


class Transport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply


class Sleeper:
    def __init__(self):
        self.waits = []

    def __call__(self, seconds):
        self.waits.append(seconds)


REQ = build_request("m", "hi")


def test_success_returns_text_usage_and_attempts():
    t = Transport(OK)
    assert complete(t, REQ, timeout=12) == {"text": "hi there", "usage": {"total_tokens": 9}, "attempts": 1}
    assert t.calls == [(REQ, 12)]


def test_usage_defaults_to_empty():
    t = Transport((200, {}, {"choices": [{"message": {"content": "x"}}]}))
    assert complete(t, REQ)["usage"] == {}


def test_retries_5xx_with_exponential_backoff():
    t, s = Transport((503, {}, {}), (500, {}, {}), OK), Sleeper()
    result = complete(t, REQ, base_delay=1.5, sleep=s)
    assert result["attempts"] == 3 and s.waits == [1.5, 3.0]
    t, s = Transport((503, {}, {}), (503, {}, {}), (503, {}, {}), OK), Sleeper()
    complete(t, REQ, max_retries=3, base_delay=1, sleep=s)
    assert s.waits == [1, 2, 4]


def test_gives_up_after_max_retries_with_the_last_error():
    t, s = Transport((500, {}, {"error": {"message": "first"}}), (503, {}, {"error": {"message": "last"}})), Sleeper()
    with pytest.raises(ServerError, match="last"):
        complete(t, REQ, max_retries=1, sleep=s)
    assert len(t.calls) == 2 and len(s.waits) == 1


def test_zero_retries_means_a_single_attempt():
    t, s = Transport((500, {}, {})), Sleeper()
    with pytest.raises(ServerError):
        complete(t, REQ, max_retries=0, sleep=s)
    assert len(t.calls) == 1 and s.waits == []


def test_non_retryable_errors_fail_immediately():
    for status, error in ((401, AuthError), (400, BadRequest)):
        t, s = Transport((status, {}, {})), Sleeper()
        with pytest.raises(error):
            complete(t, REQ, sleep=s)
        assert len(t.calls) == 1 and s.waits == []


def test_retry_after_is_respected_and_beats_backoff():
    t, s = Transport((429, {"Retry-After": "4"}, {}), (429, {}, {}), OK), Sleeper()
    complete(t, REQ, base_delay=1.0, sleep=s)
    assert s.waits == [4.0, 2.0], "перша пауза з Retry-After, друга за експонентою від спроби 2"


def test_too_long_retry_after_fails_fast():
    t, s = Transport((429, {"Retry-After": "120"}, {})), Sleeper()
    with pytest.raises(RateLimited) as info:
        complete(t, REQ, max_wait=30, sleep=s)
    assert info.value.retry_after == 120 and s.waits == [] and len(t.calls) == 1


def test_retry_after_equal_to_max_wait_is_waited():
    t, s = Transport((429, {"Retry-After": "30"}, {}), OK), Sleeper()
    complete(t, REQ, max_wait=30, sleep=s)
    assert s.waits == [30.0]


def test_timeouts_are_retried_and_reported():
    t, s = Transport(TimeoutError(), OK), Sleeper()
    assert complete(t, REQ, sleep=s)["attempts"] == 2
    t = Transport(TimeoutError())
    with pytest.raises(Timeout):
        complete(t, REQ, max_retries=1, sleep=Sleeper())
    assert len(t.calls) == 2


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{"message": {}}]}, {"choices": [{"message": {"content": ""}}]},
                                  {"choices": [{"message": {"content": None}}]}, "oops"])
def test_missing_text_is_a_bad_response(body):
    t = Transport((200, {}, body))
    with pytest.raises(BadResponse):
        complete(t, REQ, sleep=Sleeper())
    assert len(t.calls) == 1, "BadResponse не повторюється"
