import pytest

from solution import lint_dockerfile

GOOD = """\
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN apt-get update \\
    && apt-get install -y --no-install-recommends curl \\
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY . /app
RUN useradd -u 1000 app
USER 1000:1000
CMD ["python", "-m", "app"]
"""


def test_good_dockerfile_has_no_findings():
    assert lint_dockerfile(GOOD) == []


def test_empty_input():
    assert lint_dockerfile("") == []


@pytest.mark.parametrize(
    "text",
    [
        "FROM python\nUSER app\n",
        "FROM python:latest\nUSER app\n",
        "FROM ubuntu:latest AS base\nFROM base\nUSER app\n",
        "FROM registry.example.com:5000/team/app\nUSER app\n",  # порт реєстру це не тег
    ],
)
def test_df001_unpinned_base(text):
    assert lint_dockerfile(text) == ["DF001"]


@pytest.mark.parametrize(
    "text",
    [
        "FROM python:3.12-slim@sha256:" + "a" * 64 + "\nUSER app\n",
        "FROM scratch\nUSER app\n",
        "ARG BASE=python:3.12\nFROM ${BASE}\nUSER app\n",
        "FROM --platform=linux/amd64 python:3.12 AS b\nFROM b\nUSER app\n",
        "FROM registry.example.com:5000/team/app:1.4\nUSER app\n",
    ],
)
def test_df001_not_triggered(text):
    assert lint_dockerfile(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "FROM python:3.12\n",
        "FROM python:3.12\nUSER root\n",
        "FROM python:3.12\nUSER 0\n",
        "FROM python:3.12\nUSER 0:0\n",
        "FROM python:3.12\nUSER app\nUSER root\n",  # важливий саме останній USER
        "FROM python:3.12 AS b\nUSER app\nFROM python:3.12\nCMD x\n",  # USER з іншої стадії не рахується
    ],
)
def test_df002_root(text):
    assert lint_dockerfile(text) == ["DF002"]


def test_df002_non_final_stage_may_be_root():
    text = "FROM python:3.12 AS b\nRUN true\nFROM python:3.12\nUSER app\n"
    assert lint_dockerfile(text) == []


@pytest.mark.parametrize(
    "line",
    ["ADD app.py /app/", "ADD --chown=app:app src/ /app/src/", "ADD a.py b.py /app/", "add . /app"],
)
def test_df003_add_for_local_files(line):
    assert lint_dockerfile(f"FROM python:3.12\n{line}\nUSER app\n") == ["DF003"]


@pytest.mark.parametrize(
    "line",
    ["ADD https://example.com/tool.sh /usr/bin/", "ADD rootfs.tar.gz /", "ADD bundle.tgz /opt/", "COPY app.py /app/"],
)
def test_df003_allowed(line):
    assert lint_dockerfile(f"FROM python:3.12\n{line}\nUSER app\n") == []


def test_apt_rules_are_independent():
    base = "FROM debian:12\nUSER app\n"
    both = base + "RUN apt-get update && apt-get install -y curl\n"
    assert lint_dockerfile(both) == ["DF004", "DF005"]
    only5 = base + "RUN apt-get update && apt-get install -y --no-install-recommends curl\n"
    assert lint_dockerfile(only5) == ["DF005"]
    only4 = base + "RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*\n"
    assert lint_dockerfile(only4) == ["DF004"]


def test_apt_cleanup_in_separate_run_does_not_count():
    text = (
        "FROM debian:12\nUSER app\n"
        "RUN apt-get install -y --no-install-recommends curl\n"
        "RUN rm -rf /var/lib/apt/lists/*\n"
    )
    assert lint_dockerfile(text) == ["DF005"]


def test_apt_without_install_is_fine():
    assert lint_dockerfile("FROM debian:12\nUSER app\nRUN apt-get update\n") == []


def test_df006_pip_cache():
    base = "FROM python:3.12\nUSER app\n"
    assert lint_dockerfile(base + "RUN pip install flask\n") == ["DF006"]
    assert lint_dockerfile(base + "RUN pip install --no-cache-dir flask\n") == []


def test_df007_cache_unfriendly_copy():
    bad = "FROM python:3.12\nUSER app\nCOPY . /app\nRUN pip install --no-cache-dir -r /app/requirements.txt\n"
    assert lint_dockerfile(bad) == ["DF007"]
    bad2 = "FROM python:3.12\nUSER app\nCOPY . .\nRUN pip install --no-cache-dir -r requirements.txt\n"
    assert lint_dockerfile(bad2) == ["DF007"]


def test_df007_not_triggered_when_order_is_right_or_other_stage():
    ok = (
        "FROM python:3.12\nUSER app\nCOPY requirements.txt .\n"
        "RUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\n"
    )
    assert lint_dockerfile(ok) == []
    other_stage = (
        "FROM python:3.12 AS src\nCOPY . .\n"
        "FROM python:3.12\nUSER app\nCOPY requirements.txt .\n"
        "RUN pip install --no-cache-dir -r requirements.txt\n"
    )
    assert lint_dockerfile(other_stage) == []


def test_parser_handles_case_continuations_and_comments():
    text = (
        "# коментар: RUN pip install flask\n"
        "from python:3.12\n"
        "run pip install \\\n"
        "    # коментар усередині продовження\n"
        "    --no-cache-dir flask\n"
        "user app\n"
    )
    assert lint_dockerfile(text) == []


def test_multiple_findings_are_sorted_and_unique():
    text = (
        "FROM python\n"
        "COPY . .\n"
        "RUN pip install -r requirements.txt\n"
        "RUN pip install gunicorn\n"
        "ADD x.py /x.py\n"
    )
    assert lint_dockerfile(text) == ["DF001", "DF002", "DF003", "DF006", "DF007"]
