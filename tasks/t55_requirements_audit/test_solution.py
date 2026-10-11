import pytest

from solution import audit_requirements

ADV = {"Django": "4.2.11", "requests": "2.31.0", "PyYAML": "6.0.1"}

GOOD = """\
# згенеровано pip-compile
fastapi==0.110.0 \\
    --hash=sha256:aaaa \\
    --hash=sha256:bbbb
django==4.2.11 --hash=sha256:cc
uvicorn[standard]==0.30.0 --hash=sha256:dd
colorama==0.4.6 ; sys_platform == "win32" --hash=sha256:ee  # лише windows
requests==2.31.0 \\
    --hash=sha256:ff
"""


def test_good_file_is_clean():
    assert audit_requirements(GOOD, ADV) == []


def test_empty_and_comment_only():
    assert audit_requirements("", ADV) == []
    assert audit_requirements("# nothing\n\n   \n", ADV) == []


@pytest.mark.parametrize("spec", ["flask", "flask>=3.0", "flask~=3.0", "flask==3.*", "flask<4", "flask!=3.0.0", "flask===3.0"])
def test_unpinned(spec):
    assert audit_requirements(spec + " --hash=sha256:aa\n", ADV) == ["unpinned:flask"]


def test_pinned_with_spaces_around_operator():
    assert audit_requirements("flask == 3.0.2 --hash=sha256:aa\n", ADV) == []


def test_no_hash_is_reported_even_for_pinned():
    assert audit_requirements("flask==3.0.2\n", ADV) == ["no_hash:flask"]


def test_unpinned_and_no_hash_both_reported():
    assert audit_requirements("flask\n", ADV) == ["no_hash:flask", "unpinned:flask"]


def test_hash_on_continuation_line_counts():
    text = "flask==3.0.2 \\\n    --hash=sha256:aa\n"
    assert audit_requirements(text, ADV) == []


def test_hash_belongs_only_to_its_own_requirement():
    text = "flask==3.0.2 \\\n    --hash=sha256:aa\njinja2==3.1.3\n"
    assert audit_requirements(text, ADV) == ["no_hash:jinja2"]


@pytest.mark.parametrize(
    "version, bad",
    [("4.2.9", True), ("4.2.10", True), ("4.2.11", False), ("4.2.12", False), ("4.10", False), ("4.2", True),
     ("3.2.25", True), ("5.0", False)],
)
def test_vulnerable_versions_numeric_compare(version, bad):
    result = audit_requirements(f"django=={version} --hash=sha256:aa\n", ADV)
    assert result == (["vulnerable:django"] if bad else [])


def test_missing_components_are_zeros():
    assert audit_requirements("requests==2.31 --hash=sha256:aa\n", ADV) == []
    assert audit_requirements("requests==2.30 --hash=sha256:aa\n", ADV) == ["vulnerable:requests"]


def test_names_are_normalized_everywhere():
    text = "PyYAML==5.4 --hash=sha256:aa\nTyping_Extensions\nzope.interface>=1 --hash=sha256:bb\n"
    assert audit_requirements(text, ADV) == [
        "no_hash:typing-extensions",
        "unpinned:typing-extensions",
        "unpinned:zope-interface",
        "vulnerable:pyyaml",
    ]


def test_extras_and_markers_do_not_confuse_the_parser():
    text = (
        "uvicorn[standard]>=0.30 --hash=sha256:aa\n"
        'colorama==0.4.6 ; python_version < "3.9" --hash=sha256:bb\n'
    )
    assert audit_requirements(text, ADV) == ["unpinned:uvicorn"]


def test_options_and_comments_are_ignored():
    text = (
        "-r base.txt\n"
        "--index-url https://pypi.org/simple\n"
        "--extra-index-url https://example.com/simple\n"
        "flask==3.0.2 --hash=sha256:aa # зафіксовано\n"
        "   # django>=1\n"
    )
    assert audit_requirements(text, ADV) == []


def test_unpinned_package_is_not_reported_as_vulnerable():
    assert audit_requirements("django>=3 --hash=sha256:aa\n", ADV) == ["unpinned:django"]


def test_results_sorted_and_unique():
    text = "zlib-ng\nflask\nflask==3.0 --hash=sha256:aa\nDjango==3.2 --hash=sha256:bb\n"
    assert audit_requirements(text, ADV) == [
        "no_hash:flask",
        "no_hash:zlib-ng",
        "unpinned:flask",
        "unpinned:zlib-ng",
        "vulnerable:django",
    ]
