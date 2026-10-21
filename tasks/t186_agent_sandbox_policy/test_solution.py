import os

import pytest

from solution import Sandbox

RULES = [
    {"effect": "allow", "kind": "file_read", "pattern": "**"},                  # 0
    {"effect": "allow", "kind": "file_write", "pattern": "out/**"},             # 1
    {"effect": "deny", "kind": "file_read", "pattern": "secrets/**"},           # 2
    {"effect": "deny", "kind": "file_write", "pattern": "secrets/**"},          # 3
    {"effect": "deny", "kind": "file_read", "pattern": "**/.env"},              # 4
    {"effect": "ask", "kind": "file_write", "pattern": "**/*.sh"},              # 5
    {"effect": "allow", "kind": "net", "pattern": "api.example.com:443"},       # 6
    {"effect": "allow", "kind": "net", "pattern": "*.example.org:*"},           # 7
    {"effect": "deny", "kind": "net", "pattern": "169.254.*:*"},                # 8
    {"effect": "deny", "kind": "net", "pattern": "evil.example.org:*"},         # 9
    {"effect": "allow", "kind": "exec", "pattern": "git status*"},              # 10
    {"effect": "allow", "kind": "exec", "pattern": "ls"},                       # 11
    {"effect": "ask", "kind": "exec", "pattern": "git push*"},                  # 12
    {"effect": "deny", "kind": "exec", "pattern": "rm *"},                      # 13
    {"effect": "deny", "kind": "exec", "pattern": "curl*"},                     # 14
]


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "ws"
    for d in ("docs", "secrets", "out", "vault", "public"):
        (root / d).mkdir(parents=True)
    (root / "docs" / "a.md").write_text("a")
    (root / "secrets" / "key.pem").write_text("k")
    (root / "vault" / "key.pem").write_text("v")
    (root / ".env").write_text("TOKEN=1")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "passwd").write_text("root")
    return root


def make(ws, rules=None, limits=None):
    policy = {"workspace": str(ws), "rules": RULES if rules is None else rules}
    if limits is not None:
        policy["limits"] = limits
    return Sandbox(policy)


def symlink(target, link, directory=False):
    try:
        os.symlink(str(target), str(link), target_is_directory=directory)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlink недоступний на цій системі/без прав")


def rd(path):
    return {"kind": "file_read", "path": path}


def wr(path, size=1):
    return {"kind": "file_write", "path": path, "size": size}


def net(host, port=443):
    return {"kind": "net", "host": host, "port": port}


def ex(*argv):
    return {"kind": "exec", "argv": list(argv)}


def dec(sb, action):
    r = sb.decide(action)
    assert set(r) == {"decision", "reason", "rule"}
    return r["decision"], r["reason"]


# --- файли: базова поведінка і пріоритет --------------------------------------------------------

def test_basic_file_decisions(ws):
    sb = make(ws)
    assert sb.decide(rd("docs/a.md")) == {"decision": "allow", "reason": "allow-rule", "rule": 0}
    assert sb.decide(rd("secrets/key.pem")) == {"decision": "deny", "reason": "deny-rule", "rule": 2}
    assert sb.decide(wr("out/report.txt")) == {"decision": "allow", "reason": "allow-rule", "rule": 1}
    assert sb.decide(wr("docs/a.md")) == {"decision": "deny", "reason": "default-deny", "rule": None}
    assert sb.decide(wr("secrets/new.txt")) == {"decision": "deny", "reason": "deny-rule", "rule": 3}


def test_absolute_path_inside_workspace_is_the_same_as_relative(ws):
    sb = make(ws)
    assert dec(sb, rd(str(ws / "docs" / "a.md"))) == ("allow", "allow-rule")
    assert dec(sb, rd(str(ws / "secrets" / "key.pem"))) == ("deny", "deny-rule")


def test_deny_beats_allow_regardless_of_rule_order(ws):
    reordered = list(reversed(RULES))
    sb = make(ws, reordered)
    assert dec(sb, rd("secrets/key.pem")) == ("deny", "deny-rule")
    assert dec(sb, rd("docs/a.md")) == ("allow", "allow-rule")


def test_ask_beats_allow_and_deny_beats_ask(ws):
    sb = make(ws)
    assert dec(sb, wr("out/run.sh")) == ("ask", "ask-rule")      # allow out/** + ask **/*.sh
    rules = RULES + [{"effect": "deny", "kind": "file_write", "pattern": "out/run.sh"}]
    sb = make(ws, rules)
    assert dec(sb, wr("out/run.sh")) == ("deny", "deny-rule")


def test_rule_index_is_first_matching_of_winning_effect(ws):
    rules = [
        {"effect": "allow", "kind": "file_read", "pattern": "**"},
        {"effect": "deny", "kind": "file_read", "pattern": "x/**"},
        {"effect": "deny", "kind": "file_read", "pattern": "**/*.pem"},
        {"effect": "deny", "kind": "file_read", "pattern": "x/k.pem"},
    ]
    sb = make(ws, rules)
    assert sb.decide(rd("x/k.pem")) == {"decision": "deny", "reason": "deny-rule", "rule": 1}
    assert sb.decide(rd("y/k.pem")) == {"decision": "deny", "reason": "deny-rule", "rule": 2}


def test_rules_of_other_kinds_are_ignored(ws):
    rules = [{"effect": "allow", "kind": "net", "pattern": "**"}, {"effect": "allow", "kind": "exec", "pattern": "*"}]
    sb = make(ws, rules)
    assert dec(sb, rd("docs/a.md")) == ("deny", "default-deny")
    assert dec(sb, wr("out/a")) == ("deny", "default-deny")


def test_no_rules_means_default_deny(ws):
    sb = make(ws, [])
    for a in (rd("docs/a.md"), wr("out/a"), net("api.example.com"), ex("ls")):
        assert dec(sb, a) == ("deny", "default-deny")


@pytest.mark.parametrize("path, expected", [
    (".env", ("deny", "deny-rule")),
    ("docs/.env", ("deny", "deny-rule")),
    ("a/b/c/.env", ("deny", "deny-rule")),
    ("docs/.env.example", ("allow", "allow-rule")),
    ("docs/x.env", ("allow", "allow-rule")),
])
def test_double_star_slash_matches_zero_or_more_dirs(ws, path, expected):
    assert dec(make(ws), rd(path)) == expected


def test_glob_star_and_question_do_not_cross_slashes(ws):
    rules = [{"effect": "allow", "kind": "file_read", "pattern": "docs/*.md"},
             {"effect": "allow", "kind": "file_read", "pattern": "f?.txt"}]
    sb = make(ws, rules)
    assert dec(sb, rd("docs/a.md")) == ("allow", "allow-rule")
    assert dec(sb, rd("docs/sub/a.md")) == ("deny", "default-deny")
    assert dec(sb, rd("fa.txt")) == ("allow", "allow-rule")
    assert dec(sb, rd("f/.txt")) == ("deny", "default-deny")
    assert dec(sb, rd("fab.txt")) == ("deny", "default-deny")


def test_glob_special_characters_are_literal(ws):
    rules = [{"effect": "allow", "kind": "file_read", "pattern": "a[1].txt"},
             {"effect": "allow", "kind": "file_read", "pattern": "v1.0/*"}]
    sb = make(ws, rules)
    assert dec(sb, rd("a[1].txt")) == ("allow", "allow-rule")
    assert dec(sb, rd("a1.txt")) == ("deny", "default-deny")
    assert dec(sb, rd("v1x0/f")) == ("deny", "default-deny")
    assert dec(sb, rd("v1.0/f")) == ("allow", "allow-rule")


# --- файли: обходи ------------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "../outside/passwd", "docs/../../outside/passwd", "docs/../..", "./../outside/passwd",
    "a/b/../../../x", "..",
])
def test_dotdot_escapes_are_outside_workspace(ws, path):
    assert dec(make(ws), rd(path)) == ("deny", "outside-workspace")


def test_absolute_path_outside_workspace(ws, tmp_path):
    sb = make(ws)
    assert dec(sb, rd(str(tmp_path / "outside" / "passwd"))) == ("deny", "outside-workspace")
    assert dec(sb, rd(os.path.abspath(os.sep))) == ("deny", "outside-workspace")


def test_sibling_directory_with_same_prefix_is_outside(ws):
    sibling = ws.parent / (ws.name + "-evil")
    sibling.mkdir()
    sb = make(ws)
    assert dec(sb, rd(str(sibling / "x"))) == ("deny", "outside-workspace")


def test_dotdot_inside_workspace_that_returns_to_denied_area(ws):
    sb = make(ws)
    assert dec(sb, rd("public/../secrets/key.pem")) == ("deny", "deny-rule")
    assert dec(sb, rd("docs/../docs/a.md")) == ("allow", "allow-rule")
    assert dec(sb, rd("./secrets/./key.pem")) == ("deny", "deny-rule")


@pytest.mark.parametrize("path", ["SECRETS/key.pem", "Secrets/new.txt", "sEcReTs/x", "docs/.ENV", ".Env"])
def test_deny_is_case_insensitive(ws, path):
    assert dec(make(ws), rd(path)) == ("deny", "deny-rule")


def test_deny_for_write_is_case_insensitive_too(ws):
    assert dec(make(ws), wr("SECRETS/x")) == ("deny", "deny-rule")


def test_ask_is_case_insensitive(ws):
    assert dec(make(ws), wr("out/RUN.SH")) == ("ask", "ask-rule")


def test_allow_is_case_sensitive(ws):
    # теки не існують: на ФС без чутливості до регістру realpath міг би виправити регістр існуючої теки
    sb = make(ws, [{"effect": "allow", "kind": "file_write", "pattern": "Reports/**"}])
    assert dec(sb, wr("Reports/x.txt")) == ("allow", "allow-rule")
    assert dec(sb, wr("reports/x.txt")) == ("deny", "default-deny")
    assert dec(sb, wr("REPORTS/x.txt")) == ("deny", "default-deny")


def test_symlink_inside_workspace_to_denied_file_is_denied(ws):
    symlink(ws / "secrets" / "key.pem", ws / "docs" / "innocent.txt")
    assert dec(make(ws), rd("docs/innocent.txt")) == ("deny", "deny-rule")


def test_symlink_to_outside_is_outside_workspace(ws, tmp_path):
    symlink(tmp_path / "outside" / "passwd", ws / "docs" / "link.txt")
    symlink(tmp_path / "outside", ws / "docs" / "linkdir", directory=True)
    sb = make(ws)
    assert dec(sb, rd("docs/link.txt")) == ("deny", "outside-workspace")
    assert dec(sb, rd("docs/linkdir/passwd")) == ("deny", "outside-workspace")
    assert dec(sb, wr("out/../docs/linkdir/new")) == ("deny", "outside-workspace")


def test_symlinked_directory_into_denied_area(ws):
    symlink(ws / "secrets", ws / "public" / "s", directory=True)
    assert dec(make(ws), rd("public/s/key.pem")) == ("deny", "deny-rule")


def test_symlink_named_like_denied_dir_pointing_to_allowed_dir_is_still_denied(ws):
    # lexical-шлях secrets/... під deny, хоча канонічний лежить у vault/
    (ws / "secrets" / "key.pem").unlink()
    (ws / "secrets").rmdir()
    symlink(ws / "vault", ws / "secrets", directory=True)
    assert dec(make(ws), rd("secrets/key.pem")) == ("deny", "deny-rule")


def test_symlink_from_allowed_write_area_to_non_allowed_place_is_not_allowed(ws):
    symlink(ws / "docs", ws / "out" / "d", directory=True)
    assert dec(make(ws), wr("out/d/a.md")) == ("deny", "default-deny")


def test_symlink_chain_and_relative_symlink(ws):
    symlink("../secrets/key.pem", ws / "public" / "rel.txt")
    symlink(ws / "public" / "rel.txt", ws / "docs" / "chain.txt")
    sb = make(ws)
    assert dec(sb, rd("public/rel.txt")) == ("deny", "deny-rule")
    assert dec(sb, rd("docs/chain.txt")) == ("deny", "deny-rule")


def test_symlink_to_dotenv_is_denied(ws):
    symlink(ws / ".env", ws / "docs" / "config.txt")
    assert dec(make(ws), rd("docs/config.txt")) == ("deny", "deny-rule")


def test_nonexistent_paths_are_still_decided(ws):
    sb = make(ws)
    assert dec(sb, rd("no/such/file.txt")) == ("allow", "allow-rule")
    assert dec(sb, wr("out/new/deep/file.txt")) == ("allow", "allow-rule")


@pytest.mark.parametrize("path", ["", None, 5, b"docs/a.md", ["a"], "docs/\x00a.md"])
def test_invalid_paths(ws, path):
    r = make(ws).decide({"kind": "file_read", "path": path})
    assert r["decision"] == "deny"
    assert r["reason"] in ("invalid-path", "invalid-action")


@pytest.mark.parametrize("size", [None, -1, 1.5, "10", True])
def test_invalid_write_size(ws, size):
    assert dec(make(ws), {"kind": "file_write", "path": "out/a", "size": size}) == ("deny", "invalid-action")


# --- мережа -------------------------------------------------------------------------------------

@pytest.mark.parametrize("host, port, expected", [
    ("api.example.com", 443, ("allow", "allow-rule")),
    ("API.Example.COM", 443, ("allow", "allow-rule")),
    ("api.example.com.", 443, ("allow", "allow-rule")),
    ("api.example.com", 80, ("deny", "default-deny")),
    ("example.com", 443, ("deny", "default-deny")),
    ("api.example.com.evil.io", 443, ("deny", "default-deny")),
    ("xapi.example.com", 443, ("deny", "default-deny")),
    ("docs.example.org", 8080, ("allow", "allow-rule")),
    ("evil.example.org", 443, ("deny", "deny-rule")),
    ("EVIL.example.org.", 443, ("deny", "deny-rule")),
    ("example.org", 443, ("deny", "default-deny")),
    ("169.254.169.254", 80, ("deny", "deny-rule")),
    ("8.8.8.8", 53, ("deny", "default-deny")),
])
def test_net_decisions(ws, host, port, expected):
    assert dec(make(ws), net(host, port)) == expected


@pytest.mark.parametrize("host", [
    "2852039166", "0xa9fea9fe", "0251.0376.0251.0376", "169.254.169", "169.254.169.254.1", "1.2.3.256",
    "01.2.3.4", "0x7f.0.0.1", "api.example.com/x", "api.example.com:443", "user@api.example.com", "api example.com",
    "exämple.com", "[::1]", "", ".", "a..b" "\n",
])
def test_invalid_hosts(ws, host):
    r = make(ws, [{"effect": "allow", "kind": "net", "pattern": "*"}]).decide(net(host))
    assert r["decision"] == "deny" and r["reason"] in ("invalid-host", "invalid-action")


@pytest.mark.parametrize("port", [0, -1, 65536, "443", None, 443.0, True])
def test_invalid_ports(ws, port):
    r = make(ws, [{"effect": "allow", "kind": "net", "pattern": "*"}]).decide(net("api.example.com", port))
    assert r["decision"] == "deny" and r["reason"] == "invalid-action"


def test_net_missing_fields(ws):
    sb = make(ws)
    assert dec(sb, {"kind": "net", "host": "api.example.com"}) == ("deny", "invalid-action")
    assert dec(sb, {"kind": "net", "port": 443}) == ("deny", "invalid-action")
    assert dec(sb, {"kind": "net", "host": 5, "port": 443}) == ("deny", "invalid-action")


def test_net_port_boundaries(ws):
    sb = make(ws, [{"effect": "allow", "kind": "net", "pattern": "h.io:*"}])
    assert dec(sb, net("h.io", 1)) == ("allow", "allow-rule")
    assert dec(sb, net("h.io", 65535)) == ("allow", "allow-rule")


# --- процеси ------------------------------------------------------------------------------------

@pytest.mark.parametrize("argv, expected", [
    (["git", "status"], ("allow", "allow-rule")),
    (["git", "status", "-s"], ("allow", "allow-rule")),
    (["/usr/bin/git", "status"], ("allow", "allow-rule")),
    (["C:\\Program Files\\Git\\bin\\git.exe", "status"], ("allow", "allow-rule")),
    (["git", "push", "origin", "main"], ("ask", "ask-rule")),
    (["GIT", "PUSH"], ("ask", "ask-rule")),
    (["git", "log"], ("deny", "default-deny")),
    (["ls"], ("allow", "allow-rule")),
    (["ls", "-la"], ("deny", "default-deny")),
    (["rm", "-rf", "/"], ("deny", "deny-rule")),
    (["/bin/rm", "-rf", "x"], ("deny", "deny-rule")),
    (["./rm", "x"], ("deny", "deny-rule")),
    (["RM.EXE", "x"], ("deny", "deny-rule")),
    (["curl", "http://x"], ("deny", "deny-rule")),
    (["/usr/bin/CURL"], ("deny", "deny-rule")),
    (["bash", "-c", "rm -rf /"], ("deny", "default-deny")),
])
def test_exec_decisions(ws, argv, expected):
    assert dec(make(ws), ex(*argv)) == expected


@pytest.mark.parametrize("argv", [[], "git status", None, [""], ["git", 5], ["git", None], ["git\x00"], ["", "status"]])
def test_invalid_exec(ws, argv):
    assert dec(make(ws), {"kind": "exec", "argv": argv}) == ("deny", "invalid-action")


def test_exec_allow_is_case_sensitive_but_deny_is_not(ws):
    sb = make(ws)
    assert dec(sb, ex("LS")) == ("deny", "default-deny")
    assert dec(sb, ex("Rm", "x")) == ("deny", "deny-rule")


# --- некоректні дії -----------------------------------------------------------------------------

@pytest.mark.parametrize("action", [None, 5, "file_read", [], {}, {"kind": "teleport"}, {"kind": None},
                                    {"kind": "FILE_READ", "path": "a"}, {"path": "docs/a.md"}])
def test_invalid_actions_are_denied_without_exceptions(ws, action):
    assert dec(make(ws), action) == ("deny", "invalid-action")


def test_extra_keys_are_ignored(ws):
    assert dec(make(ws), {"kind": "file_read", "path": "docs/a.md", "note": "please", "decision": "allow"}) == (
        "allow", "allow-rule")


# --- ліміти -------------------------------------------------------------------------------------

def test_max_actions_counts_only_allowed(ws):
    sb = make(ws, limits={"max_actions": 3})
    assert dec(sb, rd("docs/a.md"))[0] == "allow"
    assert dec(sb, rd("secrets/key.pem"))[0] == "deny"            # deny не рахується
    assert dec(sb, wr("out/run.sh"))[0] == "ask"                  # ask не рахується
    assert dec(sb, rd("docs/a.md"))[0] == "allow"
    assert dec(sb, rd("../outside/passwd"))[0] == "deny"
    assert dec(sb, rd("docs/a.md"))[0] == "allow"
    assert dec(sb, rd("docs/a.md")) == ("deny", "limit-exceeded")
    assert dec(sb, net("api.example.com")) == ("deny", "limit-exceeded")
    assert dec(sb, rd("secrets/key.pem")) == ("deny", "deny-rule")   # причина відмови не маскується лімітом
    assert dec(sb, wr("out/run.sh")) == ("ask", "ask-rule")


def test_max_actions_zero_denies_everything_allowed(ws):
    sb = make(ws, limits={"max_actions": 0})
    assert dec(sb, rd("docs/a.md")) == ("deny", "limit-exceeded")


def test_max_write_bytes_cumulative_and_exact(ws):
    sb = make(ws, limits={"max_write_bytes": 100})
    assert dec(sb, wr("out/a", 60))[0] == "allow"
    assert dec(sb, wr("out/b", 50)) == ("deny", "limit-exceeded")
    assert dec(sb, wr("out/c", 40))[0] == "allow"                 # рівно до межі
    assert dec(sb, wr("out/d", 1)) == ("deny", "limit-exceeded")
    assert dec(sb, wr("out/e", 0))[0] == "allow"
    assert dec(sb, rd("docs/a.md"))[0] == "allow"                 # читання не рахується в байтах


def test_denied_and_ask_writes_do_not_consume_write_budget(ws):
    sb = make(ws, limits={"max_write_bytes": 10})
    assert dec(sb, wr("secrets/x", 9))[0] == "deny"
    assert dec(sb, wr("out/run.sh", 9))[0] == "ask"
    assert dec(sb, wr("out/ok", 10))[0] == "allow"


def test_write_rejected_by_budget_does_not_consume_action_budget(ws):
    sb = make(ws, limits={"max_actions": 2, "max_write_bytes": 5})
    assert dec(sb, wr("out/a", 6)) == ("deny", "limit-exceeded")
    assert dec(sb, wr("out/b", 5))[0] == "allow"
    assert dec(sb, rd("docs/a.md"))[0] == "allow"
    assert dec(sb, rd("docs/a.md")) == ("deny", "limit-exceeded")


def test_limits_are_per_sandbox_instance(ws):
    a, b = make(ws, limits={"max_actions": 1}), make(ws, limits={"max_actions": 1})
    assert dec(a, rd("docs/a.md"))[0] == "allow"
    assert dec(b, rd("docs/a.md"))[0] == "allow"
    assert dec(a, rd("docs/a.md"))[0] == "deny"


# --- валідація політики -------------------------------------------------------------------------

@pytest.mark.parametrize("mutate", [
    lambda p: p.update(workspace="relative/dir"),
    lambda p: p.update(workspace=""),
    lambda p: p.update(workspace=None),
    lambda p: p.update(rules="nope"),
    lambda p: p.update(rules=[{"effect": "permit", "kind": "net", "pattern": "x"}]),
    lambda p: p.update(rules=[{"effect": "allow", "kind": "dns", "pattern": "x"}]),
    lambda p: p.update(rules=[{"effect": "allow", "kind": "net", "pattern": ""}]),
    lambda p: p.update(rules=[{"effect": "allow", "kind": "net", "pattern": 5}]),
    lambda p: p.update(rules=[{"effect": "allow", "kind": "net"}]),
    lambda p: p.update(rules=["allow net *"]),
    lambda p: p.update(limits={"max_actions": -1}),
    lambda p: p.update(limits={"max_actions": 1.5}),
    lambda p: p.update(limits={"max_actions": True}),
    lambda p: p.update(limits={"max_cpu": 1}),
])
def test_invalid_policy_is_value_error(ws, mutate):
    policy = {"workspace": str(ws), "rules": [{"effect": "allow", "kind": "net", "pattern": "*"}]}
    mutate(policy)
    with pytest.raises(ValueError):
        Sandbox(policy)


def test_policy_is_copied_and_not_mutated(ws):
    rules = [{"effect": "allow", "kind": "file_read", "pattern": "docs/**"}]
    policy = {"workspace": str(ws), "rules": rules, "limits": {"max_actions": 1}}
    sb = Sandbox(policy)
    rules.append({"effect": "allow", "kind": "file_read", "pattern": "**"})
    rules[0]["effect"] = "deny"
    policy["limits"]["max_actions"] = 100
    assert dec(sb, rd("docs/a.md")) == ("allow", "allow-rule")
    assert dec(sb, rd("public/x")) == ("deny", "default-deny")
    assert dec(sb, rd("docs/a.md")) == ("deny", "limit-exceeded")


def test_decide_does_not_touch_the_filesystem_state(ws):
    before = sorted(p.name for p in ws.rglob("*"))
    sb = make(ws)
    sb.decide(wr("out/new.txt", 5))
    sb.decide(rd("docs/a.md"))
    assert sorted(p.name for p in ws.rglob("*")) == before
