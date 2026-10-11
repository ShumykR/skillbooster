import pytest

from solution import check_headers

GOOD = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' https://cdn.example.com; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Access-Control-Allow-Origin": "https://app.example.com",
    "Server": "nginx",
}


def without(*names):
    return {k: v for k, v in GOOD.items() if k not in names}


def with_(**kw):
    out = dict(GOOD)
    for k, v in kw.items():
        out[k.replace("_", "-")] = v
    return out


def test_good_headers_are_clean():
    assert check_headers(GOOD) == []


def test_empty_headers_report_everything_that_is_missing():
    assert check_headers({}) == ["csp_missing", "framing", "hsts", "nosniff", "referrer_policy"]


def test_header_names_are_case_insensitive():
    lowered = {k.lower(): v for k, v in GOOD.items()}
    shouted = {k.upper(): v for k, v in GOOD.items()}
    assert check_headers(lowered) == []
    assert check_headers(shouted) == []


@pytest.mark.parametrize(
    "value, bad",
    [
        ("max-age=31536000", False),
        ("max-age=15552000", False),
        ("max-age=15551999", True),
        ("max-age=0", True),
        ("includeSubDomains", True),
        ("MAX-AGE=31536000; preload", False),
    ],
)
def test_hsts(value, bad):
    assert check_headers(with_(Strict_Transport_Security=value)) == (["hsts"] if bad else [])


def test_hsts_missing():
    assert check_headers(without("Strict-Transport-Security")) == ["hsts"]


def test_csp_missing_is_not_also_weak():
    # без CSP зникає й frame-ancestors, але X-Frame-Options у GOOD є
    assert check_headers(without("Content-Security-Policy")) == ["csp_missing"]


@pytest.mark.parametrize(
    "csp",
    [
        "default-src *",
        "default-src 'self' 'unsafe-inline'",
        "script-src 'self' 'unsafe-eval'; frame-ancestors 'none'",
        "script-src * ; frame-ancestors 'none'",
        "img-src 'self'; frame-ancestors 'none'",  # немає ні script-src, ні default-src
    ],
)
def test_csp_weak(csp):
    assert check_headers(with_(Content_Security_Policy=csp)) == ["csp_weak"]


@pytest.mark.parametrize(
    "csp",
    [
        "default-src 'self'",
        "default-src 'unsafe-inline'; script-src 'self'",  # script-src має пріоритет
        "SCRIPT-SRC 'self' 'nonce-abc123'",
        "style-src 'self' 'unsafe-inline'; script-src 'self'",
    ],
)
def test_csp_strong_enough(csp):
    assert check_headers(with_(Content_Security_Policy=csp)) == []


@pytest.mark.parametrize("value, bad", [("nosniff", False), ("NOSNIFF", False), ("", True), ("sniff", True)])
def test_nosniff(value, bad):
    assert check_headers(with_(X_Content_Type_Options=value)) == (["nosniff"] if bad else [])


def test_framing_protection_either_way():
    csp_no_ancestors = "default-src 'self'"
    assert check_headers(with_(Content_Security_Policy=csp_no_ancestors)) == []  # є X-Frame-Options
    both_gone = without("X-Frame-Options")
    assert check_headers({**both_gone, "Content-Security-Policy": csp_no_ancestors}) == ["framing"]
    assert check_headers(both_gone) == []  # у CSP з GOOD є frame-ancestors
    assert check_headers(with_(X_Frame_Options="sameorigin")) == []
    assert check_headers({**with_(X_Frame_Options="ALLOW-FROM https://x.com"), "Content-Security-Policy": csp_no_ancestors}) == ["framing"]


def test_referrer_policy():
    assert check_headers(without("Referrer-Policy")) == ["referrer_policy"]


@pytest.mark.parametrize("origin, bad", [("*", True), ("null", True), ("https://app.example.com", False)])
def test_cors(origin, bad):
    assert check_headers(with_(Access_Control_Allow_Origin=origin)) == (["cors_wildcard"] if bad else [])


def test_no_cors_header_is_fine():
    assert check_headers(without("Access-Control-Allow-Origin")) == []


@pytest.mark.parametrize(
    "header, value",
    [("Server", "nginx/1.18.0"), ("Server", "Apache 2.4"), ("X-Powered-By", "Express 4"), ("X-Powered-By", "PHP/8.2")],
)
def test_version_leak(header, value):
    assert check_headers({**GOOD, header: value}) == ["version_leak"]


def test_server_without_version_is_fine():
    assert check_headers({**GOOD, "Server": "uvicorn", "X-Powered-By": "FastAPI"}) == []


def test_multiple_problems_sorted_and_unique():
    bad = {
        "Content-Security-Policy": "default-src *",
        "Access-Control-Allow-Origin": "*",
        "Server": "gunicorn/21.2",
    }
    assert check_headers(bad) == [
        "cors_wildcard",
        "csp_weak",
        "framing",
        "hsts",
        "nosniff",
        "referrer_policy",
        "version_leak",
    ]
