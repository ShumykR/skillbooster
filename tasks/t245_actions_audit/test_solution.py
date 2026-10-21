import re

import pytest

from solution import audit_workflow

SHA = "a" * 40
EXPECT = re.compile(r"\s+# EXPECT: (.*)$")


def run(text):
    """Читає очікування з коментарів `# EXPECT: rule[, rule]` (їх прибирає перед аудитом, рядки лишаються)."""
    text = text.replace("SHA", SHA)
    expected = []
    clean = []
    for n, line in enumerate(text.split("\n"), 1):
        m = EXPECT.search(line)
        if m:
            expected += [(r.strip(), n) for r in m.group(1).split(",")]
            line = line[:m.start()]
        clean.append(line)
    findings = audit_workflow("\n".join(clean))
    assert isinstance(findings, list)
    for f in findings:
        assert set(f) == {"rule", "line", "fix"}, f
        assert isinstance(f["fix"], str) and f["fix"].strip(), f
        assert isinstance(f["line"], int)
    got = [(f["rule"], f["line"]) for f in findings]
    assert got == sorted(set(expected), key=lambda e: (e[1], e[0]))
    return findings


def test_clean_workflow():
    run("""\
name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
env:
  LANG: C
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@SHA
      - uses: astral-sh/setup-uv@SHA
      - uses: ./.github/actions/local
      - uses: docker://alpine:3.20
      - run: echo "$TITLE"
        env:
          TITLE: ${{ github.event.pull_request.title }}
      - run: echo ${{ github.sha }} ${{ github.event.pull_request.number }} ${{ secrets.TOKEN }}
      - uses: actions/cache@SHA
        with:
          path: ~/.cache
          key: ${{ runner.os }}-${{ hashFiles('uv.lock') }}
""")


def test_empty_and_degenerate_inputs():
    assert audit_workflow("") == []
    assert audit_workflow("just a string") == []
    assert audit_workflow("- a\n- b\n") == []
    assert audit_workflow("on: push\njobs: {}\n") == []


def test_invalid_yaml_is_value_error():
    with pytest.raises(ValueError):
        audit_workflow("jobs: [unclosed\n  a: : :")


@pytest.mark.parametrize("ref, bad", [
    ("v4", True), ("main", True), ("SHA", False), ("a" * 39, True), ("a" * 41, True), ("A" * 40, True), ("", True),
])
def test_unpinned_action_variants(ref, bad):
    tag = "  # EXPECT: unpinned-action" if bad else ""
    run(f"""\
on: push
permissions: {{}}
jobs:
  a:
    runs-on: x
    steps:
      - uses: actions/checkout@{ref}{tag}
""".replace("SHA", SHA))


def test_unpinned_without_at_and_job_level_reusable_workflow():
    run("""\
on: push
permissions: {}
jobs:
  a:
    runs-on: x
    steps:
      - uses: some/action  # EXPECT: unpinned-action
  b:
    uses: org/repo/.github/workflows/ci.yml@v1  # EXPECT: unpinned-action
  c:
    uses: org/repo/.github/workflows/ci.yml@SHA
  d:
    uses: ./.github/workflows/local.yml
""")


def test_missing_permissions_reports_each_uncovered_job():
    run("""\
on: push
jobs:
  a:  # EXPECT: missing-permissions
    runs-on: x
    steps:
      - run: ls
  b:
    runs-on: x
    permissions: {contents: read}
    steps:
      - run: ls
  c:  # EXPECT: missing-permissions
    runs-on: x
    steps:
      - run: ls
""")


def test_top_level_permissions_cover_all_jobs():
    run("""\
on: push
permissions: read-all
jobs:
  a:
    runs-on: x
    steps:
      - run: ls
""")


def test_broad_permissions():
    run("""\
on: push
permissions: write-all  # EXPECT: broad-permissions
jobs:
  a:
    runs-on: x
    steps:
      - run: ls
""")
    run("""\
on: push
permissions:  # EXPECT: broad-permissions
  contents: read
  packages: write
jobs:
  a:
    runs-on: x
    steps:
      - run: ls
""")


def test_job_level_write_scope_is_ok_but_write_all_is_not():
    run("""\
on: push
permissions:
  contents: read
jobs:
  release:
    runs-on: x
    permissions:
      contents: write
      id-token: write
    steps:
      - run: ls
  bad:
    runs-on: x
    permissions: write-all  # EXPECT: broad-permissions
    steps:
      - run: ls
""")


@pytest.mark.parametrize("on", [
    "on: pull_request_target",
    "on: [push, pull_request_target]",
    "on:\n  pull_request_target:\n    types: [opened]",
])
def test_pr_target_checkout_trigger_shapes(on):
    run(f"""\
{on}
permissions: {{}}
jobs:
  a:
    runs-on: x
    steps:
      - uses: actions/checkout@SHA  # EXPECT: pr-target-checkout
        with:
          ref: ${{{{ github.event.pull_request.head.sha }}}}
""")


@pytest.mark.parametrize("with_block", [
    "ref: ${{ github.head_ref }}",
    "ref: refs/pull/${{ github.event.pull_request.head.ref }}/merge",
    "repository: ${{ github.event.pull_request.head.repo.full_name }}",
    "ref: ${{ github.event.workflow_run.head_sha }}",
])
def test_pr_target_checkout_ref_sources(with_block):
    run(f"""\
on: pull_request_target
permissions: {{}}
jobs:
  a:
    runs-on: x
    steps:
      - uses: actions/checkout@SHA  # EXPECT: pr-target-checkout
        with:
          {with_block}
""")


def test_pr_target_checkout_not_flagged_when_safe():
    run("""\
on: pull_request_target
permissions: {}
jobs:
  a:
    runs-on: x
    steps:
      - uses: actions/checkout@SHA
      - uses: actions/checkout@SHA
        with:
          ref: main
""")
    run("""\
on: pull_request
permissions: {}
jobs:
  a:
    runs-on: x
    steps:
      - uses: actions/checkout@SHA
        with:
          ref: ${{ github.event.pull_request.head.sha }}
""")


@pytest.mark.parametrize("expr", [
    "github.event.issue.title", "github.event.issue.body", "github.event.pull_request.title",
    "github.event.pull_request.body", "github.event.comment.body", "github.event.review.body",
    "github.event.review_comment.body", "github.event.discussion.title", "github.head_ref",
    "github.event.pull_request.head.ref", "github.event.pull_request.head.label",
    "github.event.head_commit.message", "github.event.head_commit.author.email",
    "github.event.commits[0].message", "github.event.commits[0].author.name", "github.event.pages[0].page_name",
    "github.event.workflow_run.head_branch", "github.event.workflow_run.head_commit.message",
    "format('{0}', github.event.issue.title)", "contains(github.head_ref, 'x')",
])
def test_script_injection_contexts(expr):
    run(f"""\
on: issues
permissions: {{}}
jobs:
  a:
    runs-on: x
    steps:
      - run: echo ${{{{ {expr} }}}}  # EXPECT: script-injection
""")


def test_script_injection_multiline_run_reports_the_run_key_line():
    run("""\
on: issues
permissions: {}
jobs:
  a:
    runs-on: x
    steps:
      - name: build
        run: |  # EXPECT: script-injection
          set -e
          echo "title: ${{ github.event.issue.title }}"
          make
""")


def test_script_injection_in_github_script():
    run("""\
on: issues
permissions: {}
jobs:
  a:
    runs-on: x
    steps:
      - uses: actions/github-script@SHA
        with:
          script: |  # EXPECT: script-injection
            console.log("${{ github.event.issue.title }}")
      - uses: actions/github-script@SHA
        with:
          script: |
            console.log(context.payload.issue.title)
""")


def test_env_indirection_is_safe_and_other_actions_with_script_are_ignored():
    run("""\
on: issues
permissions: {}
jobs:
  a:
    runs-on: x
    steps:
      - run: echo "$T"
        env:
          T: ${{ github.event.issue.title }}
      - uses: some/action@SHA
        with:
          script: ${{ github.event.issue.title }}
""")


def test_secrets_in_workflow_env():
    run("""\
on: push
permissions: {}
env:  # EXPECT: secrets-in-workflow-env
  A: 1
  TOKEN: ${{ secrets.DEPLOY_TOKEN }}
jobs:
  a:
    runs-on: x
    env:
      OK: ${{ secrets.FOR_THIS_JOB }}
    steps:
      - run: ls
        env:
          STEP: ${{ secrets.FOR_STEP }}
""")


@pytest.mark.parametrize("runs_on", [
    "self-hosted", "[self-hosted, linux]", "[Linux, Self-Hosted]", "{group: ci, labels: [self-hosted]}",
])
def test_self_hosted_runner_with_pr_trigger(runs_on):
    run(f"""\
on: [push, pull_request]
permissions: {{}}
jobs:
  a:
    runs-on: {runs_on}  # EXPECT: self-hosted-pr
    steps:
      - run: ls
""")


def test_self_hosted_without_pr_trigger_or_with_hosted_runner_is_ok():
    run("""\
on: push
permissions: {}
jobs:
  a:
    runs-on: self-hosted
    steps:
      - run: ls
""")
    run("""\
on: pull_request
permissions: {}
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: ls
""")


@pytest.mark.parametrize("action", ["actions/cache", "actions/cache/restore", "actions/cache/save"])
def test_cache_key_injection(action):
    run(f"""\
on: pull_request_target
permissions: {{}}
jobs:
  a:
    runs-on: x
    steps:
      - uses: {action}@SHA
        with:
          path: p
          key: v1-${{{{ github.head_ref }}}}  # EXPECT: cache-key-injection
          restore-keys: |  # EXPECT: cache-key-injection
            v1-${{{{ github.event.pull_request.title }}}}
""")


def test_cache_key_from_lockfile_hash_is_ok():
    run("""\
on: pull_request
permissions: {}
jobs:
  a:
    runs-on: x
    steps:
      - uses: actions/cache@SHA
        with:
          path: p
          key: ${{ runner.os }}-${{ hashFiles('**/uv.lock') }}
          restore-keys: ${{ runner.os }}-
""")


def test_many_findings_sorted_and_deduplicated():
    findings = run("""\
on:
  pull_request_target:
  push:
permissions: write-all  # EXPECT: broad-permissions
env:  # EXPECT: secrets-in-workflow-env
  T: ${{ secrets.T }}
jobs:
  build:
    runs-on: self-hosted  # EXPECT: self-hosted-pr
    steps:
      - uses: actions/checkout@main  # EXPECT: unpinned-action, pr-target-checkout
        with:
          ref: ${{ github.head_ref }}
      - run: echo ${{ github.event.pull_request.title }} ${{ github.head_ref }}  # EXPECT: script-injection
      - uses: actions/cache@v4  # EXPECT: unpinned-action
        with:
          key: ${{ github.head_ref }}  # EXPECT: cache-key-injection
""")
    assert len(findings) == 8


def test_comments_and_block_scalars_do_not_confuse_line_numbers():
    run("""\
# header comment
# another
on: push

permissions: {}
jobs:

  a:
    runs-on: x
    steps:
      # comment about checkout
      - name: >
          long
          folded name
        uses: actions/checkout@v4  # EXPECT: unpinned-action
""")


def test_fix_text_differs_per_rule():
    findings = run("""\
on: pull_request_target
permissions: write-all  # EXPECT: broad-permissions
jobs:
  a:
    runs-on: x
    steps:
      - uses: a/b@v1  # EXPECT: unpinned-action
""")
    assert len({f["fix"] for f in findings}) == 2
