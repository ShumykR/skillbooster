import re

import pytest

from solution import MAX_VALUE, escape_value, format_log_line

FIELD = re.compile(r'([a-z][a-z0-9_]*)="((?:[^"\\]|\\.)*)"')
ESC = re.compile(r"\\(x[0-9a-f]{2}|u[0-9a-f]{4}|.)")
SIMPLE = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"'}


def unescape(text):
    def repl(m):
        g = m.group(1)
        if g[0] == "x" and len(g) == 3:
            return chr(int(g[1:], 16))
        if g[0] == "u" and len(g) == 5:
            return chr(int(g[1:], 16))
        return SIMPLE[g]
    return ESC.sub(repl, text)


def parse(line):
    """Незалежний читач логу: повертає (level, {поле: значення}) або падає, якщо рядок не відповідає формату."""
    m = re.fullmatch(r'level=([A-Z]+)((?: [a-z][a-z0-9_]*="(?:[^"\\]|\\.)*")*)', line)
    assert m, f"рядок не відповідає формату: {line!r}"
    fields = {k: unescape(v) for k, v in FIELD.findall(m.group(2))}
    return m.group(1), fields


# --- форма -----------------------------------------------------------------------------------------

def test_basic_line():
    assert format_log_line("INFO", "user logged in", user="ann", ip="10.0.0.1") == \
        'level=INFO msg="user logged in" ip="10.0.0.1" user="ann"'


def test_fields_are_sorted_by_key():
    assert format_log_line("ERROR", "x", zeta=1, alpha=2, mid=3) == 'level=ERROR msg="x" alpha="2" mid="3" zeta="1"'


def test_no_fields():
    assert format_log_line("DEBUG", "ping") == 'level=DEBUG msg="ping"'


def test_non_string_values_use_str():
    line = format_log_line("INFO", 42, count=7, ok=True, none=None, items=[1, "a"])
    level, f = parse(line)
    assert f == {"msg": "42", "count": "7", "ok": "True", "none": "None", "items": "[1, 'a']"}


@pytest.mark.parametrize("level", ["info", "TRACE", "", None, "INFO ", "Info", 20])
def test_bad_level(level):
    with pytest.raises(ValueError):
        format_log_line(level, "m")


@pytest.mark.parametrize("key", ["Bad", "1abc", "a-b", "a b", "a" * 33, "é", "a.b", "_x"])
def test_bad_keys(key):
    with pytest.raises(ValueError):
        format_log_line("INFO", "m", **{key: "v"})


@pytest.mark.parametrize("key", ["level", "msg"])
def test_reserved_keys(key):
    with pytest.raises(ValueError):
        format_log_line("INFO", "m", **{key: "v"})


def test_key_with_injection_attempt_is_rejected():
    with pytest.raises(ValueError):
        format_log_line("INFO", "m", **{'x="1" level="INFO': "v"})


def test_key_of_max_length_is_ok():
    assert parse(format_log_line("INFO", "m", **{"k" * 32: "v"}))[1]["k" * 32] == "v"


# --- екранування -----------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, escaped",
    [("a\nb", "a\\nb"), ("a\rb", "a\\rb"), ("a\tb", "a\\tb"), ('say "hi"', 'say \\"hi\\"'), ("back\\slash", "back\\\\slash"),
     ("\x00", "\\x00"), ("\x1b[31m", "\\x1b[31m"), ("\x7f", "\\x7f"), ("\x85", "\\x85"), ("\x9f", "\\x9f"),
     (" ", "\\u2028"), (" ", "\\u2029"), ("\x08\x0b\x0c", "\\x08\\x0b\\x0c"), ("плюс Привіт 🙂", "плюс Привіт 🙂"),
     ("", ""), ("plain", "plain")],
)
def test_escape_value(raw, escaped):
    assert escape_value(raw) == escaped


def test_escape_uses_str_for_non_strings():
    assert escape_value(12) == "12"
    assert escape_value(None) == "None"


def test_backslash_is_escaped_first_no_double_escaping():
    assert escape_value("\\n") == "\\\\n"       # літерал «\n» у вхідних даних лишається літералом
    assert escape_value("\n") == "\\n"
    assert unescape(escape_value("\\n")) == "\\n"


@pytest.mark.parametrize(
    "payload",
    [
        'ann\nlevel=INFO msg="admin logged in" user="admin"',
        'ann\r\nlevel=CRITICAL msg="breach"',
        'x" level="INFO" msg="forged',
        "a level=INFO msg=forged",
        "\x1b[2J\x1b[H fake screen",
        "tab\tseparated\x00nul",
        "\\\" level=\"INFO",
        "trailing backslash \\",
        "end with quote \"",
        "emoji 😀\n",
    ],
)
def test_payloads_cannot_forge_lines_or_fields(payload):
    line = format_log_line("INFO", "login", user=payload, ip="10.0.0.1")
    assert "\n" not in line and "\r" not in line and " " not in line and " " not in line
    assert not any(ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F for c in line)
    level, fields = parse(line)  # рядок все ще рівно один запис із очікуваними ключами
    assert level == "INFO"
    assert set(fields) == {"msg", "user", "ip"}
    assert fields["user"] == payload  # і значення відновлюється без втрат
    assert fields["ip"] == "10.0.0.1"


def test_message_is_escaped_too():
    line = format_log_line("WARNING", "bad\nlevel=ERROR", user="u")
    assert "\n" not in line
    assert parse(line)[1]["msg"] == "bad\nlevel=ERROR"


def test_round_trip_for_every_control_character():
    for code in list(range(0, 0x20)) + [0x7F] + list(range(0x80, 0xA0)) + [0x2028, 0x2029, 0x22, 0x5C]:
        raw = f"a{chr(code)}b"
        _, f = parse(format_log_line("INFO", raw))
        assert f["msg"] == raw, hex(code)


# --- обрізання ------------------------------------------------------------------------------------------------

def test_values_up_to_max_are_untouched():
    value = "x" * MAX_VALUE
    assert parse(format_log_line("INFO", "m", v=value))[1]["v"] == value


def test_long_values_are_truncated_with_counter():
    assert MAX_VALUE == 200
    line = format_log_line("INFO", "m", v="y" * 250)
    assert line.endswith('v="' + "y" * 200 + '...[+50]"')


def test_truncation_happens_before_escaping():
    # 150 переносів = 150 символів до екранування; обрізання за довжиною ВХОДУ, а не результату
    line = format_log_line("INFO", "m", v="\n" * 150)
    assert line.endswith('v="' + "\\n" * 150 + '"')
    line = format_log_line("INFO", "m", v="\n" * 201)
    assert line.endswith('v="' + "\\n" * 200 + '...[+1]"')


def test_truncation_cannot_split_an_escape_sequence():
    line = format_log_line("INFO", "m", v="a" * 199 + "\n" + "tail")
    _, f = parse(line)  # якби «\» лишився сам, парсер/екранування зламалось би
    assert f["v"].startswith("a" * 199 + "\n")


def test_message_is_truncated_as_well():
    line = format_log_line("INFO", "z" * 300)
    assert line.endswith('...[+100]"')
    assert len(line) < 300


def test_every_value_is_truncated_independently():
    line = format_log_line("INFO", "m", a="1" * 210, b="2" * 5)
    assert '...[+10]"' in line and 'b="22222"' in line
