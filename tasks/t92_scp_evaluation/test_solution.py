import pytest

from solution import scp_allows

FULL = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}


def allow(action, resource="*", **kw):
    return {"Effect": "Allow", "Action": action, "Resource": resource, **kw}


def deny(action, resource="*", **kw):
    return {"Effect": "Deny", "Action": action, "Resource": resource, **kw}


def doc(*statements):
    return {"Version": "2012-10-17", "Statement": list(statements)}


REGION_LOCK = doc(
    {"Effect": "Deny", "NotAction": ["iam:*", "sts:*", "route53:*", "cloudfront:*", "support:*"], "Resource": "*",
     "Condition": {"StringNotEquals": {"aws:RequestedRegion": ["eu-west-1", "eu-central-1"]}}}
)


def test_empty_chain_and_empty_levels_deny():
    assert scp_allows([], "s3:GetObject") is False
    assert scp_allows([[]], "s3:GetObject") is False
    assert scp_allows([[FULL], []], "s3:GetObject") is False


def test_full_access_everywhere_allows():
    assert scp_allows([[FULL], [FULL], [FULL]], "ec2:RunInstances", "arn:aws:ec2:eu-west-1:1:instance/i-1") is True


def test_every_level_must_allow():
    root, ou, account = [FULL], [doc(allow(["s3:*", "ec2:*"]))], [FULL]
    chain = [root, ou, account]
    assert scp_allows(chain, "s3:GetObject") is True
    assert scp_allows(chain, "ec2:RunInstances") is True
    assert scp_allows(chain, "rds:CreateDBInstance") is False, "OU-рівень не дозволяє rds, навіть якщо акаунт FullAWSAccess"


def test_allow_at_child_level_cannot_exceed_parent():
    chain = [[doc(allow("s3:*"))], [FULL]]
    assert scp_allows(chain, "ec2:RunInstances") is False
    assert scp_allows(chain, "s3:PutObject") is True


def test_several_policies_at_one_level_are_unioned():
    chain = [[doc(allow("s3:*")), doc(allow("ec2:*"))]]
    assert scp_allows(chain, "s3:GetObject") is True
    assert scp_allows(chain, "ec2:StartInstances") is True
    assert scp_allows(chain, "rds:Describe*") is False


def test_explicit_deny_beats_allow_anywhere_in_chain():
    block = doc(deny("iam:DeleteUser"))
    for position in (0, 1, 2):
        chain = [[FULL], [FULL], [FULL]]
        chain[position] = [FULL, block]
        assert scp_allows(chain, "iam:DeleteUser") is False
        assert scp_allows(chain, "iam:CreateUser") is True


def test_deny_in_same_document_as_allow():
    chain = [[doc(allow("*"), deny("s3:DeleteBucket"))]]
    assert scp_allows(chain, "s3:DeleteBucket") is False
    assert scp_allows(chain, "s3:GetObject") is True


@pytest.mark.parametrize("pattern, action, expected", [
    ("s3:Get*", "s3:GetObject", True), ("s3:Get*", "S3:getobject", True), ("s3:Get*", "s3:PutObject", False),
    ("ec2:Describe?nstances", "ec2:DescribeInstances", True), ("ec2:Describe?nstances", "ec2:Describenstances", False),
    ("*", "anything:Goes", True), ("s3:*Bucket", "s3:DeleteBucket", True), ("s3:*Bucket", "s3:ListBuckets", False),
])
def test_action_patterns(pattern, action, expected):
    assert scp_allows([[doc(allow(pattern))]], action) is expected


def test_resource_patterns_are_case_sensitive():
    chain = [[doc(allow("s3:GetObject", "arn:aws:s3:::reports/*"))]]
    assert scp_allows(chain, "s3:GetObject", "arn:aws:s3:::reports/q1.csv") is True
    assert scp_allows(chain, "s3:GetObject", "arn:aws:s3:::Reports/q1.csv") is False
    assert scp_allows(chain, "s3:GetObject", "arn:aws:s3:::other/q1.csv") is False


def test_regex_metacharacters_are_literal():
    assert scp_allows([[doc(allow("s3:Get.bject"))]], "s3:GetObject") is False
    assert scp_allows([[doc(allow("s3:Get+"))]], "s3:Get+") is True


# ---------- Condition і NotAction: обмеження регіонів -------------------------


def test_region_lock_blocks_other_regions():
    chain = [[FULL], [FULL, REGION_LOCK]]
    assert scp_allows(chain, "ec2:RunInstances", context={"aws:RequestedRegion": "eu-west-1"}) is True
    assert scp_allows(chain, "ec2:RunInstances", context={"aws:RequestedRegion": "eu-central-1"}) is True
    assert scp_allows(chain, "ec2:RunInstances", context={"aws:RequestedRegion": "us-east-1"}) is False
    assert scp_allows(chain, "s3:CreateBucket", context={"aws:RequestedRegion": "ap-south-1"}) is False


def test_region_lock_exempts_global_services_through_notaction():
    chain = [[FULL, REGION_LOCK]]
    for action in ("iam:CreateRole", "sts:AssumeRole", "route53:ChangeResourceRecordSets", "cloudfront:CreateDistribution"):
        assert scp_allows(chain, action, context={"aws:RequestedRegion": "us-east-1"}) is True, action


def test_missing_context_key_means_stringnotequals_is_true():
    chain = [[FULL, REGION_LOCK]]
    assert scp_allows(chain, "ec2:RunInstances") is False, "ключа немає, StringNotEquals виконано, Deny спрацював"
    assert scp_allows(chain, "ec2:RunInstances", context={}) is False


def test_context_key_names_are_case_insensitive():
    chain = [[FULL, REGION_LOCK]]
    assert scp_allows(chain, "ec2:RunInstances", context={"AWS:RequestedRegion": "eu-west-1"}) is True


def test_stringequals_requires_key_to_be_present():
    only_eu = [[doc(allow("*", Condition={"StringEquals": {"aws:RequestedRegion": "eu-west-1"}}))]]
    assert scp_allows(only_eu, "s3:GetObject", context={"aws:RequestedRegion": "eu-west-1"}) is True
    assert scp_allows(only_eu, "s3:GetObject", context={"aws:RequestedRegion": "us-east-1"}) is False
    assert scp_allows(only_eu, "s3:GetObject") is False


def test_stringlike_and_notlike():
    allow_prod_tags = [[doc(allow("ec2:*", Condition={"StringLike": {"aws:PrincipalTag/team": "plat*"}}))]]
    assert scp_allows(allow_prod_tags, "ec2:RunInstances", context={"aws:PrincipalTag/team": "platform"}) is True
    assert scp_allows(allow_prod_tags, "ec2:RunInstances", context={"aws:PrincipalTag/team": "Platform"}) is False, "регістр значущий"
    assert scp_allows(allow_prod_tags, "ec2:RunInstances") is False
    block = [[FULL, doc(deny("*", Condition={"StringNotLike": {"aws:PrincipalArn": "arn:aws:iam::*:role/Admin*"}}))]]
    assert scp_allows(block, "s3:GetObject", context={"aws:PrincipalArn": "arn:aws:iam::123:role/AdminOps"}) is True
    assert scp_allows(block, "s3:GetObject", context={"aws:PrincipalArn": "arn:aws:iam::123:role/dev"}) is False


def test_bool_condition_for_mfa():
    need_mfa = [[FULL, doc(deny("iam:*", Condition={"Bool": {"aws:MultiFactorAuthPresent": "false"}}))]]
    assert scp_allows(need_mfa, "iam:CreateUser", context={"aws:MultiFactorAuthPresent": "true"}) is True
    assert scp_allows(need_mfa, "iam:CreateUser", context={"aws:MultiFactorAuthPresent": "FALSE"}) is False
    assert scp_allows(need_mfa, "iam:CreateUser") is True, "ключа немає: Bool не виконується, Deny не спрацював"


def test_all_conditions_must_hold():
    chain = [[doc(allow("*", Condition={"StringEquals": {"aws:RequestedRegion": "eu-west-1", "aws:PrincipalTag/env": ["dev", "test"]}}))]]
    assert scp_allows(chain, "s3:ListAllMyBuckets", context={"aws:RequestedRegion": "eu-west-1", "aws:PrincipalTag/env": "test"}) is True
    assert scp_allows(chain, "s3:ListAllMyBuckets", context={"aws:RequestedRegion": "eu-west-1", "aws:PrincipalTag/env": "prod"}) is False


def test_unknown_operator_never_matches():
    chain_allow = [[doc(allow("*", Condition={"IpAddress": {"aws:SourceIp": "10.0.0.0/8"}}))]]
    assert scp_allows(chain_allow, "s3:GetObject", context={"aws:SourceIp": "10.1.1.1"}) is False
    chain_deny = [[FULL, doc(deny("*", Condition={"IpAddress": {"aws:SourceIp": "10.0.0.0/8"}}))]]
    assert scp_allows(chain_deny, "s3:GetObject", context={"aws:SourceIp": "10.1.1.1"}) is True


def test_single_statement_dict_and_default_resource():
    chain = [[{"Effect": "Allow", "Action": "s3:*"}]]
    assert scp_allows(chain, "s3:GetObject", "arn:aws:s3:::any/key") is True
    single = [[{"Version": "2012-10-17", "Statement": {"Effect": "Allow", "Action": "s3:*", "Resource": "*"}}]]
    assert scp_allows(single, "s3:GetObject") is True


def test_inputs_are_not_modified():
    import copy
    chain = [[FULL, REGION_LOCK]]
    snapshot = copy.deepcopy(chain)
    scp_allows(chain, "ec2:RunInstances", context={"aws:RequestedRegion": "us-east-1"})
    assert chain == snapshot
