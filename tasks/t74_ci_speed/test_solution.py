import pytest

from solution import audit_ci, critical_path

GOOD = """\
name: ci
on: [push, pull_request]
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install ruff && ruff check .
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -r requirements.txt && pytest
  build:
    needs: [lint, test]
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - run: docker build .
"""


def variant(old, new, text=GOOD):
    assert old in text, old
    return text.replace(old, new)


def test_good_workflow_is_clean():
    assert audit_ci(GOOD) == []


def test_ci001_no_dependency_cache():
    text = variant("          python-version: ${{ matrix.python-version }}\n          cache: pip\n", "          python-version: ${{ matrix.python-version }}\n")
    assert audit_ci(text) == ["CI001"]


def test_ci001_actions_cache_step_counts_as_cache():
    text = variant("          python-version: ${{ matrix.python-version }}\n          cache: pip\n",
                   "          python-version: ${{ matrix.python-version }}\n      - uses: actions/cache@v4\n        with:\n          path: ~/.cache/pip\n          key: pip-${{ hashFiles('requirements.txt') }}\n")
    assert audit_ci(text) == []


@pytest.mark.parametrize("action", ["setup-node", "setup-java", "setup-go"])
def test_ci001_other_setup_actions(action):
    text = variant("actions/setup-python@v5", f"actions/{action}@v4", variant("          cache: pip\n", "", GOOD))
    assert "CI001" in audit_ci(text)


def test_ci002_tests_without_version_matrix():
    single = variant("""    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
""", "")
    assert audit_ci(single) == ["CI002"]
    one_value = variant('python-version: ["3.11", "3.12", "3.13"]', 'python-version: ["3.12"]')
    assert audit_ci(one_value) == ["CI002"]
    other_matrix = variant('python-version: ["3.11", "3.12", "3.13"]', 'os: [ubuntu-latest, windows-latest]')
    assert audit_ci(other_matrix) == ["CI002"]
    npm = variant("pip install -r requirements.txt && pytest", "npm ci && npm test")
    assert audit_ci(npm) == []


def test_ci002_matrix_key_may_be_any_something_version():
    text = variant("python-version: [", "node-version: [")
    assert audit_ci(text) == []


@pytest.mark.parametrize("fail_fast", ["      fail-fast: true\n", ""])
def test_ci003_fail_fast_must_be_explicitly_false(fail_fast):
    text = variant("      fail-fast: false\n", fail_fast)
    assert audit_ci(text) == ["CI003"]


def test_ci003_not_reported_without_matrix():
    text = variant("""    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
""", "    strategy:\n      fail-fast: true\n")
    assert audit_ci(text) == ["CI002"]


@pytest.mark.parametrize("block", [
    "",
    "concurrency:\n  group: ci\n",
    "concurrency:\n  group: ci\n  cancel-in-progress: false\n",
])
def test_ci004_concurrency(block):
    text = variant("concurrency:\n  group: ci-${{ github.ref }}\n  cancel-in-progress: true\n", block)
    assert audit_ci(text) == ["CI004"]


def test_ci004_string_group_form_is_not_enough():
    text = variant("concurrency:\n  group: ci-${{ github.ref }}\n  cancel-in-progress: true\n", "concurrency: ci\n")
    assert audit_ci(text) == ["CI004"]


def test_ci005_serialized_checks():
    assert audit_ci(variant("  test:\n    runs-on", "  test:\n    needs: lint\n    runs-on")) == ["CI005"]
    assert audit_ci(variant("  test:\n    runs-on", "  test:\n    needs: [lint]\n    runs-on")) == ["CI005"]
    assert audit_ci(variant("  build:\n    needs: [lint, test]", "  build:\n    needs: [lint, test]")) == []


def test_ci005_needs_on_non_check_jobs_is_fine():
    text = variant("  test:\n    runs-on", "  test:\n    needs: setup\n    runs-on")
    text += "  setup:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo hi\n"
    assert audit_ci(text) == []


def test_ci005_ids_are_matched_case_insensitively_and_by_substring():
    text = GOOD.replace("lint:", "Ruff-Lint:").replace("needs: [lint, test]", "needs: [Ruff-Lint, test]")
    text = variant("  test:\n    runs-on", "  test:\n    needs: Ruff-Lint\n    runs-on", text)
    assert audit_ci(text) == ["CI005"]


def test_ci006_timeouts():
    text = variant("    timeout-minutes: 10\n", "")
    assert audit_ci(text) == ["CI006"]
    all_missing = GOOD.replace("    timeout-minutes: 10\n", "").replace("    timeout-minutes: 20\n", "").replace("    timeout-minutes: 15\n", "")
    assert audit_ci(all_missing) == ["CI006"]


def test_ci007_full_history_in_check_jobs_only():
    text = variant("""  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
""", """  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
""")
    assert audit_ci(text) == ["CI007"]
    build = GOOD.replace(
        "  build:\n    needs: [lint, test]\n    runs-on: ubuntu-latest\n    timeout-minutes: 15\n    steps:\n      - uses: actions/checkout@v4\n",
        "  build:\n    needs: [lint, test]\n    runs-on: ubuntu-latest\n    timeout-minutes: 15\n    steps:\n      - uses: actions/checkout@v4\n        with:\n          fetch-depth: 0\n")
    assert audit_ci(build) == []


def test_many_problems_sorted_and_empty_workflow():
    bare = """\
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pytest
"""
    assert audit_ci(bare) == ["CI001", "CI002", "CI004", "CI006"]
    assert audit_ci("name: empty\njobs: {}\n") == ["CI004"]


# ---------- critical_path ----------------------------------------------------


PIPE = """\
jobs:
  lint: {runs-on: x, steps: []}
  test: {runs-on: x, steps: [], strategy: {matrix: {python-version: [a, b, c]}}}
  typecheck: {runs-on: x, steps: []}
  build: {needs: [lint, test, typecheck], runs-on: x, steps: []}
  deploy: {needs: build, runs-on: x, steps: []}
"""


def test_critical_path_is_the_longest_chain_not_the_sum():
    minutes = {"lint": 2, "test": 9, "typecheck": 4, "build": 5, "deploy": 3}
    assert critical_path(PIPE, minutes) == (17.0, ["test", "build", "deploy"])


def test_critical_path_changes_when_another_job_gets_slow():
    minutes = {"lint": 2, "test": 9, "typecheck": 20, "build": 5, "deploy": 3}
    assert critical_path(PIPE, minutes) == (28.0, ["typecheck", "build", "deploy"])


def test_missing_minutes_default_to_one():
    assert critical_path(PIPE, {}) == (3.0, ["lint", "build", "deploy"])


def test_tie_breaks_lexicographically():
    text = "jobs:\n  b: {steps: []}\n  a: {steps: []}\n  c: {needs: [a, b], steps: []}\n"
    assert critical_path(text, {"a": 5, "b": 5, "c": 1}) == (6.0, ["a", "c"])


def test_serial_pipeline_is_the_sum():
    text = "jobs:\n  a: {steps: []}\n  b: {needs: a, steps: []}\n  c: {needs: b, steps: []}\n"
    assert critical_path(text, {"a": 1.5, "b": 2, "c": 0.5}) == (4.0, ["a", "b", "c"])


def test_critical_path_errors_and_empty():
    with pytest.raises(ValueError):
        critical_path("jobs:\n  a: {needs: ghost, steps: []}\n", {})
    with pytest.raises(ValueError):
        critical_path("jobs:\n  a: {needs: b, steps: []}\n  b: {needs: a, steps: []}\n", {})
    assert critical_path("jobs: {}\n", {}) == (0.0, [])
