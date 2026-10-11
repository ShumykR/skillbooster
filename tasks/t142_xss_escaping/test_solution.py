import html
import re
from html.parser import HTMLParser

import pytest

from solution import escape_html, sanitize_html

ALLOWED_TAGS = {"b", "i", "em", "strong", "code", "pre", "p", "br", "ul", "ol", "li", "a", "blockquote"}
VOID = {"br"}


# --- незалежний «інспектор» виходу -------------------------------------------------------------

class Inspector(HTMLParser):
    """Розбирає ВИХІД санітайзера й збирає події. Усі порушення складає в self.problems."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events, self.problems, self.stack = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.problems.append(f"недозволений тег <{tag}>")
        names = [k for k, _ in attrs]
        if tag == "a":
            for k, v in attrs:
                if k not in ("href", "rel"):
                    self.problems.append(f"недозволений атрибут {k} на <a>")
                if k == "href":
                    cleaned = re.sub(r"[\x00-\x20\x7f]", "", v or "").lower()
                    ok = cleaned.startswith(("http://", "https://", "mailto:")) or (
                        cleaned.startswith("/") and not cleaned.startswith("//") and "\\" not in cleaned
                    )
                    if not ok:
                        self.problems.append(f"небезпечний href {v!r}")
            rel = dict(attrs).get("rel", "")
            if "noopener" not in rel.split():
                self.problems.append("посилання без rel=noopener")
        elif names:
            self.problems.append(f"атрибути на <{tag}>: {names}")
        self.events.append(("start", tag, dict(attrs)))
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(f"незбалансований </{tag}>")
        else:
            self.stack.pop()
        self.events.append(("end", tag))

    def handle_data(self, data):
        self.events.append(("text", data))

    def handle_comment(self, data):
        self.problems.append("коментар у виході")

    def handle_decl(self, decl):
        self.problems.append("DOCTYPE у виході")

    def handle_pi(self, data):
        self.problems.append("інструкція обробки у виході")


def inspect(out):
    ins = Inspector()
    ins.feed(out)
    ins.close()
    if ins.stack:
        ins.problems.append(f"незакриті теги {ins.stack}")
    return ins


def text_of(out):
    return "".join(e[1] for e in inspect(out).events if e[0] == "text")


def assert_safe(markup):
    out = sanitize_html(markup)
    ins = inspect(out)
    assert not ins.problems, f"{markup!r} -> {out!r}: {ins.problems}"
    assert sanitize_html(out) == out, f"не ідемпотентно: {markup!r}"
    return out


# --- escape_html -------------------------------------------------------------------------------

def test_escape_html_basic():
    out = escape_html("<script>alert('x' + \"y\")</script> & more")
    assert "<" not in out and ">" not in out and '"' not in out and "'" not in out
    assert "&amp;" in out


@pytest.mark.parametrize(
    "text",
    ["", "plain text", "a & b", "<b>", "\"quoted\" and 'single'", "&lt;already&gt;", "&amp;amp;", "😀 <3 ünï", "a\nb\tc"],
)
def test_escape_html_roundtrip(text):
    assert html.unescape(escape_html(text)) == text


def test_escape_html_is_safe_inside_a_quoted_attribute():
    payload = '" onmouseover="alert(1)'
    out = escape_html(payload)
    markup = f'<div title="{out}">x</div>'

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.attrs = None

        def handle_starttag(self, tag, attrs):
            self.attrs = dict(attrs)

    p = P()
    p.feed(markup)
    assert set(p.attrs) == {"title"} and p.attrs["title"] == payload


def test_escape_html_does_not_double_escape_in_one_pass():
    assert escape_html("&") == "&amp;"
    assert escape_html("&amp;") == "&amp;amp;"


# --- sanitize_html: корпус атак ---------------------------------------------------------------

SCRIPT_PAYLOADS = [
    "<script>alert(1)</script>",
    "<SCRIPT SRC=//evil.example/x.js></SCRIPT>",
    "<script>alert(1)",  # незакритий
    "<style>@import 'http://evil/x.css';</style>after",
    "<iframe src=\"javascript:alert(1)\"></iframe>",
    "<svg><script>alert(1)</script></svg>",
    "<textarea><script>alert(1)</script></textarea>",
    "<!--[if IE]><script>alert(1)</script><![endif]-->",
]

OTHER_PAYLOADS = [
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "<body onload=alert(1)>",
    "<b onmouseover=alert(1)>hi</b>",
    "<a href=\"javascript:alert(1)\">x</a>",
    "<a href=\"  JaVaScRiPt:alert(1)\">x</a>",
    "<a href=\"jav&#x61;script:alert(1)\">x</a>",
    "<a href=\"java\tscript:alert(1)\">x</a>",
    "<a href=\"java&#9;script:alert(1)\">x</a>",
    "<a href=\"data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==\">x</a>",
    "<a href=\"vbscript:msgbox(1)\">x</a>",
    "<a href=\"//evil.example\">x</a>",
    "<a href=\"/\\evil.example\">x</a>",
    "<a href=\"x\" onclick=\"alert(1)\">x</a>",
    "<a href='http://ok.example' target=_blank>x</a>",
    "<p style=\"background:url(javascript:alert(1))\">x</p>",
    "<scr<script>ipt>alert(1)</scr</script>ipt>",
    "<<script>alert(1)//<</script>",
    "<math><mi xlink:href=\"javascript:alert(1)\">x</mi></math>",
    "<form action=\"javascript:alert(1)\"><button>x</button></form>",
    "<noscript><p title=\"</noscript><img src=x onerror=alert(1)>\">",
    "<img src=\"x\" onerror=\"alert(1)\"//",
    "<a href=\"http://ok.example\"",
    "<<<>>>&&&\"'",
    "<a href=\"http://ok.example\"><b>unclosed",
]


@pytest.mark.parametrize("payload", SCRIPT_PAYLOADS)
def test_script_like_elements_are_removed_with_their_content(payload):
    out = assert_safe(payload)
    assert "alert" not in out and "evil" not in out.replace("&", "")


@pytest.mark.parametrize("payload", OTHER_PAYLOADS)
def test_attack_corpus_produces_safe_output(payload):
    assert_safe(payload)


def test_event_handler_attributes_are_dropped_from_allowed_tags():
    out = assert_safe('<b onmouseover="alert(1)" class="x" id="y" style="color:red">hi</b>')
    assert "onmouseover" not in out and "class" not in out and "style" not in out
    assert text_of(out) == "hi"


def test_dangerous_tags_keep_their_text_but_lose_the_tag():
    out = assert_safe("<div>hello <span>world</span></div>")
    assert text_of(out) == "hello world"
    assert "<div" not in out and "<span" not in out


def test_unsafe_href_is_dropped_but_link_text_kept():
    out = assert_safe('<a href="javascript:alert(1)">click me</a>')
    assert text_of(out) == "click me"
    assert "javascript" not in out.lower()


def test_target_blank_is_removed_and_rel_added():
    out = assert_safe('<a href="https://ok.example/x" target="_blank">go</a>')
    assert "target" not in out
    events = inspect(out).events
    assert events[0][0] == "start" and events[0][2]["href"] == "https://ok.example/x"


# --- sanitize_html: безпечний вміст не псується -----------------------------------------------

def test_simple_formatting_is_preserved():
    out = assert_safe("<p>Hello <b>bold</b>, <i>italic</i> and <code>x &lt; y</code></p>")
    tags = [e[1] for e in inspect(out).events if e[0] == "start"]
    assert tags == ["p", "b", "i", "code"]
    assert text_of(out) == "Hello bold, italic and x < y"


def test_lists_and_blockquote_and_br():
    out = assert_safe("<ul><li>a</li><li>b</li></ul><blockquote>q<br>w</blockquote>")
    tags = [e[1] for e in inspect(out).events if e[0] == "start"]
    assert tags == ["ul", "li", "li", "blockquote", "br"]


@pytest.mark.parametrize(
    "href",
    ["https://example.com/a?x=1&y=2", "http://example.com", "mailto:user@example.com", "/docs/page#top", "/a/b?c=d"],
)
def test_safe_links_are_kept(href):
    out = assert_safe(f'<a href="{html.escape(href)}">l</a>')
    start = inspect(out).events[0]
    assert start[2]["href"] == href
    assert "noopener" in start[2]["rel"]


def test_plain_text_is_escaped_not_dropped():
    out = assert_safe("Tom & Jerry <3 \"quotes\" 'single'")
    assert text_of(out) == "Tom & Jerry <3 \"quotes\" 'single'"


def test_already_escaped_entities_are_not_executed():
    out = assert_safe("&lt;script&gt;alert(1)&lt;/script&gt;")
    assert text_of(out) == "<script>alert(1)</script>"
    assert "<script" not in out


def test_empty_and_whitespace():
    assert sanitize_html("") == ""
    assert assert_safe("   ") .strip() == ""


def test_unbalanced_markup_is_repaired():
    for markup in ["<b>bold <i>x</b> tail", "<p>one<p>two", "</b></i>text</p>", "<ul><li>a<li>b</ul>", "<b><b><b>x"]:
        assert_safe(markup)


def test_non_void_tags_do_not_leak_out_of_scope():
    out = assert_safe("<b>bold</b> after <i>x</i>")
    events = inspect(out).events
    assert [e[0] for e in events if e[0] != "text"] == ["start", "end", "start", "end"]


def test_unicode_is_preserved():
    out = assert_safe("<p>Привіт, світе! 😀 ünï</p>")
    assert text_of(out) == "Привіт, світе! 😀 ünï"


def test_large_input_is_handled():
    markup = "<p>" + "<b>x</b> text & more " * 5000 + "</p>"
    out = assert_safe(markup)
    assert text_of(out).count("text & more") == 5000
