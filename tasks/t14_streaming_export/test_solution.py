import csv
import datetime as dt
import io
import json
import tracemalloc
from decimal import Decimal

from fastapi.testclient import TestClient

from solution import build_app, export_csv, export_ndjson


def many_rows(n):
    for i in range(n):
        yield {"id": i, "name": f"customer {i}", "note": "x" * 40}


def drain(chunks):
    """Споживає потік, нічого не зберігаючи; повертає (кількість шматків, байт)."""
    count = size = 0
    for chunk in chunks:
        assert isinstance(chunk, str)
        count += 1
        size += len(chunk)
    return count, size


def peak_memory(chunks):
    tracemalloc.start()
    try:
        drain(chunks)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_csv_memory_is_constant():
    peak = peak_memory(export_csv(many_rows(150_000), ["id", "name", "note"]))
    assert peak < 2 * 1024 * 1024, f"пік {peak // 1024} КБ на 150 тис. рядків: результат накопичується"


def test_ndjson_memory_is_constant():
    peak = peak_memory(export_ndjson(many_rows(150_000)))
    assert peak < 2 * 1024 * 1024, f"пік {peak // 1024} КБ на 150 тис. рядків: результат накопичується"


def test_csv_is_lazy_and_chunked():
    pulled = []

    def source():
        for i in range(10_000):
            pulled.append(i)
            yield {"id": i}

    chunks = export_csv(source(), ["id"])
    first = next(chunks)
    assert first.startswith("id\r\n")
    assert len(pulled) <= 1000, f"до першого шматка прочитано {len(pulled)} рядків"
    count, _ = drain(chunks)
    assert 5 <= count + 1 <= 10_000 // 2, "шматків має бути помірно: не весь файл одним і не по рядку-символу"


def test_csv_roundtrip_with_hostile_values():
    rows = [
        {"id": 1, "name": 'He said "hi"', "note": "a,b"},
        {"id": 2, "name": "line1\nline2", "note": None},
        {"id": 3, "name": "Іван", "note": ""},
    ]
    text = "".join(export_csv(rows, ["id", "name", "note"]))
    parsed = list(csv.reader(io.StringIO(text, newline="")))
    assert parsed[0] == ["id", "name", "note"]
    assert parsed[1] == ["1", 'He said "hi"', "a,b"]
    assert parsed[2] == ["2", "line1\nline2", ""]
    assert parsed[3] == ["3", "Іван", ""]
    assert text.endswith("\r\n")


def test_csv_missing_column_is_empty_and_extra_keys_are_ignored():
    text = "".join(export_csv([{"id": 1, "secret": "s"}], ["id", "name"]))
    assert text == "id,name\r\n1,\r\n"


def test_csv_formula_injection_is_neutralized():
    rows = [{"v": "=HYPERLINK(\"http://evil\")"}, {"v": "+1+1"}, {"v": "-2"}, {"v": "@SUM(A1)"}, {"v": "plain"}, {"v": 5}, {"v": -5}]
    parsed = list(csv.reader(io.StringIO("".join(export_csv(rows, ["v"])), newline="")))[1:]
    assert [r[0] for r in parsed] == ["'=HYPERLINK(\"http://evil\")", "'+1+1", "'-2", "'@SUM(A1)", "plain", "5", "-5"]


def test_ndjson_format():
    rows = [
        {"id": 1, "name": "Іван", "at": dt.datetime(2026, 1, 2, 3, 4, 5), "day": dt.date(2026, 1, 2), "sum": Decimal("10.50")},
        {"id": 2, "name": 'q"uote\nnl', "at": None},
    ]
    text = "".join(export_ndjson(rows))
    lines = text.split("\n")
    assert lines[-1] == "" and len(lines) == 3
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert first == {"id": 1, "name": "Іван", "at": "2026-01-02T03:04:05", "day": "2026-01-02", "sum": "10.50"}
    assert "Іван" in lines[0], "кирилиця не має екрануватись"
    assert second == {"id": 2, "name": 'q"uote\nnl', "at": None}
    assert "\n" not in lines[1], "переноси всередині значень мають бути екрановані"


def test_endpoints_stream_with_correct_headers():
    app = build_app(lambda: iter([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]))
    client = TestClient(app)

    r = client.get("/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.text == "id,name\r\n1,a\r\n2,b\r\n"

    r = client.get("/export.ndjson")
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert "attachment" in r.headers["content-disposition"]
    assert [json.loads(x) for x in r.text.splitlines()] == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]


def test_each_request_gets_fresh_rows():
    calls = []

    def factory():
        calls.append(1)
        return iter([{"id": len(calls)}])

    client = TestClient(build_app(factory))
    assert client.get("/export.ndjson").text == '{"id": 1}\n'
    assert client.get("/export.ndjson").text == '{"id": 2}\n'
