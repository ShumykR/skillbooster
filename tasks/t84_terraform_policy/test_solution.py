import copy

import pytest

from solution import evaluate_plan

TAGS = {"owner": "platform", "env": "prod"}


def rc(typ, name, after, actions=("create",), module=None):
    prefix = f"module.{module}." if module else ""
    return {
        "address": f"{prefix}{typ}.{name}",
        "type": typ,
        "name": name,
        "change": {"actions": list(actions), "after": after},
    }


def plan(*changes):
    return {"format_version": "1.2", "resource_changes": list(changes)}


GOOD = plan(
    rc("aws_s3_bucket", "data", {"bucket": "d", "acl": "private", "tags": TAGS}),
    rc(
        "aws_s3_bucket_public_access_block",
        "data",
        {
            "block_public_acls": True,
            "block_public_policy": True,
            "ignore_public_acls": True,
            "restrict_public_buckets": True,
        },
    ),
    rc(
        "aws_security_group",
        "app",
        {
            "tags": TAGS,
            "ingress": [
                {"from_port": 443, "to_port": 443, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"], "ipv6_cidr_blocks": []},
                {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["10.0.0.0/8"], "ipv6_cidr_blocks": None},
            ],
        },
    ),
    rc("aws_db_instance", "main", {"storage_encrypted": True, "publicly_accessible": False, "tags": TAGS}),
    rc("aws_instance", "web", {"ami": "ami-1", "tags": {**TAGS, "extra": "x"}}),
    rc("aws_iam_role", "r", {"name": "r"}),  # не потребує тегів за нашими правилами
)


def test_good_plan_is_clean():
    assert evaluate_plan(GOOD) == []


def test_empty_plans():
    assert evaluate_plan({}) == []
    assert evaluate_plan({"resource_changes": []}) == []
    assert evaluate_plan({"resource_changes": None}) == []


@pytest.mark.parametrize("flag", ["block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets"])
def test_s3_public_access_block_each_flag(flag):
    after = {
        "block_public_acls": True,
        "block_public_policy": True,
        "ignore_public_acls": True,
        "restrict_public_buckets": True,
    }
    after[flag] = False
    assert evaluate_plan(plan(rc("aws_s3_bucket_public_access_block", "b", after))) == [
        ("S3_PUBLIC", "aws_s3_bucket_public_access_block.b")
    ]


def test_s3_public_access_block_missing_flag_counts_as_violation():
    after = {"block_public_acls": True, "block_public_policy": True, "ignore_public_acls": True}
    assert evaluate_plan(plan(rc("aws_s3_bucket_public_access_block", "b", after))) == [
        ("S3_PUBLIC", "aws_s3_bucket_public_access_block.b")
    ]


@pytest.mark.parametrize("acl, bad", [("public-read", True), ("public-read-write", True), ("private", False), (None, False)])
def test_s3_acl(acl, bad):
    result = evaluate_plan(plan(rc("aws_s3_bucket", "b", {"acl": acl, "tags": TAGS})))
    assert result == ([("S3_PUBLIC", "aws_s3_bucket.b")] if bad else [])


def sg(*ingress):
    return plan(rc("aws_security_group", "g", {"tags": TAGS, "ingress": list(ingress)}))


@pytest.mark.parametrize(
    "rule",
    [
        {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]},
        {"from_port": 0, "to_port": 65535, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]},
        {"from_port": 20, "to_port": 30, "protocol": "tcp", "cidr_blocks": ["10.0.0.0/8", "0.0.0.0/0"]},
        {"from_port": 0, "to_port": 0, "protocol": "-1", "cidr_blocks": ["0.0.0.0/0"]},
        {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": [], "ipv6_cidr_blocks": ["::/0"]},
    ],
)
def test_sg_ssh_open(rule):
    assert evaluate_plan(sg(rule)) == [("SG_SSH_OPEN", "aws_security_group.g")]


@pytest.mark.parametrize(
    "rule",
    [
        {"from_port": 80, "to_port": 80, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]},
        {"from_port": 23, "to_port": 1000, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]},
        {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["192.168.0.0/16"]},
        {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": None, "ipv6_cidr_blocks": None},
        {"from_port": 22, "to_port": 22, "protocol": "tcp"},
    ],
)
def test_sg_not_ssh_open(rule):
    assert evaluate_plan(sg(rule)) == []


def test_sg_one_finding_even_with_several_bad_rules():
    bad = {"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}
    assert evaluate_plan(sg(bad, copy.deepcopy(bad))) == [("SG_SSH_OPEN", "aws_security_group.g")]


def test_standalone_ingress_rule_resource():
    bad = rc(
        "aws_vpc_security_group_ingress_rule",
        "ssh",
        {"cidr_ipv4": "0.0.0.0/0", "from_port": 22, "to_port": 22, "ip_protocol": "tcp"},
    )
    ok_port = rc(
        "aws_vpc_security_group_ingress_rule",
        "https",
        {"cidr_ipv4": "0.0.0.0/0", "from_port": 443, "to_port": 443, "ip_protocol": "tcp"},
    )
    ok_cidr = rc(
        "aws_vpc_security_group_ingress_rule",
        "internal",
        {"cidr_ipv4": "10.0.0.0/8", "from_port": 22, "to_port": 22, "ip_protocol": "tcp"},
    )
    v6 = rc(
        "aws_vpc_security_group_ingress_rule",
        "v6",
        {"cidr_ipv6": "::/0", "ip_protocol": "-1"},
    )
    assert evaluate_plan(plan(bad, ok_port, ok_cidr, v6)) == [
        ("SG_SSH_OPEN", "aws_vpc_security_group_ingress_rule.ssh"),
        ("SG_SSH_OPEN", "aws_vpc_security_group_ingress_rule.v6"),
    ]


def test_rds_rules_are_independent():
    both = rc("aws_db_instance", "a", {"storage_encrypted": False, "publicly_accessible": True, "tags": TAGS})
    only_enc = rc("aws_db_instance", "b", {"publicly_accessible": False, "tags": TAGS})
    only_pub = rc("aws_db_instance", "c", {"storage_encrypted": True, "publicly_accessible": True, "tags": TAGS})
    assert evaluate_plan(plan(both, only_enc, only_pub)) == [
        ("RDS_PUBLIC", "aws_db_instance.a"),
        ("RDS_PUBLIC", "aws_db_instance.c"),
        ("RDS_UNENCRYPTED", "aws_db_instance.a"),
        ("RDS_UNENCRYPTED", "aws_db_instance.b"),
    ]


@pytest.mark.parametrize(
    "tags, bad",
    [
        ({"owner": "x"}, True),
        ({"env": "dev"}, True),
        ({}, True),
        (None, True),
        ({"owner": "x", "env": "dev"}, False),
    ],
)
def test_tags_required(tags, bad):
    result = evaluate_plan(plan(rc("aws_instance", "i", {"tags": tags})))
    assert result == ([("MISSING_TAGS", "aws_instance.i")] if bad else [])


def test_tags_missing_key_entirely():
    assert evaluate_plan(plan(rc("aws_instance", "i", {"ami": "x"}))) == [("MISSING_TAGS", "aws_instance.i")]


def test_non_taggable_types_ignored():
    assert evaluate_plan(plan(rc("aws_route53_record", "r", {}))) == []


def test_deleted_resources_are_ignored():
    gone = rc("aws_db_instance", "old", None, actions=("delete",))
    assert evaluate_plan(plan(gone)) == []


def test_replace_is_still_checked():
    bad = rc("aws_db_instance", "x", {"storage_encrypted": False, "publicly_accessible": False, "tags": TAGS},
             actions=("delete", "create"))
    assert evaluate_plan(plan(bad)) == [("RDS_UNENCRYPTED", "aws_db_instance.x")]


def test_noop_resources_are_checked_too():
    bad = rc("aws_db_instance", "x", {"storage_encrypted": False, "publicly_accessible": False, "tags": TAGS},
             actions=("no-op",))
    assert evaluate_plan(plan(bad)) == [("RDS_UNENCRYPTED", "aws_db_instance.x")]


def test_module_addresses_are_kept():
    bad = rc("aws_db_instance", "main", {"storage_encrypted": False, "tags": TAGS}, module="database")
    assert evaluate_plan(plan(bad)) == [("RDS_UNENCRYPTED", "module.database.aws_db_instance.main")]


def test_result_sorted_unique_tuples():
    changes = plan(
        rc("aws_s3_bucket", "z", {"acl": "public-read"}),
        rc("aws_db_instance", "a", {"storage_encrypted": False, "publicly_accessible": True}),
    )
    assert evaluate_plan(changes) == [
        ("MISSING_TAGS", "aws_db_instance.a"),
        ("MISSING_TAGS", "aws_s3_bucket.z"),
        ("RDS_PUBLIC", "aws_db_instance.a"),
        ("RDS_UNENCRYPTED", "aws_db_instance.a"),
        ("S3_PUBLIC", "aws_s3_bucket.z"),
    ]
