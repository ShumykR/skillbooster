import pytest

from solution import diagnose_curl

DNS = """\
* Could not resolve host: api.example.invalid
* Closing connection
curl: (6) Could not resolve host: api.example.invalid
"""

REFUSED = """\
*   Trying 127.0.0.1:8080...
* connect to 127.0.0.1 port 8080 failed: Connection refused
* Failed to connect to localhost port 8080 after 0 ms: Couldn't connect to server
* Closing connection
curl: (7) Failed to connect to localhost port 8080 after 0 ms: Couldn't connect to server
"""

REFUSED_FALLBACK_IPV4 = """\
*   Trying [::1]:8080...
* connect to ::1 port 8080 failed: Connection refused
*   Trying 127.0.0.1:8080...
* connect to 127.0.0.1 port 8080 failed: Connection refused
* Failed to connect to localhost port 8080 after 0 ms: Couldn't connect to server
curl: (7) Failed to connect to localhost port 8080 after 0 ms: Couldn't connect to server
"""

CONNECT_TIMEOUT = """\
*   Trying 203.0.113.9:443...
* Connection timed out after 5001 milliseconds
* Closing connection
curl: (28) Connection timed out after 5001 milliseconds
"""

TLS_TIMEOUT = """\
*   Trying 203.0.113.9:443...
* Connected to shop.example (203.0.113.9) port 443 (#0)
* ALPN: offers h2,http/1.1
* TLSv1.3 (OUT), TLS handshake, Client hello (1):
* Closing connection
curl: (28) SSL connection timeout
"""

READ_TIMEOUT = """\
*   Trying 10.1.2.3:8000...
* Connected to svc.internal (10.1.2.3) port 8000
> GET /slow HTTP/1.1
> Host: svc.internal:8000
>
* Operation timed out after 3001 milliseconds with 0 bytes received
* Closing connection
curl: (28) Operation timed out after 3001 milliseconds with 0 bytes received
"""

CERT_EXPIRED = """\
*   Trying 198.51.100.4:443...
* Connected to old.example (198.51.100.4) port 443
* TLSv1.3 (IN), TLS handshake, Certificate (11):
* Server certificate:
*  subject: CN=old.example
*  start date: Jan  5 00:00:00 2024 GMT
*  expire date: Apr  4 23:59:59 2024 GMT
*  issuer: C=US; O=Let's Encrypt; CN=R3
* SSL certificate problem: certificate has expired
* Closing connection
curl: (60) SSL certificate problem: certificate has expired
"""

HOST_MISMATCH = """\
*   Trying 198.51.100.4:443...
* Server certificate:
*  subject: CN=www.example.com
* SSL: no alternative certificate subject name matches target host name 'api.example.com'
* Closing connection
curl: (60) SSL: no alternative certificate subject name matches target host name 'api.example.com'
"""

SELF_SIGNED = """\
*   Trying 10.0.0.9:443...
* SSL certificate problem: self-signed certificate
curl: (60) SSL certificate problem: self-signed certificate
"""

UNKNOWN_ISSUER = """\
*   Trying 10.0.0.9:443...
* SSL certificate problem: unable to get local issuer certificate
curl: (60) SSL certificate problem: unable to get local issuer certificate
"""

PLAIN_HTTP_ON_TLS = """\
*   Trying 10.0.0.5:80...
* Connected to 10.0.0.5 port 80
* TLSv1.3 (OUT), TLS handshake, Client hello (1):
curl: (35) error:0A00010B:SSL routines::wrong version number
"""

OLD_TLS = """\
*   Trying 10.0.0.5:443...
* TLSv1.3 (OUT), TLS handshake, Client hello (1):
curl: (35) error:0A000102:SSL routines::unsupported protocol
"""

TLS_ALERT_VERSION = """\
*   Trying 10.0.0.5:443...
curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL; tlsv1 alert protocol version
"""

HANDSHAKE_FAIL = """\
*   Trying 10.0.0.5:443...
curl: (35) OpenSSL SSL_connect: Connection reset by peer in connection to x
"""

EMPTY_REPLY = """\
*   Trying 10.0.0.5:8000...
> GET / HTTP/1.1
> Host: 10.0.0.5:8000
* Empty reply from server
curl: (52) Empty reply from server
"""

RESET = """\
> GET /big HTTP/1.1
< HTTP/1.1 200 OK
curl: (56) Recv failure: Connection reset by peer
"""

OK = """\
*   Trying 93.184.216.34:443...
* Connected to example.org (93.184.216.34) port 443
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384
> GET / HTTP/2
< HTTP/2 200
< content-type: text/html
"""

BAD_GATEWAY = """\
> GET /api HTTP/1.1
< HTTP/1.1 502 Bad Gateway
< server: nginx
"""

REDIRECT_CHAIN = """\
* SSL connection using TLSv1.2 / ECDHE-RSA-AES128-GCM-SHA256
> GET /old HTTP/1.1
< HTTP/1.1 301 Moved Permanently
< Location: /new
* Issue another request to this URL: 'https://x.example/new'
> GET /new HTTP/1.1
< HTTP/1.1 302 Found
< location: https://x.example/final
> GET /final HTTP/1.1
< HTTP/2 404
"""

NO_FOLLOW_REDIRECT = """\
> GET / HTTP/1.1
< HTTP/1.1 301 Moved Permanently
< Location: https://example.org/
"""

RATE_LIMIT = """\
< HTTP/1.1 429 Too Many Requests
< Retry-After: 30
"""


@pytest.mark.parametrize("output, expected", [
    (DNS, {"stage": "dns", "cause": "resolve_failed", "detail": {"host": "api.example.invalid"}}),
    (REFUSED, {"stage": "tcp", "cause": "refused", "detail": {"host": "127.0.0.1", "port": 8080}}),
    (REFUSED_FALLBACK_IPV4, {"stage": "tcp", "cause": "refused", "detail": {"host": "127.0.0.1", "port": 8080}}),
    (CONNECT_TIMEOUT, {"stage": "tcp", "cause": "connect_timeout", "detail": {"host": "203.0.113.9", "port": 443}}),
    (TLS_TIMEOUT, {"stage": "tls", "cause": "handshake_timeout", "detail": {"host": "203.0.113.9", "port": 443}}),
    (READ_TIMEOUT, {"stage": "http", "cause": "read_timeout", "detail": {"host": "10.1.2.3", "port": 8000}}),
])
def test_dns_and_tcp_failures(output, expected):
    assert diagnose_curl(output) == expected


@pytest.mark.parametrize("output, expected", [
    (CERT_EXPIRED, {"stage": "tls", "cause": "cert_expired", "detail": {"expire_date": "Apr 4 23:59:59 2024 GMT"}}),
    (HOST_MISMATCH, {"stage": "tls", "cause": "hostname_mismatch", "detail": {"target": "api.example.com"}}),
    (SELF_SIGNED, {"stage": "tls", "cause": "untrusted_issuer", "detail": {"reason": "self-signed"}}),
    (UNKNOWN_ISSUER, {"stage": "tls", "cause": "untrusted_issuer", "detail": {"reason": "unknown_issuer"}}),
    (PLAIN_HTTP_ON_TLS, {"stage": "tls", "cause": "not_tls", "detail": {"host": "10.0.0.5", "port": 80}}),
    (OLD_TLS, {"stage": "tls", "cause": "handshake_failed", "detail": {"host": "10.0.0.5", "port": 443}}),
    (TLS_ALERT_VERSION, {"stage": "tls", "cause": "protocol_version", "detail": {"host": "10.0.0.5", "port": 443}}),
    (HANDSHAKE_FAIL, {"stage": "tls", "cause": "handshake_failed", "detail": {"host": "10.0.0.5", "port": 443}}),
])
def test_tls_failures(output, expected):
    assert diagnose_curl(output) == expected


def test_server_closed_connection_cases():
    assert diagnose_curl(EMPTY_REPLY) == {"stage": "http", "cause": "empty_reply", "detail": {}}
    assert diagnose_curl(RESET) == {"stage": "http", "cause": "connection_reset", "detail": {}}


def test_ok_with_tls_version():
    assert diagnose_curl(OK) == {"stage": "http", "cause": "ok", "detail": {"status": 200, "redirects": 0, "tls": "TLSv1.3"}}


def test_http_errors():
    assert diagnose_curl(BAD_GATEWAY) == {"stage": "http", "cause": "bad_gateway", "detail": {"status": 502, "redirects": 0}}
    assert diagnose_curl(RATE_LIMIT) == {"stage": "http", "cause": "rate_limited", "detail": {"status": 429, "redirects": 0, "retry_after": 30}}


@pytest.mark.parametrize("status, cause", [
    (200, "ok"), (204, "ok"), (301, "redirect"), (401, "unauthorized"), (403, "unauthorized"),
    (404, "client_error"), (418, "client_error"), (500, "server_error"), (503, "service_unavailable"),
    (504, "gateway_timeout"), (599, "server_error"),
])
def test_status_to_cause_mapping(status, cause):
    assert diagnose_curl(f"< HTTP/1.1 {status} X\n")["cause"] == cause


def test_redirect_chain_counts_redirects_and_uses_last_status():
    result = diagnose_curl(REDIRECT_CHAIN)
    assert result == {"stage": "http", "cause": "client_error", "detail": {"status": 404, "redirects": 2, "tls": "TLSv1.2"}}


def test_unfollowed_redirect_reports_location():
    assert diagnose_curl(NO_FOLLOW_REDIRECT) == {
        "stage": "http", "cause": "redirect", "detail": {"status": 301, "redirects": 0, "location": "https://example.org/"}}


def test_curl_error_line_wins_over_earlier_http_status():
    assert diagnose_curl(RESET)["cause"] == "connection_reset"


def test_http2_status_line_without_reason_phrase_and_crlf():
    assert diagnose_curl("< HTTP/2 503\r\n< retry-after: 5\r\n")["cause"] == "service_unavailable"


@pytest.mark.parametrize("output", ["", "\n\n", "* Connected to x\n> GET / HTTP/1.1\n"])
def test_no_signal(output):
    assert diagnose_curl(output) == {"stage": "unknown", "cause": "no_signal", "detail": {}}


def test_unknown_curl_error_code_is_not_a_crash():
    result = diagnose_curl("curl: (99) something new\n")
    assert result["stage"] == "unknown" and result["cause"] == "unknown_error"


def test_with_retries_the_last_error_line_wins():
    text = ("*   Trying 10.0.0.1:80...\ncurl: (7) Failed to connect to x port 80\n"
            "*   Trying 10.0.0.1:80...\n* Connection timed out after 5000 milliseconds\ncurl: (28) Connection timed out after 5000 milliseconds\n")
    assert diagnose_curl(text) == {"stage": "tcp", "cause": "connect_timeout", "detail": {"host": "10.0.0.1", "port": 80}}


def test_http2_lowercase_location_header():
    assert diagnose_curl("< HTTP/2 302\n< location: https://x.example/a\n")["detail"]["location"] == "https://x.example/a"
