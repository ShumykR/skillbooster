import pytest

from solution import scan_secrets

# Значення згенеровані з повторюваних шматків (довжину перевіряє assert нижче),
# це не справжні ключі.
AWS = "AKIA" + "AB12" * 4
GH = "ghp_" + "ab12" * 9


def test_generated_samples_have_expected_shape():
    assert len(AWS) == 20 and AWS.isalnum() and AWS == AWS.upper()
    assert len(GH) == 40 and GH[4:].isalnum()


CLEAN = {
    "app.py": (
        "import os\n"
        'DB_PASSWORD = os.environ["DB_PASSWORD"]\n'
        'API_KEY = os.getenv("API_KEY")\n'
        'password = "short"\n'
        'token = "${GITHUB_TOKEN}"\n'
        'secret = "<your-secret-here>"\n'
        'api_key = "changeme"\n'
        'api_key = "your-api-key-here"\n'
        'password = "xxxxxxxxxxxx"\n'
        'secret_key = "example-secret-value"\n'
        "cfg = {{ vault.password }}\n"
    ),
    "docs.md": "-----BEGIN PUBLIC KEY-----\nMIIB\n-----END PUBLIC KEY-----\nAKIA is a prefix\n",
}


def test_clean_files_have_no_findings():
    assert scan_secrets(CLEAN) == []


def test_empty_input():
    assert scan_secrets({}) == []
    assert scan_secrets({"a.txt": ""}) == []


def test_aws_key_with_line_number():
    files = {"conf.ini": f"[aws]\nregion = eu-west-1\nkey = {AWS}\n"}
    assert scan_secrets(files) == [("conf.ini", 3, "aws_access_key")]


def test_aws_key_must_be_a_whole_word():
    longer = "AKIA" + "AB12" * 5
    files = {"a.txt": f"x {longer} y\nsome{AWS}\n"}
    assert scan_secrets(files) == []


@pytest.mark.parametrize("prefix", ["ghp_", "gho_", "ghu_", "ghs_", "ghr_"])
def test_github_tokens(prefix):
    token = prefix + "ab12" * 9
    assert scan_secrets({"ci.sh": f"export X={token}\n"}) == [("ci.sh", 1, "github_token")]


def test_github_token_wrong_length_or_prefix():
    files = {"a": "ghp_" + "ab12" * 8 + "\n" + "ghx_" + "ab12" * 9 + "\n"}
    assert scan_secrets(files) == []


@pytest.mark.parametrize(
    "header",
    ["-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----", "-----BEGIN OPENSSH PRIVATE KEY-----",
     "-----BEGIN EC PRIVATE KEY-----"],
)
def test_private_keys(header):
    assert scan_secrets({"id_rsa": f"{header}\nMIIE...\n"}) == [("id_rsa", 1, "private_key")]


@pytest.mark.parametrize(
    "line",
    [
        'password = "S3cure-Passw0rd"',
        "password: 'S3cure-Passw0rd'",
        'DB_PASSWORD="S3cure-Passw0rd"',
        '"api_key": "abcd1234efgh"',
        "stripe-api-key = 'abcd1234efgh'",
        'client_secret: "abcd1234efgh5678"',
        'AUTH_TOKEN = "abcd1234efgh"',
        'ApiKey = "abcd1234efgh"',
        'passwd = "abcd1234"',
    ],
)
def test_hardcoded_secret(line):
    assert scan_secrets({"x": line + "\n"}) == [("x", 1, "hardcoded_secret")]


def test_hardcoded_secret_min_length_is_8():
    assert scan_secrets({"x": 'password = "abcdefg"\n'}) == []
    assert scan_secrets({"x": 'password = "abcdefgh"\n'}) == [("x", 1, "hardcoded_secret")]


def test_non_secret_names_are_ignored():
    assert scan_secrets({"x": 'username = "alexander-the-great"\nhost = "db.internal.local"\n'}) == []


def test_nosecrets_pragma():
    files = {"x": f'key = "{AWS}"  # nosecrets\npassword = "S3cure-Passw0rd"  # nosecrets: test fixture\n'}
    assert scan_secrets(files) == []


def test_one_finding_per_line_first_rule_wins():
    files = {"x": f'token = "{GH}"\n'}
    assert scan_secrets(files) == [("x", 1, "github_token")]
    files = {"x": f'token = "{AWS}"\n'}
    assert scan_secrets(files) == [("x", 1, "aws_access_key")]


def test_results_sorted_by_path_then_line():
    files = {
        "z.py": f'a = 1\nk = "{AWS}"\n',
        "a.py": f'password = "S3cure-Passw0rd"\nx = 1\ntoken = "{GH}"\n',
    }
    assert scan_secrets(files) == [
        ("a.py", 1, "hardcoded_secret"),
        ("a.py", 3, "github_token"),
        ("z.py", 2, "aws_access_key"),
    ]


def test_crlf_and_blank_lines_keep_numbering():
    files = {"x": f"\r\n\r\nkey={AWS}\r\n"}
    assert scan_secrets(files) == [("x", 3, "aws_access_key")]
