import copy

import pytest

from solution import audit_trust_policy

PROVIDER = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
SUB = "token.actions.githubusercontent.com:sub"
AUD = "token.actions.githubusercontent.com:aud"
REPO = "acme/shop"


def policy(sub="repo:acme/shop:ref:refs/heads/main", aud="sts.amazonaws.com", operator="StringEquals", action="sts:AssumeRoleWithWebIdentity",
           principal=None, extra_conditions=None):
    cond = {}
    if aud is not None:
        cond[AUD] = aud
    if sub is not None:
        cond[SUB] = sub
    body = {"Effect": "Allow", "Principal": principal or {"Federated": PROVIDER}, "Action": action}
    conditions = {operator: cond} if cond else {}
    for k, v in (extra_conditions or {}).items():
        conditions[k] = v
    if conditions:
        body["Condition"] = conditions
    return {"Version": "2012-10-17", "Statement": [body]}


def audit(p, repo=REPO):
    return audit_trust_policy(p, repo)


def test_good_policy():
    assert audit(policy()) == []


def test_good_policy_variants():
    assert audit(policy(sub=["repo:acme/shop:ref:refs/heads/main", "repo:acme/shop:environment:production"])) == []
    assert audit(policy(sub="repo:acme/shop:environment:production")) == []
    assert audit(policy(sub="repo:acme/shop:ref:refs/tags/v*", operator="StringLike")) == []
    assert audit(policy(action=["sts:AssumeRoleWithWebIdentity"])) == []
    assert audit(policy(sub="repo:ACME/Shop:ref:refs/heads/main")) == [], "імена репозиторіїв нечутливі до регістру"
    assert audit(policy(aud=["sts.amazonaws.com"])) == []


def test_missing_sub_condition_means_any_repository_can_assume():
    assert audit(policy(sub=None)) == ["OIDC001"]


def test_no_condition_at_all():
    p = policy(sub=None, aud=None)
    assert audit(p) == ["OIDC001", "OIDC004"]


def test_sub_condition_under_stringlike_counts():
    assert audit(policy(sub="repo:acme/shop:ref:refs/heads/main", operator="StringLike")) == []


@pytest.mark.parametrize("aud", [None, "other.example.com", ["sts.amazonaws.com", "evil"]])
def test_audience(aud):
    assert audit(policy(aud=aud)) == ["OIDC004"]


@pytest.mark.parametrize("sub", ["*", "repo:*", "repo:acme/*", "repo:*/shop:*", "repo:acme/*:ref:refs/heads/main", "repo:acme"])
def test_org_wide_or_wildcard_repository(sub):
    assert audit(policy(sub=sub, operator="StringLike")) == ["OIDC002"]


@pytest.mark.parametrize("sub", ["repo:acme/other:ref:refs/heads/main", "repo:evil/shop:environment:production", "repo:acme/shop2:*"])
def test_other_repository(sub):
    assert "OIDC003" in audit(policy(sub=sub))


@pytest.mark.parametrize("sub", [
    "repo:acme/shop:*", "repo:acme/shop:pull_request", "repo:acme/shop:ref:refs/heads/*", "repo:acme/shop:environment:*",
    "repo:acme/shop:", "repo:acme/shop:ref:refs/pull/*/merge", "repo:acme/shop:pull_request:extra",
])
def test_too_broad_within_repository(sub):
    assert audit(policy(sub=sub, operator="StringLike")) == ["OIDC007"]


def test_each_sub_value_is_checked_and_codes_are_merged():
    p = policy(sub=["repo:acme/shop:ref:refs/heads/main", "repo:acme/shop:pull_request", "repo:acme/*", "repo:other/x:ref:refs/heads/main"],
               operator="StringLike")
    assert audit(p) == ["OIDC002", "OIDC003", "OIDC007"]


@pytest.mark.parametrize("action", ["sts:*", "sts:AssumeRole", "*", ["sts:AssumeRoleWithWebIdentity", "sts:TagSession"]])
def test_wrong_action(action):
    assert audit(policy(action=action)) == ["OIDC005"]


def test_action_is_case_insensitive():
    assert audit(policy(action="STS:assumerolewithwebidentity")) == []


@pytest.mark.parametrize("principal", ["*", {"AWS": "*"}, {"Federated": "*"}, {"AWS": ["arn:aws:iam::1:root", "*"]}])
def test_anyone_can_assume(principal):
    result = audit(policy(principal=principal))
    assert "OIDC006" in result


def test_non_github_principals_are_ignored_except_wildcards():
    service = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ecs-tasks.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
    assert audit(service) == []
    other_idp = policy(principal={"Federated": "arn:aws:iam::123456789012:oidc-provider/accounts.google.com"}, sub=None, aud=None)
    assert audit(other_idp) == []
    saml = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::123456789012:root"}, "Action": "sts:AssumeRole"}]}
    assert audit(saml) == []


def test_provider_arn_list_and_other_provider_prefix():
    p = policy(principal={"Federated": ["arn:aws:iam::1:oidc-provider/accounts.google.com", PROVIDER]}, sub=None)
    assert audit(p) == ["OIDC001"]
    lookalike = policy(principal={"Federated": "arn:aws:iam::1:oidc-provider/token.actions.githubusercontent.com.evil.example"}, sub=None)
    assert audit(lookalike) == []


def test_deny_statements_are_not_analyzed():
    p = policy(sub=None, aud=None)
    p["Statement"][0]["Effect"] = "Deny"
    assert audit(p) == []


def test_multiple_statements_are_all_checked():
    p = policy()
    bad = copy.deepcopy(policy(sub="repo:acme/*", operator="StringLike", action="sts:*"))
    p["Statement"].extend(bad["Statement"])
    assert audit(p) == ["OIDC002", "OIDC005"]


def test_policy_is_not_modified():
    p = policy(sub=["repo:acme/*"], operator="StringLike")
    snapshot = copy.deepcopy(p)
    audit(p)
    assert p == snapshot


def test_single_statement_given_as_dict():
    p = policy()
    p["Statement"] = p["Statement"][0]
    assert audit(p) == []
    p2 = policy(sub=None)
    p2["Statement"] = p2["Statement"][0]
    assert audit(p2) == ["OIDC001"]
