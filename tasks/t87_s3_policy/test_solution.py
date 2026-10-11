import pytest

from solution import analyze_bucket_policy

TLS_DENY = {
    "Sid": "DenyInsecureTransport",
    "Effect": "Deny",
    "Principal": "*",
    "Action": "s3:*",
    "Resource": ["arn:aws:s3:::data", "arn:aws:s3:::data/*"],
    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
}

APP_READ = {
    "Sid": "AppRead",
    "Effect": "Allow",
    "Principal": {"AWS": "arn:aws:iam::123456789012:role/app"},
    "Action": ["s3:GetObject", "s3:ListBucket"],
    "Resource": "arn:aws:s3:::data/*",
}


def policy(*statements):
    return {"Version": "2012-10-17", "Statement": list(statements)}


def test_good_policy_is_clean():
    assert analyze_bucket_policy(policy(TLS_DENY, APP_READ)) == []


def test_empty_policies():
    assert analyze_bucket_policy({"Statement": []}) == ["missing_tls_deny"]
    assert analyze_bucket_policy({}) == ["missing_tls_deny"]


@pytest.mark.parametrize("principal", ["*", {"AWS": "*"}, {"AWS": ["*"]}, {"AWS": ["arn:aws:iam::1:root", "*"]}])
def test_public_principals(principal):
    st = {"Sid": "Open", "Effect": "Allow", "Principal": principal, "Action": "s3:GetObject", "Resource": "arn:aws:s3:::data/*"}
    assert analyze_bucket_policy(policy(TLS_DENY, st)) == ["public_access:Open"]


@pytest.mark.parametrize(
    "principal",
    [{"AWS": "arn:aws:iam::123456789012:root"}, {"Service": "cloudfront.amazonaws.com"}, {"AWS": ["arn:aws:iam::1:role/a"]}],
)
def test_non_public_principals(principal):
    st = {"Sid": "Ok", "Effect": "Allow", "Principal": principal, "Action": "s3:GetObject", "Resource": "x"}
    assert analyze_bucket_policy(policy(TLS_DENY, st)) == []


@pytest.mark.parametrize(
    "condition",
    [
        {"StringEquals": {"aws:PrincipalOrgID": "o-abc123"}},
        {"StringEquals": {"aws:SourceVpce": "vpce-0abc"}},
        {"StringEquals": {"AWS:SOURCEVPC": "vpc-1"}},
        {"ArnLike": {"aws:PrincipalArn": "arn:aws:iam::1:role/*"}},
        {"StringEquals": {"aws:SourceAccount": "123456789012"}},
        {"ArnLike": {"aws:SourceArn": "arn:aws:cloudfront::1:distribution/E1"}},
        {"IpAddress": {"aws:SourceIp": "10.0.0.0/8"}, "StringEquals": {"aws:PrincipalAccount": "1"}},
    ],
)
def test_restrictive_condition_makes_public_principal_ok(condition):
    st = {"Sid": "Scoped", "Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "x", "Condition": condition}
    assert analyze_bucket_policy(policy(TLS_DENY, st)) == []


@pytest.mark.parametrize(
    "condition",
    [
        {"StringEquals": {"aws:UserAgent": "my-app"}},
        {"IpAddress": {"aws:SourceIp": "0.0.0.0/0"}},
        {"Bool": {"aws:SecureTransport": "true"}},
        {},
    ],
)
def test_weak_or_empty_condition_does_not_help(condition):
    st = {"Sid": "Weak", "Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "x", "Condition": condition}
    assert analyze_bucket_policy(policy(TLS_DENY, st)) == ["public_access:Weak"]


def test_deny_statements_never_count_as_public_access_or_wildcard():
    st = {"Sid": "BlockAll", "Effect": "Deny", "Principal": "*", "Action": "*", "Resource": "x"}
    assert analyze_bucket_policy(policy(TLS_DENY, st)) == []


@pytest.mark.parametrize("action, bad", [("*", True), ("s3:*", True), (["s3:GetObject", "s3:*"], True),
                                          ("s3:Get*", False), ("s3:GetObject", False), (["s3:Put*", "s3:Delete*"], False)])
def test_wildcard_action(action, bad):
    st = {"Sid": "W", "Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::1:role/r"}, "Action": action, "Resource": "x"}
    assert analyze_bucket_policy(policy(TLS_DENY, st)) == (["wildcard_action:W"] if bad else [])


def test_both_rules_on_one_statement():
    st = {"Sid": "Everything", "Effect": "Allow", "Principal": "*", "Action": "s3:*", "Resource": "*"}
    assert analyze_bucket_policy(policy(TLS_DENY, st)) == ["public_access:Everything", "wildcard_action:Everything"]


def test_statements_without_sid_use_their_index():
    open_stmt = {"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "x"}
    wild = {"Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::1:root"}, "Action": "*", "Resource": "x"}
    assert analyze_bucket_policy(policy(TLS_DENY, open_stmt, wild)) == ["public_access:#1", "wildcard_action:#2"]


def test_single_statement_as_dict_is_accepted():
    pol = {"Version": "2012-10-17", "Statement": TLS_DENY}
    assert analyze_bucket_policy(pol) == []


# --- перевірка TLS ---------------------------------------------------------------------------

def tls(**changes):
    st = {**TLS_DENY, **changes}
    return st


@pytest.mark.parametrize(
    "stmt",
    [
        tls(),
        tls(Condition={"Bool": {"aws:SecureTransport": "FALSE"}}),
        tls(Condition={"Bool": {"aws:SecureTransport": False}}),
        tls(Condition={"Bool": {"AWS:securetransport": "false"}}),
        tls(Action="*"),
        tls(Action=["s3:GetObject", "s3:*"]),
        tls(Principal={"AWS": "*"}),
    ],
)
def test_valid_tls_deny_variants(stmt):
    assert analyze_bucket_policy(policy(stmt)) == []


@pytest.mark.parametrize(
    "stmt",
    [
        tls(Effect="Allow"),                                              # не Deny
        tls(Condition={"Bool": {"aws:SecureTransport": "true"}}),         # інверсія
        tls(Condition={"StringEquals": {"aws:SecureTransport": "false"}}),  # не Bool
        tls(Action="s3:GetObject"),                                       # не всі дії
        tls(Principal={"AWS": "arn:aws:iam::1:root"}),                    # не всіх
        {k: v for k, v in TLS_DENY.items() if k != "Condition"},          # без умови
    ],
)
def test_invalid_tls_deny_variants(stmt):
    assert "missing_tls_deny" in analyze_bucket_policy(policy(stmt))


def test_tls_deny_may_be_any_statement_in_the_list():
    assert analyze_bucket_policy(policy(APP_READ, APP_READ, TLS_DENY)) == []


def test_results_sorted_unique():
    a = {"Sid": "Z", "Effect": "Allow", "Principal": "*", "Action": "*", "Resource": "x"}
    b = {"Sid": "A", "Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "x"}
    assert analyze_bucket_policy(policy(a, b)) == [
        "missing_tls_deny", "public_access:A", "public_access:Z", "wildcard_action:Z",
    ]
