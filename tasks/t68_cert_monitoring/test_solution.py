import pytest

from solution import DAY, CertInfo, check_certificate, days_left, hostname_matches, monitor, should_renew

NOW = 1_800_000_000.0


def cert(days_valid_left=60, age_days=30, sans=("example.com", "www.example.com"), **kw):
    return CertInfo(
        subject=kw.pop("subject", "CN=example.com"),
        issuer=kw.pop("issuer", "CN=R3,O=Let's Encrypt"),
        not_before=NOW - age_days * DAY,
        not_after=NOW + days_valid_left * DAY,
        sans=list(sans),
        **kw,
    )


# ---------- hostname_matches --------------------------------------------------


@pytest.mark.parametrize("pattern, host, expected", [
    ("example.com", "example.com", True),
    ("Example.COM", "example.com", True),
    ("example.com.", "example.com", True),
    ("example.com", "www.example.com", False),
    ("*.example.com", "www.example.com", True),
    ("*.example.com", "WWW.Example.com", True),
    ("*.example.com", "example.com", False),
    ("*.example.com", "a.b.example.com", False),
    ("*.example.com", ".example.com", False),
    ("f*.example.com", "foo.example.com", False),
    ("*oo.example.com", "foo.example.com", False),
    ("www.*.example.com", "www.a.example.com", False),
    ("*.com", "example.com", False),
    ("*.co.uk", "example.co.uk", True),
    ("*", "localhost", False),
    ("*.example.com", "evilexample.com", False),
    ("*.example.com", "www.example.com.evil.net", False),
    ("example.com", "example.com.evil.net", False),
])
def test_hostname_matching(pattern, host, expected):
    assert hostname_matches(pattern, host) is expected


# ---------- days_left ---------------------------------------------------------


@pytest.mark.parametrize("delta, expected", [
    (0, 0), (DAY - 1, 0), (DAY, 1), (30.5 * DAY, 30), (-1, -1), (-DAY, -1), (-DAY - 1, -2),
])
def test_days_left_floor(delta, expected):
    assert days_left(NOW + delta, NOW) == expected


# ---------- check_certificate -------------------------------------------------


def test_healthy_certificate():
    assert check_certificate(cert(), "www.example.com", NOW) == {"status": "ok", "days_left": 60, "problems": []}


@pytest.mark.parametrize("left, status", [(60, "ok"), (22, "ok"), (21, "warning"), (8, "warning"), (7, "critical"), (0, "critical")])
def test_status_by_days_left(left, status):
    assert check_certificate(cert(days_valid_left=left), "example.com", NOW)["status"] == status


def test_custom_thresholds():
    c = cert(days_valid_left=40)
    assert check_certificate(c, "example.com", NOW, warn_days=45, crit_days=10)["status"] == "warning"
    assert check_certificate(c, "example.com", NOW, warn_days=45, crit_days=40)["status"] == "critical"


def test_expired_certificate():
    result = check_certificate(cert(days_valid_left=-3), "example.com", NOW)
    assert result == {"status": "expired", "days_left": -3, "problems": ["expired"]}


def test_not_yet_valid():
    c = cert(age_days=-2)
    result = check_certificate(c, "example.com", NOW)
    assert result["status"] == "invalid" and result["problems"] == ["not_yet_valid"]


def test_hostname_mismatch_uses_san_not_cn():
    result = check_certificate(cert(sans=["other.example.com"]), "example.com", NOW)
    assert result["status"] == "invalid" and result["problems"] == ["hostname_mismatch"]
    no_san = check_certificate(cert(sans=[]), "example.com", NOW)
    assert no_san["problems"] == ["hostname_mismatch"], "CN=example.com не рятує: без SAN сучасні клієнти відмовляють"


def test_wildcard_san_covers_one_level_only():
    c = cert(sans=["*.example.com"])
    assert check_certificate(c, "api.example.com", NOW)["problems"] == []
    assert check_certificate(c, "example.com", NOW)["problems"] == ["hostname_mismatch"]
    assert check_certificate(c, "a.b.example.com", NOW)["problems"] == ["hostname_mismatch"]


def test_incomplete_chain_and_self_signed():
    assert check_certificate(cert(chain_ok=False), "example.com", NOW) == {
        "status": "invalid", "days_left": 60, "problems": ["chain_incomplete"]}
    result = check_certificate(cert(subject="CN=x", issuer="CN=x"), "example.com", NOW)
    assert result["status"] == "invalid" and result["problems"] == ["self_signed"]


def test_validity_too_long_is_informational():
    long_lived = CertInfo("CN=a", "CN=ca", NOW - 10 * DAY, NOW + 600 * DAY, ["example.com"])
    result = check_certificate(long_lived, "example.com", NOW)
    assert result["status"] == "ok" and result["problems"] == ["validity_too_long"]
    boundary = CertInfo("CN=a", "CN=ca", NOW - 98 * DAY, NOW + 300 * DAY, ["example.com"])  # рівно 398 діб
    assert check_certificate(boundary, "example.com", NOW)["problems"] == []


def test_expired_beats_everything_and_problems_are_sorted():
    c = cert(days_valid_left=-1, sans=["other.com"], chain_ok=False)
    result = check_certificate(c, "example.com", NOW)
    assert result["status"] == "expired"
    assert result["problems"] == ["chain_incomplete", "expired", "hostname_mismatch"]


def test_invalid_beats_expiry_urgency():
    result = check_certificate(cert(days_valid_left=2, chain_ok=False), "example.com", NOW)
    assert result["status"] == "invalid"


# ---------- should_renew ------------------------------------------------------


def renew(left_days, **kw):
    return should_renew(NOW + left_days * DAY, NOW, **kw)


def test_not_due_and_due():
    assert renew(45) == {"renew": False, "reason": "not_due"}
    assert renew(31) == {"renew": False, "reason": "not_due"}
    assert renew(30) == {"renew": True, "reason": "due"}
    assert renew(5) == {"renew": True, "reason": "due"}


def test_custom_renew_before():
    assert renew(20, renew_before_days=14) == {"renew": False, "reason": "not_due"}
    assert renew(14, renew_before_days=14)["renew"] is True


def test_expired_is_renewed_immediately_even_in_backoff():
    result = renew(-2, failures=4, last_attempt=NOW - 10)
    assert result == {"renew": True, "reason": "expired"}


def test_rate_limit_blocks_even_expired_but_not_when_not_due():
    assert renew(10, issued_this_week=5) == {"renew": False, "reason": "rate_limited"}
    assert renew(-1, issued_this_week=7) == {"renew": False, "reason": "rate_limited"}
    assert renew(10, issued_this_week=4)["renew"] is True
    assert renew(60, issued_this_week=9) == {"renew": False, "reason": "not_due"}


@pytest.mark.parametrize("failures, waited_hours, expected", [
    (1, 0.5, ("backoff", False)), (1, 1, ("retry", True)),
    (2, 1.9, ("backoff", False)), (2, 2, ("retry", True)),
    (3, 3.9, ("backoff", False)), (3, 4, ("retry", True)),
    (5, 15.9, ("backoff", False)), (5, 16, ("retry", True)),
    (9, 23.9, ("backoff", False)), (9, 24, ("retry", True)),
    (20, 24, ("retry", True)),
])
def test_backoff_after_failures(failures, waited_hours, expected):
    result = renew(10, failures=failures, last_attempt=NOW - waited_hours * 3600)
    assert (result["reason"], result["renew"]) == expected


# ---------- monitor -----------------------------------------------------------


def test_monitor_orders_items_and_sets_exit_code():
    certs = [
        ("ok.example.com", cert(days_valid_left=80, sans=["ok.example.com"])),
        ("warn.example.com", cert(days_valid_left=15, sans=["warn.example.com"])),
        ("crit.example.com", cert(days_valid_left=3, sans=["crit.example.com"])),
        ("bad.example.com", cert(days_valid_left=50, sans=["other.example.com"])),
        ("dead.example.com", cert(days_valid_left=-5, sans=["dead.example.com"])),
        ("crit2.example.com", cert(days_valid_left=1, sans=["crit2.example.com"])),
    ]
    report = monitor(certs, NOW)
    assert report["exit_code"] == 2
    assert [(i["host"], i["status"]) for i in report["items"]] == [
        ("dead.example.com", "expired"), ("bad.example.com", "invalid"),
        ("crit2.example.com", "critical"), ("crit.example.com", "critical"),
        ("warn.example.com", "warning"), ("ok.example.com", "ok"),
    ]
    assert report["items"][0] == {"host": "dead.example.com", "status": "expired", "days_left": -5, "problems": ["expired"]}


@pytest.mark.parametrize("left, code", [(80, 0), (15, 1), (3, 2), (-1, 2)])
def test_monitor_exit_codes(left, code):
    assert monitor([("a.example.com", cert(days_valid_left=left, sans=["a.example.com"]))], NOW)["exit_code"] == code


def test_monitor_empty_and_thresholds_and_tie_break_by_host():
    assert monitor([], NOW) == {"exit_code": 0, "items": []}
    certs = [("b.example.com", cert(days_valid_left=10, sans=["b.example.com"])), ("a.example.com", cert(days_valid_left=10, sans=["a.example.com"]))]
    report = monitor(certs, NOW, warn_days=30, crit_days=12)
    assert [i["host"] for i in report["items"]] == ["a.example.com", "b.example.com"]
    assert {i["status"] for i in report["items"]} == {"critical"}
