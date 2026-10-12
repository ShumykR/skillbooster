import pytest

from solution import changelog, next_version, parse_commit


# ---------- parse_commit ------------------------------------------------------


def test_parse_simple_and_scoped():
    assert parse_commit("feat: add search") == {"type": "feat", "scope": None, "description": "add search", "breaking": False, "note": None}
    assert parse_commit("fix(api): handle empty body") == {
        "type": "fix", "scope": "api", "description": "handle empty body", "breaking": False, "note": None}


def test_parse_bang_is_breaking_with_description_as_note():
    r = parse_commit("feat(api)!: drop v1")
    assert r["breaking"] is True and r["note"] == "drop v1" and r["scope"] == "api"
    assert parse_commit("refactor!: rename")["breaking"] is True


@pytest.mark.parametrize("footer", ["BREAKING CHANGE: tokens now expire", "BREAKING-CHANGE: tokens now expire"])
def test_parse_breaking_footer(footer):
    r = parse_commit(f"feat: new auth\n\nlong body here\n\nRefs #12\n{footer}  \n")
    assert r["breaking"] is True and r["note"] == "tokens now expire" and r["description"] == "new auth"


def test_breaking_text_in_the_middle_of_a_line_is_not_a_footer():
    assert parse_commit("fix: x\n\nthis is not a BREAKING CHANGE: really")["breaking"] is False


@pytest.mark.parametrize("message", ["", "update stuff", "Feat: caps", "feat:no space", "feat(): empty scope", "feat: ", "fix(a b): x", ": nothing", "feat(api: broken"])
def test_parse_rejects_nonconforming(message):
    assert parse_commit(message) is None


def test_parse_trims_whitespace():
    assert parse_commit("feat:   spaced out   ")["description"] == "spaced out"


# ---------- next_version ------------------------------------------------------


@pytest.mark.parametrize("current, messages, expected", [
    ("1.2.3", ["fix: a"], "1.2.4"),
    ("1.2.3", ["perf: a"], "1.2.4"),
    ("1.2.3", ["feat: a"], "1.3.0"),
    ("1.2.3", ["feat!: a"], "2.0.0"),
    ("1.2.3", ["fix: a\n\nBREAKING CHANGE: b"], "2.0.0"),
    ("1.2.3", ["docs: a", "chore: b", "ci: c"], None),
    ("1.2.3", ["chore!: drop python 3.9"], "2.0.0"),
    ("1.2.3", ["fix: a", "feat: b", "docs: c"], "1.3.0"),
    ("1.2.3", ["fix: a", "feat: b", "feat!: c", "fix: d"], "2.0.0"),
    ("1.2.3", ["random message", "WIP"], None),
    ("1.2.3", [], None),
    ("0.4.1", ["feat: a"], "0.4.2"),
    ("0.4.1", ["fix: a"], "0.4.2"),
    ("0.4.1", ["feat!: a"], "0.5.0"),
    ("0.4.1", ["docs: a"], None),
    ("0.0.0", ["feat!: a"], "0.1.0"),
    ("9.9.9", ["feat: a"], "9.10.0"),
])
def test_next_version(current, messages, expected):
    assert next_version(current, messages) == expected


@pytest.mark.parametrize("bad", ["1.2", "v1.2.3", "1.2.3-rc.1", "x.y.z", ""])
def test_next_version_rejects_bad_current(bad):
    with pytest.raises(ValueError):
        next_version(bad, ["fix: a"])


# ---------- changelog ---------------------------------------------------------


COMMITS = [
    ("abcdef1234567", "feat(api): add /users"),
    ("1111111aaaaaaa", "fix(db): close cursor"),
    ("2222222bbbbbbb", "docs: update readme"),
    ("3333333ccccccc", "feat: dark mode"),
    ("4444444ddddddd", "perf(cache): faster lookup"),
    ("5555555eeeeeee", "fix: typo\n\nBREAKING CHANGE: error codes renamed"),
    ("666666", "not conventional"),
]


def test_changelog_full_example():
    expected = """\
## 1.3.0 (2026-01-02)

### ⚠ BREAKING CHANGES

* error codes renamed (5555555)

### Features

* **api:** add /users (abcdef1)
* dark mode (3333333)

### Bug Fixes

* **db:** close cursor (1111111)
* typo (5555555)

### Performance Improvements

* **cache:** faster lookup (4444444)
"""
    assert changelog("1.3.0", "2026-01-02", COMMITS) == expected


def test_changelog_only_headline_when_nothing_to_report():
    assert changelog("1.0.1", "2026-02-03", [("abc1234", "docs: x"), ("def5678", "chore: y")]) == "## 1.0.1 (2026-02-03)\n"
    assert changelog("1.0.1", "2026-02-03", []) == "## 1.0.1 (2026-02-03)\n"


def test_changelog_skips_empty_sections_and_keeps_order_of_sections():
    out = changelog("1.0.1", "2026-02-03", [("aaaaaaa1", "perf: p"), ("bbbbbbb2", "fix: f")])
    assert out == "## 1.0.1 (2026-02-03)\n\n### Bug Fixes\n\n* f (bbbbbbb)\n\n### Performance Improvements\n\n* p (aaaaaaa)\n"


def test_breaking_from_chore_appears_only_in_breaking_section():
    out = changelog("2.0.0", "2026-03-04", [("abcdef0123", "chore!: drop python 3.9")])
    assert out == "## 2.0.0 (2026-03-04)\n\n### ⚠ BREAKING CHANGES\n\n* drop python 3.9 (abcdef0)\n"


def test_breaking_bang_feature_is_listed_in_both_sections():
    out = changelog("2.0.0", "2026-03-04", [("abcdef0123", "feat(api)!: new auth")])
    assert "### ⚠ BREAKING CHANGES\n\n* **api:** new auth (abcdef0)" in out
    assert "### Features\n\n* **api:** new auth (abcdef0)" in out


def test_short_sha_is_not_padded():
    assert "(abc)" in changelog("1.0.1", "d", [("abc", "fix: x")])
