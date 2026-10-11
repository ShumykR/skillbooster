import re

import pytest

from solution import UploadRejected, validate_upload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
PDF = b"%PDF-1.7\n%..."
TXT = "Привіт, світе\nline 2".encode("utf-8")
HTML = b"<html><script>alert(1)</script></html>"


def factory(value="stored"):
    return lambda: value


def ok(filename, content, **kw):
    kw.setdefault("name_factory", factory())
    return validate_upload(filename, content, **kw)


def reason(filename, content, **kw):
    with pytest.raises(UploadRejected) as e:
        validate_upload(filename, content, **kw)
    return e.value.reason


@pytest.mark.parametrize(
    "filename, content, stored, ctype",
    [
        ("photo.png", PNG, "stored.png", "image/png"),
        ("photo.jpg", JPG, "stored.jpg", "image/jpeg"),
        ("photo.jpeg", JPG, "stored.jpg", "image/jpeg"),
        ("anim.gif", GIF, "stored.gif", "image/gif"),
        ("anim.gif", b"GIF87a" + b"\x00" * 4, "stored.gif", "image/gif"),
        ("doc.pdf", PDF, "stored.pdf", "application/pdf"),
        ("notes.txt", TXT, "stored.txt", "text/plain"),
    ],
)
def test_valid_uploads(filename, content, stored, ctype):
    result = ok(filename, content)
    assert result == {"stored_name": stored, "content_type": ctype, "original_name": filename}


def test_extension_case_is_normalized_but_original_name_is_kept():
    result = ok("My Photo.PNG", PNG)
    assert result["stored_name"] == "stored.png"
    assert result["original_name"] == "My Photo.PNG"


def test_unicode_filename_is_allowed():
    assert ok("фото_кота.png", PNG)["original_name"] == "фото_кота.png"


def test_stored_name_has_nothing_from_the_client_but_extension():
    result = ok("../../etc/passwd.png", PNG, name_factory=factory("abc123"))
    assert result["stored_name"] == "abc123.png"
    assert "passwd" not in result["stored_name"] and "/" not in result["stored_name"]


def test_default_name_factory_gives_unique_hex_names():
    a = validate_upload("a.png", PNG)["stored_name"]
    b = validate_upload("a.png", PNG)["stored_name"]
    assert a != b
    assert re.fullmatch(r"[0-9a-f]{32}\.png", a)


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("C:\\fakepath\\photo.png", "photo.png"),
        ("../../x.png", "x.png"),
        ("dir/sub/y.png", "y.png"),
        ("..\\..\\z.png", "z.png"),
        ("/etc/w.png", "w.png"),
    ],
)
def test_directories_are_stripped(filename, expected):
    assert ok(filename, PNG)["original_name"] == expected


# --- відмови: кожна причина ------------------------------------------------------------------

def test_too_large():
    assert reason("a.png", PNG + b"x" * 100, max_size=50) == "too_large"
    assert ok("a.png", PNG, max_size=len(PNG))  # рівно ліміт дозволено


def test_empty():
    assert reason("a.png", b"") == "empty"


@pytest.mark.parametrize(
    "filename",
    ["", ".", "..", ".htaccess", ".png", " a.png", "a.png ", "a.png.", "a\x00.png", "a\n.png", "a\x7f.png", "x" * 97 + ".png",
     "dir/", "dir\\"],
)
def test_bad_filenames(filename):
    assert reason(filename, PNG) == "bad_filename"


def test_hundred_char_name_is_ok():
    assert ok("x" * 96 + ".png", PNG)


@pytest.mark.parametrize(
    "filename",
    ["shell.php", "shell.php.png", "shell.png.php", "SHELL.PHP", "a.phtml", "run.exe", "run.sh", "page.html", "page.htm",
     "pic.svg", "script.js", "x.py", "a.jsp.txt", "a.PHP.png", "archive.war"],
)
def test_dangerous_extensions_anywhere_in_the_name(filename):
    assert reason(filename, PNG) == "dangerous_extension"


@pytest.mark.parametrize("filename", ["noextension", "archive.tar.gz", "doc.docx", "data.json", "photo.bmp", "x.png.bak", "a.webp"])
def test_extension_not_allowed(filename):
    assert reason(filename, PNG) == "extension_not_allowed"


@pytest.mark.parametrize(
    "filename, content",
    [
        ("evil.png", HTML),
        ("evil.png", b"GIF89a-looks-like-gif"),
        ("evil.jpg", PNG),
        ("evil.gif", JPG),
        ("evil.pdf", HTML),
        ("evil.txt", b"binary\x00data"),
        ("evil.txt", b"\xff\xfe\xfa not utf8"),
        ("tiny.png", b"\x89PNG"),
    ],
)
def test_content_mismatch(filename, content):
    assert reason(filename, content) == "content_mismatch"


def test_order_of_checks():
    assert reason("shell.php", b"x" * 100, max_size=10) == "too_large"       # розмір раніше за все
    assert reason(".htaccess", b"") == "empty"                               # порожній раніше за ім'я
    assert reason(".php", PNG) == "bad_filename"                             # ім'я раніше за розширення
    assert reason("a.php.exe", HTML) == "dangerous_extension"                # небезпечне раніше за вміст
    assert reason("a.docx", HTML) == "extension_not_allowed"                 # розширення раніше за вміст


def test_error_type_and_attribute():
    with pytest.raises(ValueError) as e:
        validate_upload("a.php", PNG)
    assert isinstance(e.value, UploadRejected)
    assert e.value.reason == "dangerous_extension"


def test_text_file_with_html_text_is_a_plain_text_file():
    # text/plain віддається без виконання; вміст "<script>" у .txt не відхиляємо
    assert ok("note.txt", HTML)["content_type"] == "text/plain"
