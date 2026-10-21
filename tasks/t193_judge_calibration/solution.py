"""Завдання №193: калібрування LLM-судді.

LLM-as-judge (№131) дешевший за людей, але має власні перекоси: любить першу позицію, довші
відповіді й «погоджується» не завжди з людьми. Перш ніж довіряти судді гейт у CI, його
калібрують: порівнюють з людською розміткою, міряють position bias і length bias. Суддя в
тестах це звичайна функція `judge(a, b) -> "A" | "B" | "tie"` (A це перша відповідь у запиті,
B друга). Нічого не викликає мережі й LLM.

`cohens_kappa(human, judge) -> float`
    Узгодженість двох розміток одного набору кейсів. `human` і `judge` це списки міток
    (будь-які hashable значення) однакової непорожньої довжини, інакше `ValueError`.
    po = частка збігів; pe = сума за мітками c від p_human(c) * p_judge(c);
    kappa = (po - pe) / (1 - pe), `round(.., 6)`. Якщо pe == 1 (обидві розмітки
    складаються з однієї й тієї ж єдиної мітки): `1.0`.

`agreement_report(human, judge) -> dict`
    `{"n": довжина, "accuracy": збіги / n (round 6), "kappa": cohens_kappa(...),
      "confusion": {мітка_людини: {мітка_судді: кількість}}}`; ключі обох рівнів відсортовані
    за `str(мітка)`, у вкладеному словнику лише ненульові кількості. Ті самі перевірки входу.

`position_bias(judge, pairs) -> dict`
    `pairs` це непорожній список пар `(x, y)` відповідей. Для КОЖНОЇ пари суддю викликають
    рівно двічі, у такому порядку: `judge(x, y)`, потім `judge(y, x)`. Вердикти зводяться до
    переможця: у виклику `judge(x, y)` "A" це x, "B" це y; у виклику `judge(y, x)` "A" це y, "B"
    це x; "tie" це «без переможця». Невідомий вердикт це `ValueError`.
    * `consistent`: пара, де переможець однаковий в обох порядках (два "tie" теж збіг);
    * `flips`: пара, де обидва вердикти рішучі (не "tie"), але переможці різні (суддя
      обирав позицію, а не зміст);
    Результат: `{"n": кількість пар, "consistent": ..., "consistency_rate": consistent / n,
    "flips": ..., "flip_rate": flips / n, "first_position_rate": частка вердиктів "A" серед
    усіх РІШУЧИХ вердиктів обох порядків (0.0, якщо рішучих немає), "tie_rate": частка "tie"
    серед усіх 2n вердиктів}`; усі частки `round(.., 6)`.

`length_bias(judge, pairs) -> dict`
    `pairs` це непорожній список пар `(x, y)` відповідей РІВНОЇ якості (наприклад, одна з
    «водою»), різної довжини (`len(x) != len(y)`, інакше `ValueError`; відповіді це `str`).
    Суддю викликають для кожної пари двічі, як у `position_bias`. Рішучий вердикт обирає або
    довшу, або коротшу відповідь.
    `{"calls": 2 * n, "decisive": кількість рішучих вердиктів, "longer_wins": скільки разів
      обрано довшу, "longer_win_rate": longer_wins / decisive (round 6; 0.5, якщо рішучих
      немає)}`. Для неупередженого судді частка близька до 0.5.

`trust_decision(report, min_kappa=0.6, min_consistency=0.9, max_length_skew=0.15, min_samples=30) -> dict`
    Чи можна довіряти судді. `report` це dict із ключами `"n"` (кількість людських міток),
    `"kappa"`, `"consistency_rate"`, `"longer_win_rate"`; відсутній ключ чи не число (`bool`
    теж не число) це `ValueError`. Причини відмови в такому порядку:
      * `"too-few-samples"`: `n < min_samples`;
      * `"low-agreement"`: `kappa < min_kappa`;
      * `"position-bias"`: `consistency_rate < min_consistency`;
      * `"length-bias"`: `abs(longer_win_rate - 0.5) > max_length_skew`.
    `{"trusted": bool (причин немає), "reasons": [...]}`. Пороги строгі: рівність це не порушення.
"""


def cohens_kappa(human: list, judge: list) -> float:
    raise NotImplementedError


def agreement_report(human: list, judge: list) -> dict:
    raise NotImplementedError


def position_bias(judge, pairs: list) -> dict:
    raise NotImplementedError


def length_bias(judge, pairs: list) -> dict:
    raise NotImplementedError


def trust_decision(report: dict, min_kappa: float = 0.6, min_consistency: float = 0.9,
                   max_length_skew: float = 0.15, min_samples: int = 30) -> dict:
    raise NotImplementedError
