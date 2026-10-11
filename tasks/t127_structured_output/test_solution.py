import json
from datetime import date

import pytest

from solution import ExtractionError, Invoice, extract_invoice

TEXT = "Рахунок від Acme Ltd на 1250.50 EUR, оплатити до 2026-03-15."
GOOD = {"vendor": "Acme Ltd", "total": 1250.5, "currency": "EUR", "due_date": "2026-03-15"}
EXPECTED = Invoice(vendor="Acme Ltd", total=1250.5, currency="EUR", due_date=date(2026, 3, 15))


class ScriptedLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        reply = self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_clean_json():
    llm = ScriptedLLM(json.dumps(GOOD))
    assert extract_invoice(llm, TEXT) == EXPECTED
    assert len(llm.prompts) == 1


def test_first_prompt_contains_text_and_schema():
    llm = ScriptedLLM(json.dumps(GOOD))
    extract_invoice(llm, TEXT)
    assert TEXT in llm.prompts[0]
    assert "vendor" in llm.prompts[0] and "due_date" in llm.prompts[0]


def test_fenced_json():
    llm = ScriptedLLM("```json\n" + json.dumps(GOOD) + "\n```")
    assert extract_invoice(llm, TEXT) == EXPECTED
    assert len(llm.prompts) == 1


def test_json_with_prose_around():
    llm = ScriptedLLM("Ось результат:\n" + json.dumps(GOOD) + "\nСподіваюсь, це допоможе!")
    assert extract_invoice(llm, TEXT) == EXPECTED


def test_retry_after_invalid_json_includes_feedback():
    llm = ScriptedLLM("це взагалі не JSON", json.dumps(GOOD))
    assert extract_invoice(llm, TEXT) == EXPECTED
    assert len(llm.prompts) == 2
    assert TEXT in llm.prompts[1]
    assert "це взагалі не JSON" in llm.prompts[1], "покажи моделі її попередню відповідь"


def test_retry_after_validation_error_mentions_the_field():
    bad = dict(GOOD, currency="GBP")
    llm = ScriptedLLM(json.dumps(bad), json.dumps(GOOD))
    assert extract_invoice(llm, TEXT) == EXPECTED
    assert "currency" in llm.prompts[1], "у prompt має бути текст помилки валідації"


def test_missing_field_triggers_retry():
    bad = {k: v for k, v in GOOD.items() if k != "total"}
    llm = ScriptedLLM(json.dumps(bad), json.dumps(GOOD))
    assert extract_invoice(llm, TEXT) == EXPECTED
    assert "total" in llm.prompts[1]


def test_gives_up_after_max_attempts():
    llm = ScriptedLLM("nope")
    with pytest.raises(ExtractionError):
        extract_invoice(llm, TEXT, max_attempts=3)
    assert len(llm.prompts) == 3


def test_max_attempts_one():
    llm = ScriptedLLM("nope", json.dumps(GOOD))
    with pytest.raises(ExtractionError):
        extract_invoice(llm, TEXT, max_attempts=1)
    assert len(llm.prompts) == 1


def test_stops_calling_after_success():
    llm = ScriptedLLM("bad", json.dumps(GOOD), json.dumps(GOOD))
    extract_invoice(llm, TEXT, max_attempts=5)
    assert len(llm.prompts) == 2


def test_llm_errors_are_not_swallowed():
    llm = ScriptedLLM(ConnectionError("proxy down"))
    with pytest.raises(ConnectionError):
        extract_invoice(llm, TEXT)
    assert len(llm.prompts) == 1


def test_json_array_or_scalar_is_invalid():
    llm = ScriptedLLM("[1, 2, 3]", json.dumps(GOOD))
    assert extract_invoice(llm, TEXT) == EXPECTED
    assert len(llm.prompts) == 2
