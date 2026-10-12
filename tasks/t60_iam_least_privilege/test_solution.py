import pytest

from solution import generate_policy, is_allowed

BUCKET = "arn:aws:s3:::reports"
OBJ = "arn:aws:s3:::reports/2026/q1.csv"


def pol(*statements):
    return {"Version": "2012-10-17", "Statement": list(statements)}


def allow(action, resource, **extra):
    return {"Effect": "Allow", "Action": action, "Resource": resource, **extra}


def deny(action, resource, **extra):
    return {"Effect": "Deny", "Action": action, "Resource": resource, **extra}


# ---------- симулятор ---------------------------------------------------------


def test_implicit_deny():
    assert not is_allowed(pol(), "s3:GetObject", OBJ)
    assert not is_allowed(pol(allow("s3:PutObject", OBJ)), "s3:GetObject", OBJ)
    assert not is_allowed(pol(allow("s3:GetObject", OBJ)), "s3:GetObject", OBJ + "x")


def test_exact_allow_and_single_statement_dict():
    assert is_allowed(pol(allow("s3:GetObject", OBJ)), "s3:GetObject", OBJ)
    assert is_allowed({"Version": "2012-10-17", "Statement": allow("s3:GetObject", OBJ)}, "s3:GetObject", OBJ)


def test_action_is_case_insensitive_resource_is_not():
    p = pol(allow("S3:GetObject", OBJ))
    assert is_allowed(p, "s3:getobject", OBJ)
    assert not is_allowed(pol(allow("s3:GetObject", OBJ)), "s3:GetObject", OBJ.upper())


@pytest.mark.parametrize("pattern, action, expected", [
    ("*", "iam:DeleteUser", True),
    ("s3:*", "s3:GetObject", True),
    ("s3:*", "ec2:RunInstances", False),
    ("s3:Get*", "s3:GetObject", True),
    ("s3:Get*", "s3:PutObject", False),
    ("s3:Get?bject", "s3:GetObject", True),
    ("s3:Get?bject", "s3:Getbject", False),
    ("s3:*Object", "s3:PutObject", True),
    ("s3:*Object", "s3:PutObjectAcl", False),
])
def test_action_wildcards(pattern, action, expected):
    assert is_allowed(pol(allow(pattern, "*")), action, OBJ) is expected


@pytest.mark.parametrize("pattern, resource, expected", [
    ("*", OBJ, True),
    ("arn:aws:s3:::reports/*", OBJ, True),
    ("arn:aws:s3:::reports/*", BUCKET, False),
    ("arn:aws:s3:::reports", BUCKET, True),
    ("arn:aws:s3:::reports/2026/q?.csv", OBJ, True),
    ("arn:aws:s3:::*", OBJ, True),
    ("arn:aws:s3:::other/*", OBJ, False),
])
def test_resource_wildcards(pattern, resource, expected):
    assert is_allowed(pol(allow("s3:GetObject", pattern)), "s3:GetObject", resource) is expected


def test_regex_metacharacters_in_policy_are_literal():
    assert not is_allowed(pol(allow("s3:Get.bject", "*")), "s3:GetObject", OBJ)
    assert is_allowed(pol(allow("s3:Get.bject", "*")), "s3:Get.bject", OBJ)
    assert not is_allowed(pol(allow("s3:Get+", "*")), "s3:GetObject", OBJ)


def test_lists_of_actions_and_resources():
    p = pol(allow(["s3:GetObject", "s3:PutObject"], [OBJ, BUCKET]))
    assert is_allowed(p, "s3:PutObject", BUCKET)
    assert not is_allowed(p, "s3:DeleteObject", BUCKET)


def test_explicit_deny_beats_allow_regardless_of_order():
    allow_all = allow("s3:*", "*")
    block = deny("s3:DeleteObject", "arn:aws:s3:::reports/*")
    for statements in ((allow_all, block), (block, allow_all)):
        p = pol(*statements)
        assert not is_allowed(p, "s3:DeleteObject", OBJ)
        assert is_allowed(p, "s3:GetObject", OBJ)
        assert is_allowed(p, "s3:DeleteObject", "arn:aws:s3:::other/x")


def test_unsupported_keys_are_treated_conservatively():
    cond = {"StringEquals": {"aws:RequestedRegion": "eu-west-1"}}
    assert not is_allowed(pol(allow("s3:GetObject", OBJ, Condition=cond)), "s3:GetObject", OBJ)
    assert not is_allowed(pol(allow("s3:*", "*"), deny("s3:GetObject", OBJ, Condition=cond)), "s3:GetObject", OBJ)
    assert not is_allowed(pol(allow("s3:GetObject", OBJ, NotResource="x")), "s3:GetObject", OBJ)


# ---------- генератор ---------------------------------------------------------


def statements_of(policy):
    return policy["Statement"]


def test_empty_log_gives_empty_policy():
    assert generate_policy([]) == {"Version": "2012-10-17", "Statement": []}


def test_one_event_one_exact_statement():
    p = generate_policy([("s3:GetObject", OBJ)])
    assert p == {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": [OBJ]}]}


def test_same_action_set_on_several_resources_is_merged():
    events = [("s3:GetObject", OBJ), ("s3:PutObject", OBJ), ("s3:PutObject", "arn:aws:s3:::reports/2026/q2.csv"),
              ("s3:GetObject", "arn:aws:s3:::reports/2026/q2.csv"), ("s3:GetObject", OBJ)]
    p = generate_policy(events)
    assert statements_of(p) == [{"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
                                 "Resource": [OBJ, "arn:aws:s3:::reports/2026/q2.csv"]}]


def test_different_action_sets_stay_separate_and_sorted():
    events = [("s3:ListBucket", BUCKET), ("s3:GetObject", OBJ), ("dynamodb:GetItem", "arn:aws:dynamodb:eu-west-1:1:table/t")]
    st = statements_of(generate_policy(events))
    assert [s["Action"] for s in st] == [["dynamodb:GetItem"], ["s3:GetObject"], ["s3:ListBucket"]]


def test_resourceless_actions_get_star_resource_in_last_statement():
    events = [("sts:GetCallerIdentity", "arn:aws:iam::1:user/x"), ("ec2:DescribeInstances", "arn:aws:ec2:eu-west-1:1:instance/i-1"),
              ("EC2:DescribeVolumes", "*"), ("s3:ListAllMyBuckets", "*"), ("s3:GetObject", OBJ)]
    st = statements_of(generate_policy(events))
    assert st[0] == {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": [OBJ]}
    assert st[-1]["Resource"] == "*"
    assert st[-1]["Action"] == ["EC2:DescribeVolumes", "ec2:DescribeInstances", "s3:ListAllMyBuckets", "sts:GetCallerIdentity"]
    assert len(st) == 2


def test_never_emits_wildcard_actions_or_resources_for_resource_scoped_actions():
    events = [("s3:GetObject", OBJ), ("s3:PutObject", OBJ), ("iam:PassRole", "arn:aws:iam::1:role/app"), ("ec2:DescribeVpcs", "*")]
    for st in statements_of(generate_policy(events)):
        assert all("*" not in a and "?" not in a for a in st["Action"] if not a.lower().startswith("ec2:describe"))
        if st["Resource"] != "*":
            assert all("*" not in r for r in st["Resource"])


def test_generated_policy_allows_exactly_what_was_observed():
    events = [("s3:GetObject", OBJ), ("s3:PutObject", OBJ), ("s3:ListBucket", BUCKET), ("sts:GetCallerIdentity", "*"),
              ("dynamodb:Query", "arn:aws:dynamodb:eu-west-1:1:table/t")]
    p = generate_policy(events)
    for action, resource in events:
        assert is_allowed(p, action, resource), (action, resource)
    # ніщо інше не дозволено
    assert not is_allowed(p, "s3:DeleteObject", OBJ)
    assert not is_allowed(p, "s3:GetObject", BUCKET)
    assert not is_allowed(p, "s3:GetObject", "arn:aws:s3:::reports/other.csv")
    assert not is_allowed(p, "s3:PutObject", BUCKET)
    assert not is_allowed(p, "iam:CreateUser", "*")
    assert not is_allowed(p, "dynamodb:PutItem", "arn:aws:dynamodb:eu-west-1:1:table/t")


def test_generate_does_not_depend_on_event_order():
    events = [("s3:GetObject", OBJ), ("s3:ListBucket", BUCKET), ("s3:PutObject", OBJ), ("s3:GetObject", BUCKET)]
    assert generate_policy(events) == generate_policy(list(reversed(events)))
