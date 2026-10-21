import textwrap

import pytest

from solution import analyze

CFG = {"package": "shop", "shared": ["shared"], "forbidden": []}


def make(tmp_path, files):
    """files: {"shop/orders/api.py": "source", ...}; усі директорії-пакети отримують `__init__.py`."""
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src).lstrip("\n"), encoding="utf-8")
    for d in {p.parent for p in tmp_path.rglob("*.py")}:
        init = d / "__init__.py"
        if d != tmp_path and not init.exists():
            init.write_text("", encoding="utf-8")
    return tmp_path


def rules(report):
    return [(v["rule"], v["file"], v["line"], v["chain"]) for v in report["violations"]]


BASE = {
    "shop/main.py": """
        from shop.orders import api as orders_api
        from shop.billing import api as billing_api
        from shop.orders.infra import db
    """,
    "shop/orders/api.py": "from shop.orders.domain import order\nfrom shop.shared import money\n",
    "shop/orders/domain/order.py": "x = 1\n",
    "shop/orders/infra/db.py": "import sqlalchemy\n",
    "shop/billing/api.py": "from shop.shared import money\n",
    "shop/billing/domain/invoice.py": "y = 2\n",
    "shop/shared/money.py": "z = 3\n",
}


# --- чистий проєкт, метрики -------------------------------------------------------------------

def test_clean_project_has_no_findings(tmp_path):
    report = analyze(make(tmp_path, BASE), CFG)
    assert report["violations"] == []
    assert report["cycles"] == []


def test_metrics(tmp_path):
    files = {**BASE, "shop/orders/api.py": """
        from shop.billing import api
        from shop.billing.api import charge
        from shop.shared import money
        import shop.shared.money
    """}
    report = analyze(make(tmp_path, files), CFG)
    m = report["metrics"]
    assert set(m) == {"orders", "billing", "shared"}
    assert m["orders"] == {"ca": 0, "ce": 2, "instability": 1.0}
    assert m["billing"] == {"ca": 1, "ce": 1, "instability": 0.5}
    assert m["shared"] == {"ca": 2, "ce": 0, "instability": 0.0}


def test_instability_is_rounded_and_isolated_module_is_zero(tmp_path):
    files = {
        "shop/a/api.py": "from shop.c import api\n",
        "shop/b/api.py": "from shop.c import api\n",
        "shop/c/api.py": "from shop.d import api\n",
        "shop/d/api.py": "x = 1\n",
        "shop/lonely/api.py": "x = 1\n",
    }
    m = analyze(make(tmp_path, files), CFG)["metrics"]
    assert m["c"] == {"ca": 2, "ce": 1, "instability": 0.3333}
    assert m["lonely"] == {"ca": 0, "ce": 0, "instability": 0.0}


def test_composition_root_and_non_python_dirs_are_not_modules(tmp_path):
    files = {**BASE, "shop/helpers.py": "from shop.orders.domain import order\n"}
    make(tmp_path, files)
    (tmp_path / "shop" / "static").mkdir()
    (tmp_path / "shop" / "static" / "logo.txt").write_text("x")
    report = analyze(tmp_path, CFG)
    assert set(report["metrics"]) == {"orders", "billing", "shared"}
    assert report["violations"] == []


# --- private-import ---------------------------------------------------------------------------

def test_import_of_foreign_internals_is_flagged(tmp_path):
    files = {**BASE, "shop/orders/app/svc.py": """
        from shop.billing.domain.invoice import Invoice
        from shop.billing import api
        from shop.billing.api import charge
        import shop.billing.domain.invoice
    """}
    report = analyze(make(tmp_path, files), CFG)
    assert rules(report) == [
        ("private-import", "shop/orders/app/svc.py", 1, ["shop.orders.app.svc", "shop.billing.domain.invoice"]),
        ("private-import", "shop/orders/app/svc.py", 4, ["shop.orders.app.svc", "shop.billing.domain.invoice"]),
    ]


def test_package_root_import_is_not_the_public_api(tmp_path):
    files = {**BASE, "shop/orders/app/svc.py": "from shop.billing import Invoice\nfrom shop.billing import domain\n"}
    report = analyze(make(tmp_path, files), CFG)
    assert rules(report) == [
        ("private-import", "shop/orders/app/svc.py", 1, ["shop.orders.app.svc", "shop.billing"]),
        ("private-import", "shop/orders/app/svc.py", 2, ["shop.orders.app.svc", "shop.billing.domain"]),
    ]


def test_api_prefix_trap_apiary_is_not_api(tmp_path):
    files = {k: v for k, v in BASE.items() if k != "shop/billing/api.py"}
    files.update({"shop/billing/api/v1.py": "x = 1\n", "shop/billing/apiary.py": "x = 1\n",
                  "shop/orders/app/svc.py": "from shop.billing import apiary\nfrom shop.billing.api import v1\n"})
    report = analyze(make(tmp_path, files), CFG)
    assert rules(report) == [("private-import", "shop/orders/app/svc.py", 1, ["shop.orders.app.svc", "shop.billing.apiary"])]


def test_same_module_shared_and_composition_root_are_allowed(tmp_path):
    files = {**BASE,
             "shop/orders/app/svc.py": "from shop.orders.infra import db\nfrom shop.orders.domain.order import x\nfrom shop.shared.money import z\n",
             "shop/main.py": "from shop.orders.infra import db\nfrom shop.billing.domain import invoice\n"}
    assert analyze(make(tmp_path, files), CFG)["violations"] == []


def test_shared_modules_come_from_config(tmp_path):
    files = {"shop/orders/app/svc.py": "from shop.shared.money import z\n", "shop/shared/money.py": "z = 3\n"}
    report = analyze(make(tmp_path, files), {"package": "shop", "shared": []})
    assert rules(report) == [("private-import", "shop/orders/app/svc.py", 1, ["shop.orders.app.svc", "shop.shared.money"])]


def test_imports_inside_functions_and_type_checking_count(tmp_path):
    files = {**BASE, "shop/orders/app/svc.py": """
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            from shop.billing.domain.invoice import Invoice

        def f():
            import shop.billing.domain.invoice as inv
            return inv
    """}
    report = analyze(make(tmp_path, files), CFG)
    assert [(v["line"]) for v in report["violations"]] == [3, 6]


def test_relative_imports_are_resolved(tmp_path):
    files = {**BASE, "shop/orders/app/svc.py": """
        from ..domain import order
        from . import helper
        from ...billing.domain import invoice
        from ...billing import api
        from .. import infra
    """, "shop/orders/app/helper.py": "x = 1\n"}
    report = analyze(make(tmp_path, files), CFG)
    assert rules(report) == [
        ("private-import", "shop/orders/app/svc.py", 3, ["shop.orders.app.svc", "shop.billing.domain.invoice"]),
    ]


def test_relative_import_in_init_uses_its_own_directory(tmp_path):
    files = {"shop/orders/app/__init__.py": "from . import helper\nfrom .helper import x\n",
             "shop/orders/app/helper.py": "x = 1\n", "shop/orders/api.py": "x = 1\n"}
    report = analyze(make(tmp_path, files), CFG)
    assert report["violations"] == []
    assert report["metrics"]["orders"]["ce"] == 0


def test_relative_import_above_the_package_is_value_error(tmp_path):
    files = {**BASE, "shop/main.py": "from .. import x\n"}
    with pytest.raises(ValueError):
        analyze(make(tmp_path, files), CFG)


# --- forbidden-import --------------------------------------------------------------------------

DOMAIN_RULES = {"package": "shop", "shared": ["shared"],
                "forbidden": [("shop.orders.domain", "shop.orders.infra"), ("shop.orders.domain", "sqlalchemy")]}


def test_direct_forbidden_import(tmp_path):
    files = {**BASE, "shop/orders/domain/order.py": "x = 1\nfrom shop.orders.infra import db\n"}
    report = analyze(make(tmp_path, files), DOMAIN_RULES)
    assert rules(report) == [
        ("forbidden-import", "shop/orders/domain/order.py", 2,
         ["shop.orders.domain.order", "shop.orders.infra.db"]),
        ("forbidden-import", "shop/orders/domain/order.py", 2,
         ["shop.orders.domain.order", "shop.orders.infra.db", "sqlalchemy"]),
    ]


def test_transitive_chain_and_each_source_module_reported(tmp_path):
    files = {**BASE,
             "shop/orders/domain/order.py": "from shop.orders.domain import helpers\n",
             "shop/orders/domain/helpers.py": "import json\nfrom shop.orders.domain import deep\n",
             "shop/orders/domain/deep.py": "from sqlalchemy.orm import Session\n"}
    report = analyze(make(tmp_path, files), DOMAIN_RULES)
    assert rules(report) == [
        ("forbidden-import", "shop/orders/domain/deep.py", 1, ["shop.orders.domain.deep", "sqlalchemy.orm"]),
        ("forbidden-import", "shop/orders/domain/helpers.py", 2,
         ["shop.orders.domain.helpers", "shop.orders.domain.deep", "sqlalchemy.orm"]),
        ("forbidden-import", "shop/orders/domain/order.py", 1,
         ["shop.orders.domain.order", "shop.orders.domain.helpers", "shop.orders.domain.deep", "sqlalchemy.orm"]),
    ]


def test_shortest_chain_wins(tmp_path):
    files = {**BASE,
             "shop/orders/domain/order.py": "from shop.orders.domain import slow\nfrom shop.orders.infra import db\n",
             "shop/orders/domain/slow.py": "from shop.orders.infra import db\n"}
    report = analyze(make(tmp_path, files), {"package": "shop", "shared": ["shared"],
                                              "forbidden": [("shop.orders.domain.order", "shop.orders.infra")]})
    assert rules(report) == [("forbidden-import", "shop/orders/domain/order.py", 2,
                              ["shop.orders.domain.order", "shop.orders.infra.db"])]


def test_line_is_the_smallest_among_imports_with_the_same_first_hop(tmp_path):
    files = {**BASE, "shop/orders/domain/order.py": "x = 1\nimport shop.orders.infra.db\nfrom shop.orders.infra import db\n"}
    report = analyze(make(tmp_path, files), {"package": "shop", "shared": ["shared"],
                                              "forbidden": [("shop.orders.domain", "shop.orders.infra")]})
    assert [(v["line"]) for v in report["violations"]] == [2]


def test_prefix_matching_is_by_dotted_segments(tmp_path):
    files = {**BASE, "shop/orders/domain_extra.py": "from shop.orders.infra import db\n",
             "shop/orders/infrastructure.py": "x = 1\n",
             "shop/orders/domain/order.py": "from shop.orders import infrastructure\n"}
    report = analyze(make(tmp_path, files), DOMAIN_RULES)
    assert report["violations"] == []


def test_source_matching_the_target_prefix_is_not_a_violation(tmp_path):
    files = {**BASE, "shop/orders/infra/db.py": "import sqlalchemy\nfrom shop.orders.infra import models\n",
             "shop/orders/infra/models.py": "x = 1\n"}
    cfg = {"package": "shop", "shared": ["shared"], "forbidden": [("shop.orders", "shop.orders.infra")]}
    assert analyze(make(tmp_path, files), cfg)["violations"] == []


def test_no_forbidden_rules_means_no_forbidden_violations(tmp_path):
    files = {**BASE, "shop/orders/domain/order.py": "from shop.orders.infra import db\n"}
    assert analyze(make(tmp_path, files), {"package": "shop", "shared": ["shared"]})["violations"] == []


def test_violations_sorted_by_rule_file_line(tmp_path):
    files = {**BASE,
             "shop/orders/domain/order.py": "from shop.orders.infra import db\n",
             "shop/billing/domain/invoice.py": "from shop.orders.domain import order\nfrom shop.orders import api\n"}
    report = analyze(make(tmp_path, files), DOMAIN_RULES)
    keys = [(v["rule"], v["file"], v["line"]) for v in report["violations"]]
    assert keys == sorted(keys)
    assert {k[0] for k in keys} == {"forbidden-import", "private-import"}


# --- cycles -----------------------------------------------------------------------------------

def test_two_module_cycle(tmp_path):
    files = {**BASE, "shop/orders/api.py": "from shop.billing import api\n", "shop/billing/api.py": "from shop.orders import api\n"}
    report = analyze(make(tmp_path, files), CFG)
    assert report["cycles"] == [["billing", "orders", "billing"]]


def test_three_module_cycle_and_shortest_return_path(tmp_path):
    files = {
        "shop/a/api.py": "from shop.b import api\nfrom shop.c import api as c\n",
        "shop/b/api.py": "from shop.c import api\n",
        "shop/c/api.py": "from shop.a import api\n",
    }
    assert analyze(make(tmp_path, files), CFG)["cycles"] == [["a", "c", "a"]]
    files["shop/a/api.py"] = "from shop.b import api\n"
    assert analyze(make(tmp_path / "x", files), CFG)["cycles"] == [["a", "b", "c", "a"]]


def test_two_independent_cycles_sorted_by_start(tmp_path):
    files = {
        "shop/y/api.py": "from shop.z import api\n", "shop/z/api.py": "from shop.y import api\n",
        "shop/a/api.py": "from shop.b import api\n", "shop/b/api.py": "from shop.a import api\n",
        "shop/m/api.py": "from shop.a import api\n",
    }
    assert analyze(make(tmp_path, files), CFG)["cycles"] == [["a", "b", "a"], ["y", "z", "y"]]


def test_composition_root_and_self_imports_create_no_cycles(tmp_path):
    files = {**BASE, "shop/orders/app/svc.py": "from shop.orders import api\n",
             "shop/orders/api.py": "from shop.orders.app import svc\n"}
    assert analyze(make(tmp_path, files), CFG)["cycles"] == []


def test_cycle_found_through_private_imports_too(tmp_path):
    files = {**BASE, "shop/orders/domain/order.py": "from shop.billing.domain import invoice\n",
             "shop/billing/domain/invoice.py": "from shop.orders.domain import order\n"}
    report = analyze(make(tmp_path, files), CFG)
    assert report["cycles"] == [["billing", "orders", "billing"]]
    assert len([v for v in report["violations"] if v["rule"] == "private-import"]) == 2


# --- вхід -------------------------------------------------------------------------------------

def test_syntax_error_mentions_file(tmp_path):
    files = {**BASE, "shop/orders/domain/broken.py": "def (:\n"}
    with pytest.raises(ValueError, match="broken.py"):
        analyze(make(tmp_path, files), CFG)


def test_files_outside_the_package_are_ignored_and_code_is_not_executed(tmp_path):
    files = {**BASE, "tests/test_x.py": "def (:\n", "scripts/tool.py": "from shop.billing.domain import invoice\n",
             "shop/orders/domain/boom.py": "raise RuntimeError('executed!')\n"}
    report = analyze(make(tmp_path, files), CFG)
    assert report["violations"] == []


def test_missing_package_gives_empty_report(tmp_path):
    report = analyze(tmp_path, CFG)
    assert report == {"violations": [], "cycles": [], "metrics": {}}


def test_ties_between_equal_cycles_and_chains_break_alphabetically(tmp_path):
    files = {
        "shop/a/api.py": "from shop.c import api\nfrom shop.b import api as b\n",
        "shop/b/api.py": "from shop.a import api\n",
        "shop/c/api.py": "from shop.a import api\n",
    }
    assert analyze(make(tmp_path, files), CFG)["cycles"] == [["a", "b", "a"]]
    files = {**BASE, "shop/orders/domain/order.py": "from shop.orders.infra import zeta\nfrom shop.orders.infra import alpha\n",
             "shop/orders/infra/zeta.py": "x = 1\n", "shop/orders/infra/alpha.py": "x = 1\n"}
    report = analyze(make(tmp_path / "x", files), {"package": "shop", "shared": ["shared"],
                                                    "forbidden": [("shop.orders.domain.order", "shop.orders.infra")]})
    assert [v["chain"] for v in report["violations"]] == [["shop.orders.domain.order", "shop.orders.infra.alpha"]]
    assert [v["line"] for v in report["violations"]] == [2]
