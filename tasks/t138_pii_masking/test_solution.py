import pytest

from solution import Pseudonymizer, detect, find_leaks, moderate


def spans(text):
    return [(s["type"], s["value"]) for s in detect(text)]


# ---------- detect -------------------------------------------------------------------------------------------------------


def test_each_kind_of_pii():
    text = ("Mail ann.lee+shop@Example.co.uk, phone +380 67 123 45 67, card 4111 1111 1111 1111, "
            "iban DE89 3704 0044 0532 0130 00, ssn 123-45-6789.")
    assert spans(text) == [("EMAIL", "ann.lee+shop@Example.co.uk"), ("PHONE", "+380 67 123 45 67"), ("CARD", "4111 1111 1111 1111"),
                           ("IBAN", "DE89 3704 0044 0532 0130 00"), ("SSN", "123-45-6789")]


def test_positions_are_exact():
    text = "x ann@example.com y"
    s = detect(text)[0]
    assert text[s["start"]:s["end"]] == "ann@example.com" == s["value"]


@pytest.mark.parametrize("text", [
    "order 123456789 shipped", "date 2026-03-15", "version 1.2.3.4", "short 555-1234", "id 12345678901234567890123",
    "card 4111 1111 1111 1112",           # не проходить Луна
    "iban DE89 3704 0044 0532 0130 02",   # не проходить mod 97
    "no at sign example.com", "mail me@x", "price 1 234 567,00 UAH",
])
def test_things_that_look_like_pii_but_are_not(text):
    assert detect(text) == []


@pytest.mark.parametrize("phone", ["+380 67 123 45 67", "(555) 123-4567", "+1 (555) 123-4567", "555.123.4567", "067-123-45-67", "+44 20 7946 0958"])
def test_phone_formats(phone):
    assert spans(f"call {phone} now") == [("PHONE", phone)]


@pytest.mark.parametrize("card", ["4111111111111111", "4111-1111-1111-1111", "5500 0000 0000 0004", "3782 822463 10005"])
def test_cards_with_valid_luhn(card):
    assert spans(f"pay {card}.")[0][0] == "CARD"


def test_card_is_not_reported_as_a_phone_and_trailing_separators_are_excluded():
    text = "card 4111 1111 1111 1111 - thanks"
    assert spans(text) == [("CARD", "4111 1111 1111 1111")]
    assert detect(text)[0]["end"] == text.index(" - thanks")


def test_valid_ibans():
    assert spans("IBAN: GB82 WEST 1234 5698 7654 32.") == [("IBAN", "GB82 WEST 1234 5698 7654 32")]
    assert spans("DE89370400440532013000 end")[0] == ("IBAN", "DE89370400440532013000")


def test_email_wins_over_overlapping_matches():
    assert spans("1234567890@example.com") == [("EMAIL", "1234567890@example.com")]


def test_results_are_sorted_and_do_not_overlap():
    found = detect("a@b.com 4111 1111 1111 1111 c@d.org +380 67 123 45 67")
    starts = [s["start"] for s in found]
    assert starts == sorted(starts) and len(found) == 4
    assert all(a["end"] <= b["start"] for a, b in zip(found, found[1:]))


# ---------- mask and restore -------------------------------------------------------------------------------------------------


def test_mask_replaces_with_numbered_placeholders():
    p = Pseudonymizer()
    out = p.mask("Write to ann@example.com or bob@example.com, call +380 67 123 45 67.")
    assert out == "Write to [EMAIL_1] or [EMAIL_2], call [PHONE_1]."
    assert p.mapping == {"[EMAIL_1]": "ann@example.com", "[EMAIL_2]": "bob@example.com", "[PHONE_1]": "+380 67 123 45 67"}


def test_same_value_gets_the_same_placeholder_in_any_notation():
    p = Pseudonymizer()
    out = p.mask("ann@example.com, ANN@Example.com, +380 67 123 45 67, +380-67-123-45-67, 4111 1111 1111 1111 and 4111-1111-1111-1111")
    assert out == "[EMAIL_1], [EMAIL_1], [PHONE_1], [PHONE_1], [CARD_1] and [CARD_1]"
    assert p.mapping["[EMAIL_1]"] == "ann@example.com", "оригіналом лишається перше написання"
    assert p.mapping["[PHONE_1]"] == "+380 67 123 45 67"


def test_numbering_continues_between_calls():
    p = Pseudonymizer()
    assert p.mask("a@x.com") == "[EMAIL_1]"
    assert p.mask("b@x.com and a@x.com") == "[EMAIL_2] and [EMAIL_1]"
    assert p.mask("c@x.com, 123-45-6789") == "[EMAIL_3], [SSN_1]"


def test_mask_leaves_other_text_untouched_and_is_idempotent():
    p = Pseudonymizer()
    text = "order 123456789 on 2026-03-15, price 100 UAH"
    assert p.mask(text) == text
    once = p.mask("mail a@x.com")
    assert p.mask(once) == once


def test_names_are_masked_as_whole_words_without_touching_emails():
    p = Pseudonymizer(names=["Ann"])
    out = p.mask("Hannah met ann today, her mail is ann@example.com; ANN agreed.")
    assert out == "Hannah met [NAME_1] today, her mail is [EMAIL_1]; [NAME_1] agreed."
    assert p.mapping == {"[NAME_1]": "ann", "[EMAIL_1]": "ann@example.com"}


def test_longer_names_win_and_names_with_special_characters():
    p = Pseudonymizer(names=["Ann", "Ann Lee", "O'Neil (Jr.)"])
    assert p.mask("Ann Lee and Ann; O'Neil (Jr.) too") == "[NAME_1] and [NAME_2]; [NAME_3] too"


def test_restore_puts_originals_back():
    p = Pseudonymizer(names=["Ann Lee"])
    masked = p.mask("Ann Lee wrote from ann@example.com, phone +380 67 123 45 67")
    answer = f"Dear {masked.split(' wrote')[0]}, we will reply to [email_1] and call [Phone_1]. Ignore [EMAIL_9] and [NOPE_1]."
    assert p.restore(answer) == "Dear Ann Lee, we will reply to ann@example.com and call +380 67 123 45 67. Ignore [EMAIL_9] and [NOPE_1]."


def test_round_trip():
    p = Pseudonymizer(names=["Bob"])
    text = "Bob (bob@x.org, 555-123-4567, SSN 123-45-6789) paid with 4111 1111 1111 1111."
    masked = p.mask(text)
    assert find_leaks(masked) == [] and "Bob" not in masked and "bob@x.org" not in masked
    assert p.restore(masked) == text


def test_mapping_is_a_copy():
    p = Pseudonymizer()
    p.mask("a@x.com")
    p.mapping["[EMAIL_1]"] = "hacked"
    assert p.mapping["[EMAIL_1]"] == "a@x.com"
    assert Pseudonymizer().mapping == {}


# ---------- leaks and moderation ------------------------------------------------------------------------------------------------


def test_find_leaks():
    assert find_leaks("ann@example.com, +380 67 123 45 67 and 4111 1111 1111 1111") == ["CARD", "EMAIL", "PHONE"]
    assert find_leaks("nothing here") == [] and find_leaks("[EMAIL_1] called [PHONE_2]") == []


CATEGORIES = {"violence": ["kill", "bomb"], "self_harm": ["hurt myself"], "fraud": ["card dump"]}


@pytest.mark.parametrize("text, hits", [
    ("How to build a Bomb?", ["violence"]),
    ("I want to KILL the process", ["violence"]),
    ("improve your skills", []),
    ("I might hurt myself", ["self_harm"]),
    ("buy a card dump and kill time", ["fraud", "violence"]),
    ("a bombastic claim", []),
    ("", []),
])
def test_moderation(text, hits):
    assert moderate(text, CATEGORIES) == {"allowed": not hits, "categories": hits}


def test_moderation_without_categories_allows_everything():
    assert moderate("anything", {}) == {"allowed": True, "categories": []}
