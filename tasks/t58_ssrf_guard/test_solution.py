import pytest

from solution import UnsafeURL, validate_url


def public(host):
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/path?q=1",
        "http://example.com:80/x",
        "https://example.com:443/",
        "http://93.184.216.34/",
        "https://sub.example.org/a/b",
    ],
)
def test_safe_urls_pass(url):
    assert validate_url(url, resolve=public) == url


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "gopher://example.com/",
        "javascript:alert(1)",
        "//example.com/no-scheme",
        "",
        "http://",
    ],
)
def test_bad_scheme_or_shape(url):
    with pytest.raises(UnsafeURL):
        validate_url(url, resolve=public)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.5/admin",
        "http://172.16.5.4/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://[fd00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:169.254.169.254]/",
    ],
)
def test_private_ip_literals_rejected(url):
    with pytest.raises(UnsafeURL):
        validate_url(url, resolve=public)


@pytest.mark.parametrize(
    "url",
    ["http://2130706433/", "http://0x7f.1/", "http://127.1/", "http://0177.0.0.1/", "http://0x7f000001/"],
)
def test_exotic_ip_notations_rejected(url):
    with pytest.raises(UnsafeURL):
        validate_url(url, resolve=public)


@pytest.mark.parametrize(
    "url",
    ["http://localhost/", "http://LOCALHOST:80/", "http://api.localhost/", "http://db.internal/"],
)
def test_localhost_names_rejected(url):
    with pytest.raises(UnsafeURL):
        validate_url(url, resolve=public)


def test_userinfo_trick_rejected():
    with pytest.raises(UnsafeURL):
        validate_url("http://example.com@127.0.0.1/", resolve=public)
    with pytest.raises(UnsafeURL):
        validate_url("http://user:pass@example.com/", resolve=public)


@pytest.mark.parametrize("url", ["https://example.com:22/", "http://example.com:8080/", "http://example.com:99999/"])
def test_unusual_ports_rejected(url):
    with pytest.raises(UnsafeURL):
        validate_url(url, resolve=public)


def test_dns_pointing_to_private_ip_rejected():
    with pytest.raises(UnsafeURL):
        validate_url("http://evil.example.com/", resolve=lambda h: ["10.0.0.7"])


def test_any_private_address_among_many_rejected():
    with pytest.raises(UnsafeURL):
        validate_url("http://rebind.example.com/", resolve=lambda h: ["93.184.216.34", "127.0.0.1"])


def test_dns_to_metadata_service_rejected():
    with pytest.raises(UnsafeURL):
        validate_url("https://x.example.com/", resolve=lambda h: ["169.254.169.254"])


def test_resolver_returning_nothing_rejected():
    with pytest.raises(UnsafeURL):
        validate_url("http://ghost.example.com/", resolve=lambda h: [])


def test_resolver_failure_rejected():
    def boom(host):
        raise OSError("NXDOMAIN")

    with pytest.raises(UnsafeURL):
        validate_url("http://nope.example.com/", resolve=boom)


def test_ip_literal_does_not_call_resolver():
    calls = []
    validate_url("http://93.184.216.34/", resolve=lambda h: calls.append(h) or ["93.184.216.34"])
    assert calls == []
