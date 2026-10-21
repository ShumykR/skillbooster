import hashlib
import re

import pytest

from solution import chunk_markdown

FENCE = "```"
CODE = "\n".join([FENCE + "bash", "# install it", "pip install thing", FENCE])
TABLE = "\n".join(["| os | cmd |", "|----|-----|", "| mac | brew |"])
PARA_INSTALL = "Run the installer now."

DOC = "\n".join([
    "Intro line one.",
    "",
    "# Guide",
    "",
    "Guide intro paragraph here.",
    "",
    "## Install",
    "",
    PARA_INSTALL,
    "",
    CODE,
    "",
    TABLE,
    "",
    "### Windows",
    "",
    "Use the msi.",
    "",
    "## Usage",
    "",
    "Call the thing.",
])


def texts(res, kind="children"):
    return [c["text"] for c in res[kind]]


def paths(res, kind="children"):
    return [c["path"] for c in res[kind]]


def sha(title, path, kind, text):
    return hashlib.sha1("\x1f".join([title, " > ".join(path), kind, text]).encode()).hexdigest()[:12]


# --- структура: секції, шляхи, parent ----------------------------------------------------------

def test_parents_follow_sections_with_paths_and_body_text():
    res = chunk_markdown(DOC, "Docs", max_words=1000)
    assert set(res) == {"parents", "children"}
    assert paths(res, "parents") == [[], ["Guide"], ["Guide", "Install"], ["Guide", "Install", "Windows"],
                                     ["Guide", "Usage"]]
    assert texts(res, "parents") == [
        "Intro line one.",
        "Guide intro paragraph here.",
        PARA_INSTALL + "\n\n" + CODE + "\n\n" + TABLE,
        "Use the msi.",
        "Call the thing.",
    ]
    assert all(p["kind"] == "parent" for p in res["parents"])
    assert "## Install" not in res["parents"][2]["text"]


def test_children_have_context_prefix_and_parent_links():
    res = chunk_markdown(DOC, "Docs", max_words=1000)
    assert len(res["children"]) == 5
    by_id = {p["id"]: p for p in res["parents"]}
    assert len(by_id) == 5
    for child, parent in zip(res["children"], res["parents"]):
        assert child["kind"] == "child"
        assert child["parent_id"] == parent["id"]
        assert child["path"] == parent["path"]
        assert child["text"] == parent["text"]
    c = res["children"][2]
    assert c["context"] == "Docs > Guide > Install"
    assert c["embed_text"] == "Docs > Guide > Install\n\n" + c["text"]
    first = res["children"][0]
    assert first["path"] == [] and first["context"] == "Docs"
    assert first["embed_text"] == "Docs\n\nIntro line one."


def test_children_of_a_section_rebuild_the_parent_without_loss():
    for mw in (1, 3, 5, 8, 12, 40, 1000):
        res = chunk_markdown(DOC, "Docs", max_words=mw)
        by_parent = {}
        for c in res["children"]:
            by_parent.setdefault(c["parent_id"], []).append(c["text"])
        for p in res["parents"]:
            assert "\n\n".join(by_parent[p["id"]]) == p["text"], mw


def test_output_is_in_document_order():
    res = chunk_markdown(DOC, "Docs", max_words=5)
    order = [c["path"] for c in res["children"]]
    assert order[:2] == [[], ["Guide"]]
    assert order[-2:] == [["Guide", "Install", "Windows"], ["Guide", "Usage"]] or order[-1] == ["Guide", "Usage"]
    assert order.index(["Guide", "Usage"]) > order.index(["Guide", "Install", "Windows"])


# --- пакування й цілісність блоків -------------------------------------------------------------

def test_greedy_packing_with_small_limit_keeps_blocks_whole():
    res = chunk_markdown(DOC, "Docs", max_words=5)
    install = [c["text"] for c in res["children"] if c["path"] == ["Guide", "Install"]]
    assert install == [PARA_INSTALL, CODE, TABLE]


def test_packing_limit_is_inclusive():
    # абзац 4 слова + код 8 слів = 12 рівно в межі; таблиця (13 слів) не вміщається
    res = chunk_markdown(DOC, "Docs", max_words=12)
    install = [c["text"] for c in res["children"] if c["path"] == ["Guide", "Install"]]
    assert install == [PARA_INSTALL + "\n\n" + CODE, TABLE]
    res = chunk_markdown(DOC, "Docs", max_words=11)
    install = [c["text"] for c in res["children"] if c["path"] == ["Guide", "Install"]]
    assert install == [PARA_INSTALL, CODE, TABLE]


@pytest.mark.parametrize("mw", list(range(1, 31)) + [100])
def test_code_and_tables_are_never_split(mw):
    res = chunk_markdown(DOC, "Docs", max_words=mw)
    kids = texts(res)
    assert any(CODE in t for t in kids)
    assert any(TABLE in t for t in kids)
    for t in kids:
        assert t.count(FENCE) % 2 == 0
        table_lines = [ln for ln in t.split("\n") if ln.startswith("|")]
        assert len(table_lines) in (0, 3)


def test_oversized_block_gets_its_own_chunk():
    text = "a b\n\none two three four five six seven eight nine ten\n\nc d"
    res = chunk_markdown(text, "T", max_words=3)
    assert texts(res) == ["a b", "one two three four five six seven eight nine ten", "c d"]


def test_consecutive_small_blocks_are_packed_together():
    text = "\n\n".join(["aa bb cc"] * 5)
    res = chunk_markdown(text, "T", max_words=7)
    assert texts(res) == ["aa bb cc\n\naa bb cc"] * 2 + ["aa bb cc"]


# --- заголовки та fenced-код -------------------------------------------------------------------

def test_heading_inside_fence_is_not_a_heading():
    text = "# A\n\n" + FENCE + "\n# not a heading\n## neither\n" + FENCE + "\n\nafter"
    res = chunk_markdown(text, "T", max_words=1000)
    assert paths(res, "parents") == [["A"]]
    assert res["parents"][0]["text"] == FENCE + "\n# not a heading\n## neither\n" + FENCE + "\n\nafter"


def test_tilde_fence_and_longer_fence_with_inner_fence():
    text = "~~~\n# x\n~~~\n\n````\n```\ninner\n```\n````\n\nafter"
    res = chunk_markdown(text, "T", max_words=1000)
    assert paths(res, "parents") == [[]]
    assert texts(res) == ["~~~\n# x\n~~~\n\n````\n```\ninner\n```\n````\n\nafter"]
    res = chunk_markdown(text, "T", max_words=1)
    assert texts(res) == ["~~~\n# x\n~~~", "````\n```\ninner\n```\n````", "after"]


def test_fence_closer_must_match_character_and_length():
    text = "```\na\n~~~\n``\n# still code\n```\n\n# Real"
    res = chunk_markdown(text, "T", max_words=1)
    assert texts(res) == ["```\na\n~~~\n``\n# still code\n```"]
    assert res["children"][0]["path"] == []


def test_unclosed_fence_runs_to_end_of_document():
    text = "# A\n\nintro\n\n" + FENCE + "\ncode\n# Not heading\n\nstill code\n\n\n"
    res = chunk_markdown(text, "T", max_words=1)
    assert texts(res) == ["intro", FENCE + "\ncode\n# Not heading\n\nstill code"]
    assert paths(res) == [["A"], ["A"]]


@pytest.mark.parametrize("line", ["#NoSpace", "####### Seven", "    # indented", "text # not", "#hashtag rules"])
def test_not_a_heading_stays_in_paragraph(line):
    res = chunk_markdown("# A\n\n" + line, "T", max_words=1000)
    assert paths(res, "parents") == [["A"]]
    assert res["parents"][0]["text"] == line


@pytest.mark.parametrize("line, title", [
    ("## Title ##", "Title"), ("## Title", "Title"), ("   ## Three spaces", "Three spaces"), ("# C#", "C#"),
    ("###### Deep   ", "Deep"), ("#\tTabbed", "Tabbed"), ("# Trailing ###   ", "Trailing"),
])
def test_heading_title_parsing(line, title):
    res = chunk_markdown(line + "\n\nbody", "T", max_words=1000)
    assert paths(res, "parents") == [[title]]


def test_empty_heading_is_a_heading_with_empty_title():
    res = chunk_markdown("# A\n\nx\n\n###\n\ny", "T", max_words=1000)
    assert paths(res, "parents") == [["A"], ["A", ""]]
    assert texts(res, "parents") == ["x", "y"]
    assert res["children"][1]["context"] == "T > A > "


def test_levels_may_be_skipped_and_siblings_reset_the_path():
    text = "# A\n\na\n\n### C\n\nc\n\n## B\n\nb\n\n# D\n\nd\n\n#### E\n\ne"
    res = chunk_markdown(text, "T", max_words=1000)
    assert paths(res, "parents") == [["A"], ["A", "C"], ["A", "B"], ["D"], ["D", "E"]]


def test_heading_without_body_makes_no_chunk_but_stays_in_path():
    res = chunk_markdown("# A\n## B\n\nbody\n\n## C\n### D\n\nmore", "T", max_words=1000)
    assert paths(res, "parents") == [["A", "B"], ["A", "C", "D"]]
    assert texts(res) == ["body", "more"]


def test_text_before_first_heading_has_empty_path():
    res = chunk_markdown("preface\n\n# A\n\nbody", "My Doc", max_words=1000)
    assert paths(res, "parents") == [[], ["A"]]
    assert res["children"][0]["context"] == "My Doc"


def test_heading_directly_after_paragraph_line_breaks_the_paragraph():
    res = chunk_markdown("text\n## H\nbody", "T", max_words=1000)
    assert paths(res, "parents") == [[], ["H"]]
    assert texts(res, "parents") == ["text", "body"]


# --- абзаци, таблиці, порожні рядки ------------------------------------------------------------

def test_table_and_fence_interrupt_a_paragraph_without_blank_line():
    text = "para line\n| t |\n| - |\nnext\n" + FENCE + "\ncode\n" + FENCE + "\nlast"
    res = chunk_markdown(text, "T", max_words=1)
    assert texts(res) == ["para line", "| t |\n| - |", "next", FENCE + "\ncode\n" + FENCE, "last"]


def test_indented_table_rows_are_recognised_and_kept_verbatim():
    text = "x\n\n  | a | b |\n  | - | - |\n\ny"
    res = chunk_markdown(text, "T", max_words=1)
    assert texts(res) == ["x", "  | a | b |\n  | - | - |", "y"]


def test_multiline_paragraph_is_one_block_and_whitespace_only_line_separates():
    res = chunk_markdown("line one\nline two\n   \nsecond", "T", max_words=1)
    assert texts(res) == ["line one\nline two", "second"]


def test_crlf_equals_lf_and_trailing_blank_lines_are_ignored():
    lf = chunk_markdown(DOC, "Docs", max_words=7)
    crlf = chunk_markdown(DOC.replace("\n", "\r\n") + "\r\n\r\n", "Docs", max_words=7)
    assert crlf == lf
    assert chunk_markdown(DOC + "\n\n   \n", "Docs", max_words=7) == lf


@pytest.mark.parametrize("text", ["", "\n\n", "   \n  "])
def test_empty_documents(text):
    assert chunk_markdown(text, "T") == {"parents": [], "children": []}


@pytest.mark.parametrize("bad", [0, -1, -50])
def test_invalid_max_words(bad):
    with pytest.raises(ValueError):
        chunk_markdown("text", "T", max_words=bad)


def test_unicode_titles_and_text():
    text = "# Вступ\n\nПерший абзац.\n\n## Запуск\n\nДругий абзац."
    res = chunk_markdown(text, "Довідка", max_words=1000)
    assert paths(res, "parents") == [["Вступ"], ["Вступ", "Запуск"]]
    assert res["children"][1]["context"] == "Довідка > Вступ > Запуск"
    assert res["children"][1]["text"] == "Другий абзац."


# --- стабільні id ------------------------------------------------------------------------------

def test_id_format_and_formula():
    res = chunk_markdown(DOC, "Docs", max_words=1000)
    for c in res["parents"] + res["children"]:
        assert re.fullmatch(r"[0-9a-f]{12}", c["id"]), c["id"]
    p = res["parents"][1]
    assert p["id"] == sha("Docs", ["Guide"], "parent", p["text"])
    c = res["children"][1]
    assert c["id"] == sha("Docs", ["Guide"], "child", c["text"])
    assert c["id"] != p["id"]


def test_ids_are_deterministic_and_unique():
    a = chunk_markdown(DOC, "Docs", max_words=5)
    b = chunk_markdown(DOC, "Docs", max_words=5)
    assert a == b
    ids = [c["id"] for c in a["parents"]] + [c["id"] for c in a["children"]]
    assert len(ids) == len(set(ids))


def test_editing_one_section_keeps_ids_of_all_others():
    before = chunk_markdown(DOC, "Docs", max_words=5)
    edited = DOC.replace("Call the thing.", "Call the thing twice.")
    after = chunk_markdown(edited, "Docs", max_words=5)
    old = {c["text"]: c["id"] for c in before["children"]}
    new = {c["text"]: c["id"] for c in after["children"]}
    unchanged = [t for t in old if t != "Call the thing."]
    assert unchanged and all(new[t] == old[t] for t in unchanged)
    assert "Call the thing." not in new
    assert new["Call the thing twice."] != old["Call the thing."]
    old_p = {p["path"][-1] if p["path"] else "": p["id"] for p in before["parents"]}
    new_p = {p["path"][-1] if p["path"] else "": p["id"] for p in after["parents"]}
    assert old_p["Usage"] != new_p["Usage"]
    assert all(old_p[k] == new_p[k] for k in old_p if k != "Usage")


def test_ids_do_not_depend_on_position_in_document():
    a = "# One\n\nalpha text\n\n# Two\n\nbeta text"
    b = "# Two\n\nbeta text\n\n# One\n\nalpha text"
    ra, rb = chunk_markdown(a, "T"), chunk_markdown(b, "T")
    assert {c["id"] for c in ra["children"]} == {c["id"] for c in rb["children"]}
    assert {c["id"] for c in ra["parents"]} == {c["id"] for c in rb["parents"]}


def test_ids_depend_on_title_and_path():
    a = chunk_markdown("# One\n\nsame text", "T1")
    b = chunk_markdown("# One\n\nsame text", "T2")
    c = chunk_markdown("# Other\n\nsame text", "T1")
    assert a["children"][0]["id"] != b["children"][0]["id"]
    assert a["children"][0]["id"] != c["children"][0]["id"]


def test_duplicate_chunks_get_numbered_suffixes():
    res = chunk_markdown("# A\n\nsame\n\nsame\n\nsame", "T", max_words=1)
    base = sha("T", ["A"], "child", "same")
    assert [c["id"] for c in res["children"]] == [base, base + "-2", base + "-3"]
    assert len(res["parents"]) == 1
    assert res["parents"][0]["id"] == sha("T", ["A"], "parent", "same\n\nsame\n\nsame")


def test_same_text_under_different_headings_is_not_a_duplicate():
    res = chunk_markdown("# A\n\nsame\n\n# B\n\nsame", "T", max_words=1000)
    ids = [c["id"] for c in res["children"]]
    assert ids[0] != ids[1] and all("-" not in i for i in ids)


def test_input_is_not_modified_and_results_are_independent():
    res = chunk_markdown(DOC, "Docs", max_words=1000)
    res["children"][2]["path"].append("mutated")
    again = chunk_markdown(DOC, "Docs", max_words=1000)
    assert again["children"][2]["path"] == ["Guide", "Install"]
    assert res["parents"][2]["path"] == ["Guide", "Install"]
