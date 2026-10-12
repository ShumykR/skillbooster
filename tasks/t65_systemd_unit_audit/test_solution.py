import pytest

from solution import audit_unit

GOOD = """\
[Unit]
Description=Orders API
Wants=network-online.target
After=network-online.target postgresql.service

[Service]
Type=simple
User=orders
ExecStart=/opt/orders/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
ProtectSystem=strict
MemoryMax=512M
EnvironmentFile=/etc/orders/env

[Install]
WantedBy=multi-user.target
"""


def variant(old, new, text=GOOD):
    assert old in text, old
    return text.replace(old, new)


def test_good_unit_is_clean():
    assert audit_unit(GOOD) == []


def test_comments_and_blank_lines_do_not_matter():
    assert audit_unit("# header\n\n" + GOOD.replace("Type=simple", "; note\nType=simple")) == []


@pytest.mark.parametrize("text", [
    variant("Restart=on-failure\n", ""),
    variant("Restart=on-failure", "Restart=no"),
    variant("Restart=on-failure", "Restart=No"),
    variant("Restart=on-failure", "Restart=  "),
])
def test_sd001_no_restart(text):
    assert "SD001" in audit_unit(text)
    assert "SD002" not in audit_unit(text)


def test_sd001_is_not_reported_for_oneshot():
    text = variant("Type=simple", "Type=oneshot", variant("Restart=on-failure\nRestartSec=3\n", ""))
    assert audit_unit(text) == []


def test_type_and_restart_are_case_insensitive():
    text = variant("Type=simple", "Type=OneShot", variant("Restart=on-failure\nRestartSec=3\n", ""))
    assert audit_unit(text) == []
    assert audit_unit(variant("Restart=on-failure", "Restart=ALWAYS")) == []


def test_sd002_restart_without_restartsec():
    assert audit_unit(variant("RestartSec=3\n", "")) == ["SD002"]


@pytest.mark.parametrize("change", [
    ("User=orders\n", ""),
    ("User=orders", "User=root"),
    ("User=orders", "User=0"),
])
def test_sd003_runs_as_root(change):
    assert audit_unit(variant(*change)) == ["SD003"]


def test_dynamic_user_is_fine():
    assert audit_unit(variant("User=orders", "DynamicUser=yes")) == []


@pytest.mark.parametrize("value, expected", [("yes", []), ("true", []), ("1", []), ("on", []), ("no", ["SD004"])])
def test_sd004_no_new_privileges(value, expected):
    assert audit_unit(variant("NoNewPrivileges=yes", f"NoNewPrivileges={value}")) == expected


def test_sd004_missing():
    assert audit_unit(variant("NoNewPrivileges=yes\n", "")) == ["SD004"]


@pytest.mark.parametrize("value, expected", [("strict", []), ("full", []), ("yes", []), ("true", []), ("no", ["SD005"]), ("", ["SD005"])])
def test_sd005_protect_system(value, expected):
    assert audit_unit(variant("ProtectSystem=strict", f"ProtectSystem={value}")) == expected


def test_sd005_missing():
    assert audit_unit(variant("ProtectSystem=strict\n", "")) == ["SD005"]


@pytest.mark.parametrize("exec_start, expected", [
    ("uvicorn app.main:app", ["SD006"]),
    ("./run.sh", ["SD006"]),
    ("-/usr/bin/true", []),
    ("@/usr/bin/foo bar", []),
    ("!!/usr/bin/foo", []),
    ("/usr/bin/env python app.py", []),
])
def test_sd006_execstart_path(exec_start, expected):
    text = GOOD.replace("/opt/orders/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000", exec_start)
    assert audit_unit(text) == expected


def test_sd006_checks_every_execstart_and_handles_continuation():
    text = variant("ExecStart=/opt/orders/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000",
                   "ExecStart=/bin/true\nExecStart=\\\n  python worker.py")
    assert audit_unit(text) == ["SD006"]
    ok = variant("ExecStart=/opt/orders/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000",
                 "ExecStart=\\\n  /opt/orders/bin/run \\\n  --flag")
    assert audit_unit(ok) == []


def test_sd007_wants_without_after():
    assert audit_unit(variant("After=network-online.target postgresql.service", "After=postgresql.service")) == ["SD007"]
    assert audit_unit(variant("After=network-online.target postgresql.service\n", "")) == ["SD007"]


def test_sd007_not_reported_without_wants_or_with_list():
    no_wants = variant("Wants=network-online.target\n", "", variant("After=network-online.target postgresql.service", "After=postgresql.service"))
    assert audit_unit(no_wants) == []
    listed = variant("Wants=network-online.target", "Requires=postgresql.service network-online.target")
    assert audit_unit(listed) == []


@pytest.mark.parametrize("env, expected", [
    ('Environment=DB_PASSWORD=hunter2', ["SD008"]),
    ('Environment="API_KEY=abc" "LOG_LEVEL=info"', ["SD008"]),
    ("Environment=LOG_LEVEL=info DEBUG=0", []),
    ("Environment=DB_PASSWORD=%d/pw", []),
    ("Environment=SECRET_TOKEN=$CREDENTIALS_DIRECTORY/t", []),
    ("Environment=API_TOKEN=", []),
    ("Environment=monkey=1", ["SD008"]),
])
def test_sd008_inline_secrets(env, expected):
    assert audit_unit(variant("EnvironmentFile=/etc/orders/env", env)) == expected


def test_sd008_second_environment_line_counts():
    text = variant("EnvironmentFile=/etc/orders/env", "Environment=LOG=1\nEnvironment=ADMIN_PASSWORD=x")
    assert audit_unit(text) == ["SD008"]


@pytest.mark.parametrize("install", ["WantedBy=multi-user.target", "RequiredBy=x.target"])
def test_sd009_install_section_ok(install):
    assert audit_unit(variant("WantedBy=multi-user.target", install)) == []


def test_sd009_missing_install():
    assert audit_unit(variant("\n[Install]\nWantedBy=multi-user.target\n", "")) == ["SD009"]
    assert audit_unit(variant("WantedBy=multi-user.target", "Alias=x.service")) == ["SD009"]


def test_sd010_forking_needs_pidfile():
    text = variant("Type=simple", "Type=forking")
    assert audit_unit(text) == ["SD010"]
    assert audit_unit(variant("Type=simple", "Type=forking\nPIDFile=/run/orders.pid")) == []


@pytest.mark.parametrize("limit, expected", [("MemoryHigh=400M", []), ("MemoryMax=1G", []), ("CPUQuota=50%", ["SD011"])])
def test_sd011_memory_limit(limit, expected):
    assert audit_unit(variant("MemoryMax=512M", limit)) == expected


def test_many_violations_are_sorted_and_unique():
    bare = "[Service]\nExecStart=python app.py\nEnvironment=TOKEN=x\nEnvironment=KEY=y\n"
    assert audit_unit(bare) == ["SD001", "SD003", "SD004", "SD005", "SD006", "SD008", "SD009", "SD011"]
    assert audit_unit("") == ["SD001", "SD003", "SD004", "SD005", "SD009", "SD011"]
