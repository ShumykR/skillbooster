import pytest

from solution import cost_ratio, decode, encode, train_bpe

EN = (
    "The quick brown fox jumps over the lazy dog. Machine learning models read text as tokens, "
    "and every token costs money. The cost of a request depends on the number of tokens in the "
    "prompt and in the answer. Short prompts are cheap and long documents are expensive."
)
UK = (
    "Швидка руда лисиця стрибає через ледачого собаку. Моделі машинного навчання читають текст "
    "як токени, і кожен токен коштує грошей. Вартість запиту залежить від кількості токенів "
    "у запиті й у відповіді. Короткі запити дешеві, а довгі документи дорогі."
)
MIXED = ["", "a", "ab", "hello world", "Привіт, світе!", "🚀", "🚀🚀🚀 launch 🚀", "naïve café", "é",
         "\x00\x01\x02", "line1\nline2\r\nline3\t!", "ᐃᓄᒃᑎᑐᑦ", "日本語のテキスト", "a" * 50, "ab" * 40,
         "Ще один рядок: цифри 12345 та символи ~!@#", "\U0001F468‍\U0001F469‍\U0001F467"]


# --- train_bpe ---------------------------------------------------------------------------------

def test_wikipedia_example_exact_merges_and_encoding():
    merges = train_bpe("aaabdaaabac", 3)
    assert merges == [(97, 97), (97, 98), (256, 257)]
    assert encode("aaabdaaabac", merges) == [258, 100, 258, 97, 99]


def test_tie_break_prefers_smallest_pair():
    merges = train_bpe("abcdabcd", 3)
    assert merges == [(97, 98), (99, 100), (256, 257)]


def test_overlapping_pairs_are_counted_by_position():
    # (97, 97) стоїть у "aaaa" на трьох позиціях (з накладанням), а (120, 121) теж три рази: нічия, менша пара перша
    assert train_bpe("aaaaxyxyxy", 1) == [(97, 97)]
    merges = train_bpe("aaaaaa", 5)
    assert merges == [(97, 97), (256, 256)]
    assert encode("aaaaaa", merges) == [257, 256]


def test_no_merge_for_pairs_seen_once():
    assert train_bpe("abcd", 5) == []
    assert train_bpe("", 5) == []
    assert train_bpe("x", 5) == []


def test_zero_merges_and_invalid_count():
    assert train_bpe(EN, 0) == []
    for bad in (-1, 1.5, "3", None, True):
        with pytest.raises(ValueError):
            train_bpe(EN, bad)


def test_training_is_deterministic():
    assert train_bpe(EN + UK, 40) == train_bpe(EN + UK, 40)


def test_merges_reference_only_known_ids_and_stop_early():
    merges = train_bpe(EN, 10_000)
    assert 0 < len(merges) < 10_000
    for i, (a, b) in enumerate(merges):
        assert 0 <= a < 256 + i and 0 <= b < 256 + i


def test_training_works_on_utf8_bytes_not_characters():
    # «і» (U+0456) це байти D1 96: пара (209, 150) трапляється 4 рази, (150, 209) лише 3
    assert train_bpe("іііі", 1) == [(209, 150)]


def test_training_is_byte_level_for_cyrillic_and_emoji():
    merges = train_bpe("🚀🚀🚀🚀 " * 5, 4)
    assert merges and all(a < 256 + i and b < 256 + i for i, (a, b) in enumerate(merges))
    # байти емодзі 🚀 це F0 9F 9A 80: перша пара найчастіша
    assert merges[0][0] in (0xF0, 0x9F, 0x9A, 0x80, 0x20)


# --- encode / decode ---------------------------------------------------------------------------

def test_encode_without_merges_is_utf8_bytes():
    for text in MIXED:
        assert encode(text, []) == list(text.encode("utf-8"))


@pytest.mark.parametrize("n", [0, 5, 30, 200])
def test_roundtrip_without_loss(n):
    merges = train_bpe(EN + UK + "🚀🚀 emoji 🚀", n)
    for text in MIXED + [EN, UK]:
        ids = encode(text, merges)
        assert all(isinstance(t, int) and 0 <= t < 256 + len(merges) for t in ids)
        assert decode(ids, merges) == text


def test_merges_are_applied_in_training_order():
    # (b,c) -> 256 застосовується першою, тож "abc" це [a, 256], а потім (a,256) -> 257
    merges = [(98, 99), (97, 256)]
    assert encode("abc", merges) == [257]
    # у зворотному порядку правило (a,b) відпрацьовує першим, а (256, c) другим
    assert encode("abc", [(97, 98), (256, 99)]) == [257]
    # пріоритет має значення: (b,c) раніше за (a,b) блокує друге правило
    assert encode("abc", [(98, 99), (97, 98)]) == [97, 256]
    assert encode("abc", [(97, 98), (98, 99)]) == [256, 99]


def test_every_occurrence_is_merged_left_to_right():
    assert encode("aaaaa", [(97, 97)]) == [256, 256, 97]
    assert encode("abababab", [(97, 98)]) == [256, 256, 256, 256]
    assert encode("xabyabz", [(97, 98)]) == [120, 256, 121, 256, 122]


def test_training_compresses_the_corpus_monotonically():
    sizes = [len(encode(EN, train_bpe(EN, n))) for n in (0, 5, 20, 60)]
    assert sizes[0] == len(EN.encode())
    assert sizes == sorted(sizes, reverse=True) and sizes[-1] < sizes[0] * 0.7


def test_decode_expands_merged_tokens_and_rejects_unknown_ids():
    merges = train_bpe("aaabdaaabac", 3)
    assert decode([258, 100, 258, 97, 99], merges) == "aaabdaaabac"
    assert decode([], merges) == ""
    for bad in (256 + len(merges), 10_000, -1):
        with pytest.raises(ValueError):
            decode([bad], merges)


def test_decode_of_partial_utf8_does_not_raise():
    ids = list("🚀".encode())[:2]
    assert "�" in decode(ids, [])
    assert decode(list("🚀".encode()), []) == "🚀"


def test_encode_does_not_mutate_merges():
    merges = train_bpe(EN, 20)
    snapshot = list(merges)
    encode(EN, merges)
    decode(encode(EN, merges), merges)
    assert merges == snapshot


# --- ціна токенів ------------------------------------------------------------------------------

def test_ukrainian_costs_more_tokens_than_english_with_english_vocabulary():
    merges = train_bpe((EN + " ") * 4, 120)
    assert cost_ratio(merges, UK, EN) >= 1.3
    assert cost_ratio(merges, EN, UK) <= 1 / 1.3


def test_without_merges_cyrillic_costs_two_tokens_per_character():
    ratio = cost_ratio([], "привітсвіте", "helloworld")
    assert ratio == pytest.approx(2.0)


def test_training_on_ukrainian_reduces_the_gap():
    en_only = train_bpe((EN + " ") * 4, 120)
    both = train_bpe((EN + " ") * 4 + (UK + " ") * 4, 240)
    assert cost_ratio(both, UK, EN) < cost_ratio(en_only, UK, EN)


def test_cost_ratio_rejects_empty_text():
    with pytest.raises(ValueError):
        cost_ratio([], "", "abc")
    with pytest.raises(ValueError):
        cost_ratio([], "abc", "")
