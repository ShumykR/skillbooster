"""Завдання №91: Disaster recovery: RTO/RPO, стратегії і перевірка відновлення.

RPO (recovery point objective) це скільки даних ми готові втратити (у хвилинах), RTO (recovery time objective) скільки готові
чекати на відновлення. Їх вирішує бізнес, а інженер перевіряє, чи поточна архітектура їх витримує, і не вигадує цифри з повітря.

Компонент плану:
  {"strategy": "backup_restore" | "pilot_light" | "warm_standby" | "active_active",
   "data_gb": float, "backup_interval_min": float, "copy_delay_min": float (типово 0),
   "replication_lag_s": float | None, "restore_gb_per_min": float, "provision_min": float, "scale_min": float,
   "failover_min": float (DNS/перемикання), "depends_on": [імена], "last_restore_test": секунди епохи | None}
Відсутні числові поля вважаються 0 (restore_gb_per_min потрібне лише для backup_restore; якщо data_gb == 0, час
відновлення даних 0 навіть без нього; data_gb > 0 при restore_gb_per_min == 0: ValueError).

component_rpo(c) -> float    хвилини втрати даних у найгіршому разі: для pilot_light, warm_standby та active_active, коли задано
    `replication_lag_s`: lag/60; в інших випадках (backup_restore, або реплікації немає): backup_interval_min + copy_delay_min.
component_recovery_min(c) -> float    власний час відновлення компонента (без очікування залежностей і без виявлення аварії):
    active_active: failover_min; warm_standby: scale_min + failover_min; pilot_light: provision_min + failover_min;
    backup_restore: provision_min + data_gb / restore_gb_per_min + failover_min.
dr_report(components, objectives, *, detection_min=5) -> dict    `components`: {імʼя: компонент}; `objectives`: {"rpo_min", "rto_min"}.
    * finish(c) = max(finish(d) для d у depends_on, 0) + component_recovery_min(c): компонент піднімається після залежностей;
    * rto_min = detection_min + max(finish(c)); rpo_min = max(component_rpo(c)); порожній план: rto = detection_min, rpo = 0;
    * meets_rto / meets_rpo: вкладаємось (<=) у цілі; "violations": відсортовані імена компонентів, у яких
      detection_min + finish(c) > rto-ціль АБО component_rpo(c) > rpo-ціль;
    * усі числа округлені до 2 знаків; невідома залежність або цикл: ValueError.
    Результат: {"rto_min", "rpo_min", "meets_rto", "meets_rpo", "violations"}.
recommend_strategy(rto_min, rpo_min) -> str    найдешевша стратегія, що в принципі витримує цілі:
    rto < 5 або rpo < 1 -> "active_active"; інакше rto < 30 або rpo < 5 -> "warm_standby"; інакше rto < 240 або rpo < 60 ->
    "pilot_light"; інакше "backup_restore". (Ціль нижча за межу, отже потрібна дорожча стратегія.)
restore_tests_due(components, now, *, max_age_days=90) -> list[str]    імена компонентів, чиє останнє успішне тестове
    відновлення старіше за max_age_days (now - last_restore_test > max_age_days * 86400) або відсутнє (None / немає ключа);
    відсортовано. Бекап, який жодного разу не відновлювали, це не бекап.
"""


def component_rpo(c: dict) -> float:
    raise NotImplementedError


def component_recovery_min(c: dict) -> float:
    raise NotImplementedError


def dr_report(components: dict[str, dict], objectives: dict, *, detection_min: float = 5) -> dict:
    raise NotImplementedError


def recommend_strategy(rto_min: float, rpo_min: float) -> str:
    raise NotImplementedError


def restore_tests_due(components: dict[str, dict], now: float, *, max_age_days: int = 90) -> list[str]:
    raise NotImplementedError
