"""Завдання №85: Автомасштабування сервісу за ALB (ECS Fargate / EKS): target tracking.

Target tracking тримає середню метрику (CPU, запити на ціль) біля заданого значення: метрика вдвічі вища за ціль
означає «потрібно вдвічі більше інстансів». Складнощі в деталях: охолодження (cooldown), щоб не смикатись на кожен сплеск,
асиметрія (масштабуємось угору швидко, вниз обережно) і межі min/max. Реалізуй рішення, яке автомасштабувальник
приймає на кожному вимірі.

TargetTrackingScaler(target, min_capacity, max_capacity, scale_out_cooldown=60, scale_in_cooldown=300)
    `target` > 0, 0 <= min_capacity <= max_capacity, інакше ValueError. Час передається в evaluate (секунди).
.evaluate(current, metric, now) -> int    бажана кількість інстансів (повертається завжди; "без змін" це current):
    1. якщо current < min_capacity: повернути min_capacity (запис про масштабування вгору); якщо current > max_capacity:
       повернути max_capacity (запис про масштабування вниз); cooldown і метрика тут не потрібні;
    2. metric це None або NaN (немає даних): повернути current;
    3. raw = ceil(current * metric / target) (при current == 0: 1, якщо metric > 0, інакше 0);
    4. raw > current (потрібно більше): якщо від останнього масштабування ВГОРУ минуло менше за scale_out_cooldown, повернути
       current; інакше new = min(raw, max_capacity); якщо new > current, запам'ятати час масштабування вгору; повернути new;
    5. raw < current (можна менше): масштабуємось вниз лише якщо metric < 0.9 * target (запас проти хитання: поки метрика
       поблизу цілі, нічого не змінюємо) І від останнього масштабування в БУДЬ-ЯКИЙ бік (вгору чи вниз) минуло не менше
       за scale_in_cooldown. Крок вниз обмежений: new = max(raw, current - max(1, current // 4), min_capacity); якщо
       new < current, запам'ятати час масштабування вниз; повернути new. Інакше повернути current;
    6. raw == current: повернути current.
    Cooldown вважається минулим, якщо `now - last >= cooldown`; перше масштабування (last немає) нічим не блокується.
"""
import math  # noqa: F401


class TargetTrackingScaler:
    def __init__(
        self,
        target: float,
        min_capacity: int,
        max_capacity: int,
        scale_out_cooldown: float = 60,
        scale_in_cooldown: float = 300,
    ) -> None:
        raise NotImplementedError

    def evaluate(self, current: int, metric: float | None, now: float) -> int:
        raise NotImplementedError
