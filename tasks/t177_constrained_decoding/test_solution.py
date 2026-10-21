import json
import random

import pytest

from solution import constrained_generate, is_complete, token_mask, valid_prefix

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "maxLength": 6},
        "age": {"type": "integer"},
        "admin": {"type": "boolean"},
        "role": {"enum": ["user", "admin", 'a"b']},
    },
    "required": ["name", "age", "admin", "role"],
}
ROLES = ["user", "admin", 'a"b']
MULTI = ['{"', '":', '","', '":"', 'tru', 'e,', 'fal', 'se', '"}', '},', 'ad', 'min', 'use', 'r"', '12', '00',
         '\\"', '\\n', '\\\\', 'é', 'я', '-1', '"ro', 'le"', 'age', 'adm', 'in"', '9,"', '0,', '1,', ',"a']
VOCAB = [chr(c) for c in range(32, 127)] + ["é", "я", "\n", "\t"] + MULTI


def doc(name="ab", age=7, admin=True, role="user"):
    return json.dumps({"name": name, "age": age, "admin": admin, "role": role}, separators=(",", ":"),
                      ensure_ascii=False)


# --- таблиці валідних документів і префіксів ---------------------------------------------------

VALID_DOCS = [
    doc(), doc(name="", age=0, admin=False, role="admin"), doc(name="abcdef", age=-123456789, role='a"b'),
    doc(name='q"\\\n', age=999999999), doc(name="éяé", age=-5), '{"name":"\\"\\"\\"\\"\\"\\"","age":1,"admin":true,"role":"user"}',
]


@pytest.mark.parametrize("text", VALID_DOCS)
def test_valid_documents_and_all_their_prefixes(text):
    assert is_complete(SCHEMA, text)
    assert json.loads(text)
    for i in range(len(text) + 1):
        assert valid_prefix(SCHEMA, text[:i]), text[:i]
        assert is_complete(SCHEMA, text[:i]) == (i == len(text))


@pytest.mark.parametrize("text", [
    " ", "[", '{"x', '{"name":1', '{"name":"abcdefg', '{"name":"a\\x', '{"name":"a\tb"', '{"name":"a\nb"',
    '{"name":"ab"}', '{"name":"ab"x', '{"name":"ab","age":"1"', '{"name":"ab","age":+1', '{"name":"ab","age":01',
    '{"name":"ab","age":-0', '{"name":"ab","age":1.5', '{"name":"ab","age":1234567890', '{"name":"ab","age":-a',
    '{"name":"ab","age":1,"admin":True', '{"name":"ab","age":1,"admin":"true"', '{"name":"ab","age":1,"admin":tru,',
    '{"name":"ab","age":1,"admin":true,"role":"root', '{"name":"ab","age":1,"admin":true,"role":"use"',
    '{"name":"ab","age":1,"admin":true,"role":"user"} ', '{"name":"ab","age":1,"admin":true,"role":"user"}x',
    '{"name":"ab","age":1,"admin":true,"role":"user"}}', '{"age":1', '{"name":"ab","age":1,"role":"user"',
    '{"name": "ab"', '{ "name":"ab"', '{"name":"ab" ,', '{"name":"ab","age":1,"admin":true,"role":"user","x":1',
    '{"name":"ab","age":1,"admin":true,"role":"user",', '{"name":"\\u0041"', '{"name":\'ab\'',
])
def test_invalid_prefixes(text):
    assert valid_prefix(SCHEMA, text) is False
    assert is_complete(SCHEMA, text) is False


def test_empty_text_is_prefix_but_not_complete():
    assert valid_prefix(SCHEMA, "") is True
    assert is_complete(SCHEMA, "") is False


def test_string_limits_and_escapes():
    schema = {"type": "object", "properties": {"s": {"type": "string", "maxLength": 3}}}
    assert is_complete(schema, '{"s":"abc"}')
    assert not valid_prefix(schema, '{"s":"abcd')
    assert is_complete(schema, '{"s":"\\"\\"\\""}')  # екранування це один символ
    assert not valid_prefix(schema, '{"s":"\\"\\"\\"\\"')
    assert valid_prefix(schema, '{"s":"ab\\')  # недописане екранування
    assert not valid_prefix(schema, '{"s":"ab\\t')
    assert not valid_prefix(schema, '{"s":"ab\\/')
    assert is_complete({"type": "object", "properties": {"s": {"type": "string", "maxLength": 0}}}, '{"s":""}')
    default = {"type": "object", "properties": {"s": {"type": "string"}}}  # maxLength за замовчуванням 16
    assert is_complete(default, '{"s":"' + "x" * 16 + '"}')
    assert not valid_prefix(default, '{"s":"' + "x" * 17)


def test_integer_rules():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
    for ok in ("0", "7", "-7", "123456789", "-123456789", "100000000"):
        assert is_complete(schema, '{"n":%s}' % ok), ok
    for bad in ("00", "01", "-0", "+1", "1.0", "1e3", "1234567890", "-1234567890", "--1", "a", ""):
        assert not is_complete(schema, '{"n":%s}' % bad), bad
    assert valid_prefix(schema, '{"n":-')
    assert not valid_prefix(schema, '{"n":-}')
    assert valid_prefix(schema, '{"n":0') and not valid_prefix(schema, '{"n":00')


def test_empty_object_and_edge_schemas():
    empty = {"type": "object", "properties": {}}
    assert is_complete(empty, "{}")
    assert valid_prefix(empty, "{") and not valid_prefix(empty, "{ ")
    assert not valid_prefix(empty, "{}{")


def test_enum_with_shared_prefix_values():
    schema = {"type": "object", "properties": {"r": {"enum": ["a", "ab", "b"]}}}
    assert is_complete(schema, '{"r":"a"}') and is_complete(schema, '{"r":"ab"}') and is_complete(schema, '{"r":"b"}')
    assert valid_prefix(schema, '{"r":"a') and not valid_prefix(schema, '{"r":"abc')
    assert not valid_prefix(schema, '{"r":"c')


def test_property_order_is_fixed():
    assert valid_prefix(SCHEMA, '{"name":"a","age":1')
    assert not valid_prefix(SCHEMA, '{"age":1')


# --- маска -------------------------------------------------------------------------------------

def allowed_texts(prefix, vocab=VOCAB):
    mask = token_mask(SCHEMA, prefix, vocab)
    assert len(mask) == len(vocab)
    return {vocab[i] for i, m in enumerate(mask) if m}


def test_mask_at_start_allows_only_open_brace_tokens():
    assert allowed_texts("") == {"{", '{"'}


def test_mask_inside_string_blocks_overlong_and_control_chars():
    t = allowed_texts('{"name":"abc')
    assert {"d", '"', "é", '\\"', "\\n", "\\\\", "\\", "}", ",", '","'} <= t
    assert "\n" not in t and "\t" not in t
    assert '":' not in t and '"}' not in t
    full = allowed_texts('{"name":"abcdef')  # ліміт довжини вичерпано: лише закриття рядка
    assert full == {'"', '","'}


def test_mask_for_multi_char_tokens_crossing_boundaries():
    t = allowed_texts('{"name":"ab')
    assert '","' in t
    t = allowed_texts('{"name":"ab","age":')
    assert {"-1", "12", "1", "9", "0", "0,"} <= t
    assert "00" not in t and "tru" not in t and '"' not in t and "," not in t
    t = allowed_texts('{"name":"ab","age":1')
    assert {",", "2", "0", "12", "00", "0,", "1,", ',"a'} <= t
    assert "-1" not in t and "}" not in t and '"' not in t
    t = allowed_texts('{"name":"ab","age":0')
    assert "," in t and "0" not in t and "1" not in t and "12" not in t


def test_mask_for_boolean_and_enum():
    t = allowed_texts('{"name":"ab","age":1,"admin":')
    assert {"t", "f", "tru", "fal"} <= t
    assert "x" not in t and '"' not in t and "1" not in t
    assert allowed_texts('{"name":"ab","age":1,"admin":tru') == {"e", "e,"}
    t = allowed_texts('{"name":"ab","age":1,"admin":true,"role":"')
    assert {"u", "a", "ad", "use", "adm"} <= t
    assert "x" not in t and "r" not in t and '"' not in t and '\\"' not in t
    assert allowed_texts('{"name":"ab","age":1,"admin":true,"role":"user') == {'"', '"}'}
    assert allowed_texts('{"name":"ab","age":1,"admin":true,"role":"user"') == {"}"}
    t = allowed_texts('{"name":"ab","age":1,"admin":true,"role":"a')  # admin або a"b
    assert {"d", '\\"'} <= t and "u" not in t and '"' not in t


def test_mask_after_complete_document_is_all_false():
    assert not any(token_mask(SCHEMA, doc(), VOCAB))


def test_mask_rejects_invalid_prefix_and_bad_vocab():
    with pytest.raises(ValueError):
        token_mask(SCHEMA, '{"x', VOCAB)
    with pytest.raises(ValueError):
        token_mask(SCHEMA, "", ["a", ""])
    with pytest.raises(ValueError):
        token_mask(SCHEMA, "", ["abcd"])
    with pytest.raises(ValueError):
        token_mask(SCHEMA, "", ["a", 5])


def random_valid_doc(rng):
    alphabet = [chr(c) for c in range(32, 127)] + ["é", "я", "\n"]
    name = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 6)))
    return doc(name=name, age=rng.choice([0, rng.randint(-999999999, 999999999)]), admin=rng.choice([True, False]),
               role=rng.choice(ROLES))


def random_segmentation(text, rng):
    """Розбиває текст на токени зі словника довільно: маска не має блокувати жодного кроку."""
    pieces, pos = [], 0
    while pos < len(text):
        options = [t for t in VOCAB if text.startswith(t, pos)]
        t = rng.choice(options)
        pieces.append(t)
        pos += len(t)
    return pieces


def test_mask_never_blocks_a_valid_continuation():
    rng = random.Random(20)
    multi_seen = 0
    for _ in range(20):
        text = random_valid_doc(rng)
        prefix = ""
        for piece in random_segmentation(text, rng):
            mask = token_mask(SCHEMA, prefix, VOCAB)
            assert mask[VOCAB.index(piece)], (prefix, piece)
            multi_seen += len(piece) > 1
            prefix += piece
        assert is_complete(SCHEMA, prefix)
    assert multi_seen > 15


# --- генерація ---------------------------------------------------------------------------------

def check_schema_valid(text):
    obj = json.loads(text)
    assert list(obj) == ["name", "age", "admin", "role"]
    assert isinstance(obj["name"], str) and len(obj["name"]) <= 6
    assert type(obj["age"]) is int and len(str(abs(obj["age"]))) <= 9 and str(obj["age"]) != "-0"
    assert type(obj["admin"]) is bool
    assert obj["role"] in ROLES
    assert text == doc(**obj)  # канонічний вигляд


def test_random_model_always_produces_valid_documents():
    rng = random.Random(7)
    seen_roles, seen_lengths = set(), set()
    for _ in range(25):
        text = constrained_generate(SCHEMA, VOCAB, lambda prefix, allowed: rng.choice(allowed))
        check_schema_valid(text)
        obj = json.loads(text)
        seen_roles.add(obj["role"])
        seen_lengths.add(len(obj["name"]))
    assert len(seen_roles) >= 2 and len(seen_lengths) >= 3


@pytest.mark.parametrize("pick", [
    lambda prefix, allowed: allowed[0],
    lambda prefix, allowed: allowed[-1],
    lambda prefix, allowed: allowed[len(allowed) // 2],
    lambda prefix, allowed: max(allowed, key=lambda i: (len(VOCAB[i]), i)),
    lambda prefix, allowed: min(allowed, key=lambda i: (len(VOCAB[i]), -i)),
], ids=["first", "last", "middle", "longest-token", "shortest-token"])
def test_adversarial_models_cannot_break_the_format(pick):
    check_schema_valid(constrained_generate(SCHEMA, VOCAB, pick))


def test_model_that_wants_to_close_early_is_forced_to_finish_fields():
    def pick(prefix, allowed):
        for i in allowed:
            if VOCAB[i] in ("}", '"}', "},"):
                return i
        return allowed[0]
    check_schema_valid(constrained_generate(SCHEMA, VOCAB, pick))


def test_choose_receives_prefix_and_allowed_only():
    calls = []

    def pick(prefix, allowed):
        calls.append((prefix, list(allowed)))
        return allowed[0]

    text = constrained_generate(SCHEMA, VOCAB, pick)
    assert calls[0][0] == ""
    assert all(a == [i for i, m in enumerate(token_mask(SCHEMA, p, VOCAB)) if m] for p, a in calls)
    assert all(not is_complete(SCHEMA, p) for p, _ in calls)
    assert calls[-1][0] != text


def test_choose_returning_disallowed_index_is_value_error():
    with pytest.raises(ValueError):
        constrained_generate(SCHEMA, VOCAB, lambda prefix, allowed: VOCAB.index("x"))


def test_max_steps_and_stuck_vocabulary():
    long_schema = {"type": "object", "properties": {"s": {"type": "string", "maxLength": 64}}}
    with pytest.raises(RuntimeError):
        constrained_generate(long_schema, VOCAB, lambda p, a: a[0], max_steps=10)
    no_close = [t for t in VOCAB if "}" not in t]
    with pytest.raises(RuntimeError):
        constrained_generate(SCHEMA, no_close, lambda p, a: a[0])
    text = constrained_generate(SCHEMA, VOCAB, lambda p, a: a[0], max_steps=500)
    assert is_complete(SCHEMA, text)


def test_exact_step_budget():
    schema = {"type": "object", "properties": {}}
    assert constrained_generate(schema, ["{", "}"], lambda p, a: a[0], max_steps=2) == "{}"
    with pytest.raises(RuntimeError):
        constrained_generate(schema, ["{", "}"], lambda p, a: a[0], max_steps=1)


def test_single_char_vocab_is_enough():
    vocab = sorted({c for c in doc() + "0123456789-truefalsadminuser}{,:\"" })
    rng = random.Random(3)
    for _ in range(20):
        text = constrained_generate(SCHEMA, vocab, lambda p, a: rng.choice(a))
        check_schema_valid(text)


# --- схема -------------------------------------------------------------------------------------

@pytest.mark.parametrize("schema", [
    None, [], {}, {"type": "array"}, {"type": "object"}, {"type": "object", "properties": []},
    {"type": "object", "properties": {"a": {"type": "array"}}},
    {"type": "object", "properties": {"a": {"type": "number"}}},
    {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "integer"}}, "required": ["a"]},
    {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a", "zzz"]},
    {"type": "object", "properties": {"a": {"enum": []}}},
    {"type": "object", "properties": {"a": {"enum": ["x", "x"]}}},
    {"type": "object", "properties": {"a": {"enum": [1, 2]}}},
    {"type": "object", "properties": {"a": {"type": "string", "maxLength": -1}}},
    {"type": "object", "properties": {"a": {"type": "string", "maxLength": 65}}},
    {"type": "object", "properties": {"a": {"type": "string", "maxLength": True}}},
    {"type": "object", "properties": {"a": {"type": "string", "maxLength": 2.5}}},
])
def test_unsupported_schema_is_value_error_everywhere(schema):
    with pytest.raises(ValueError):
        valid_prefix(schema, "")
    with pytest.raises(ValueError):
        is_complete(schema, "{}")
    with pytest.raises(ValueError):
        token_mask(schema, "", ["{"])
    with pytest.raises(ValueError):
        constrained_generate(schema, ["{", "}"], lambda p, a: a[0])


def test_required_may_be_omitted_or_listed_in_any_order():
    props = {"a": {"type": "boolean"}, "b": {"type": "integer"}}
    for schema in ({"type": "object", "properties": props},
                   {"type": "object", "properties": props, "required": ["b", "a"]}):
        assert is_complete(schema, '{"a":true,"b":5}')
        assert not valid_prefix(schema, '{"b":5')


def test_keys_are_json_escaped_in_output():
    schema = {"type": "object", "properties": {'k"1': {"type": "boolean"}, "ключ": {"type": "integer"}}}
    text = '{"k\\"1":false,"ключ":-3}'
    assert is_complete(schema, text)
    assert all(valid_prefix(schema, text[:i]) for i in range(len(text) + 1))
