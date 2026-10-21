import pytest

from solution import (IDK, check_grounding, claim_text, extract_citations, guarded_answer, overlap,
                      split_claims)

CHUNKS = [
    {"id": "c1", "text": "Paris is the capital of France and its largest city."},
    {"id": "c2", "text": "The Eiffel Tower was completed in 1889 for the World's Fair."},
    {"id": "c3", "text": "Berlin is the capital of Germany."},
]


class FakeNLI:
    """Мок-суддя: відповідає за таблицею (claim, фрагмент чанка) або за замовчуванням; рахує виклики."""

    def __init__(self, table=None, default="supported"):
        self.table = table or {}
        self.default = default
        self.calls = []

    def __call__(self, claim, chunk_text):
        self.calls.append((claim, chunk_text))
        for (c, t), verdict in self.table.items():
            if c in claim and t in chunk_text:
                return verdict
        return self.default


# --- split_claims ------------------------------------------------------------------------------

def test_split_claims_basic():
    assert split_claims("Paris is in France [1]. Berlin is in Germany [3].") == [
        "Paris is in France [1].", "Berlin is in Germany [3]."]
    assert split_claims("Really? Yes! Fine.") == ["Really?", "Yes!", "Fine."]


def test_split_claims_does_not_cut_inside_numbers_or_without_whitespace():
    assert split_claims("The value is 3.5 percent. Next.") == ["The value is 3.5 percent.", "Next."]
    assert split_claims("See file.txt now") == ["See file.txt now"]


@pytest.mark.parametrize("answer, expected", [
    ("Paris is in France. [1]", ["Paris is in France. [1]"]),
    ("Paris is in France. [1, 2]", ["Paris is in France. [1, 2]"]),
    ("A is B. [1] C is D. [2]", ["A is B.", "[1] C is D. [2]"]),
    ("Paris is in France. [1][2]", ["Paris is in France. [1][2]"]),
    ("A is B. [1] [2]", ["A is B. [1] [2]"]),
])
def test_split_claims_attaches_bare_citation_chunks_to_previous_sentence(answer, expected):
    assert split_claims(answer) == expected


def test_split_claims_strips_and_drops_empty():
    assert split_claims("") == []
    assert split_claims("   \n ") == []
    assert split_claims("  One.   Two.  ") == ["One.", "Two."]
    assert split_claims("No punctuation at all") == ["No punctuation at all"]


# --- extract_citations / claim_text / overlap --------------------------------------------------

@pytest.mark.parametrize("sentence, expected", [
    ("Paris [1].", [1]), ("Paris [1, 2].", [1, 2]), ("Paris [2][1][2].", [1, 2]), ("Paris [1 ,3 , 2].", [1, 2, 3]),
    ("Paris [10] and [9].", [9, 10]), ("Paris.", []), ("Paris [a].", []), ("Paris [1a].", []), ("Paris [].", []),
    ("Paris [ 1 ].", []), ("Paris [1,].", []), ("Paris [0].", [0]),
])
def test_extract_citations(sentence, expected):
    assert extract_citations(sentence) == expected


@pytest.mark.parametrize("sentence, expected", [
    ("Paris is in France [1].", "Paris is in France."),
    ("Hi   there [1][2] !", "Hi there!"),
    ("A [1, 2]; B , c : d.", "A; B, c: d."),
    ("Keep [a] markers.", "Keep [a] markers."),
    ("Plain sentence.", "Plain sentence."),
    ("Wait [3] ? Yes [4] .", "Wait? Yes."),
])
def test_claim_text(sentence, expected):
    assert claim_text(sentence) == expected


def test_overlap_formula():
    assert overlap("The cat sat", "the CAT is here") == pytest.approx(2 / 3)
    assert overlap("cat dog", "a cat and a dog") == 1.0
    assert overlap("cat dog bird fish", "cat") == 0.25
    assert overlap("cat cat cat dog", "dog") == 0.5          # множина токенів, а не мультимножина
    assert overlap("is in a", "is in a") == 0.0              # слова коротші за 3 символи не рахуються
    assert overlap("", "anything") == 0.0
    assert overlap("Київ столиця", "Київ є столицею") == 0.5  # \w працює з кирилицею; без округлення
    assert overlap("one two three", "one two") == 2 / 3


# --- check_grounding: вердикти -----------------------------------------------------------------

def verdicts(answer, nli=None, chunks=CHUNKS, **kw):
    report = check_grounding(answer, chunks, nli or FakeNLI(), **kw)
    return [c["verdict"] for c in report["claims"]], report


def test_supported_claim_and_report_fields():
    nli = FakeNLI()
    v, report = verdicts("Paris is the capital of France [1].", nli)
    assert v == ["supported"]
    claim = report["claims"][0]
    assert claim["sentence"] == "Paris is the capital of France [1]."
    assert claim["text"] == "Paris is the capital of France."
    assert claim["citations"] == [1]
    assert claim["overlap"] == 1.0
    assert report["supported_ratio"] == 1.0
    assert nli.calls == [("Paris is the capital of France.", CHUNKS[0]["text"])]


def test_uncited_and_invented_citation_do_not_call_nli():
    nli = FakeNLI()
    v, report = verdicts("Paris is big. Paris is the capital of France [7]. Paris is the capital [0].", nli)
    assert v == ["uncited", "invented-citation", "invented-citation"]
    assert nli.calls == []
    assert report["claims"][1]["citations"] == [7]
    assert report["claims"][1]["overlap"] == 0.0
    assert report["supported_ratio"] == 0.0


def test_invented_citation_wins_even_if_other_citations_are_valid_and_overlap_ignores_invalid():
    nli = FakeNLI()
    v, report = verdicts("Paris is the capital of France [1, 9].", nli)
    assert v == ["invented-citation"]
    assert nli.calls == []
    assert report["claims"][0]["citations"] == [1, 9]
    assert report["claims"][0]["overlap"] == 1.0


def test_low_overlap_chunks_are_not_sent_to_nli_and_claim_is_unsupported():
    nli = FakeNLI()
    v, report = verdicts("The Eiffel Tower was completed in 1889 [3].", nli)
    assert v == ["unsupported"]
    assert nli.calls == []
    assert report["claims"][0]["overlap"] == pytest.approx(0.1667, abs=1e-4)   # 1/6 токенів: "the"


def test_overlap_threshold_is_inclusive_and_configurable():
    answer = "Berlin is the capital of Spain [3]."   # токени: berlin, the, capital, spain -> 3/4 в чанку
    nli = FakeNLI()
    assert verdicts(answer, nli, min_overlap=0.75)[0] == ["supported"] and len(nli.calls) == 1
    nli2 = FakeNLI()
    assert verdicts(answer, nli2, min_overlap=0.76)[0] == ["unsupported"] and nli2.calls == []
    assert verdicts(answer, FakeNLI(), min_overlap=0.0)[0] == ["supported"]


def test_nli_unknown_or_garbage_means_unsupported():
    for answer in ("Paris is the capital of France [1].",):
        for value in ("unknown", "maybe", "", None, 5):
            assert verdicts(answer, FakeNLI(default=value))[0] == ["unsupported"]


def test_contradicted_beats_supported_across_multiple_citations_and_order_is_ascending():
    nli = FakeNLI({("Paris", "Paris is the capital"): "supported", ("Paris", "Eiffel"): "contradicted"})
    answer = "Paris is the capital of France and the Eiffel Tower [2, 1]."
    v, _ = verdicts(answer, nli, min_overlap=0.2)
    assert v == ["contradicted"]
    assert [t for _, t in nli.calls] == [CHUNKS[0]["text"], CHUNKS[1]["text"]]


def test_supported_if_any_chunk_supports_and_none_contradicts():
    nli = FakeNLI({("Paris", "Eiffel"): "unknown"})
    answer = "Paris is the capital of France and the Eiffel Tower [1, 2]."
    assert verdicts(answer, nli, min_overlap=0.2)[0] == ["supported"]
    assert len(nli.calls) == 2


def test_nli_called_exactly_once_per_qualifying_chunk_per_claim_with_clean_claim_text():
    nli = FakeNLI()
    check_grounding("Paris is the capital of France [1]. Berlin is the capital of Germany [3][3].", CHUNKS, nli)
    assert nli.calls == [("Paris is the capital of France.", CHUNKS[0]["text"]),
                         ("Berlin is the capital of Germany.", CHUNKS[2]["text"])]


def test_overlap_field_is_max_over_valid_cited_chunks_only_and_rounded():
    answer = "Paris is the capital of Germany and Spain [1, 3]."
    report = check_grounding(answer, CHUNKS, FakeNLI(), min_overlap=0.1)
    # токени: paris, the, capital, germany, and, spain; чанк 1: paris, the, capital, and (4/6); чанк 3: the, capital, germany (3/6)
    assert report["claims"][0]["overlap"] == pytest.approx(0.6667, abs=1e-9)
    assert report["claims"][0]["overlap"] == round(4 / 6, 4)
    other = check_grounding("Paris is the capital of Germany and Spain [3].", CHUNKS, FakeNLI(), min_overlap=0.1)
    assert other["claims"][0]["overlap"] == 0.5


def test_supported_ratio_rounding_and_empty_answer():
    answer = "Paris is the capital of France [1]. Something else. Berlin is the capital of Germany [3]."
    report = check_grounding(answer, CHUNKS, FakeNLI())
    assert [c["verdict"] for c in report["claims"]] == ["supported", "uncited", "supported"]
    assert report["supported_ratio"] == round(2 / 3, 4) == 0.6667
    assert check_grounding("", CHUNKS, FakeNLI()) == {"claims": [], "supported_ratio": 0.0}


@pytest.mark.parametrize("bad", [-0.01, 1.01, 5, -1])
def test_check_grounding_validates_min_overlap(bad):
    with pytest.raises(ValueError):
        check_grounding("Paris [1].", CHUNKS, FakeNLI(), min_overlap=bad)


def test_boundary_min_overlap_values_are_valid():
    check_grounding("Paris [1].", CHUNKS, FakeNLI(), min_overlap=0)
    check_grounding("Paris [1].", CHUNKS, FakeNLI(), min_overlap=1)


# --- guarded_answer ----------------------------------------------------------------------------

GOOD = "Paris is the capital of France [1]. Berlin is the capital of Germany [3]."


def test_guarded_answer_passes_grounded_answer_through_unchanged():
    result = guarded_answer(GOOD, CHUNKS, FakeNLI())
    assert result["answer"] == GOOD and result["abstained"] is False
    assert result["report"] == check_grounding(GOOD, CHUNKS, FakeNLI())


def test_guarded_answer_abstains_when_ratio_below_threshold():
    answer = GOOD + " Madrid is nice."
    result = guarded_answer(answer, CHUNKS, FakeNLI(), threshold=0.8)   # 2/3 < 0.8
    assert result["answer"] == IDK and result["abstained"] is True
    assert guarded_answer(answer, CHUNKS, FakeNLI(), threshold=0.66)["abstained"] is False   # 0.6667 >= 0.66


def test_guarded_answer_threshold_boundary_is_inclusive():
    answer = " ".join(["Paris is the capital of France [1]."] * 4 + ["Unknown filler."])
    result = guarded_answer(answer, CHUNKS, FakeNLI(), threshold=0.8)   # 4/5 == 0.8
    assert result["abstained"] is False and result["answer"] == answer


def test_guarded_answer_abstains_on_any_contradiction_even_with_high_ratio():
    nli = FakeNLI({("Berlin", "Berlin"): "contradicted"})
    answer = " ".join(["Paris is the capital of France [1]."] * 9 + ["Berlin is the capital of Germany [3]."])
    result = guarded_answer(answer, CHUNKS, nli, threshold=0.5)
    assert result["report"]["supported_ratio"] == 0.9
    assert result["abstained"] is True and result["answer"] == IDK


def test_guarded_answer_abstains_on_invented_citation_even_with_high_ratio():
    answer = " ".join(["Paris is the capital of France [1]."] * 9 + ["Paris is the capital of France [8]."])
    result = guarded_answer(answer, CHUNKS, FakeNLI(), threshold=0.5)
    assert result["abstained"] is True


def test_guarded_answer_uncited_claims_only_lower_the_ratio():
    answer = " ".join(["Paris is the capital of France [1]."] * 9 + ["Just an opinion."])
    result = guarded_answer(answer, CHUNKS, FakeNLI(), threshold=0.9)
    assert result["abstained"] is False


def test_guarded_answer_empty_answer_abstains_and_custom_idk():
    assert guarded_answer("", CHUNKS, FakeNLI())["abstained"] is True
    assert guarded_answer("", CHUNKS, FakeNLI(), threshold=0.0)["abstained"] is True   # порожня відповідь завжди «не знаю»
    result = guarded_answer("Unsupported claim.", CHUNKS, FakeNLI(), idk="Не знаю.")
    assert result["answer"] == "Не знаю." and result["abstained"] is True


@pytest.mark.parametrize("kw", [{"threshold": -0.1}, {"threshold": 1.5}, {"min_overlap": 2}])
def test_guarded_answer_validates_parameters(kw):
    with pytest.raises(ValueError):
        guarded_answer(GOOD, CHUNKS, FakeNLI(), **kw)


def test_min_overlap_is_forwarded_to_the_checker():
    answer = "Berlin is the capital of Spain [3]."
    assert guarded_answer(answer, CHUNKS, FakeNLI(), min_overlap=0.9)["abstained"] is True
    assert guarded_answer(answer, CHUNKS, FakeNLI(), min_overlap=0.5, threshold=1.0)["abstained"] is False
