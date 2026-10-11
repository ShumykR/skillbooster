"""Завдання №94: симулятор probes у Kubernetes.

Час у цілих секундах. Контейнер стартує в момент 0. `probes` це словник із необовʼязковими
ключами "startup", "liveness", "readiness"; кожен це словник параметрів (відсутні беруться зі
значень за замовчуванням):
    initial_delay      0   секунд від старту контейнера до першої перевірки
    period             10  інтервал між перевірками (>= 1)
    failure_threshold  3   скільки НЕВДАЧ ПОСПІЛЬ потрібно для спрацювання (>= 1)
    success_threshold  1   скільки УСПІХІВ ПОСПІЛЬ потрібно readiness-проби, щоб pod став ready (>= 1)
Невідоме імʼя проби, період < 1, пороги < 1, `initial_delay` < 0: `ValueError`.

Застосунок `app`: {"ready_after": 30, "down": [(60, 80), (120, None)]}.
`age` це секунди від старту поточного контейнера. Застосунок відповідає OK, якщо
`age >= ready_after` і `age` не лежить у жодному «вікні недоступності» `[from, to)`
(`to` = None означає «назавжди»). `ready_after` за замовчуванням 0, `down` порожній;
`ready_after < 0` це `ValueError`.

Пробу виконують у моменти, коли `age >= initial_delay` і `(age - initial_delay) % period == 0`.
Правила:
- Якщо є `startup`, то `liveness` і `readiness` не виконуються, поки startup не пройшов
  (перший успішний startup-запит). Усі `failure_threshold` невдач поспіль у startup: контейнер
  вбито. Сам startup після успіху більше не виконується.
- `liveness`: успіх обнуляє лічильник невдач; `failure_threshold` невдач поспіль: контейнер вбито.
- `readiness`: pod стає ready після `success_threshold` успіхів поспіль, перестає бути ready
  після `failure_threshold` невдач поспіль (контейнер НЕ перезапускається). Невдача обнуляє
  лічильник успіхів, успіх обнуляє лічильник невдач. На початку pod не ready.
- Якщо readiness-проби немає, pod ready від моменту, коли startup пройшов (без startup: від
  `age == 0`).
- В один момент спершу обробляється startup, потім liveness, потім readiness; після вбивства
  решта проб цього моменту не виконується. Вбивство в момент `t` означає перезапуск: новий
  контейнер має `age == 0` у момент `t + 1`, стан проб скинуто, pod не ready.

`simulate(probes, app, duration) -> dict` проганяє моменти 0..duration включно й повертає
    {"restarts": N, "restart_times": [моменти вбивств], "first_ready_at": момент або None,
     "ready_at_end": bool}   # стан ready після обробки моменту `duration`
`duration < 0` це `ValueError`.

`max_startup_seconds(probes) -> int | None`: найбільший `ready_after`, з яким застосунок ще
виживе без перезапуску: керує startup-проба, а якщо її немає, liveness. Якщо немає жодної,
повертає None (вбивати нікому).
"""


def simulate(probes: dict, app: dict, duration: int) -> dict:
    raise NotImplementedError


def max_startup_seconds(probes: dict):
    raise NotImplementedError
