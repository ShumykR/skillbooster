import base64
import copy
import hashlib
import hmac
import json

import pytest

from solution import Decision, pae, verify_provenance

PT = "application/vnd.in-toto+json"
REPO = "https://github.com/acme/app"
BUILDER = "https://github.com/acme/builder/.github/workflows/build.yml@refs/tags/v2.1.0"
WORKFLOW = ".github/workflows/release.yml"
DIGEST_HEX = hashlib.sha256(b"image-a").hexdigest()
OTHER_HEX = hashlib.sha256(b"image-b").hexdigest()
DIGEST = "sha256:" + DIGEST_HEX
KEYS = {"k1": b"key-one", "k2": b"key-two"}

POLICY = {
    "allowed_builders": [BUILDER],
    "repository": REPO,
    "allowed_refs": ["refs/heads/main", "refs/tags/v*"],
    "workflow_path": WORKFLOW,
}


def fake_sign(key, data):
    return hmac.new(key, data, hashlib.sha256).digest()


class Verifier:
    """verify(key, data, sig): HMAC замість асиметричного підпису; запамʼятовує виклики."""

    def __init__(self):
        self.calls = []

    def __call__(self, key, data, sig):
        self.calls.append((key, data, sig))
        return hmac.compare_digest(fake_sign(key, data), sig)


def statement(*, digest_hex=DIGEST_HEX, builder=BUILDER, repository=REPO, ref="refs/heads/main",
              path=WORKFLOW, event="push", source_repo=None, subjects=None):
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects if subjects is not None else [{"name": "app", "digest": {"sha256": digest_hex}}],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "externalParameters": {"workflow": {"repository": repository, "ref": ref, "path": path}},
                "internalParameters": {"github": {"event_name": event}},
                "resolvedDependencies": [
                    {"uri": f"git+{source_repo or repository}@{ref}", "digest": {"gitCommit": "abc123"}},
                ],
            },
            "runDetails": {"builder": {"id": builder}},
        },
    }


def envelope_for(stmt, *, key_id="k1", raw=None):
    raw = raw if raw is not None else json.dumps(stmt).encode()
    sig = fake_sign(KEYS[key_id], pae(PT, raw))
    return {
        "payloadType": PT,
        "payload": base64.b64encode(raw).decode(),
        "signatures": [{"keyid": key_id, "sig": base64.b64encode(sig).decode()}],
    }


def run(envelope, *, digest=DIGEST, policy=POLICY, keys=KEYS, verifier=None):
    v = verifier or Verifier()
    return verify_provenance(envelope, artifact_digest=digest, policy=policy, trusted_keys=keys, verify=v), v


def good(**kw):
    return envelope_for(statement(**kw))


# --- pae ---------------------------------------------------------------------------------------

def test_pae_known_vector():
    assert pae("http://example.com/HelloWorld", b"hello world") == \
        b"DSSEv1 29 http://example.com/HelloWorld 11 hello world"


def test_pae_lengths_are_in_bytes():
    assert pae("тип", "привіт".encode()) == b"DSSEv1 6 " + "тип".encode() + b" 12 " + "привіт".encode()
    assert pae("t", b"") == b"DSSEv1 1 t 0 "


# --- щасливий шлях і виклик verify -------------------------------------------------------------

def test_valid_provenance_is_allowed():
    d, _ = run(good())
    assert isinstance(d, Decision)
    assert d.allowed is True
    assert d.reasons == []


def test_tag_ref_matching_prefix_pattern_is_allowed():
    d, _ = run(good(ref="refs/tags/v1.2.3"))
    assert d == (True, [])


def test_verify_is_called_with_pae_of_raw_payload_bytes():
    stmt = statement()
    raw = json.dumps(stmt, indent=3, sort_keys=False).encode() + b"\n\n"  # нетипове форматування
    env = envelope_for(stmt, raw=raw)
    d, v = run(env)
    assert d.allowed
    assert len(v.calls) == 1
    key, data, sig = v.calls[0]
    assert key == KEYS["k1"]
    assert data == pae(PT, raw)
    assert sig == base64.b64decode(env["signatures"][0]["sig"])


def test_unknown_keyid_is_skipped_without_calling_verify():
    env = good()
    env["signatures"].insert(0, {"keyid": "stranger", "sig": base64.b64encode(b"x").decode()})
    d, v = run(env)
    assert d.allowed
    assert [c[0] for c in v.calls] == [KEYS["k1"]]


def test_any_one_valid_signature_is_enough():
    env = good()
    env["signatures"].insert(0, {"keyid": "k2", "sig": base64.b64encode(b"garbage").decode()})
    d, v = run(env)
    assert d.allowed
    assert len(v.calls) == 2


def test_signature_made_by_other_key_than_keyid_is_rejected():
    stmt = statement()
    env = envelope_for(stmt, key_id="k2")
    env["signatures"][0]["keyid"] = "k1"
    d, _ = run(env)
    assert d == (False, ["signature-invalid"])


# --- fail closed: підпис ---------------------------------------------------------------------

def test_invalid_signature_reports_only_signature_even_if_statement_is_bad():
    env = envelope_for(statement(digest_hex=OTHER_HEX, builder="https://evil", repository="https://github.com/evil/app"))
    env["signatures"][0]["sig"] = base64.b64encode(b"0" * 32).decode()
    d, _ = run(env)
    assert d.allowed is False
    assert d.reasons == ["signature-invalid"]


def test_payload_tampered_after_signing():
    env = good()
    forged = json.dumps(statement(ref="refs/heads/main", event="push")).encode() + b" "
    env["payload"] = base64.b64encode(forged).decode()
    d, _ = run(env)
    assert d == (False, ["signature-invalid"])


def test_verify_exception_means_denied():
    def boom(key, data, sig):
        raise RuntimeError("kms down")

    d, _ = run(good(), verifier=boom)
    assert d == (False, ["signature-invalid"])


@pytest.mark.parametrize("value", ["yes", 1, [True], object(), None])
def test_only_exactly_true_counts_as_valid_signature(value):
    d, _ = run(good(), verifier=lambda k, data, s: value)
    assert d == (False, ["signature-invalid"])


def test_no_trusted_keys_means_denied_and_verify_not_called():
    d, v = run(good(), keys={})
    assert d == (False, ["signature-invalid"])
    assert v.calls == []


def test_signature_entry_with_bad_base64_is_just_invalid():
    env = good()
    env["signatures"][0]["sig"] = "***not-base64***"
    d, _ = run(env)
    assert d == (False, ["signature-invalid"])


def test_malformed_signature_entries_do_not_raise():
    env = good()
    env["signatures"] = [None, "str", {"keyid": "k1"}, {"sig": "AAAA"}, {"keyid": ["k1"], "sig": "AAAA"}] + env["signatures"]
    d, _ = run(env)
    assert d.allowed


# --- форма envelope ----------------------------------------------------------------------------

@pytest.mark.parametrize("env", [None, [], "text", 5, {}, {"payloadType": PT}])
def test_garbage_envelope(env):
    d, v = run(env)
    assert d == (False, ["bad-envelope"])
    assert v.calls == []


def test_wrong_payload_type():
    env = good()
    env["payloadType"] = "text/plain"
    d, v = run(env)
    assert d == (False, ["bad-envelope"])
    assert v.calls == []


@pytest.mark.parametrize("payload", ["not base64!", "e30", "e3 0=", None, 12, "-_-_"])
def test_payload_must_be_strict_standard_base64(payload):
    env = good()
    env["payload"] = payload
    d, v = run(env)
    assert d == (False, ["bad-envelope"])
    assert v.calls == []


@pytest.mark.parametrize("sigs", [None, [], "sig", {}, 5])
def test_signatures_must_be_non_empty_list(sigs):
    env = good()
    env["signatures"] = sigs
    d, v = run(env)
    assert d == (False, ["bad-envelope"])
    assert v.calls == []


@pytest.mark.parametrize("digest", ["", "sha256:", "sha256:abc", DIGEST_HEX, "sha512:" + DIGEST_HEX,
                                    "sha256:" + DIGEST_HEX.upper(), "sha256:" + DIGEST_HEX + "0", None, 5,
                                    DIGEST + "\n"])
def test_bad_artifact_digest_is_denied_before_verify(digest):
    d, v = run(good(), digest=digest)
    assert d == (False, ["bad-artifact-digest"])
    assert v.calls == []


# --- statement ---------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [b"not json", b"[1, 2]", b"42", b"null", b'"s"', b"\xff\xfe", b""])
def test_signed_but_non_object_payload(raw):
    d, _ = run(envelope_for(None, raw=raw))
    assert d == (False, ["bad-statement"])


def test_wrong_statement_type():
    stmt = statement()
    stmt["_type"] = "https://in-toto.io/Statement/v0.1"
    assert run(envelope_for(stmt))[0] == (False, ["bad-statement"])
    del stmt["_type"]
    assert run(envelope_for(stmt))[0] == (False, ["bad-statement"])


@pytest.mark.parametrize("ptype", ["https://slsa.dev/provenance/v0.2", "https://spdx.dev/Document", None])
def test_wrong_predicate_type(ptype):
    stmt = statement()
    stmt["predicateType"] = ptype
    assert run(envelope_for(stmt))[0] == (False, ["wrong-predicate-type"])


# --- перевірки політики (по одному порушенню) -------------------------------------------------

def test_digest_of_another_artifact_is_rejected():
    # валідний підпис і чесний provenance, але для ІНШОГО образу
    d, _ = run(good(digest_hex=OTHER_HEX))
    assert d == (False, ["subject-mismatch"])


def test_subject_may_be_any_of_several():
    subs = [{"name": "a", "digest": {"sha256": OTHER_HEX}}, {"name": "b", "digest": {"sha256": DIGEST_HEX}}]
    assert run(good(subjects=subs))[0].allowed


@pytest.mark.parametrize("subs", [
    [], None, "x", [{"name": "a"}], [{"name": "a", "digest": {"sha512": DIGEST_HEX}}],
    [{"name": "a", "digest": {"sha256": DIGEST_HEX.upper()}}], ["str"], [{"name": "a", "digest": "x"}],
])
def test_subject_edge_cases(subs):
    stmt = statement()
    stmt["subject"] = subs
    assert run(envelope_for(stmt))[0] == (False, ["subject-mismatch"])


@pytest.mark.parametrize("builder", [
    BUILDER + "-evil", BUILDER.replace("v2.1.0", "v2.0.0"), BUILDER.upper(), BUILDER[:-1], "",
    "https://github.com/acme/builder/.github/workflows/build.yml@refs/heads/main",
    BUILDER + "/../../x",
])
def test_builder_must_match_exactly(builder):
    d, _ = run(good(builder=builder))
    assert d == (False, ["builder-not-allowed"])


def test_fork_repository_is_rejected():
    stmt = statement(source_repo=REPO)
    stmt["predicate"]["buildDefinition"]["externalParameters"]["workflow"]["repository"] = "https://github.com/evil/app"
    assert run(envelope_for(stmt))[0] == (False, ["repository-mismatch"])


@pytest.mark.parametrize("repo", [REPO + "-fork", REPO + "/", REPO.upper(), "https://github.com/acme", REPO + ".git"])
def test_repository_must_match_exactly(repo):
    stmt = statement()
    stmt["predicate"]["buildDefinition"]["externalParameters"]["workflow"]["repository"] = repo
    assert run(envelope_for(stmt))[0] == (False, ["repository-mismatch"])


def test_fork_build_fully_consistent_gets_repository_and_source_reasons():
    d, _ = run(good(repository="https://github.com/evil/app"))
    assert d.allowed is False
    assert "repository-mismatch" in d.reasons and "source-mismatch" in d.reasons


@pytest.mark.parametrize("ref", [
    "refs/heads/feature/x", "refs/heads/main-evil", "refs/heads/mainx", "refs/pull/12/merge", "refs/tags/x1",
    "refs/tags/", "refs/tag/v1", "main", "",
])
def test_ref_must_be_allowed(ref):
    d, _ = run(good(ref=ref))
    assert d == (False, ["ref-not-allowed"])


def test_tag_prefix_patterns():
    assert run(good(ref="refs/tags/v"))[0].allowed
    assert run(good(ref="refs/tags/v1.0.0-rc.1"))[0].allowed


@pytest.mark.parametrize("path", [".github/workflows/test.yml", ".github/workflows/release.yml.bak", "release.yml", ""])
def test_workflow_path_must_match_exactly(path):
    d, _ = run(good(path=path))
    assert d == (False, ["workflow-path-mismatch"])


@pytest.mark.parametrize("event", ["pull_request", "pull_request_target", "issue_comment", "workflow_run", "", "PUSH"])
def test_event_must_be_allowed(event):
    d, _ = run(good(event=event))
    assert d == (False, ["event-not-allowed"])


@pytest.mark.parametrize("event", ["push", "release", "workflow_dispatch"])
def test_default_events_allowed(event):
    assert run(good(event=event))[0].allowed


def test_custom_allowed_events():
    policy = {**POLICY, "allowed_events": ["schedule"]}
    assert run(good(event="schedule"), policy=policy)[0].allowed
    assert run(good(event="push"), policy=policy)[0] == (False, ["event-not-allowed"])


def test_source_must_match_repo_and_ref():
    stmt = statement()
    stmt["predicate"]["buildDefinition"]["resolvedDependencies"] = [
        {"uri": "git+https://github.com/acme/app@refs/heads/other", "digest": {}},
        {"uri": "git+https://github.com/evil/app@refs/heads/main", "digest": {}},
        {"digest": {}},
    ]
    assert run(envelope_for(stmt))[0] == (False, ["source-mismatch"])
    stmt["predicate"]["buildDefinition"]["resolvedDependencies"].append(
        {"uri": "git+https://github.com/acme/app@refs/heads/main", "digest": {}})
    assert run(envelope_for(stmt))[0].allowed


def test_reasons_accumulate_in_fixed_order_without_duplicates():
    stmt = statement(digest_hex=OTHER_HEX, builder="https://evil/builder", repository="https://github.com/evil/app",
                     ref="refs/pull/1/merge", path="x.yml", event="pull_request", source_repo="https://github.com/evil/app")
    d, _ = run(envelope_for(stmt))
    assert d.allowed is False
    assert d.reasons == ["subject-mismatch", "builder-not-allowed", "repository-mismatch", "ref-not-allowed",
                         "workflow-path-mismatch", "event-not-allowed", "source-mismatch"]


@pytest.mark.parametrize("path", [
    ("predicate",), ("predicate", "buildDefinition"), ("predicate", "buildDefinition", "externalParameters"),
    ("predicate", "buildDefinition", "externalParameters", "workflow"),
    ("predicate", "buildDefinition", "internalParameters"), ("predicate", "buildDefinition", "resolvedDependencies"),
    ("predicate", "runDetails"), ("predicate", "runDetails", "builder"), ("subject",),
])
def test_missing_or_mistyped_fields_are_denials_not_exceptions(path):
    for replacement in ("DELETE", None, "string", 5, [], ["x"]):
        stmt = statement()
        node = stmt
        for key in path[:-1]:
            node = node[key]
        if replacement == "DELETE":
            del node[path[-1]]
        else:
            node[path[-1]] = replacement
        d, _ = run(envelope_for(stmt))
        assert d.allowed is False
        assert d.reasons and all(isinstance(r, str) for r in d.reasons)


# --- політика ----------------------------------------------------------------------------------

@pytest.mark.parametrize("patch", [
    {"allowed_builders": []}, {"allowed_builders": BUILDER}, {"allowed_builders": [BUILDER, "https://x/*"]},
    {"allowed_builders": ["*"]}, {"allowed_builders": [""]}, {"allowed_builders": [None]},
    {"repository": ""}, {"repository": None}, {"workflow_path": ""}, {"workflow_path": None},
    {"allowed_refs": []}, {"allowed_refs": "refs/heads/main"}, {"allowed_refs": ["refs/*/main"]},
    {"allowed_refs": ["*x"]}, {"allowed_refs": [""]}, {"allowed_refs": [None]},
])
def test_invalid_policy_is_value_error_before_verify(patch):
    policy = {**POLICY, **patch}
    v = Verifier()
    with pytest.raises(ValueError):
        verify_provenance(good(), artifact_digest=DIGEST, policy=policy, trusted_keys=KEYS, verify=v)
    assert v.calls == []


@pytest.mark.parametrize("missing", ["allowed_builders", "repository", "allowed_refs", "workflow_path"])
def test_missing_policy_key_is_value_error(missing):
    policy = {k: v for k, v in POLICY.items() if k != missing}
    with pytest.raises(ValueError):
        run(good(), policy=policy)


def test_catch_all_ref_pattern_is_allowed_by_policy_only_when_explicit():
    policy = {**POLICY, "allowed_refs": ["*"]}
    assert run(good(ref="refs/pull/1/merge"), policy=policy)[0].allowed


def test_inputs_are_not_mutated():
    env, policy, keys = good(), copy.deepcopy(POLICY), dict(KEYS)
    env_before, policy_before = copy.deepcopy(env), copy.deepcopy(policy)
    run(env, policy=policy, keys=keys)
    assert env == env_before and policy == policy_before and keys == KEYS
