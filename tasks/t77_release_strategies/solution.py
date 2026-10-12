"""Завдання №77: Стратегії релізів: rolling, blue-green, canary і відкат.

Симуляція: який відсоток користувачів встигає постраждати від зламаного релізу при кожній стратегії і чи вмикається відкат.
Ми не розгортаємо нічого справді: функція `health(share)` моделює спостережуваний рівень помилок НОВОЇ версії, коли вона
отримує частку трафіку `share` (0.0..1.0). Це може бути «зламано завжди» або «ламається лише під навантаженням».

simulate_release(strategy, *, health, replicas=10, threshold=0.05, canary_steps=(5, 25, 50, 100)) -> dict

Рівень помилок БІЛЬШИЙ за `threshold` (строго) це провал кроку. Результат:
    {"status": "promoted" | "rolled_back" | "rejected", "exposure": float, "log": [dict, ...]}
де `exposure` це найбільша частка трафіку, яку НОВА версія отримала за весь час (скільки користувачів її побачили),
а `log` це хронологічний список кроків. Запис кроку містить "action", "traffic_new" (частка після кроку) і, якщо
рівень помилок вимірювався, "error_rate".

* "canary": для кожного p з canary_steps (зростають, останній 100) крок {"action": "shift", "traffic_new": p/100,
  "error_rate": health(p/100)}; якщо провал, додати {"action": "rollback", "traffic_new": 0.0}, status "rolled_back",
  exposure = p/100 (частка, на якій зламалось), далі кроків немає. Усі кроки пройшли: "promoted", exposure 1.0.
* "rolling": для k від 1 до replicas крок {"action": "replace", "new_pods": k, "traffic_new": k/replicas,
  "error_rate": health(k/replicas)}; провал це rollback як вище з exposure = k/replicas. Пройшло все: "promoted", 1.0.
* "blue_green": спершу {"action": "deploy_green", "traffic_new": 0.0}, потім {"action": "smoke", "traffic_new": 0.0,
  "error_rate": health(0.0)}; якщо провал: status "rejected", exposure 0.0, більше кроків немає (користувачі нічого не бачили).
  Інакше {"action": "switch", "traffic_new": 1.0, "error_rate": health(1.0)}; провал: {"action": "rollback",
  "traffic_new": 0.0}, status "rolled_back", exposure 1.0; успіх: "promoted", exposure 1.0.
  Результат blue_green має додатковий ключ "old_kept": True (стара версія лишається для миттєвого відкату).
Невідома стратегія, `replicas < 1`, `canary_steps`, що не зростають строго або не закінчуються на 100: ValueError.
"""
from typing import Callable


def simulate_release(
    strategy: str,
    *,
    health: Callable[[float], float],
    replicas: int = 10,
    threshold: float = 0.05,
    canary_steps: tuple[int, ...] | list[int] = (5, 25, 50, 100),
) -> dict:
    raise NotImplementedError
