"""Завдання №209: Перевірка упередженості (контрфактичні тести).

Класифікатор резюме `clf(resume: dict) -> bool` (True: кандидата запрошено) це мок або модель, яку ви перевіряєте. Ідея
контрфактичного тесту: беремо те саме резюме й міняємо лише захищену ознаку (ім'я, стать, мову): рішення не повинно змінитись.

Резюме це dict: {"name": str, "gender": str, "language": str, "years": число, "text": str, ...}.

make_counterfactuals(resume: dict, groups: dict) -> dict
    groups: {назва_групи: {поле: нове_значення, ...}} (перевизначення полів). Повертає {назва_групи: варіант резюме} у тому
    самому порядку груп. Варіант це ГЛИБОКА копія resume, до якої застосовано перевизначення (ключі, яких не було, додаються).
    Додатково, якщо в перевизначеннях є "name", а старе resume["name"] це непорожній рядок: у КОЖНОМУ іншому полі-рядку
    варіанта (наприклад "text") усі входження старого імені замінюються новим (str.replace), щоб текст не розходився з
    полем name (поля, які самі є в перевизначеннях, не чіпаються; значення не-рядки теж). Оригінал resume не змінюється. groups не dict, порожній чи значення групи не dict: ValueError.

audit(clf, resumes, attributes, thresholds=None) -> dict
    resumes: непорожній список резюме (dict); attributes: {назва_ознаки: groups}, кожен groups має >= 2 груп, інакше ValueError
    (як і порожній attributes чи resumes).
    Для кожної ознаки (у порядку attributes) для кожного резюме (у порядку списку) для кожної групи (у порядку groups)
    викликається clf(варіант), де варіант це СВІЖА глибока копія з make_counterfactuals; рішення приводиться до bool.
    Метрики ознаки (усі round(.., 6)):
        "rates":  {група: частка True серед усіх резюме у цій групі}
        "gap":    max(rates) - min(rates)
        "disparate_impact": min(rates) / max(rates); 1.0, якщо max(rates) == 0
        "flip_rate": частка резюме, для яких рішення НЕ однакове в усіх групах
        "violations": коди в порядку "gap", "impact", "flips":
            "gap":    gap > max_gap
            "impact": disparate_impact < min_impact
            "flips":  flip_rate > max_flip_rate
    thresholds (відсутні ключі беруть типові): {"max_gap": 0.05, "min_impact": 0.8, "max_flip_rate": 0.05};
    невідомий ключ чи не число (`bool` теж не число): ValueError. Елемент `resumes`, що не dict: ValueError. Порівняння строгі й робляться по округлених метриках.
    Результат:
        {"attributes": {назва_ознаки: {"rates", "gap", "disparate_impact", "flip_rate", "violations"}},
         "violations": ["ознака:код", ...] (за порядком ознак і кодів; порожній, якщо все гаразд),
         "passed": bool (True, якщо violations порожній)}
    Виняток класифікатора не перехоплюється.
"""


def make_counterfactuals(resume: dict, groups: dict) -> dict:
    raise NotImplementedError


def audit(clf, resumes: list, attributes: dict, thresholds: dict | None = None) -> dict:
    raise NotImplementedError
