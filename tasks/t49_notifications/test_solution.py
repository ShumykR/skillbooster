import html as htmllib
import re
from urllib.parse import parse_qs, urlparse

import pytest

from solution import InvalidToken, NotificationService, PermanentFailure, TemplateError, TemporaryFailure

BASE = "https://app.example"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Transport:
    def __init__(self):
        self.sent = []
        self.script = []  # винятки для наступних викликів

    def __call__(self, message):
        if self.script:
            step = self.script.pop(0)
            if step is not None:
                raise step
        self.sent.append(message)


@pytest.fixture
def env():
    clock, transport = Clock(), Transport()
    service = NotificationService(transport, "s3cret", BASE, clock, max_attempts=3, retry_delay=60.0)
    return service, transport, clock


def mail(service, to="Ann@Example.com", kind="transactional", subject="Hi {{name}}", html="<p>{{ name }}</p>", text="Hi {{name}}",
         context=None, key=None):
    return service.enqueue(to, kind, subject, html, text, context if context is not None else {"name": "Ann"}, dedupe_key=key)


# ---------- шаблони й безпека ------------------------------------------------


def test_render_and_normalize_address(env):
    service, transport, _ = env
    assert mail(service, to="  Ann@Example.COM ") is True
    assert service.process() == 1
    m = transport.sent[0]
    assert (m.to, m.subject, m.text, m.html, m.kind) == ("ann@example.com", "Hi Ann", "Hi Ann", "<p>Ann</p>", "transactional")


def test_html_is_autoescaped_but_text_is_not(env):
    service, transport, _ = env
    mail(service, context={"name": '<script>alert("x")</script> & co'})
    service.process()
    m = transport.sent[0]
    assert m.html == "<p>" + htmllib.escape('<script>alert("x")</script> & co', quote=True) + "</p>"
    assert "<script>" not in m.html
    assert m.text == 'Hi <script>alert("x")</script> & co'


def test_subject_cannot_inject_headers(env):
    service, transport, _ = env
    mail(service, context={"name": "Ann\r\nBcc: evil@example.com"})
    service.process()
    subject = transport.sent[0].subject
    assert "\r" not in subject and "\n" not in subject
    assert subject == "Hi Ann  Bcc: evil@example.com"


@pytest.mark.parametrize("bad", ["no-at-sign", "a@b.com\r\nBcc: x@y.com", "a@b.com\nbcc:x", ""])
def test_bad_addresses_are_rejected(env, bad):
    service, _, _ = env
    with pytest.raises(ValueError):
        mail(service, to=bad)


def test_unknown_kind_and_unknown_template_variable(env):
    service, _, _ = env
    with pytest.raises(ValueError):
        mail(service, kind="spam")
    with pytest.raises(TemplateError):
        mail(service, subject="Hi {{ nope }}")
    assert service.pending() == 0


# ---------- marketing: відписка ----------------------------------------------


def test_marketing_has_unsubscribe_headers_and_footer(env):
    service, transport, _ = env
    mail(service, kind="marketing")
    service.process()
    m = transport.sent[0]
    url = service.unsubscribe_url("ann@example.com", "marketing")
    assert m.headers["List-Unsubscribe"] == f"<{url}>"
    assert m.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert m.text.endswith(f"\n\n--\nUnsubscribe: {url}")
    assert m.html.endswith(f'<p><a href="{htmllib.escape(url, quote=True)}">Unsubscribe</a></p>')


def test_transactional_has_no_unsubscribe_machinery(env):
    service, transport, _ = env
    mail(service)
    service.process()
    m = transport.sent[0]
    assert "List-Unsubscribe" not in m.headers and "Unsubscribe" not in m.text and "Unsubscribe" not in m.html


def test_unsubscribe_token_format(env):
    service, _, _ = env
    url = service.unsubscribe_url("ann@example.com", "marketing")
    parsed = urlparse(url)
    assert url.startswith(f"{BASE}/unsubscribe?token=")
    token = parse_qs(parsed.query)["token"][0]
    assert re.fullmatch(r"[A-Za-z0-9_\-]+\.[0-9a-f]{32}", token)


def test_unsubscribe_blocks_marketing_but_not_transactional(env):
    service, transport, _ = env
    token = parse_qs(urlparse(service.unsubscribe_url("ann@example.com", "marketing")).query)["token"][0]
    service.unsubscribe(token)
    service.unsubscribe(token)  # ідемпотентно
    assert service.is_suppressed("ann@example.com", "marketing")
    assert not service.is_suppressed("ann@example.com", "transactional")
    assert mail(service, kind="marketing") is False
    assert mail(service, kind="transactional") is True
    assert service.pending() == 1


@pytest.mark.parametrize("mutate", [
    lambda t: t[:-1] + ("0" if t[-1] != "0" else "1"),   # зіпсований підпис
    lambda t: "garbage",
    lambda t: "",
    lambda t: t.split(".")[0] + ".",                       # підпис обрізано
    lambda t: t.split(".")[1],                             # без payload
])
def test_forged_or_malformed_token_is_rejected(env, mutate):
    service, _, _ = env
    token = parse_qs(urlparse(service.unsubscribe_url("ann@example.com", "marketing")).query)["token"][0]
    with pytest.raises(InvalidToken):
        service.unsubscribe(mutate(token))
    assert not service.is_suppressed("ann@example.com", "marketing")


def test_token_cannot_be_reused_for_another_address(env):
    service, _, _ = env
    token = parse_qs(urlparse(service.unsubscribe_url("ann@example.com", "marketing")).query)["token"][0]
    payload, signature = token.split(".")
    import base64

    other = base64.urlsafe_b64encode(b"bob@example.com|marketing").rstrip(b"=").decode()
    with pytest.raises(InvalidToken):
        service.unsubscribe(f"{other}.{signature}")


def test_token_for_transactional_cannot_unsubscribe(env):
    service, _, _ = env
    token = parse_qs(urlparse(service.unsubscribe_url("ann@example.com", "transactional")).query)["token"][0]
    with pytest.raises(InvalidToken):
        service.unsubscribe(token)
    assert not service.is_suppressed("ann@example.com", "transactional")


def test_unsubscribe_after_enqueue_drops_the_message(env):
    service, transport, _ = env
    mail(service, kind="marketing")
    token = parse_qs(urlparse(service.unsubscribe_url("ann@example.com", "marketing")).query)["token"][0]
    service.unsubscribe(token)
    assert service.process() == 0
    assert transport.sent == [] and service.pending() == 0


# ---------- bounce -----------------------------------------------------------


def test_bounce_kinds(env):
    service, _, _ = env
    service.record_bounce("soft@example.com", "soft")
    assert not service.is_suppressed("soft@example.com", "marketing")
    service.record_bounce("spam@example.com", "complaint")
    assert service.is_suppressed("spam@example.com", "marketing")
    assert not service.is_suppressed("spam@example.com", "transactional")
    service.record_bounce("dead@example.com", "hard")
    assert service.is_suppressed("dead@example.com", "marketing") and service.is_suppressed("dead@example.com", "transactional")
    assert mail(service, to="dead@example.com") is False


def test_permanent_failure_suppresses_address_everywhere(env):
    service, transport, _ = env
    transport.script = [PermanentFailure("550 no such user")]
    mail(service)
    assert service.process() == 1
    assert service.pending() == 0 and service.is_suppressed("ann@example.com", "transactional")
    assert mail(service) is False


# ---------- черга і повтори --------------------------------------------------


def test_dedupe_key(env):
    service, _, _ = env
    assert mail(service, key="reset-42") is True
    assert mail(service, key="reset-42") is False
    assert mail(service, to="bob@example.com", key="reset-42") is True
    assert mail(service, key="reset-43") is True
    assert mail(service) is True and mail(service) is True  # без ключа дублікати дозволені
    assert service.pending() == 5


def test_temporary_failure_is_retried_with_backoff(env):
    service, transport, clock = env
    transport.script = [TemporaryFailure("421 try later"), TemporaryFailure("421"), None]
    mail(service)
    assert service.process() == 1 and service.pending() == 1
    assert service.process() == 0, "ще не час повторювати"
    clock.now += 60
    assert service.process() == 1 and service.pending() == 1
    clock.now += 119
    assert service.process() == 0, "друга пауза 120 с"
    clock.now += 1
    assert service.process() == 1
    assert len(transport.sent) == 1 and service.pending() == 0


def test_gives_up_into_dead_letters_after_max_attempts(env):
    service, transport, clock = env
    transport.script = [TemporaryFailure()] * 5
    mail(service)
    for _ in range(3):
        service.process()
        clock.now += 1000
    assert service.pending() == 0
    assert len(service.dead_letters) == 1 and service.dead_letters[0].to == "ann@example.com"
    assert not service.is_suppressed("ann@example.com", "transactional"), "тимчасові збої не придушують адресу"


def test_failed_message_does_not_block_the_queue(env):
    service, transport, _ = env
    transport.script = [TemporaryFailure(), None]
    mail(service, to="a@example.com")
    mail(service, to="b@example.com")
    assert service.process() == 2
    assert [m.to for m in transport.sent] == ["b@example.com"]
    assert service.pending() == 1


def test_token_signature_is_compared_in_constant_time():
    import inspect

    import solution

    assert "compare_digest" in inspect.getsource(solution.NotificationService), "підпис токена порівнюється через hmac.compare_digest"
