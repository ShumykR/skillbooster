import pytest

from solution import affected_services, path_matches


@pytest.mark.parametrize("pattern, path, expected", [
    ("services/api/main.py", "services/api/main.py", True),
    ("services/api/main.py", "services/api/other.py", False),
    ("services/*", "services/api", True),
    ("services/*", "services/api/main.py", False),
    ("services/**", "services/api/main.py", True),
    ("services/**", "services/api", True),
    ("services/**", "services", False),
    ("services/**", "other/api", False),
    ("**/*.md", "README.md", True),
    ("**/*.md", "docs/a/b/c.md", True),
    ("**/*.md", "docs/a/b/c.txt", False),
    ("docs/**/*.md", "docs/a.md", True),
    ("docs/**/*.md", "docs/x/y/a.md", True),
    ("docs/**/*.md", "src/docs/a.md", False),
    ("*.lock", "uv.lock", True),
    ("*.lock", "sub/uv.lock", False),
    ("**/*.lock", "sub/uv.lock", True),
    ("libs/core/**", "libs/core-extra/x.py", False),
    ("src/?.py", "src/a.py", True),
    ("src/?.py", "src/ab.py", False),
    ("a/**/b", "a/b", True),
    ("a/**/b", "a/x/y/b", True),
    ("a/**/b", "a/x/y/c", False),
    ("Dockerfile", "dockerfile", False),
    ("a.b", "aXb", False),
    ("service(1)/*", "service(1)/x", True),
])
def test_path_matches(pattern, path, expected):
    assert path_matches(pattern, path) is expected


SERVICES = {
    "api": {"paths": ["services/api/**"], "depends_on": ["core", "db"]},
    "worker": {"paths": ["services/worker/**"], "depends_on": ["core"]},
    "web": {"paths": ["services/web/**"], "depends_on": []},
    "admin": {"paths": ["services/admin/**"], "depends_on": ["api"]},
    "core": {"paths": ["libs/core/**"], "depends_on": ["utils"], "deploy": False},
    "utils": {"paths": ["libs/utils/**"], "depends_on": [], "deploy": False},
    "db": {"paths": ["libs/db/**"], "depends_on": ["utils"], "deploy": False},
}
GLOBAL = ["uv.lock", ".github/workflows/**"]
IGNORE = ["**/*.md", "docs/**"]


def run(changed, **kw):
    kw.setdefault("global_paths", GLOBAL)
    kw.setdefault("ignore", IGNORE)
    return affected_services(changed, SERVICES, **kw)


def test_nothing_changed():
    assert run([]) == []


def test_single_service_change():
    assert run(["services/web/app.py"]) == ["web"]


def test_leaf_service_with_no_dependents():
    assert run(["services/worker/tasks.py"]) == ["worker"]


def test_dependents_are_included_transitively():
    assert run(["services/api/routes.py"]) == ["admin", "api"]


def test_library_change_triggers_all_dependents_but_not_the_library():
    assert run(["libs/core/models.py"]) == ["admin", "api", "worker"]


def test_deep_library_change_goes_through_two_levels():
    assert run(["libs/utils/log.py"]) == ["admin", "api", "worker"]


def test_other_library_only_hits_its_chain():
    assert run(["libs/db/pool.py"]) == ["admin", "api"]


def test_multiple_changes_are_merged_and_sorted_without_duplicates():
    assert run(["services/web/a.py", "libs/db/x.py", "libs/core/y.py", "services/web/b.py"]) == ["admin", "api", "web", "worker"]


def test_ignored_files_do_not_trigger_anything():
    assert run(["README.md", "docs/guide/intro.rst", "services/api/NOTES.md"]) == []


def test_ignored_files_do_not_hide_real_changes():
    assert run(["docs/x.md", "services/web/app.py"]) == ["web"]


def test_global_path_triggers_all_deployables():
    assert run(["uv.lock"]) == ["admin", "api", "web", "worker"]
    assert run([".github/workflows/ci.yml", "services/web/a.py"]) == ["admin", "api", "web", "worker"]


def test_global_path_that_is_ignored_does_not_trigger():
    assert run(["uv.lock"], ignore=["uv.lock"]) == []


def test_file_matching_no_service_is_ignored():
    assert run(["scripts/release.sh", "random.txt"]) == []


def test_service_paths_can_have_several_patterns():
    services = {"a": {"paths": ["a/**", "shared/a-*.yml"], "depends_on": []}}
    assert affected_services(["shared/a-conf.yml"], services) == ["a"]
    assert affected_services(["shared/b-conf.yml"], services) == []


def test_deploy_defaults_to_true():
    services = {"a": {"paths": ["a/**"], "depends_on": []}}
    assert affected_services(["a/x"], services) == ["a"]


def test_unknown_dependency_is_an_error_even_without_changes():
    services = {"a": {"paths": ["a/**"], "depends_on": ["ghost"]}}
    with pytest.raises(ValueError):
        affected_services([], services)


def test_dependency_cycle_is_an_error():
    services = {"a": {"paths": ["a/**"], "depends_on": ["b"]}, "b": {"paths": ["b/**"], "depends_on": ["c"]}, "c": {"paths": ["c/**"], "depends_on": ["a"]}}
    with pytest.raises(ValueError):
        affected_services(["a/x"], services)
    with pytest.raises(ValueError):
        affected_services([], services)


def test_diamond_dependencies_are_not_a_cycle():
    services = {
        "top": {"paths": ["top/**"], "depends_on": ["l", "r"]},
        "l": {"paths": ["l/**"], "depends_on": ["base"], "deploy": False},
        "r": {"paths": ["r/**"], "depends_on": ["base"], "deploy": False},
        "base": {"paths": ["base/**"], "depends_on": [], "deploy": False},
    }
    assert affected_services(["base/x"], services) == ["top"]
