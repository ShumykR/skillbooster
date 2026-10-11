import pytest

from solution import check_compose

GOOD = """\
services:
  app:
    image: registry.example.com:5000/team/app:1.4.2
    environment:
      DATABASE_URL: postgresql://app@db/app
      DB_PASSWORD_FILE: /run/secrets/db_password
      API_TOKEN: ${API_TOKEN}
      LOG_LEVEL: info
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    ports:
      - "8000:8000"
  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_PASSWORD_FILE=/run/secrets/db_password
      - POSTGRES_USER=app
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "app"]
      interval: 5s
  cache:
    image: redis:7
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
"""


def svc_file(body):
    return "services:\n" + body


def test_good_compose_is_clean():
    assert check_compose(GOOD) == []


def test_empty_and_no_services():
    assert check_compose("") == []
    assert check_compose("version: '3'\n") == []


@pytest.mark.parametrize(
    "image, bad",
    [
        ("nginx", True),
        ("nginx:latest", True),
        ("ghcr.io/org/app:latest", True),
        ("registry:5000/app", True),
        ("registry:5000/app:2.0", False),
        ("nginx:1.27", False),
        ("nginx@sha256:" + "b" * 64, False),
        ("${APP_IMAGE}", False),
    ],
)
def test_unpinned_image(image, bad):
    result = check_compose(svc_file(f"  web:\n    image: {image}\n"))
    assert result == (["unpinned_image:web"] if bad else [])


def test_service_with_build_and_no_image_is_fine():
    assert check_compose(svc_file("  web:\n    build: .\n")) == []


@pytest.mark.parametrize("image", ["postgres:16", "redis:7", "mysql:8", "mariadb:11", "mongo:7", "docker.io/library/postgres:16"])
def test_exposed_db(image):
    text = svc_file(f"  store:\n    image: {image}\n    ports:\n      - '5432:5432'\n")
    assert check_compose(text) == ["exposed_db:store"]


def test_db_without_ports_and_web_with_ports_are_fine():
    text = svc_file("  db:\n    image: postgres:16\n  web:\n    image: nginx:1.27\n    ports: ['80:80']\n")
    assert check_compose(text) == []


def test_hardcoded_secret_in_mapping_and_list_forms():
    mapping = svc_file("  a:\n    image: x:1\n    environment:\n      DB_PASSWORD: hunter2\n")
    listing = svc_file("  a:\n    image: x:1\n    environment:\n      - STRIPE_SECRET_KEY=sk_live_123\n")
    assert check_compose(mapping) == ["hardcoded_secret:a"]
    assert check_compose(listing) == ["hardcoded_secret:a"]


@pytest.mark.parametrize(
    "env_line",
    [
        "DB_PASSWORD: ${DB_PASSWORD}",
        "- DB_PASSWORD=${DB_PASSWORD:-}",
        "- DB_PASSWORD",
        "DB_PASSWORD_FILE: /run/secrets/pw",
        "- API_KEY=",
        "LOG_LEVEL: debug",
        "PASSIVE_MODE: 'yes'",
    ],
)
def test_secret_lookalikes_are_fine(env_line):
    env = f"    environment:\n      {env_line}\n"
    assert check_compose(svc_file(f"  a:\n    image: x:1\n{env}")) == []


def test_depends_on_list_form_waits_only_for_start():
    text = svc_file(
        "  app:\n    image: app:1\n    depends_on: [db]\n"
        "  db:\n    image: postgres:16\n    healthcheck:\n      test: ['CMD', 'pg_isready']\n"
    )
    assert check_compose(text) == ["not_waiting:app->db"]


def test_depends_on_started_condition():
    text = svc_file(
        "  app:\n    image: app:1\n    depends_on:\n      db:\n        condition: service_started\n"
        "  db:\n    image: postgres:16\n    healthcheck:\n      test: ['CMD', 'pg_isready']\n"
    )
    assert check_compose(text) == ["not_waiting:app->db"]


def test_depends_on_without_condition_in_mapping():
    text = svc_file(
        "  app:\n    image: app:1\n    depends_on:\n      db: {}\n"
        "  db:\n    image: postgres:16\n    healthcheck:\n      test: ['CMD', 'pg_isready']\n"
    )
    assert check_compose(text) == ["not_waiting:app->db"]


def test_dependency_without_healthcheck_is_reported_once_for_all_dependents():
    text = svc_file(
        "  app:\n    image: app:1\n    depends_on:\n      db:\n        condition: service_healthy\n"
        "  worker:\n    image: worker:1\n    depends_on: [db]\n"
        "  db:\n    image: postgres:16\n"
    )
    assert check_compose(text) == ["missing_healthcheck:db"]


def test_disabled_healthcheck_counts_as_missing():
    text = svc_file(
        "  app:\n    image: app:1\n    depends_on: [db]\n"
        "  db:\n    image: postgres:16\n    healthcheck:\n      disable: true\n"
    )
    assert check_compose(text) == ["missing_healthcheck:db"]


def test_dependency_on_unknown_service_does_not_crash():
    text = svc_file("  app:\n    image: app:1\n    depends_on: [ghost]\n")
    assert check_compose(text) == ["missing_healthcheck:ghost"]


def test_independent_services_without_healthchecks_are_fine():
    text = svc_file("  a:\n    image: a:1\n  b:\n    image: b:1\n")
    assert check_compose(text) == []


def test_findings_sorted_and_unique():
    text = svc_file(
        "  web:\n    image: nginx\n    environment:\n      A_TOKEN: x\n      B_TOKEN: y\n    depends_on: [db]\n"
        "  db:\n    image: postgres\n    ports: ['5432:5432']\n"
    )
    assert check_compose(text) == [
        "exposed_db:db",
        "hardcoded_secret:web",
        "missing_healthcheck:db",
        "unpinned_image:db",
        "unpinned_image:web",
    ]
