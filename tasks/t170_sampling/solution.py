"""Завдання №170: sampling з logits: temperature, top-k, top-p, logprobs.

Модель повертає не слово, а вектор `logits` (по одному числу на токен словника). Те, що ви
бачите як «творчість» чи «детермінізм» моделі, це налаштування цього кроку.

`logits` це список `float`; `-inf` означає «токен заборонено». Порожній список, `nan`, `+inf`
і список лише з `-inf` це `ValueError`.

`softmax(logits, temperature=1.0) -> list[float]`
    `softmax(logits / temperature)`. `temperature` має бути > 0 (інакше `ValueError`).
    Має бути числово стійкою (великі logits на кшталт 1000 не дають переповнення), `-inf` дає 0.
`log_softmax(logits, temperature=1.0) -> list[float]`
    Логарифми тих самих ймовірностей без втрати точності (не `log(softmax)`: для `-1000`
    не має вийти `-inf`); токен з `-inf` лишається `-inf`.
`filter_top_k(probs, k) -> list[float]`
    Лишає `k` найімовірніших токенів (при нічиїй спершу менший індекс), решту обнуляє й
    ПЕРЕНОРМОВУЄ суму до 1. `k` це `int` (не `bool`) >= 1, інакше `ValueError`; `k` більше за
    розмір списку не змінює його. Вхідний список не змінюється.
`filter_top_p(probs, p) -> list[float]`
    Nucleus: токени за спаданням ймовірності (нічия: менший індекс); лишається найкоротший
    префікс, накопичена сума якого `>= p` (мінімум один токен), решта обнуляється, результат
    перенормовується. `0 < p <= 1`, інакше `ValueError`.
`sample(logits, rng, temperature=1.0, top_k=None, top_p=None) -> (index, logprob)`
    * `temperature == 0`: greedy, `argmax(logits)` (при нічиїй менший індекс); `rng` НЕ
      використовується, `top_k`/`top_p` ігноруються. `temperature < 0` це `ValueError`;
    * інакше: `probs = softmax(logits, temperature)`, потім `top_k` (якщо задано), потім
      `top_p` (якщо задано) на вже перенормованому результаті;
    * рівно ОДИН виклик `rng.random()` = `u`; повертається найменший індекс `i` з
      `probs[i] > 0`, для якого `u < накопичена сума probs[0..i]` (строге порівняння). Якщо
      через похибку float таких немає, повертається останній індекс з `probs[i] > 0`;
    * `logprob` це `log_softmax(logits)` (temperature 1, БЕЗ фільтрів) для обраного токена, як
      у `logprobs` API провайдерів.
    `rng` це будь-який обʼєкт з методом `random()` (наприклад `random.Random(seed)`).
"""


def softmax(logits: list[float], temperature: float = 1.0) -> list[float]:
    raise NotImplementedError


def log_softmax(logits: list[float], temperature: float = 1.0) -> list[float]:
    raise NotImplementedError


def filter_top_k(probs: list[float], k: int) -> list[float]:
    raise NotImplementedError


def filter_top_p(probs: list[float], p: float) -> list[float]:
    raise NotImplementedError


def sample(logits: list[float], rng, temperature: float = 1.0, top_k: int | None = None,
           top_p: float | None = None) -> tuple[int, float]:
    raise NotImplementedError
