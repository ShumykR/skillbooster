import os
from pathlib import Path

import pytest

from solution import PathTraversal, safe_join


@pytest.fixture
def env(tmp_path):
    """tmp/uploads (база), tmp/uploads-evil (сусід з тим самим префіксом), tmp/secret.txt (поза базою)."""
    base = tmp_path / "uploads"
    (base / "sub").mkdir(parents=True)
    (base / "a.txt").write_text("a")
    (base / "sub" / "b.txt").write_text("b")
    evil = tmp_path / "uploads-evil"
    evil.mkdir()
    (evil / "x.txt").write_text("x")
    (tmp_path / "secret.txt").write_text("top secret")
    return base


def real(p):
    return Path(os.path.realpath(p))


@pytest.mark.parametrize("user_path", ["a.txt", "sub/b.txt", "sub/../a.txt", "./a.txt", "sub//b.txt", "sub/./b.txt"])
def test_legit_paths_are_inside_base(env, user_path):
    result = safe_join(env, user_path)
    assert isinstance(result, Path)
    assert result == real(env / user_path)
    assert result.is_relative_to(real(env))


def test_nonexistent_target_is_allowed(env):
    result = safe_join(env, "new/dir/file.txt")
    assert result == real(env) / "new" / "dir" / "file.txt"
    assert not result.exists()


def test_base_may_be_str_or_path(env):
    assert safe_join(str(env), "a.txt") == safe_join(env, "a.txt")


def test_dotdot_that_stays_inside_is_fine(env):
    assert safe_join(env, "sub/../sub/b.txt") == real(env / "sub" / "b.txt")


@pytest.mark.parametrize(
    "user_path",
    [
        "../secret.txt",
        "../../etc/passwd",
        "sub/../../secret.txt",
        "sub/../../../../../../etc/passwd",
        "a/b/c/../../../../secret.txt",
        "./../secret.txt",
    ],
)
def test_relative_traversal_is_rejected(env, user_path):
    with pytest.raises(PathTraversal):
        safe_join(env, user_path)


def test_sibling_directory_with_same_prefix_is_rejected(env):
    with pytest.raises(PathTraversal):
        safe_join(env, "../uploads-evil/x.txt")


@pytest.mark.parametrize("user_path", ["/etc/passwd", "/", "//server/share", "/a.txt"])
def test_absolute_paths_are_rejected(env, user_path):
    with pytest.raises(PathTraversal):
        safe_join(env, user_path)


@pytest.mark.parametrize("user_path", ["C:\\Windows\\win.ini", "C:/Windows/win.ini", "c:foo", "D:"])
def test_drive_letters_are_rejected(env, user_path):
    with pytest.raises(PathTraversal):
        safe_join(env, user_path)


@pytest.mark.parametrize("user_path", ["..\\secret.txt", "sub\\b.txt", "a\\..\\..\\secret.txt", "\\\\server\\share"])
def test_backslashes_are_rejected_on_every_os(env, user_path):
    with pytest.raises(PathTraversal):
        safe_join(env, user_path)


@pytest.mark.parametrize("user_path", ["a.txt\x00.png", "\x00", "sub/\x00/../../secret.txt"])
def test_null_byte_is_rejected(env, user_path):
    with pytest.raises(PathTraversal):
        safe_join(env, user_path)


@pytest.mark.parametrize("user_path", ["", ".", "./", "sub/..", "sub/../.", "a/b/../.."])
def test_base_itself_or_empty_is_rejected(env, user_path):
    with pytest.raises(PathTraversal):
        safe_join(env, user_path)


@pytest.mark.parametrize("bad", [None, b"a.txt", 5, ["a.txt"]])
def test_non_string_is_type_error(env, bad):
    with pytest.raises(TypeError):
        safe_join(env, bad)


def test_names_that_merely_look_suspicious_are_ordinary_names(env):
    # без імен з кінцевими крапками («....», «a..»): Windows відкидає їх, поведінка залежить від ОС
    for name in ["...hidden", "a..b", "%2e%2e", "%2e%2e%2fsecret.txt", "..a"]:
        result = safe_join(env, name)
        assert result.parent == real(env), name


def test_error_is_a_value_error(env):
    with pytest.raises(ValueError):
        safe_join(env, "../secret.txt")


def _symlink(target, link):
    try:
        os.symlink(target, link, target_is_directory=Path(target).is_dir())
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlink недоступний у цій ОС або без прав")


def test_symlink_pointing_outside_base_is_rejected(env, tmp_path):
    _symlink(tmp_path, env / "link-out")
    with pytest.raises(PathTraversal):
        safe_join(env, "link-out/secret.txt")
    with pytest.raises(PathTraversal):
        safe_join(env, "link-out")


def test_symlink_to_file_outside_base_is_rejected(env, tmp_path):
    _symlink(tmp_path / "secret.txt", env / "innocent.txt")
    with pytest.raises(PathTraversal):
        safe_join(env, "innocent.txt")


def test_symlink_staying_inside_base_is_allowed_and_resolved(env):
    _symlink(env / "sub", env / "alias")
    result = safe_join(env, "alias/b.txt")
    assert result == real(env / "sub" / "b.txt")


def test_symlink_to_sibling_with_same_prefix_is_rejected(env, tmp_path):
    _symlink(tmp_path / "uploads-evil", env / "evil-link")
    with pytest.raises(PathTraversal):
        safe_join(env, "evil-link/x.txt")


def test_result_can_be_opened_only_if_inside(env):
    p = safe_join(env, "sub/b.txt")
    assert p.read_text() == "b"
