"""Завдання №96: автомасштабування в Kubernetes: HPA за метрикою і KEDA за довжиною черги.

hpa_desired(current, metric, target, *, min_replicas=1, max_replicas=10, tolerance_pct=10) -> int
    Формула HPA. `metric` це поточне середнє значення на один pod (наприклад, % CPU від request), `target` цільове.
    * якщо |metric - target| * 100 <= tolerance_pct * target (зона нечутливості), реплік стільки ж: `current`;
    * інакше desired = ceil(current * metric / target);
    * результат завжди обмежений [min_replicas, max_replicas] (і у зоні нечутливості теж).
    ValueError: current < 1, metric < 0, target <= 0, min_replicas < 1, max_replicas < min_replicas, tolerance_pct < 0.

simulate_hpa(metrics, *, initial, target, min_replicas=1, max_replicas=10, tolerance_pct=10, period=15, scale_down_window=300) -> list[int]
    `metrics[i]` це середнє на pod, яке HPA бачить у момент t = i * period секунд. Для кожного кроку:
    1. raw = hpa_desired(current, metrics[i], target, ...); (current на старті = initial);
    2. запиши (t, raw) в історію рекомендацій;
    3. raw >= current: масштабуємося одразу (new = raw);
       raw < current: вікно стабілізації: new = min(current, max(рекомендації з історії, чий час tt задовольняє t - tt <= scale_down_window)).
       Тобто реплік зменшується лише коли ВСІ рекомендації за вікно кажуть «можна менше», і не нижче за найбільшу з них.
    Повертає кількість реплік ПІСЛЯ кожного кроку. Порожній список метрик: [].

simulate_queue_scaler(queue, *, messages_per_replica, max_replicas, min_replicas=0, period=30, cooldown=300,
                      scale_down_window=300, initial=0) -> list[int]
    Модель KEDA для воркерів черги. `queue[i]` це довжина черги у момент t = i * period.
    raw (бажана кількість) на кроці:
    * queue[i] > 0: активність (запамʼятати t як last_active), raw = ceil(queue / messages_per_replica), обмежений
      [max(min_replicas, 1), max_replicas];
    * queue[i] == 0, min_replicas > 0: raw = min_replicas;
    * queue[i] == 0, min_replicas == 0: якщо last_active існує і t - last_active < cooldown, raw = 1 (ще не час засинати), інакше raw = 0.
    Далі як у HPA: raw >= current -> new = raw; raw == 0 -> new = 0 одразу (cooldown уже відстояли); 0 < raw < current ->
    new = min(current, max(рекомендації за вікно scale_down_window, t - tt <= scale_down_window)).
    Повертає кількість реплік після кожного кроку. ValueError: messages_per_replica < 1, max_replicas < 1, min_replicas < 0 або
    > max_replicas.
"""


def hpa_desired(current: int, metric: float, target: float, *, min_replicas: int = 1, max_replicas: int = 10,
                tolerance_pct: int = 10) -> int:
    raise NotImplementedError


def simulate_hpa(metrics: list[float], *, initial: int, target: float, min_replicas: int = 1, max_replicas: int = 10,
                 tolerance_pct: int = 10, period: int = 15, scale_down_window: int = 300) -> list[int]:
    raise NotImplementedError


def simulate_queue_scaler(queue: list[int], *, messages_per_replica: int, max_replicas: int, min_replicas: int = 0,
                          period: int = 30, cooldown: int = 300, scale_down_window: int = 300, initial: int = 0) -> list[int]:
    raise NotImplementedError
