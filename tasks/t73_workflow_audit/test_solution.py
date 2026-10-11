import pytest

from solution import audit_workflow

SHA = "a" * 40

GOOD = f"""\
name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@{SHA}
      - run: pytest -q
      - run: echo "branch is $BRANCH"
        env:
          BRANCH: ${{{{ github.head_ref }}}}
"""


def test_good_workflow_is_clean():
    assert audit_workflow(GOOD) == []


def test_empty_and_minimal():
    assert audit_workflow("") == []
    assert audit_workflow("on: push\njobs: {}\n") == []


def test_gha001_missing_permissions():
    text = "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: ls\n"
    assert audit_workflow(text) == ["GHA001"]


def test_gha001_job_level_permissions_everywhere_is_ok():
    text = (
        "on: push\njobs:\n"
        "  a:\n    runs-on: x\n    permissions: {contents: read}\n    steps:\n      - run: ls\n"
        "  b:\n    runs-on: x\n    permissions: {}\n    steps:\n      - run: ls\n"
    )
    assert audit_workflow(text) == []


def test_gha001_one_job_without_permissions():
    text = (
        "on: push\njobs:\n"
        "  a:\n    runs-on: x\n    permissions: {contents: read}\n    steps:\n      - run: ls\n"
        "  b:\n    runs-on: x\n    steps:\n      - run: ls\n"
    )
    assert audit_workflow(text) == ["GHA001"]


def wf(step_yaml, on="push"):
    return f"on: {on}\npermissions: read-all\njobs:\n  a:\n    runs-on: x\n    steps:\n{step_yaml}"


@pytest.mark.parametrize(
    "uses",
    ["someone/action@v3", "someone/action@main", f"someone/action@{SHA[:39]}", "someone/action/sub@v1"],
)
def test_gha002_unpinned_third_party(uses):
    assert audit_workflow(wf(f"      - uses: {uses}\n")) == ["GHA002"]


@pytest.mark.parametrize(
    "uses",
    [f"someone/action@{SHA}", "actions/checkout@v4", "github/codeql-action/init@v3", "./.github/actions/local",
     "docker://alpine:3.20"],
)
def test_gha002_allowed(uses):
    assert audit_workflow(wf(f"      - uses: {uses}\n")) == []


@pytest.mark.parametrize(
    "expr",
    [
        "${{ github.event.pull_request.title }}",
        "${{ github.event.issue.body }}",
        "${{ github.head_ref }}",
        "${{ github.event.comment.body || 'x' }}",
    ],
)
def test_gha003_script_injection(expr):
    step = f"      - run: echo '{expr}'\n"
    assert audit_workflow(wf(step)) == ["GHA003"]


def test_gha003_multiline_run_and_safe_expressions():
    bad = "      - run: |\n          echo start\n          echo ${{ github.event.pull_request.head.ref }}\n"
    assert audit_workflow(wf(bad)) == ["GHA003"]
    safe = "      - run: echo ${{ github.sha }} ${{ github.run_id }} ${{ secrets.TOKEN }}\n"
    assert audit_workflow(wf(safe)) == []


def test_gha003_untrusted_in_env_is_fine():
    step = "      - run: echo \"$TITLE\"\n        env:\n          TITLE: ${{ github.event.pull_request.title }}\n"
    assert audit_workflow(wf(step)) == []


CHECKOUT_HEAD = (
    "      - uses: actions/checkout@v4\n"
    "        with:\n"
    "          ref: ${{ github.event.pull_request.head.sha }}\n"
)


@pytest.mark.parametrize("on", ["pull_request_target", "[push, pull_request_target]", "{pull_request_target: {types: [opened]}}"])
def test_gha004_pwn_request(on):
    assert audit_workflow(wf(CHECKOUT_HEAD, on=on)) == ["GHA004"]


def test_gha004_head_ref_variant():
    step = "      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.head_ref }}\n"
    assert audit_workflow(wf(step, on="pull_request_target")) == ["GHA004"]


def test_gha004_not_triggered_for_plain_pull_request_or_default_checkout():
    assert audit_workflow(wf(CHECKOUT_HEAD, on="pull_request")) == []
    assert audit_workflow(wf("      - uses: actions/checkout@v4\n", on="pull_request_target")) == []


def test_gha005_long_lived_aws_keys():
    step = (
        "      - uses: aws-actions/configure-aws-credentials@" + SHA + "\n"
        "        with:\n"
        "          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}\n"
        "          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}\n"
    )
    assert audit_workflow(wf(step)) == ["GHA005"]


def test_gha005_oidc_is_fine():
    step = (
        "      - uses: aws-actions/configure-aws-credentials@" + SHA + "\n"
        "        with:\n"
        "          role-to-assume: arn:aws:iam::123456789012:role/ci\n"
        "          aws-region: eu-central-1\n"
    )
    assert audit_workflow(wf(step)) == []


def test_reusable_workflow_job_without_steps():
    text = "on: push\npermissions: read-all\njobs:\n  call:\n    uses: ./.github/workflows/reusable.yml\n"
    assert audit_workflow(text) == []


def test_everything_wrong_at_once():
    text = (
        "on: [pull_request_target]\n"
        "jobs:\n"
        "  a:\n"
        "    runs-on: x\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "        with:\n"
        "          ref: ${{ github.event.pull_request.head.sha }}\n"
        "      - uses: evil/action@main\n"
        "      - run: echo ${{ github.event.pull_request.title }}\n"
        "        env:\n"
        "          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}\n"
    )
    assert audit_workflow(text) == ["GHA001", "GHA002", "GHA003", "GHA004", "GHA005"]
