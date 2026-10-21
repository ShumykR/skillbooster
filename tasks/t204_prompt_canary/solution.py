"""Завдання №204: Canary для промптів і моделей.

Нову версію промпту чи моделі («canary») не вмикають усім одразу: спершу невеликій частці трафіку, порівнюють
з поточною («stable») за помилками, якістю, вартістю й затримкою і або розширюють, або відкочують.

CanaryController(salt, steps=(5, 25, 50, 100), thresholds=None, min_samples=20)
    salt: рядок для хешування. steps: зростаючий список відсотків трафіку на canary (цілі 1..100, останній 100).
    thresholds (відсутні ключі беруть типові значення):
        {"max_error_delta": 0.02,     # частка помилок canary мінус stable
         "max_quality_drop": 0.05,    # середня якість stable мінус canary
         "max_cost_ratio": 1.25,      # середня вартість canary / stable
         "max_latency_ratio": 1.5}    # p95 затримки canary / stable
    Початково weight = steps[0], state = "running", стартовий індекс кроку 0.
    Невалідні steps (порожні, не зростають, останній не 100, значення поза 1..100) та min_samples < 1: ValueError.

    .weight -> int                    поточний відсоток трафіку на canary (0 після відкоту).
    .state -> str                     "running" | "promoted" (canary отримав 100%) | "rolled_back".

    .assign(user_id) -> "stable" | "canary"
        Прив'язка користувача (sticky): bucket = int(sha256(f"{salt}:{user_id}".encode()).hexdigest(), 16) % 100.
        "canary", якщо bucket < weight, інакше "stable". Відсоток зростає: хто вже був у canary, лишається в ньому.
        Після rolled_back усі "stable". user_id приводиться до str.

    .record(variant, ok, cost, latency_ms, quality=None)
        Записує один запит варіанта "stable" чи "canary" за ПОТОЧНИЙ крок. ok: bool (False це помилка), cost >= 0 (USD),
        latency_ms >= 0, quality: число або None (None не враховується в середній якості).
        Невідомий variant, від'ємні cost/latency: ValueError. Після state != "running" запис ігнорується.

    .evaluate() -> dict   (нічого не змінює)
        {"action": "wait" | "rollback" | "promote" | "done", "reasons": [...], "metrics": {...}}
        - "done", якщо state != "running" (reasons []).
        - "wait", якщо на цьому кроці менше min_samples записів у canary АБО у stable (reasons []).
        - інакше порівняння; порушення, СУВОРО більші за поріг, у такому порядку кодів:
            "error-rate": error_rate(canary) - error_rate(stable) > max_error_delta
            "quality":    mean_quality(stable) - mean_quality(canary) > max_quality_drop (лише коли в обох варіантів є хоч одна якість)
            "cost":       mean_cost(canary) / mean_cost(stable) > max_cost_ratio (якщо mean_cost(stable) == 0: порушення, лише коли
                          mean_cost(canary) > 0)
            "latency":    p95(canary) / p95(stable) > max_latency_ratio (p95 за nearest-rank: відсортувати, елемент з індексом
                          ceil(0.95 * n) - 1; якщо p95(stable) == 0: порушення, лише коли p95(canary) > 0)
          Є порушення: "rollback" з reasons. Немає: "promote", reasons [].
        - metrics: {"stable": {"n", "error_rate", "mean_cost", "p95_latency", "mean_quality"}, "canary": {...}},
          mean_quality None, якщо якостей немає. Числа round(.., 6).

    .step() -> dict
        decision = evaluate(); застосовує його і повертає {"action", "reasons", "weight", "state"} (weight і state після дії):
        - "rollback": state = "rolled_back", weight = 0;
        - "promote": перехід на наступний крок steps (weight = новий відсоток), лічильники ОБОХ варіантів обнуляються;
          якщо після переходу weight == 100, то state = "promoted" (так само для steps=(100,): "promote" одразу
          робить state "promoted");
        - "wait" і "done": без змін.
"""


class CanaryController:
    def __init__(self, salt, steps=(5, 25, 50, 100), thresholds=None, min_samples=20):
        raise NotImplementedError

    @property
    def weight(self):
        raise NotImplementedError

    @property
    def state(self):
        raise NotImplementedError

    def assign(self, user_id):
        raise NotImplementedError

    def record(self, variant, ok, cost, latency_ms, quality=None):
        raise NotImplementedError

    def evaluate(self):
        raise NotImplementedError

    def step(self):
        raise NotImplementedError
