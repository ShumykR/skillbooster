import pytest

from solution import mask_pii


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("user john.doe@example.com logged in", "user j***@example.com logged in"),
        ("a@b.co and Zed_99@mail.example.org", "a***@b.co and Z***@mail.example.org"),
    ],
)
def test_email(raw, expected):
    assert mask_pii(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("card 4111111111111111 charged", "card **** **** **** 1111 charged"),
        ("card 4111 1111 1111 1111.", "card **** **** **** 1111."),
        ("card 4111-1111-1111-1111", "card **** **** **** 1111"),
        ("amex 378282246310005", "amex **** **** **** 0005"),
    ],
)
def test_valid_cards_masked(raw, expected):
    assert mask_pii(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "order 1234567890123 shipped",         # 13 цифр, не проходить Луна
        "trace_id=1700000000123457",           # 16 цифр, не проходить Луна
        "phone 380 50 123 45 67 ok",
        "total 123456",
    ],
)
def test_non_cards_untouched(raw):
    assert mask_pii(raw) == raw


def test_bearer_token():
    assert mask_pii("Authorization: Bearer eyJhbGciOi.abc-DEF_123.sig") == "Authorization: Bearer [REDACTED]"
    assert mask_pii("header bearer abc123 end") == "header bearer [REDACTED] end"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("login password=hunter2 ok", "login password=[REDACTED] ok"),
        ("password: hunter2, user=bob", "password: [REDACTED], user=bob"),
        ('{"user": "bob", "password": "hunter2"}', '{"user": "bob", "password": "[REDACTED]"}'),
        ("api_key=sk-12345&x=1", "api_key=[REDACTED]&x=1"),
        ("X-Api-Key: abcDEF", "X-Api-Key: [REDACTED]"),
        ("access_token=abc.def", "access_token=[REDACTED]"),
        ('{"secret":"s3"}', '{"secret":"[REDACTED]"}'),
    ],
)
def test_secret_keys(raw, expected):
    assert mask_pii(raw) == expected


def test_normal_text_untouched():
    for s in ["GET /health 200 12ms", "tokenizer=bert", "user_id=42 action=login", "никаких секретов тут нет"]:
        assert mask_pii(s) == s


@pytest.mark.parametrize(
    "raw",
    [
        "john@example.com paid with 4111 1111 1111 1111 using Bearer abc.def password=x",
        '{"password": "p", "email": "q@w.io"}',
    ],
)
def test_idempotent(raw):
    once = mask_pii(raw)
    assert mask_pii(once) == once


def test_multiple_items_in_one_line():
    out = mask_pii("bob@x.io card 4111111111111111 token=abc")
    assert out == "b***@x.io card **** **** **** 1111 token=[REDACTED]"
