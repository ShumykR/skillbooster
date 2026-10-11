"""Завдання №86: ревʼю конфігурації RDS і бюджет зʼєднань.

`review_rds(db, sgs, params, env="prod") -> list[str]` повертає відсортований список
унікальних кодів правил, які порушені.

- `db` це один елемент `DBInstances` з `aws rds describe-db-instances` (ключі PascalCase):
  `Engine`, `MultiAZ`, `BackupRetentionPeriod`, `StorageEncrypted`, `PubliclyAccessible`,
  `DeletionProtection`, `PerformanceInsightsEnabled`, `VpcSecurityGroups`
  (список `{"VpcSecurityGroupId": "sg-..."}`). Відсутній булевий ключ це False,
  відсутній `BackupRetentionPeriod` це 0.
- `sgs` це `{id групи: [правила ingress на порт БД]}`, правило: `{"cidr": "10.0.0.0/16"}`
  або `{"sg": "sg-app"}`. Групи, яких немає в `sgs`, ігноруй.
- `params` це дієві значення параметр-групи (рядки): `{"rds.force_ssl": "1", ...}`.
- `env` це "prod" або "dev"; інше значення `ValueError`.

Правила (позначка prod = лише для env == "prod"):
- RDS001 prod: `MultiAZ` не True
- RDS002 prod: `BackupRetentionPeriod` менше 7 днів
- RDS003: `StorageEncrypted` не True
- RDS004: `PubliclyAccessible` True
- RDS005 prod: `DeletionProtection` не True
- RDS006: у будь-якій приєднаній групі є правило з `cidr` "0.0.0.0/0" або "::/0"
- RDS007: TLS не примусовий. Engine, що починається з "postgres": `params["rds.force_ssl"]`
  не дорівнює "1". Engine "mysql" або "mariadb": `params["require_secure_transport"]` не
  "1" і не "ON" (без урахування регістру). Інші двигуни це правило не перевіряють
- RDS008: Engine починається з "postgres", а `log_min_duration_statement` у params
  відсутній або дорівнює "-1" (повільні запити не логуються)
- RDS009 prod: `PerformanceInsightsEnabled` не True

`connection_budget(max_connections, services, reserved=10, surge_pct=25) -> dict`:
ці цифри потрібні, щоб пули застосунків не вичерпали `max_connections` бази.
`services` це список `{"name", "replicas", "pool_size", "max_overflow"}` (`max_overflow`
необовʼязковий, за замовчуванням 0). Під час rolling update реплік тимчасово більше, тому
кількість реплік рахується з запасом: `ceil(replicas * (100 + surge_pct) / 100)` (цілі числа).
Результат: {"available": max_connections - reserved,
            "needed": сума по сервісах (реплік_з_запасом * (pool_size + max_overflow)),
            "fits": needed <= available,
            "headroom": available - needed}
Від'ємні значення чи `reserved > max_connections` це `ValueError`.

`default_max_connections(memory_gib) -> int`: значення за замовчуванням для RDS PostgreSQL:
`min(памʼять_у_байтах // 9531392, 5000)`, де памʼять у байтах це `memory_gib * 1024**3`.
`memory_gib <= 0` це `ValueError`.
"""


def review_rds(db: dict, sgs: dict, params: dict, env: str = "prod") -> list[str]:
    raise NotImplementedError


def connection_budget(max_connections, services, reserved=10, surge_pct=25) -> dict:
    raise NotImplementedError


def default_max_connections(memory_gib) -> int:
    raise NotImplementedError
