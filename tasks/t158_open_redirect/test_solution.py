import pytest

from solution import safe_redirect_target

HOSTS = ["app.example.com", "admin.example.com:8443"]
D = "/home"


def check(url, hosts=HOSTS):
    return safe_redirect_target(url, hosts, D)


# --- дозволене -----------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    ["/", "/dashboard", "/a/b/c?x=1&y=2#frag", "/search?q=//evil.com", "/%2F/evil.com", "/..//x", "/path with space",
     "/üñí", "/a​b"],
)
def test_local_paths_are_returned_unchanged(url):
    assert check(url) == url


@pytest.mark.parametrize(
    "url",
    ["https://app.example.com/profile", "http://app.example.com", "https://app.example.com:443/x",
     "http://app.example.com:80/x", "HTTPS://APP.EXAMPLE.COM/x", "https://app.example.com?x=1",
     "https://admin.example.com:8443/panel", "https://app.example.com/a?next=https://evil.com"],
)
def test_allowed_absolute_urls_are_returned_unchanged(url):
    assert check(url) == url


def test_default_is_returned_on_refusal_and_is_customisable():
    assert safe_redirect_target("//evil.com", HOSTS) == "/"
    assert safe_redirect_target("//evil.com", HOSTS, default="/login") == "/login"


# --- відмови: не-локальні шляхи ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    ["//evil.com", "//evil.com/x", "///evil.com", "////evil.com", "//app.example.com/x",  # навіть «свій» хост через //
     "/\\evil.com", "\\\\evil.com", "\\/evil.com", "/\\/evil.com", "/a\\b"],
)
def test_protocol_relative_and_backslash_tricks(url):
    assert check(url) == D


@pytest.mark.parametrize("url", ["/\t/evil.com", "/\n/evil.com", "/\r/evil.com", "\t//evil.com", "/\x00/evil.com",
                                 "/a\x1fb", "/a\x7fb", "/\t\t/evil.com"])
def test_control_characters_are_refused(url):
    assert check(url) == D


@pytest.mark.parametrize("url", [" /dashboard", "/dashboard ", " /x", " https://app.example.com", "\n/x"])
def test_surrounding_whitespace_is_refused(url):
    assert check(url) == D


@pytest.mark.parametrize("url", ["dashboard", "evil.com", "evil.com/x", "?a=1", "#top", "./x", "../x", "www.evil.com",
                                 "%2F%2Fevil.com"])
def test_relative_without_leading_slash_is_refused(url):
    assert check(url) == D


# --- відмови: абсолютні URL -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    ["https://evil.com", "http://evil.com/app.example.com", "https://evil.com/?h=app.example.com",
     "https://app.example.com.evil.com/x", "https://evilapp.example.com/x", "https://sub.app.example.com/x",
     "https://app.example.com./x", "https://app.example.org/x", "https://example.com/x"],
)
def test_other_hosts_are_refused(url):
    assert check(url) == D


@pytest.mark.parametrize(
    "url",
    ["https://app.example.com@evil.com/x", "https://evil.com@app.example.com/x", "https://user:pw@app.example.com/x",
     "https://app.example.com:pw@evil.com", "https://@app.example.com", "https://app.example.com%40evil.com@evil.com"],
)
def test_userinfo_is_refused(url):
    assert check(url) == D


@pytest.mark.parametrize(
    "url",
    ["https:///evil.com", "https:evil.com", "https:/evil.com", "http:evil.com", "https://", "https:", "//", "https://:443/x"],
)
def test_missing_host_is_refused(url):
    assert check(url) == D


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<script>alert(1)</script>", "file:///etc/passwd",
     "ftp://app.example.com/x", "vbscript:x", "mailto:a@app.example.com", "ws://app.example.com", "blob:https://app.example.com/x",
     "javascript://app.example.com/%0aalert(1)"],
)
def test_non_http_schemes_are_refused(url):
    assert check(url) == D


@pytest.mark.parametrize(
    "url",
    ["https://app.example.com:8443/x", "http://app.example.com:8080/x", "https://app.example.com:444/x",
     "https://admin.example.com/x", "https://admin.example.com:443/x", "https://admin.example.com:9999/x",
     "https://app.example.com:abc/x", "https://app.example.com:99999/x", "https://app.example.com:-1/x",
     "http://app.example.com:443/x", "https://app.example.com:80/x"],
)
def test_ports_must_match_the_allowed_entry(url):
    assert check(url) == D


def test_lookalike_unicode_and_idn_hosts_are_refused():
    assert check("https://аpp.example.com/x") == D  # перша «а» кирилична
    assert check("https://app.example.com／x") == D  # повноширинна скісна риска
    assert check("https://app。example。com/x") == D  # ідеографічні крапки
    assert check("https://ａpp.example.com/x") == D


def test_ipv6_and_ip_hosts_are_refused_unless_listed():
    assert check("http://[::1]/x") == D
    assert check("http://127.0.0.1/x") == D
    assert check("http://2130706433/x") == D
    assert check("http://127.0.0.1/x", ["127.0.0.1"]) == "http://127.0.0.1/x"


# --- загальне ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [None, 5, b"/x", ["/x"], {"a": 1}, "", "x" * 3000, "/" + "a" * 2048])
def test_non_str_empty_and_too_long(bad):
    assert check(bad) == D


def test_exactly_2048_chars_is_allowed():
    url = "/" + "a" * 2047
    assert check(url) == url


def test_allowed_hosts_are_case_insensitive_and_can_be_any_iterable():
    assert check("https://app.example.com/x", ["APP.Example.COM"]) == "https://app.example.com/x"
    assert check("https://app.example.com/x", {"app.example.com"}) == "https://app.example.com/x"
    assert check("https://app.example.com/x", (h for h in ["app.example.com"])) == "https://app.example.com/x"
    assert check("https://app.example.com/x", []) == D
    assert check("/local", []) == "/local"  # локальні шляхи не залежать від списку хостів


def test_never_raises_on_hostile_input():
    for url in ["http://[", "http://[::1", "https://a b/", "http://%zz/", "http://app.example.com:\x00", "\ud800", "https://℀.com"]:
        assert check(url) == D
