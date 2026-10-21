"""Завдання №192: Статистика evals: bootstrap, парне порівняння, розмір набору, регресійний гейт.

Новий промпт набрав 78% замість 74%. Це покращення чи шум? На 50 кейсах різниця в 4 п.п. це 2 кейси, і вона зникає при
іншому seed моделі. Без статистики гейт у CI або падає на шумі (команда перестає йому вірити), або пропускає справжнє
погіршення. Усі функції детерміновані: випадковість лише через `random.Random(seed)`.

Оцінки кейсів це списки чисел (0/1 для pass/fail або бали 0..1, 1..5): `scores[i]` це результат i-го кейсу. Елемент не
число (int/float, bool допустимо) або список порожній: ValueError.

`bootstrap_ci(scores, *, n_resamples=2000, confidence=0.95, seed=0) -> (low, high)`
    Процентильний bootstrap для СЕРЕДНЬОГО. rng = random.Random(seed). Кожен із `n_resamples` ресемплів це n елементів,
    вибраних із поверненням (rng.choices(scores, k=n)); береться їхнє середнє. Середні сортуються за зростанням (B =
    n_resamples), alpha = 1 - confidence:
        low  = means[int(alpha / 2 * B)]
        high = means[min(B - 1, int((1 - alpha / 2) * B))]
    ValueError: n_resamples не int або < 100; confidence не в (0, 1).
    Для сталих даних (усі однакові) повертає (c, c).

`paired_bootstrap(baseline, candidate, *, n_resamples=2000, confidence=0.95, seed=0) -> dict`
    Порівняння двох версій промпту на ТИХ САМИХ кейсах (baseline[i] і candidate[i] це один кейс). Довжини різні: ValueError.
    Ресемплінг парний: індекси кейсів вибираються разом для обох списків (rng.choices(range(n), k=n)), різниця
    рахується як mean(candidate) - mean(baseline) на ресемплі. Повертає:
      {"mean_diff": точна різниця середніх (не з ресемплів), "ci": (low, high) процентилі різниць за тими ж формулами,
       "p_worse": частка ресемплів, де різниця СТРОГО менша за 0}
    Парність важлива: кейси мають різну складність, і саме вона спільна для обох версій; парний ресемплінг прибирає цей шум.

`min_sample_size(margin, *, p=0.5, confidence=0.95) -> int`
    Мінімальна кількість кейсів, щоб довірчий інтервал частки p мав півширину не більше `margin`:
    ceil(z^2 * p * (1 - p) / margin^2), z = statistics.NormalDist().inv_cdf(1 - (1 - confidence) / 2).
    ValueError: margin не в (0, 1); p не в (0, 1); confidence не в (0, 1).

`regression_gate(baseline, candidate, *, min_cases=30, tolerance=0.0, n_resamples=2000, confidence=0.95, seed=0) -> dict`
    Рішення для CI. Повертає {"decision": "pass" | "fail" | "inconclusive", "reason": str, "mean_diff", "ci", "n"}.
      * менше за `min_cases` кейсів: "inconclusive", reason "too-few-cases", mean_diff і ci це None (на такому наборі
        не можна ні пропустити, ні заблокувати);
      * інакше парний bootstrap. Якщо ВЕРХНЯ межа інтервалу < -tolerance (достовірно гірше, ніж дозволено): "fail",
        reason "significant-regression";
      * інакше "pass", reason "no-significant-regression" (покращення, різниця в межах шуму чи погіршення, що не
        відрізнити від шуму).
    Довжини різні, порожні списки, tolerance < 0, min_cases < 1: ValueError.
"""


def bootstrap_ci(scores: list, *, n_resamples: int = 2000, confidence: float = 0.95, seed: int = 0) -> tuple:
    raise NotImplementedError


def paired_bootstrap(baseline: list, candidate: list, *, n_resamples: int = 2000, confidence: float = 0.95,
                     seed: int = 0) -> dict:
    raise NotImplementedError


def min_sample_size(margin: float, *, p: float = 0.5, confidence: float = 0.95) -> int:
    raise NotImplementedError


def regression_gate(baseline: list, candidate: list, *, min_cases: int = 30, tolerance: float = 0.0,
                    n_resamples: int = 2000, confidence: float = 0.95, seed: int = 0) -> dict:
    raise NotImplementedError
