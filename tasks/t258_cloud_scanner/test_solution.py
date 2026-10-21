import copy

import pytest

from solution import scan_account

ALL_BPA = {"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True}
GOOD_TRAIL = {"cloudtrails": [{"name": "main", "is_multi_region": True, "is_logging": True}]}
SEV_ORDER = ["critical", "high", "medium", "low"]


def scan(snapshot, with_trail=True):
    snap = dict(GOOD_TRAIL) if with_trail else {}
    snap.update(snapshot)
    return scan_account(snap)


def triples(findings):
    return {(f["rule"], f["resource"], f["severity"]) for f in findings}


def pub_policy(action="s3:GetObject", principal="*", condition=None, effect="Allow", **extra):
    st = {"Effect": effect, "Principal": principal, "Action": action, "Resource": "arn:aws:s3:::b/*", **extra}
    if condition:
        st["Condition"] = condition
    return {"Version": "2012-10-17", "Statement": st}


def bucket(name="b", bpa=None, grants=None, policy=None):
    return {"name": name, "block_public_access": bpa or {}, "acl_grants": grants or [], "policy": policy}


# --- форма ----------------------------------------------------------------------------------------

def test_clean_account_has_no_findings():
    snap = {
        "account_block_public_access": ALL_BPA,
        "s3_buckets": [bucket("private", grants=[{"grantee": "CanonicalUser:abc", "permission": "FULL_CONTROL"}])],
        "security_groups": [{"id": "sg-1", "ingress": [
            {"protocol": "tcp", "from_port": 443, "to_port": 443, "cidrs": ["0.0.0.0/0"], "ipv6_cidrs": []},
            {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidrs": ["10.0.0.0/8"], "ipv6_cidrs": []}]}],
        "instances": [{"id": "i-1", "metadata_options": {"http_tokens": "required", "http_endpoint": "enabled"}},
                      {"id": "i-2", "metadata_options": {"http_tokens": "optional", "http_endpoint": "disabled"}}],
        "kms_keys": [{"id": "k-1", "key_manager": "CUSTOMER", "key_spec": "SYMMETRIC_DEFAULT",
                      "key_state": "Enabled", "rotation_enabled": True}],
        "rds_instances": [{"id": "db-1", "publicly_accessible": False}],
    }
    assert scan(snap) == []


@pytest.mark.parametrize("bad", [None, [], "x", 5])
def test_snapshot_must_be_dict(bad):
    with pytest.raises(ValueError):
        scan_account(bad)


def test_empty_snapshot_only_reports_missing_cloudtrail():
    got = scan_account({})
    assert triples(got) == {("cloudtrail-missing", "account", "high")}


def test_finding_shape_sorting_and_no_mutation():
    snap = {
        "s3_buckets": [bucket("zeta", grants=[{"grantee": "AllUsers", "permission": "READ"}]),
                       bucket("alpha", grants=[{"grantee": "AllUsers", "permission": "WRITE"}])],
        "rds_instances": [{"id": "db-9", "publicly_accessible": True}],
        "kms_keys": [{"id": "k", "key_manager": "CUSTOMER", "key_spec": "SYMMETRIC_DEFAULT",
                      "key_state": "Enabled", "rotation_enabled": False}],
    }
    before = copy.deepcopy(snap)
    got = scan(snap)
    assert snap == before
    assert all(set(f) == {"rule", "resource", "severity", "fix"} for f in got)
    assert all(isinstance(f["fix"], str) and f["fix"].strip() for f in got)
    keys = [(SEV_ORDER.index(f["severity"]), f["rule"], f["resource"]) for f in got]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))
    assert got[0]["severity"] == "critical"
    assert [f["resource"] for f in got if f["rule"] == "s3-public"] == ["alpha", "zeta"]


# --- S3: ефективна публічність -----------------------------------------------------------------

def test_acl_all_users_read_is_high_and_write_is_critical():
    read = scan({"s3_buckets": [bucket(grants=[{"grantee": "AllUsers", "permission": "READ"}])]})
    assert ("s3-public", "b", "high") in triples(read)
    for perm in ("WRITE", "WRITE_ACP", "FULL_CONTROL"):
        got = scan({"s3_buckets": [bucket(grants=[{"grantee": "AuthenticatedUsers", "permission": perm}])]})
        assert ("s3-public", "b", "critical") in triples(got), perm


def test_max_severity_over_all_grants():
    grants = [{"grantee": "AllUsers", "permission": "READ"}, {"grantee": "AllUsers", "permission": "WRITE"}]
    got = [f for f in scan({"s3_buckets": [bucket(grants=grants)]}) if f["rule"] == "s3-public"]
    assert len(got) == 1 and got[0]["severity"] == "critical"


def test_acl_to_canonical_user_is_private():
    got = scan({"s3_buckets": [bucket(bpa=ALL_BPA, grants=[{"grantee": "CanonicalUser:x", "permission": "READ"}])]})
    assert got == []


def test_ignore_public_acls_neutralises_acl_at_bucket_or_account_level():
    grants = [{"grantee": "AllUsers", "permission": "FULL_CONTROL"}]
    bucket_level = scan({"s3_buckets": [bucket(bpa={"IgnorePublicAcls": True}, grants=grants)]})
    assert "s3-public" not in {f["rule"] for f in bucket_level}
    account_level = scan({"account_block_public_access": {"IgnorePublicAcls": True},
                          "s3_buckets": [bucket(grants=grants)]})
    assert "s3-public" not in {f["rule"] for f in account_level}


def test_block_public_acls_alone_does_not_neutralise_existing_acl():
    grants = [{"grantee": "AllUsers", "permission": "READ"}]
    got = scan({"s3_buckets": [bucket(bpa={"BlockPublicAcls": True, "BlockPublicPolicy": True}, grants=grants)]})
    assert ("s3-public", "b", "high") in triples(got)


@pytest.mark.parametrize("principal", ["*", {"AWS": "*"}, {"AWS": ["arn:aws:iam::1:root", "*"]}])
def test_public_policy_principals(principal):
    got = scan({"s3_buckets": [bucket(policy=pub_policy(principal=principal))]})
    assert ("s3-public", "b", "high") in triples(got)


@pytest.mark.parametrize("action, severity", [
    ("s3:GetObject", "high"), (["s3:GetObject", "s3:ListBucket"], "high"), ("s3:PutObject", "critical"),
    ("S3:DELETEOBJECT", "critical"), ("s3:*", "critical"), ("*", "critical"), (["s3:GetObject", "s3:PutObjectAcl"], "critical"),
    ("s3:Get*", "high"),
])
def test_policy_severity_by_action(action, severity):
    got = scan({"s3_buckets": [bucket(policy=pub_policy(action=action))]})
    assert ("s3-public", "b", severity) in triples(got)


@pytest.mark.parametrize("condition", [
    {"StringEquals": {"aws:PrincipalOrgID": "o-123"}},
    {"StringEquals": {"AWS:SourceVpce": "vpce-1"}},
    {"StringEquals": {"aws:SourceVpc": "vpc-1"}},
    {"ArnLike": {"aws:PrincipalArn": "arn:aws:iam::1:role/x"}},
    {"StringEquals": {"aws:SourceAccount": "111122223333"}},
])
def test_restrictive_conditions_make_policy_non_public(condition):
    got = scan({"s3_buckets": [bucket(policy=pub_policy(condition=condition))]})
    assert "s3-public" not in {f["rule"] for f in got}


def test_non_restrictive_condition_does_not_help():
    got = scan({"s3_buckets": [bucket(policy=pub_policy(condition={"StringEquals": {"aws:UserAgent": "x"}}))]})
    assert ("s3-public", "b", "high") in triples(got)


def test_deny_and_non_public_principal_are_fine():
    assert "s3-public" not in {f["rule"] for f in scan({"s3_buckets": [bucket(policy=pub_policy(effect="Deny"))]})}
    named = pub_policy(principal={"AWS": "arn:aws:iam::123456789012:root"})
    assert "s3-public" not in {f["rule"] for f in scan({"s3_buckets": [bucket(policy=named)]})}
    notp = pub_policy(principal="*", NotPrincipal={"AWS": "x"})
    assert "s3-public" not in {f["rule"] for f in scan({"s3_buckets": [bucket(policy=notp)]})}


def test_restrict_public_buckets_neutralises_policy_but_block_public_policy_does_not():
    pol = pub_policy()
    assert "s3-public" not in {f["rule"] for f in scan({"s3_buckets": [bucket(bpa={"RestrictPublicBuckets": True}, policy=pol)]})}
    assert "s3-public" not in {f["rule"] for f in scan({"account_block_public_access": {"RestrictPublicBuckets": True},
                                                       "s3_buckets": [bucket(policy=pol)]})}
    still = scan({"s3_buckets": [bucket(bpa={"BlockPublicPolicy": True}, policy=pol)]})
    assert ("s3-public", "b", "high") in triples(still)


def test_statement_list_and_one_neutralised_path_still_leaves_the_other():
    pol = {"Statement": [pub_policy(effect="Deny")["Statement"], pub_policy("s3:PutObject")["Statement"]]}
    got = scan({"s3_buckets": [bucket(bpa={"IgnorePublicAcls": True}, grants=[{"grantee": "AllUsers", "permission": "READ"}],
                                      policy=pol)]})
    assert ("s3-public", "b", "critical") in triples(got)
    only_acl_blocked = scan({"s3_buckets": [bucket(bpa={"IgnorePublicAcls": True}, grants=[
        {"grantee": "AllUsers", "permission": "FULL_CONTROL"}], policy=pub_policy())]})
    assert ("s3-public", "b", "high") in triples(only_acl_blocked)  # лишився шлях через політику (читання)


def test_missing_policy_and_acl_fields_are_tolerated():
    assert triples(scan({"s3_buckets": [{"name": "bare"}]})) == {("s3-bpa-incomplete", "bare", "low")}
    assert "s3-public" not in {f["rule"] for f in scan({"s3_buckets": [bucket(policy=None)]})}


def test_bpa_incomplete_uses_or_of_account_and_bucket_flags():
    half_a = {"BlockPublicAcls": True, "IgnorePublicAcls": True}
    half_b = {"BlockPublicPolicy": True, "RestrictPublicBuckets": True}
    assert scan({"account_block_public_access": half_a, "s3_buckets": [bucket(bpa=half_b)]}) == []
    got = scan({"account_block_public_access": half_a, "s3_buckets": [bucket(bpa={"BlockPublicPolicy": True})]})
    assert triples(got) == {("s3-bpa-incomplete", "b", "low")}


# --- security groups -----------------------------------------------------------------------------

def rule(protocol="tcp", lo=None, hi=None, cidrs=("0.0.0.0/0",), v6=()):
    return {"protocol": protocol, "from_port": lo, "to_port": hi, "cidrs": list(cidrs), "ipv6_cidrs": list(v6)}


def sg(*ingress, sid="sg-1"):
    return {"security_groups": [{"id": sid, "ingress": list(ingress)}]}


@pytest.mark.parametrize("port", [22, 3389, 5432])
def test_admin_port_open_to_world(port):
    got = scan(sg(rule(lo=port, hi=port)))
    assert triples(got) == {("sg-open-admin-port", f"sg-1:{port}", "high")}


def test_ipv6_world_and_port_ranges():
    assert triples(scan(sg(rule(lo=22, hi=22, cidrs=(), v6=("::/0",))))) == {("sg-open-admin-port", "sg-1:22", "high")}
    got = scan(sg(rule(lo=20, hi=25)))
    assert triples(got) == {("sg-open-admin-port", "sg-1:22", "high")}
    got = scan(sg(rule(lo=3000, hi=6000)))
    assert triples(got) == {("sg-open-admin-port", "sg-1:3389", "high"), ("sg-open-admin-port", "sg-1:5432", "high")}


def test_range_boundaries_are_inclusive_and_exclusive_correctly():
    assert triples(scan(sg(rule(lo=22, hi=80)))) == {("sg-open-admin-port", "sg-1:22", "high")}
    assert triples(scan(sg(rule(lo=1, hi=22)))) == {("sg-open-admin-port", "sg-1:22", "high")}
    assert scan(sg(rule(lo=23, hi=3388))) == []
    assert scan(sg(rule(lo=3390, hi=5431))) == []


@pytest.mark.parametrize("r", [
    rule(lo=22, hi=22, cidrs=("10.0.0.0/8",)),
    rule(lo=22, hi=22, cidrs=("0.0.0.0/1",)),
    rule(lo=22, hi=22, cidrs=("203.0.113.7/32",)),
    rule("udp", 22, 22),
    rule("icmp", None, None),
    rule(lo=80, hi=443),
])
def test_not_a_finding(r):
    assert scan(sg(r)) == []


def test_open_all_variants_and_no_duplicate_port_findings():
    for r in (rule("-1"), rule("tcp", 0, 65535), rule("udp", 0, 65535), rule("-1", cidrs=(), v6=("::/0",))):
        assert triples(scan(sg(r, rule(lo=22, hi=22)))) == {("sg-open-all", "sg-1", "critical")}
    assert scan(sg(rule("tcp", 0, 65535, cidrs=("10.0.0.0/8",)))) == []


def test_each_group_is_independent_and_duplicates_collapse():
    snap = {"security_groups": [
        {"id": "sg-a", "ingress": [rule(lo=22, hi=22), rule(lo=22, hi=22, cidrs=(), v6=("::/0",))]},
        {"id": "sg-b", "ingress": [rule("-1")]},
        {"id": "sg-c", "ingress": []},
    ]}
    assert triples(scan(snap)) == {("sg-open-admin-port", "sg-a:22", "high"), ("sg-open-all", "sg-b", "critical")}


# --- IMDS, CloudTrail, KMS, RDS ------------------------------------------------------------------

def test_imds_rules():
    snap = {"instances": [
        {"id": "i-default"},
        {"id": "i-optional", "metadata_options": {"http_tokens": "optional", "http_endpoint": "enabled"}},
        {"id": "i-required", "metadata_options": {"http_tokens": "required", "http_endpoint": "enabled"}},
        {"id": "i-disabled", "metadata_options": {"http_tokens": "optional", "http_endpoint": "disabled"}},
        {"id": "i-only-tokens-field", "metadata_options": {"http_tokens": "required"}},
        {"id": "i-only-endpoint-field", "metadata_options": {"http_endpoint": "enabled"}},
    ]}
    assert triples(scan(snap)) == {("imdsv1-enabled", "i-default", "high"), ("imdsv1-enabled", "i-optional", "high"),
                                   ("imdsv1-enabled", "i-only-endpoint-field", "high")}


def test_cloudtrail_missing_variants():
    assert triples(scan({}, with_trail=False)) == {("cloudtrail-missing", "account", "high")}
    regional = {"cloudtrails": [{"name": "r", "is_multi_region": False, "is_logging": True}]}
    assert triples(scan(regional, with_trail=False)) == {("cloudtrail-missing", "account", "high")}
    stopped = {"cloudtrails": [{"name": "s", "is_multi_region": True, "is_logging": False}]}
    assert triples(scan(stopped, with_trail=False)) == {("cloudtrail-missing", "account", "high"),
                                                       ("cloudtrail-not-logging", "s", "high")}


def test_cloudtrail_ok_with_extra_stopped_trail_reports_only_that_trail():
    snap = {"cloudtrails": [{"name": "good", "is_multi_region": True, "is_logging": True},
                            {"name": "old", "is_multi_region": False, "is_logging": False}]}
    assert triples(scan(snap, with_trail=False)) == {("cloudtrail-not-logging", "old", "high")}


def key(**kw):
    base = {"id": "k", "key_manager": "CUSTOMER", "key_spec": "SYMMETRIC_DEFAULT", "key_state": "Enabled",
            "rotation_enabled": False}
    base.update(kw)
    return base


def test_kms_rotation_rules():
    assert triples(scan({"kms_keys": [key()]})) == {("kms-no-rotation", "k", "medium")}
    for skip in (key(rotation_enabled=True), key(key_manager="AWS"), key(key_spec="RSA_2048"),
                 key(key_spec="ECC_NIST_P256"), key(key_state="Disabled"), key(key_state="PendingDeletion")):
        assert scan({"kms_keys": [skip]}) == [], skip


def test_public_rds():
    snap = {"rds_instances": [{"id": "db-pub", "publicly_accessible": True},
                              {"id": "db-priv", "publicly_accessible": False}, {"id": "db-unknown"}]}
    assert triples(scan(snap)) == {("rds-public", "db-pub", "critical")}


def test_everything_together():
    snap = {
        "account_block_public_access": {"BlockPublicAcls": True},
        "s3_buckets": [bucket("data", grants=[{"grantee": "AllUsers", "permission": "READ"}])],
        "security_groups": [{"id": "sg-9", "ingress": [rule(lo=3389, hi=3389)]}],
        "instances": [{"id": "i-1"}],
        "kms_keys": [key()],
        "rds_instances": [{"id": "db", "publicly_accessible": True}],
    }
    assert triples(scan(snap)) == {
        ("s3-public", "data", "high"), ("s3-bpa-incomplete", "data", "low"),
        ("sg-open-admin-port", "sg-9:3389", "high"), ("imdsv1-enabled", "i-1", "high"),
        ("kms-no-rotation", "k", "medium"), ("rds-public", "db", "critical"),
    }
