import time
import xml.etree.ElementTree as ET

import pytest

from solution import MalformedXML, TooLarge, UnsafeXML, parse_xml_safely


# --- чесні документи ---------------------------------------------------------------------------------

def test_simple_document():
    root = parse_xml_safely("<order id='7'><item sku='A'>2</item><item sku='B'>5</item></order>")
    assert isinstance(root, ET.Element)
    assert root.tag == "order" and root.get("id") == "7"
    assert [(i.get("sku"), i.text) for i in root] == [("A", "2"), ("B", "5")]


def test_bytes_and_str_inputs_are_equivalent():
    doc = "<a><b>Привіт 🙂</b></a>"
    assert parse_xml_safely(doc).find("b").text == "Привіт 🙂"
    assert parse_xml_safely(doc.encode("utf-8")).find("b").text == "Привіт 🙂"


def test_xml_declaration_is_fine():
    assert parse_xml_safely(b'<?xml version="1.0" encoding="UTF-8"?><a/>').tag == "a"


def test_text_and_tail():
    root = parse_xml_safely("<p>one <b>two</b> three</p>")
    assert root.text == "one " and root.find("b").text == "two" and root.find("b").tail == " three"


def test_long_text_is_not_split():
    body = "x" * 100_000
    assert parse_xml_safely(f"<a>{body}</a>").text == body


def test_standard_and_numeric_entities():
    root = parse_xml_safely("<a t='&quot;q&quot;'>&lt;&gt;&amp;&apos;&#65;&#x42;</a>")
    assert root.text == "<>&'AB" and root.get("t") == '"q"'


def test_comments_and_processing_instructions_are_allowed_and_ignored():
    root = parse_xml_safely("<?xml-stylesheet href='x'?><!-- note --><a><!-- inner --><?pi data?><b/></a>")
    assert [c.tag for c in root] == ["b"]


def test_cdata():
    assert parse_xml_safely("<a><![CDATA[<not> & markup]]></a>").text == "<not> & markup"


def test_namespaces_like_elementtree():
    root = parse_xml_safely('<a xmlns="urn:x" xmlns:p="urn:p" p:attr="1"><p:b/></a>')
    assert root.tag == "{urn:x}a"
    assert root.get("{urn:p}attr") == "1"
    assert root[0].tag == "{urn:p}b"


def test_doctype_text_inside_comment_or_cdata_is_not_a_doctype():
    assert parse_xml_safely("<a><!-- <!DOCTYPE x [<!ENTITY e 'v'>]> --></a>").tag == "a"
    assert parse_xml_safely("<a><![CDATA[<!DOCTYPE x [<!ENTITY e 'v'>]>]]></a>").text.startswith("<!DOCTYPE")
    assert parse_xml_safely("<a note='&lt;!DOCTYPE x&gt;'>&lt;!ENTITY&gt;</a>").tag == "a"


# --- XXE і сутності -------------------------------------------------------------------------------------------

def test_external_entity_to_local_file_is_refused_and_never_read(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-VALUE")
    doc = f'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY xxe SYSTEM "{secret.as_uri()}">]><r>&xxe;</r>'
    with pytest.raises(UnsafeXML) as info:
        parse_xml_safely(doc)
    assert "TOP-SECRET-VALUE" not in str(info.value)


@pytest.mark.parametrize(
    "doc",
    [
        '<!DOCTYPE r [<!ENTITY x SYSTEM "http://169.254.169.254/latest/meta-data/">]><r>&x;</r>',
        '<!DOCTYPE r SYSTEM "http://evil.example/evil.dtd"><r/>',
        '<!DOCTYPE r PUBLIC "-//X//EN" "http://evil.example/evil.dtd"><r/>',
        '<!DOCTYPE r [<!ENTITY % p SYSTEM "http://evil.example/p.dtd"> %p;]><r/>',
        '<!DOCTYPE r [<!ENTITY x "plain internal">]><r>&x;</r>',
        "<!DOCTYPE r><r/>",
        "<!DOCTYPE r [ ]><r/>",
        '<?xml version="1.0"?>\n<!-- c -->\n<!DOCTYPE r [<!ELEMENT r ANY>]>\n<r/>',
        '<!DOCTYPE r [<!ATTLIST r a CDATA "default">]><r/>',
    ],
)
def test_any_doctype_is_unsafe(doc):
    with pytest.raises(UnsafeXML):
        parse_xml_safely(doc)


def test_billion_laughs_is_refused_fast():
    laughs = "".join(f'<!ENTITY lol{i} "&lol{i-1};&lol{i-1};&lol{i-1};&lol{i-1};&lol{i-1};&lol{i-1};&lol{i-1};&lol{i-1};&lol{i-1};&lol{i-1};">'
                     for i in range(1, 10))
    doc = f'<!DOCTYPE lolz [<!ENTITY lol0 "lol">{laughs}]><lolz>&lol9;</lolz>'
    started = time.perf_counter()
    with pytest.raises(UnsafeXML):
        parse_xml_safely(doc)
    assert time.perf_counter() - started < 1.0


def test_quadratic_blowup_is_refused():
    big = "A" * 10_000
    refs = "&a;" * 2_000
    with pytest.raises(UnsafeXML):
        parse_xml_safely(f'<!DOCTYPE r [<!ENTITY a "{big}">]><r>{refs}</r>')


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32"])
def test_doctype_in_other_encodings_is_not_a_bypass(encoding, tmp_path):
    secret = tmp_path / "s.txt"
    secret.write_text("SECRET")
    text = f'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "{secret.as_uri()}">]><r>&x;</r>'
    payload = text.encode(encoding)
    with pytest.raises(ValueError) as info:
        parse_xml_safely(payload)
    assert "SECRET" not in str(info.value)
    assert not isinstance(info.value, TooLarge)


def test_doctype_with_declared_latin1_encoding_is_refused():
    doc = '<?xml version="1.0" encoding="ISO-8859-1"?><!DOCTYPE r [<!ENTITY x "é">]><r>&x;</r>'.encode("latin-1")
    with pytest.raises(UnsafeXML):
        parse_xml_safely(doc)


def test_undefined_entity_is_malformed_not_unsafe():
    with pytest.raises(MalformedXML):
        parse_xml_safely("<a>&foo;</a>")


# --- ліміти --------------------------------------------------------------------------------------------------------

def test_size_limit_is_in_bytes_and_checked_first():
    doc = "<a>" + "я" * 600 + "</a>"  # кирилиця: 2 байти на символ
    assert len(doc) < 1000 < len(doc.encode("utf-8"))
    with pytest.raises(TooLarge):
        parse_xml_safely(doc, max_bytes=1000)
    assert parse_xml_safely(doc, max_bytes=2000).tag == "a"
    with pytest.raises(TooLarge):  # навіть для некоректного документа розмір перевіряється раніше за розбір
        parse_xml_safely(b"<<<<" * 1000, max_bytes=100)


def test_depth_limit():
    def nested(n):
        return "<a>" * n + "</a>" * n

    assert parse_xml_safely(nested(50)).tag == "a"
    with pytest.raises(TooLarge):
        parse_xml_safely(nested(51))
    assert parse_xml_safely(nested(5), max_depth=5).tag == "a"
    with pytest.raises(TooLarge):
        parse_xml_safely(nested(6), max_depth=5)


def test_extremely_deep_document_stops_early_without_recursion_error():
    doc = "<a>" * 200_000 + "</a>" * 200_000
    started = time.perf_counter()
    with pytest.raises(TooLarge):
        parse_xml_safely(doc, max_bytes=10_000_000)
    assert time.perf_counter() - started < 2.0


def test_node_limit_counts_all_elements():
    ok = "<r>" + "<c/>" * 9_999 + "</r>"
    assert len(parse_xml_safely(ok)) == 9_999
    with pytest.raises(TooLarge):
        parse_xml_safely("<r>" + "<c/>" * 10_000 + "</r>")
    with pytest.raises(TooLarge):
        parse_xml_safely("<r><a><b/></a><a><b/></a></r>", max_nodes=4)
    assert parse_xml_safely("<r><a><b/></a><a><b/></a></r>", max_nodes=5).tag == "r"


def test_attribute_values_cannot_be_used_to_smuggle_entities():
    with pytest.raises(MalformedXML):
        parse_xml_safely('<a x="&undefined;"/>')


# --- некоректний ввід ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "doc",
    ["", "   ", "plain text", "<a>", "<a></b>", "<a/><b/>", "<a/>trailing", "<a b=1/>", "<", "<a><b></a></b>",
     b"\xff\xfe\x00", "<a>\x00</a>", "<?xml version='1.0'?>"],
)
def test_malformed_documents(doc):
    with pytest.raises(MalformedXML):
        parse_xml_safely(doc)


def test_errors_are_value_errors_and_not_leaking_parser_exceptions():
    for exc in (UnsafeXML, TooLarge, MalformedXML):
        assert issubclass(exc, ValueError)
    with pytest.raises(MalformedXML) as info:
        parse_xml_safely("<a>")
    assert not isinstance(info.value, SyntaxError)


@pytest.mark.parametrize("bad", [None, 5, ["<a/>"], {"a": 1}])
def test_type_error_for_non_text(bad):
    with pytest.raises(TypeError):
        parse_xml_safely(bad)
