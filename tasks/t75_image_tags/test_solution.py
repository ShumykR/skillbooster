import pytest

from solution import image_tags

SHA = "0123456789abcdef0123456789abcdef01234567"
S7 = "sha-0123456"


def tags(ref, existing=(), event="push", **kw):
    return image_tags(event, ref, SHA, existing_versions=existing, **kw)


def test_pull_request_builds_but_never_pushes():
    assert image_tags("pull_request", "refs/pull/7/merge", SHA, pr_number=7) == {"push": False, "tags": ["pr-7"], "reason": "pull_request"}


def test_default_branch():
    assert tags("refs/heads/main") == {"push": True, "tags": ["main", S7], "reason": "branch"}
    assert tags("refs/heads/trunk", default_branch="trunk")["tags"] == ["trunk", S7]


@pytest.mark.parametrize("ref", ["refs/heads/feature/x", "refs/heads/release/1.x", "refs/heads/main2"])
def test_other_branches_are_not_published(ref):
    assert tags(ref) == {"push": False, "tags": [], "reason": "branch_not_published"}


@pytest.mark.parametrize("ref", ["refs/tags/foo", "refs/tags/1.2.3", "refs/tags/v1.2", "refs/tags/v1.2.3.4", "refs/tags/v01.2.x", "refs/tags/release-1"])
def test_non_semver_tags(ref):
    assert tags(ref) == {"push": False, "tags": [], "reason": "not_semver"}


def test_first_release_gets_all_floating_tags():
    assert tags("refs/tags/v1.2.3") == {"push": True, "tags": ["1.2.3", "1.2", "1", "latest", S7], "reason": "release"}


def test_new_patch_moves_floating_tags():
    assert tags("refs/tags/v1.2.4", existing=["1.2.3", "1.2.0", "1.1.9"])["tags"] == ["1.2.4", "1.2", "1", "latest", S7]


def test_new_minor_keeps_old_minor_untouched():
    assert tags("refs/tags/v1.3.0", existing=["1.2.9", "1.2.0"])["tags"] == ["1.3.0", "1.3", "1", "latest", S7]


def test_new_major():
    assert tags("refs/tags/v2.0.0", existing=["1.9.9"])["tags"] == ["2.0.0", "2.0", "2", "latest", S7]


def test_hotfix_for_old_line_does_not_move_latest_or_major():
    result = tags("refs/tags/v1.2.5", existing=["1.2.4", "1.3.0", "2.0.0"])
    assert result["tags"] == ["1.2.5", "1.2", S7], "1.2 лінія: найбільший; 1.x і latest: ні (є 1.3.0 і 2.0.0)"


def test_patch_for_older_major_keeps_its_major_tag_but_not_latest():
    result = tags("refs/tags/v1.9.1", existing=["1.9.0", "2.0.0"])
    assert result["tags"] == ["1.9.1", "1.9", "1", S7]


def test_old_patch_released_late_moves_nothing_floating():
    result = tags("refs/tags/v1.2.1", existing=["1.2.3", "1.3.0"])
    assert result["tags"] == ["1.2.1", S7]


def test_comparison_is_numeric_not_lexicographic():
    result = tags("refs/tags/v1.10.0", existing=["1.9.0", "1.2.0"])
    assert result["tags"] == ["1.10.0", "1.10", "1", "latest", S7]
    result = tags("refs/tags/v1.9.5", existing=["1.10.0"])
    assert "latest" not in result["tags"] and "1" not in result["tags"] and "1.9" in result["tags"]


def test_existing_version_is_immutable():
    assert tags("refs/tags/v1.2.3", existing=["1.2.3"]) == {"push": False, "tags": [], "reason": "version_exists"}


@pytest.mark.parametrize("ref, version", [("refs/tags/v1.3.0-rc.1", "1.3.0-rc.1"), ("refs/tags/v2.0.0-beta", "2.0.0-beta"), ("refs/tags/v1.0.0-alpha.1+x", None)])
def test_prerelease_has_no_floating_tags(ref, version):
    result = tags(ref, existing=["1.2.0"])
    if version is None:
        assert result["reason"] == "not_semver"
    else:
        assert result == {"push": True, "tags": [version, S7], "reason": "prerelease"}


def test_prerelease_of_an_already_released_version_is_still_a_prerelease():
    assert tags("refs/tags/v1.2.3-rc.2", existing=["1.2.3"])["reason"] == "prerelease"


def test_existing_versions_accept_any_iterable_and_unordered_input():
    assert tags("refs/tags/v3.0.0", existing=("2.1.0", "10.0.0", "2.10.0"))["tags"] == ["3.0.0", "3.0", "3", S7]
