"""Завдання №247: SBOM diff і VEX-тріаж: список дій замість сотні CVE.

Сканер видає сотні CVE на реліз, але більшість не стосується вашого коду. Мета: порівняти SBOM
двох релізів, знайти вразливі компоненти, застосувати VEX-твердження, оцінити досяжність за
імпортами й вивести короткий список дій. Мережі немає: SBOM, OSV і VEX це JSON-фікстури.

Формати
    SBOM (CycloneDX, спрощено): {"components": [{"bom-ref": "r1", "name": "requests",
        "version": "2.31.0", "group": "optional"}, ...],
        "dependencies": [{"ref": "r1", "dependsOn": ["r2", ...]}, ...]}
        Ключ компонента: нормалізоване (PEP 503) `name`, з префіксом `group/`, якщо є `group`.
    OSV-запис: {"id": "GHSA-1", "aliases": ["CVE-2024-1"], "withdrawn": "..." (необовʼязково),
        "affected": [{"package": {"name": "requests", "ecosystem": "PyPI"},
                      "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.32.0"}]}],
                      "versions": ["2.0.0"]}]}
    VEX-твердження: {"id": "CVE-2024-1", "component": "requests", "versions": ["2.31.0"] (необовʼязково:
        немає або порожньо = усі), "state": "not_affected" | "exploitable" | "in_triage" |
        "resolved" | "false_positive", "justification": "code_not_reachable"}

Уже реалізовано: `normalize_name`, `parse_version`, `JUSTIFICATIONS`.

1. `diff_sbom(old, new) -> dict`
   {"added": [{"name", "version"}], "removed": [{"name", "version"}],
    "updated": [{"name", "from", "to", "direction"}], "unchanged": int}
   Компонент порівнюється за ключем. `name` у результаті це `group/name` або `name` як у SBOM
   (без нормалізації). `direction` це "upgrade" або "downgrade" (за `parse_version`), а якщо
   версії не розбираються, то "changed". Усі списки відсортовані за ключем. Однаковий ключ і
   версія двічі в одному SBOM це один компонент; однаковий ключ із різними версіями в одному
   SBOM, компонент без `name` чи `version` це `ValueError`.

2. `match_vulns(sbom, osv_records) -> list[dict]`
   Знахідки `{"id", "aliases", "component", "version", "fixed"}`, відсортовані за
   `(нормалізоване component, id)`. Запис збігається з компонентом, якщо є `affected` із
   `ecosystem == "PyPI"`, імʼям (після нормалізації) як у компонента (групи ігноруються) і:
   `version` компонента є в `versions` (точний рядок) АБО потрапляє у діапазон `ECOSYSTEM`.
   Діапазон: події впорядкувати за версією (при рівності `fixed`/`last_affected` раніше за `introduced`, щоб сусідні інтервали [0, 1.0) і [1.0, 2.0) не склеювались), `introduced`
   відкриває інтервал, `fixed` закриває його НЕвключно (`[introduced, fixed)`), `last_affected`
   закриває ВКЛЮЧНО, незакритий інтервал нескінченний. Записи з `withdrawn` пропускаються.
   `fixed` у знахідці це найбільша з `fixed`-версій інтервалів, що вмістили версію, або `None`.
   Один запис дає не більше однієї знахідки на компонент.

3. `apply_vex(findings, vex) -> {"active": [...], "suppressed": [...]}`
   Твердження стосується знахідки, якщо `id` збігається з `id` або одним з `aliases`, `component`
   (нормалізований) збігається, і `versions` порожні/відсутні або містять версію знахідки.
   * знахідка пригнічується (потрапляє в `suppressed`), якщо є збіжне твердження зі станом
     `not_affected` і `justification` з `JUSTIFICATIONS`, або зі станом `false_positive`
     (justification не потрібен), і НЕМАЄ збіжного твердження `exploitable`;
   * `not_affected` без допустимого `justification` НЕ пригнічує;
   * кожна знахідка в результаті це копія з доданим `"vex"`: у `active` стан, що вирішив
     (`"exploitable"` має перевагу, далі `"in_triage"`, далі `"invalid"` для негідного
     `not_affected`, інакше `None`), у `suppressed` значення `"not_affected"` чи
     `"false_positive"`. `resolved` ні на що не впливає. Порядок знахідок зберігається.

4. `imported_modules(sources: dict[str, str]) -> set[str]`
   Імена верхнього рівня з усіх `import a.b` і `from a.b import c` (будь-де у файлі, також у
   функціях і `try`). Відносні імпорти (`from . import x`) ігноруються. Код не виконується.
   Файл із синтаксичною помилкою це `ValueError`.

5. `triage(old_sbom, new_sbom, osv_records, vex, sources, import_names=None) -> dict`
   Знахідки рахуються лише для `new_sbom` (`match_vulns`, потім `apply_vex`).
   Досяжність компонента: він досяжний, якщо його імпортують напряму (`import_names` це
   `{нормалізоване імʼя пакета: [імена модулів]}`; якщо пакета там нема, модуль це
   нормалізоване імʼя з `-` на `_`), або від досяжного компонента до нього веде ланцюжок
   `dependsOn` (за `bom-ref`; невідомі ref ігноруються, цикли безпечні).
   Результат:
   {"actions": [...], "suppressed": [{"id", "component", "version", "vex"}],
    "summary": {"upgrade": n, "review": n, "monitor": n, "suppressed": n}}
   Одна дія на компонент із активними знахідками: {"component", "version", "action", "ids",
   "fixed_in", "unfixed", "reachable", "new_in_release"}:
   * `ids` відсортовані id активних знахідок; `fixed_in` найбільша `fixed` серед них
     (за `parse_version`) або `None`; `unfixed` відсортовані id знахідок без `fixed`;
   * `action`: "upgrade" якщо досяжний і `fixed_in` не `None`; "review" якщо досяжний і
     `fixed_in` is `None`; "monitor" якщо недосяжний;
   * `new_in_release`: True, якщо компонента нема в `old_sbom` або його версія змінилась;
   * порядок дій: upgrade, review, monitor; всередині за нормалізованим імʼям компонента.
   `suppressed` впорядковано за `(component, id)`.
"""
import ast  # noqa: F401  (знадобиться)
import re

JUSTIFICATIONS = frozenset({
    "code_not_present", "code_not_reachable", "requires_configuration", "requires_dependency",
    "requires_environment", "protected_by_compiler", "protected_at_runtime", "protected_at_perimeter",
    "protected_by_mitigating_control",
})


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_version(version: str) -> tuple[int, ...]:
    """'1.2.3' -> (1, 2, 3); хвостові нулі відкидаються, нечислові сегменти це ValueError."""
    if not isinstance(version, str) or not re.fullmatch(r"\d+(\.\d+)*", version):
        raise ValueError(f"unsupported version: {version!r}")
    parts = [int(p) for p in version.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def diff_sbom(old: dict, new: dict) -> dict:
    raise NotImplementedError


def match_vulns(sbom: dict, osv_records: list[dict]) -> list[dict]:
    raise NotImplementedError


def apply_vex(findings: list[dict], vex: list[dict]) -> dict:
    raise NotImplementedError


def imported_modules(sources: dict[str, str]) -> set[str]:
    raise NotImplementedError


def triage(old_sbom: dict, new_sbom: dict, osv_records: list[dict], vex: list[dict],
           sources: dict[str, str], import_names: dict | None = None) -> dict:
    raise NotImplementedError
