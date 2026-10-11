import pytest

from solution import build_set_cookie, content_disposition, safe_header


# ---------- safe_header ----------

def test_safe_header_passes_normal_values():
    assert safe_header("Location", "/dashboard?x=1") == ("Location", "/dashboard?x=1")
    assert safe_header("X-Request-Id", "abc-123") == ("X-Request-Id", "abc-123")


def test_safe_header_trims_outer_whitespace_only():
    assert safe_header("X-A", " \t a b \t ") == ("X-A", "a b")
    assert safe_header("X-A", "a\tb") == ("X-A", "a\tb")


def test_safe_header_empty_value_allowed():
    assert safe_header("X-A", "") == ("X-A", "")
    assert safe_header("X-A", "   ") == ("X-A", "")


@pytest.mark.parametrize("value", [
    "/ok\r\nSet-Cookie: session=evil",
    "/ok\nX-Evil: 1",
    "/ok\rX-Evil: 1",
    "/ok\r\n\r\n<html>",
    "a\x00b",
    "a\x07b",
    "a\x1bb",
    "a\x7fb",
    "\r\nX: 1",
    "x\r\n",
])
def test_safe_header_rejects_control_characters(value):
    with pytest.raises(ValueError):
        safe_header("Location", value)


def test_safe_header_rejects_non_latin1():
    with pytest.raises(ValueError):
        safe_header("X-A", "привіт")
    with pytest.raises(ValueError):
        safe_header("X-A", "Ā")


def test_safe_header_latin1_ok():
    assert safe_header("X-A", "café") == ("X-A", "café")
    assert safe_header("X-A", "ÿ") == ("X-A", "ÿ")


@pytest.mark.parametrize("name", ["", "X Y", "X:Y", "X\r\nY", "Імʼя", "a(b)", "a/b", "a;b", "a=b", "a,b", "a\x00"])
def test_safe_header_rejects_bad_names(name):
    with pytest.raises(ValueError):
        safe_header(name, "v")


@pytest.mark.parametrize("name", ["Location", "X-Custom_Header.1", "a!#$%&'*+^`|~", "Z"])
def test_safe_header_accepts_token_names(name):
    assert safe_header(name, "v") == (name, "v")


@pytest.mark.parametrize("value", [None, 5, b"x", ["x"]])
def test_safe_header_rejects_non_str_value(value):
    with pytest.raises(ValueError):
        safe_header("X-A", value)


def test_safe_header_rejects_non_str_name():
    with pytest.raises(ValueError):
        safe_header(None, "v")


# ---------- content_disposition ----------

def test_cd_simple():
    assert content_disposition("report.pdf") == 'attachment; filename="report.pdf"'


def test_cd_inline():
    assert content_disposition("a.png", inline=True) == 'inline; filename="a.png"'


def test_cd_spaces_are_fine():
    assert content_disposition("my report.pdf") == 'attachment; filename="my report.pdf"'


def test_cd_strips_directories():
    assert content_disposition("/etc/passwd") == 'attachment; filename="passwd"'
    assert content_disposition("..\\..\\win\\sys.ini") == 'attachment; filename="sys.ini"'
    assert content_disposition("a/b\\c/report.txt") == 'attachment; filename="report.txt"'


@pytest.mark.parametrize("name", ["", ".", "..", "dir/", "dir\\", "a/..", "/"])
def test_cd_rejects_empty_dot_names(name):
    with pytest.raises(ValueError):
        content_disposition(name)


@pytest.mark.parametrize("name", ["a\r\nSet-Cookie: x=1", "a\nb", "a\rb", "a\x00b", "a\x7fb", "a\tb"])
def test_cd_rejects_control_characters(name):
    with pytest.raises(ValueError):
        content_disposition(name)


def test_cd_quote_is_not_injectable():
    got = content_disposition('x".exe')
    assert got == 'attachment; filename="x_.exe"; filename*=UTF-8\'\'x%22.exe'
    assert got.count('"') == 2


def test_cd_backslash_semicolon_percent():
    assert content_disposition("a;b.txt") == 'attachment; filename="a_b.txt"; filename*=UTF-8\'\'a%3Bb.txt'
    assert content_disposition("100%.txt") == 'attachment; filename="100_.txt"; filename*=UTF-8\'\'100%25.txt'
    # '\\' відкидається як розділювач шляху, тож у запасному його не буває
    assert content_disposition("dir\\a.txt") == 'attachment; filename="a.txt"'


def test_cd_unicode_gets_rfc5987_form():
    got = content_disposition("звіт 2026.pdf")
    assert got == (
        'attachment; filename="____ 2026.pdf"; '
        "filename*=UTF-8''%D0%B7%D0%B2%D1%96%D1%82%20" + "2026.pdf"
    )


def test_cd_unicode_inline():
    assert content_disposition("é.txt", inline=True) == 'inline; filename="_.txt"; filename*=UTF-8\'\'%C3%A9.txt'


def test_cd_non_str():
    with pytest.raises(ValueError):
        content_disposition(None)


# ---------- build_set_cookie ----------

def test_cookie_defaults():
    assert build_set_cookie("sid", "abc") == "sid=abc; Path=/; Secure; HttpOnly; SameSite=Lax"


def test_cookie_all_parts_in_order():
    got = build_set_cookie("sid", "abc", max_age=3600, domain="example.com", path="/app",
                           secure=True, httponly=True, samesite="strict")
    assert got == "sid=abc; Max-Age=3600; Domain=example.com; Path=/app; Secure; HttpOnly; SameSite=Strict"


def test_cookie_flags_can_be_disabled():
    got = build_set_cookie("pref", "dark", secure=False, httponly=False)
    assert got == "pref=dark; Path=/; SameSite=Lax"


def test_cookie_max_age_zero_is_valid():
    assert "Max-Age=0" in build_set_cookie("sid", "", max_age=0)


def test_cookie_empty_value():
    assert build_set_cookie("sid", "").startswith("sid=; ")


@pytest.mark.parametrize("given, shown", [("strict", "Strict"), ("LAX", "Lax"), ("None", "None"), ("none", "None")])
def test_cookie_samesite_normalized(given, shown):
    assert build_set_cookie("a", "b", samesite=given).endswith(f"SameSite={shown}")


def test_cookie_samesite_none_requires_secure():
    with pytest.raises(ValueError):
        build_set_cookie("a", "b", samesite="None", secure=False)


@pytest.mark.parametrize("samesite", ["", "relaxed", None, 1])
def test_cookie_invalid_samesite(samesite):
    with pytest.raises(ValueError):
        build_set_cookie("a", "b", samesite=samesite)


@pytest.mark.parametrize("value", [
    "a b", "a;b", "a,b", 'a"b', "a\\b", "a\r\nSet-Cookie: x=1", "a\nb", "a\x00b", "привіт", "a\tb", "a\x7fb",
])
def test_cookie_rejects_bad_values(value):
    with pytest.raises(ValueError):
        build_set_cookie("sid", value)


@pytest.mark.parametrize("value", [None, 5, b"x"])
def test_cookie_rejects_non_str_value(value):
    with pytest.raises(ValueError):
        build_set_cookie("sid", value)


@pytest.mark.parametrize("name", ["", "a b", "a;b", "a=b", "a\r\nb", "імʼя", "a,b"])
def test_cookie_rejects_bad_names(name):
    with pytest.raises(ValueError):
        build_set_cookie(name, "v")


@pytest.mark.parametrize("max_age", [-1, 1.5, "60", True, False])
def test_cookie_rejects_bad_max_age(max_age):
    with pytest.raises(ValueError):
        build_set_cookie("a", "b", max_age=max_age)


@pytest.mark.parametrize("domain", ["", "exa mple.com", "a.com; Path=/x", "a.com\r\nX: 1", "пример.рф", 5])
def test_cookie_rejects_bad_domain(domain):
    with pytest.raises(ValueError):
        build_set_cookie("a", "b", domain=domain)


@pytest.mark.parametrize("path", ["", "app", "/a;b", "/a\r\nb", "/a\x00", None])
def test_cookie_rejects_bad_path(path):
    with pytest.raises(ValueError):
        build_set_cookie("a", "b", path=path)


def test_cookie_secure_prefix():
    assert build_set_cookie("__Secure-sid", "v").startswith("__Secure-sid=v")
    with pytest.raises(ValueError):
        build_set_cookie("__Secure-sid", "v", secure=False)


def test_cookie_host_prefix():
    assert build_set_cookie("__Host-sid", "v") == "__Host-sid=v; Path=/; Secure; HttpOnly; SameSite=Lax"
    with pytest.raises(ValueError):
        build_set_cookie("__Host-sid", "v", secure=False)
    with pytest.raises(ValueError):
        build_set_cookie("__Host-sid", "v", path="/app")
    with pytest.raises(ValueError):
        build_set_cookie("__Host-sid", "v", domain="example.com")


def test_cookie_prefix_is_case_sensitive():
    assert build_set_cookie("__host-sid", "v", secure=False, domain="a.com")


def test_cookie_value_with_allowed_punctuation():
    assert build_set_cookie("sid", "a.b-c_d~e=f/g+h").startswith("sid=a.b-c_d~e=f/g+h;")
