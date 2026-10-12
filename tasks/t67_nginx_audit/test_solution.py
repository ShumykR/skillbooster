import pytest

from solution import audit_nginx, parse_nginx

GOOD = """\
worker_processes auto;

http {
    server_tokens off;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
    client_max_body_size 10m;
    ssl_protocols TLSv1.2 TLSv1.3;
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    upstream app {
        server 127.0.0.1:8000;
        keepalive 16;
    }

    server {
        listen 80;
        server_name example.com;
        location /.well-known/acme-challenge/ { root /var/www/acme; }
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name example.com;
        ssl_certificate /etc/ssl/example.pem;
        ssl_certificate_key /etc/ssl/example.key;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        location / {
            limit_req zone=api burst=20;
            proxy_pass http://app;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
"""


def variant(old, new, text=GOOD):
    assert old in text, old
    return text.replace(old, new)


def test_parser_builds_tree_and_ignores_comments_and_quotes():
    tree = parse_nginx('# top\nhttp {\n  add_header X "a; b{c}"; # tail\n  server { listen 80; }\n}\n')
    http = tree[0]
    assert http["name"] == "http" and http["args"] == []
    assert http["block"][0] == {"name": "add_header", "args": ["X", "a; b{c}"], "block": None}
    assert http["block"][1]["block"] == [{"name": "listen", "args": ["80"], "block": None}]


def test_good_config_is_clean():
    assert audit_nginx(GOOD) == []


def test_ng001_server_tokens_inherited_and_overridden():
    assert audit_nginx(variant("server_tokens off;\n", "")) == ["NG001"]
    assert audit_nginx(variant("server_tokens off;", "server_tokens on;")) == ["NG001"]
    # server-рівень перекриває http
    overridden = variant("server_name example.com;\n        ssl_certificate", "server_name example.com;\n        server_tokens on;\n        ssl_certificate")
    assert audit_nginx(overridden) == ["NG001"]
    moved = variant("    server_tokens off;\n", "")
    moved = variant("        listen 80;", "        listen 80;\n        server_tokens off;", moved)
    moved = variant("        listen 443 ssl http2;", "        listen 443 ssl http2;\n        server_tokens off;", moved)
    assert audit_nginx(moved) == []


@pytest.mark.parametrize("protocols, ok", [
    ("TLSv1.2 TLSv1.3", True), ("TLSv1.3", True), ("TLSv1 TLSv1.2", False), ("TLSv1.1 TLSv1.2", False),
    ("SSLv3 TLSv1.2", False), ("tlsv1.2 sslv2", False),
])
def test_ng002_ssl_protocols(protocols, ok):
    assert (audit_nginx(variant("ssl_protocols TLSv1.2 TLSv1.3;", f"ssl_protocols {protocols};")) == []) is ok


def test_ng002_missing_ssl_protocols_only_matters_for_tls_servers():
    no_protocols = variant("    ssl_protocols TLSv1.2 TLSv1.3;\n", "")
    assert audit_nginx(no_protocols) == ["NG002"]
    plain_only = """\
http {
    server_tokens off; gzip on; gzip_types text/plain;
    server { listen 80; return 301 https://$host$request_uri; }
}
"""
    assert audit_nginx(plain_only) == ["NG004"]


def test_ng002_ssl_certificate_marks_a_tls_server_even_without_listen_ssl():
    text = variant("listen 443 ssl http2;", "listen 8443;")
    text = variant("    ssl_protocols TLSv1.2 TLSv1.3;\n", "", text)
    assert audit_nginx(text) == ["NG002"]


@pytest.mark.parametrize("listen", ["80", "0.0.0.0:80", "[::]:80", "*:80"])
def test_ng003_http_server_must_redirect(listen):
    broken = variant("listen 80;", f"listen {listen};").replace("return 301 https://$host$request_uri;", "")
    assert audit_nginx(broken) == ["NG003"]


@pytest.mark.parametrize("ret, ok", [
    ("return 301 https://$host$request_uri;", True),
    ("return 308 https://example.com$request_uri;", True),
    ("return 302 HTTPS://example.com;", True),
    ("return 200 'hello';", False),
    ("return 301 http://example.com$request_uri;", False),
    ("return 404;", False),
])
def test_ng003_redirect_details(ret, ok):
    text = variant("return 301 https://$host$request_uri;", ret)
    assert (audit_nginx(text) == []) is ok


def test_ng003_return_inside_location_does_not_count():
    text = variant("        return 301 https://$host$request_uri;\n", "        location / { return 301 https://$host$request_uri; }\n")
    assert audit_nginx(text) == ["NG003"]


def test_ng003_ssl_on_port_80_is_not_plain_http():
    text = variant("listen 80;", "listen 80 ssl;")
    assert "NG003" not in audit_nginx(text)


def test_ng004_rate_limit_must_be_applied_and_declared():
    assert audit_nginx(variant("            limit_req zone=api burst=20;\n", "")) == ["NG004"]
    assert audit_nginx(variant("zone=api burst=20", "zone=ghost burst=20")) == ["NG004"]
    assert audit_nginx(variant("zone=api:10m rate=10r/s", "zone=other:10m rate=10r/s")) == ["NG004"]
    server_level = variant("            limit_req zone=api burst=20;\n", "")
    server_level = variant("        add_header Strict", "        limit_req zone=api;\n        add_header Strict", server_level)
    assert audit_nginx(server_level) == []


def test_ng005_proxy_headers_all_three_required():
    for header in ("Host $host", "X-Forwarded-For $proxy_add_x_forwarded_for", "X-Forwarded-Proto $scheme"):
        assert audit_nginx(variant(f"            proxy_set_header {header};\n", "")) == ["NG005"], header


def test_ng005_header_names_are_case_insensitive():
    text = variant("proxy_set_header Host $host;", "proxy_set_header host $host;")
    assert audit_nginx(text) == []


def test_ng005_headers_set_above_are_inherited_by_locations_without_their_own():
    moved = variant("""            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
""", "")
    moved = variant("        add_header Strict", """        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        add_header Strict""", moved)
    assert audit_nginx(moved) == []


def test_ng005_one_header_in_location_replaces_everything_from_above():
    text = variant("            proxy_pass http://app;", "            proxy_pass http://app;\n            proxy_set_header X-Request-Id $request_id;")
    broken = variant("""            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
""", "", text)
    broken = variant("        add_header Strict", """        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        add_header Strict""", broken)
    assert audit_nginx(broken) == ["NG005"], "один proxy_set_header у location скасовує набір із server"


def test_ng006_hsts_missing_and_replaced_by_location_add_header():
    assert audit_nginx(variant('        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;\n', "")) == ["NG006"]
    text = variant("            proxy_http_version 1.1;", "            proxy_http_version 1.1;\n            add_header X-Frame-Options DENY;")
    assert audit_nginx(text) == ["NG006"], "add_header у location замінює набір сервера, HSTS зникає"
    both = variant("            proxy_http_version 1.1;",
                   '            proxy_http_version 1.1;\n            add_header X-Frame-Options DENY;\n            add_header Strict-Transport-Security "max-age=1" always;')
    assert audit_nginx(both) == []


def test_ng006_hsts_in_http_level_is_inherited():
    text = variant('        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;\n', "")
    text = variant("    server_tokens off;\n", '    server_tokens off;\n    add_header Strict-Transport-Security "max-age=1" always;\n', text)
    assert audit_nginx(text) == []


def test_ng006_not_required_for_plain_http_server():
    plain = GOOD.split("    server {\n        listen 443")[0] + "}\n"
    assert "NG006" not in audit_nginx(plain)


@pytest.mark.parametrize("value, ok", [("10m", True), ("0", False), ("100k", True)])
def test_ng007_body_limit(value, ok):
    assert (audit_nginx(variant("client_max_body_size 10m;", f"client_max_body_size {value};")) == []) is ok


def test_ng007_missing_everywhere_and_location_override():
    assert audit_nginx(variant("    client_max_body_size 10m;\n", "")) == ["NG007"]
    text = variant("            proxy_http_version 1.1;", "            proxy_http_version 1.1;\n            client_max_body_size 0;")
    assert audit_nginx(text) == ["NG007"]
    fixed = variant("    client_max_body_size 10m;\n", "")
    fixed = variant("            proxy_http_version 1.1;", "            proxy_http_version 1.1;\n            client_max_body_size 5m;", fixed)
    assert audit_nginx(fixed) == []


def test_ng008_gzip():
    assert audit_nginx(variant("    gzip on;\n", "")) == ["NG008"]
    assert audit_nginx(variant("gzip on;", "gzip off;")) == ["NG008"]
    assert audit_nginx(variant("    gzip_types text/plain text/css application/json application/javascript;\n", "")) == ["NG008"]


def test_ng009_upstream_keepalive():
    assert audit_nginx(variant("        keepalive 16;\n", "")) == ["NG009"]


def test_ng010_autoindex():
    assert audit_nginx(variant("            proxy_http_version 1.1;", "            proxy_http_version 1.1;\n            autoindex on;")) == ["NG010"]
    assert audit_nginx(variant("            proxy_http_version 1.1;", "            proxy_http_version 1.1;\n            autoindex off;")) == []


def test_comments_do_not_trigger_or_hide_rules():
    text = variant("    server_tokens off;\n", "    # server_tokens on;\n    server_tokens off;\n")
    assert audit_nginx(text) == []
    assert audit_nginx(variant("    server_tokens off;\n", "    # server_tokens off;\n")) == ["NG001"]


def test_many_violations_sorted():
    bare = "http { server { listen 80; location / { proxy_pass http://x; autoindex on; } } upstream x { server 1.1.1.1; } }"
    assert audit_nginx(bare) == ["NG001", "NG003", "NG004", "NG005", "NG007", "NG008", "NG009", "NG010"]
