import pytest

from solution import plan_previews, preview_name

NOW = 1_800_000_000.0
H = 3600


@pytest.mark.parametrize("number, branch, expected", [
    (12, "feature/Login_Page", "pr-12-feature-login-page"),
    (7, "fix--double  space", "pr-7-fix-double-space"),
    (7, "-leading-and-trailing-", "pr-7-leading-and-trailing"),
    (3, "", "pr-3"),
    (3, "///", "pr-3"),
    (3, "Українська-гілка", "pr-3"),
    (3, "ok-Українська", "pr-3-ok"),
    (99, "release/2026.01", "pr-99-release-2026-01"),
])
def test_preview_name(number, branch, expected):
    assert preview_name(number, branch) == expected


def test_preview_name_is_truncated_without_trailing_dash():
    name = preview_name(1234, "feature/" + "very-long-branch-name-" * 5)
    assert len(name) <= 40 and name.startswith("pr-1234-feature-very-long")
    assert not name.endswith("-")
    cut = preview_name(5, "a" * 30 + "-" + "b" * 30)  # "pr-5-" + 30 a + "-" = 36, ще влазить; обрізка по 40 лишає "-bbb"
    assert len(cut) == 40 and cut == "pr-5-" + "a" * 30 + "-bbbb"
    edge = preview_name(5, "a" * 34 + "-bbb")  # обрізка по 40 символах закінчується на "-": його треба прибрати
    assert edge == "pr-5-" + "a" * 34 and len(edge) == 39


def pr(number, branch="b", updated=NOW - 100, labels=()):
    return {"number": number, "branch": branch, "updated_at": updated, "labels": list(labels)}


def env(number, branch="b", deployed=NOW - 500):
    return {"name": preview_name(number, branch), "pr": number, "last_deploy_at": deployed}


def plan(prs, envs, **kw):
    return plan_previews(prs, envs, NOW, **kw)


def brief(actions):
    return [(a["action"], a["pr"], a["reason"]) for a in actions]


def test_new_pr_gets_environment():
    result = plan([pr(1, "feature/x")], [])
    assert result == [{"action": "create", "pr": 1, "name": "pr-1-feature-x", "reason": "opened"}]


def test_up_to_date_environment_needs_no_action():
    assert plan([pr(1, updated=NOW - 1000)], [env(1, deployed=NOW - 500)]) == []


def test_new_commits_trigger_update_with_existing_name():
    existing = {"name": "pr-1-old-branch-name", "pr": 1, "last_deploy_at": NOW - 500}
    result = plan([pr(1, "renamed", updated=NOW - 10)], [existing])
    assert result == [{"action": "update", "pr": 1, "name": "pr-1-old-branch-name", "reason": "new_commits"}]


def test_closed_pr_environment_is_destroyed():
    result = plan([pr(2)], [env(1), env(2, deployed=NOW)])
    assert result == [{"action": "destroy", "pr": 1, "name": "pr-1-b", "reason": "pr_closed"}]


def test_expired_environment_is_destroyed_unless_kept():
    old = env(1, deployed=NOW - 73 * H)
    assert brief(plan([pr(1, updated=NOW - 74 * H)], [old])) == [("destroy", 1, "expired")]
    assert plan([pr(1, updated=NOW - 74 * H, labels=["keep-preview"])], [old]) == []
    just_inside = env(1, deployed=NOW - 72 * H)
    assert plan([pr(1, updated=NOW - 80 * H)], [just_inside]) == []


def test_custom_ttl():
    e = env(1, deployed=NOW - 5 * H)
    assert brief(plan([pr(1, updated=NOW - 6 * H)], [e], ttl_hours=4)) == [("destroy", 1, "expired")]


def test_expired_with_new_commits_is_destroyed_not_updated():
    old = env(1, deployed=NOW - 100 * H)
    assert brief(plan([pr(1, updated=NOW - H)], [old])) == [("destroy", 1, "expired")]


def test_no_preview_label():
    assert plan([pr(1, labels=["no-preview"])], []) == []
    assert brief(plan([pr(1, labels=["no-preview"])], [env(1)])) == [("destroy", 1, "opted_out")]


def test_no_preview_beats_keep_preview():
    assert brief(plan([pr(1, labels=["keep-preview", "no-preview"])], [env(1)])) == [("destroy", 1, "opted_out")]


def test_quota_output_order_is_by_pr_number_within_action():
    prs = [pr(1, updated=NOW - 500), pr(2, updated=NOW - 100), pr(3, updated=NOW - 300), pr(4, updated=NOW - 50)]
    assert brief(plan(prs, [], max_envs=2)) == [("create", 2, "opened"), ("create", 4, "opened"), ("skip", 1, "quota"), ("skip", 3, "quota")]


def test_quota_tie_goes_to_lower_pr_number():
    prs = [pr(5, updated=NOW - 10), pr(3, updated=NOW - 10)]
    assert brief(plan(prs, [], max_envs=1)) == [("create", 3, "opened"), ("skip", 5, "quota")]


def test_destroyed_environments_free_slots_in_the_same_plan():
    envs = [env(1), env(2), env(3, deployed=NOW - 100 * H)]
    prs = [pr(2, updated=NOW - 1000), pr(3, updated=NOW - 101 * H), pr(4, updated=NOW - 5)]
    result = plan(prs, envs, max_envs=3)
    assert brief(result) == [("destroy", 1, "pr_closed"), ("destroy", 3, "expired"), ("create", 4, "opened")]


def test_updated_environments_still_occupy_slots():
    envs = [env(1, deployed=NOW - 500), env(2, deployed=NOW - 500)]
    prs = [pr(1, updated=NOW - 10), pr(2, updated=NOW - 20), pr(3)]
    assert brief(plan(prs, envs, max_envs=2)) == [("update", 1, "new_commits"), ("update", 2, "new_commits"), ("skip", 3, "quota")]


def test_full_quota_without_changes_creates_nothing_new_for_existing_prs():
    envs = [env(i) for i in range(1, 4)]
    prs = [pr(i, updated=NOW - 1000) for i in range(1, 4)]
    assert plan(prs, envs, max_envs=3) == []


def test_zero_quota_skips_everything_new():
    assert brief(plan([pr(1), pr(2)], [], max_envs=0)) == [("skip", 1, "quota"), ("skip", 2, "quota")]


def test_inputs_are_not_mutated():
    prs, envs = [pr(1, labels=["x"])], [env(2)]
    import copy
    before = copy.deepcopy((prs, envs))
    plan(prs, envs)
    assert (prs, envs) == before
