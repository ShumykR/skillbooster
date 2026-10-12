import hashlib
import hmac
import inspect

import pytest

import solution
from solution import Expired, FileNotFound, FileService, SignatureError, sign_download, verify_download

SECRET = "k" * 32
ALICE = {"id": 1, "is_admin": False}
BOB = {"id": 2, "is_admin": False}
CAROL = {"id": 3, "is_admin": False}
ADMIN = {"id": 99, "is_admin": True}


class Clock:
    def __init__(self):
        self.now = 1_700_000_000.0

    def __call__(self):
        return self.now


def make_service():
    clock = Clock()
    files = {
        "f1": {"owner_id": 1, "shared_with": {2}, "path": "/data/alice/report.pdf"},
        "f2": {"owner_id": 1, "shared_with": set(), "path": "/data/alice/secret.txt"},
        "other-1": {"owner_id": 3, "shared_with": set(), "path": "/data/carol/x.bin"},
        "../../etc/passwd": {"owner_id": 99, "shared_with": set(), "path": "/etc/passwd"},
        "f 1": {"owner_id": 99, "shared_with": set(), "path": "/data/space"},
    }
    return FileService(files, SECRET, clock, ttl=300), clock, files


# ---------- підписане посилання -----------------------------------------------


def test_sign_format_and_hmac():
    params = sign_download("f1", 7, 1_700_000_300, SECRET)
    assert set(params) == {"file", "uid", "exp", "sig"}
    assert (params["file"], params["uid"], params["exp"]) == ("f1", "7", "1700000300")
    expected = hmac.new(SECRET.encode(), b"f1\n7\n1700000300", hashlib.sha256).hexdigest()
    assert params["sig"] == expected


def test_verify_roundtrip():
    params = sign_download("f1", 7, 1_700_000_300, SECRET)
    assert verify_download(params, SECRET, now=1_700_000_000, current_user_id=7) == "f1"
    assert verify_download(params, SECRET, now=1_700_000_300, current_user_id=7) == "f1", "рівно в момент exp ще діє"


@pytest.mark.parametrize("field, value", [("file", "f2"), ("uid", "8"), ("exp", "1700009999"), ("sig", "0" * 64)])
def test_any_tampering_breaks_signature(field, value):
    params = sign_download("f1", 7, 1_700_000_300, SECRET)
    params[field] = value
    with pytest.raises(SignatureError) as e:
        verify_download(params, SECRET, now=1_700_000_000, current_user_id=int(params["uid"]) if params["uid"].isdigit() else 7)
    assert not isinstance(e.value, Expired)


def test_wrong_secret_and_missing_or_garbage_params():
    params = sign_download("f1", 7, 1_700_000_300, SECRET)
    with pytest.raises(SignatureError):
        verify_download(params, "other-secret", now=1_700_000_000, current_user_id=7)
    for field in params:
        broken = {k: v for k, v in params.items() if k != field}
        with pytest.raises(SignatureError):
            verify_download(broken, SECRET, now=1_700_000_000, current_user_id=7)
    with pytest.raises(SignatureError):
        verify_download({**params, "exp": "tomorrow"}, SECRET, now=1_700_000_000, current_user_id=7)


def test_expired_link():
    params = sign_download("f1", 7, 1_700_000_300, SECRET)
    with pytest.raises(Expired):
        verify_download(params, SECRET, now=1_700_000_301, current_user_id=7)


def test_link_is_bound_to_the_user_it_was_issued_to():
    params = sign_download("f1", 7, 1_700_000_300, SECRET)
    with pytest.raises(SignatureError):
        verify_download(params, SECRET, now=1_700_000_000, current_user_id=8)


def test_signature_is_compared_in_constant_time():
    assert "compare_digest" in inspect.getsource(solution.verify_download)


# ---------- сервіс: IDOR ------------------------------------------------------


def test_owner_shared_user_and_admin_get_links():
    service, clock, _ = make_service()
    for user in (ALICE, BOB, ADMIN):
        params = service.download_link(user, "f1")
        assert params["uid"] == str(user["id"])
        assert params["exp"] == str(int(clock.now) + 300)
        assert service.open(params, user) == "/data/alice/report.pdf"


def test_stranger_cannot_get_link_and_error_is_same_as_for_missing_file():
    service, _, _ = make_service()
    with pytest.raises(FileNotFound) as forbidden:
        service.download_link(CAROL, "f2")
    with pytest.raises(FileNotFound) as missing:
        service.download_link(CAROL, "nope")
    assert str(forbidden.value) == str(missing.value) == "file not found"


def test_sharing_is_one_way():
    service, _, _ = make_service()
    service.download_link(BOB, "f1")
    with pytest.raises(FileNotFound):
        service.download_link(BOB, "f2")


def test_leaked_link_is_useless_to_another_user():
    service, _, _ = make_service()
    params = service.download_link(ALICE, "f2")
    with pytest.raises(SignatureError):
        service.open(params, BOB)


def test_access_revoked_after_link_was_issued():
    service, _, files = make_service()
    params = service.download_link(BOB, "f1")
    files["f1"]["shared_with"].discard(2)
    with pytest.raises(FileNotFound):
        service.open(params, BOB)


def test_expired_link_is_rejected_by_service():
    service, clock, _ = make_service()
    params = service.download_link(ALICE, "f1")
    clock.now += 301
    with pytest.raises(Expired):
        service.open(params, ALICE)


def test_forged_link_for_someone_elses_file_is_rejected():
    service, _, _ = make_service()
    own = service.download_link(CAROL, "other-1")
    forged = {**own, "file": "f2"}
    with pytest.raises(SignatureError):
        service.open(forged, CAROL)


def test_link_signed_with_valid_secret_still_needs_current_permission():
    # навіть коли хтось (наприклад, інший код із секретом) підписав посилання, право перевіряється заново
    service, clock, _ = make_service()
    params = sign_download("f2", 3, int(clock.now) + 100, SECRET)
    with pytest.raises(FileNotFound):
        service.open(params, CAROL)


@pytest.mark.parametrize("file_id", ["../../etc/passwd", "f1/../f2", "", "a" * 65, "f 1", "f1\n", "/data/alice/secret.txt"])
def test_odd_file_ids_are_not_found(file_id):
    service, _, _ = make_service()
    with pytest.raises(FileNotFound):
        service.download_link(ADMIN, file_id)
