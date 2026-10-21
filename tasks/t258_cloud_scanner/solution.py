"""Завдання №258: сканер хибних налаштувань хмари (знімок акаунта AWS).

`scan_account(snapshot: dict) -> list[dict]` аналізує JSON-знімок акаунта (так виглядає
злитий вивід `describe`-викликів) і повертає знахідки. Чиста функція: без мережі, без
зміни `snapshot`. Не-словник на вході це `ValueError`. Відсутній розділ знімка це порожній
список ресурсів; відсутнє поле ресурсу має значення за замовчуванням, як в AWS (див. нижче).

Знімок (усе необовʼязкове):
    "account_block_public_access": {"BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy",
                                    "RestrictPublicBuckets"}      # bool, за замовчуванням False
    "s3_buckets": [{"name", "block_public_access": {...ті самі 4 прапорці},
                    "acl_grants": [{"grantee": "AllUsers" | "AuthenticatedUsers" | "CanonicalUser:<id>",
                                    "permission": "READ" | "WRITE" | "READ_ACP" | "WRITE_ACP" | "FULL_CONTROL"}],
                    "policy": {розібраний JSON політики} | None}]
    "security_groups": [{"id", "ingress": [{"protocol": "tcp" | "udp" | "icmp" | "-1",
                                            "from_port", "to_port", "cidrs": [...], "ipv6_cidrs": [...]}]}]
    "instances": [{"id", "metadata_options": {"http_tokens": "optional" | "required",
                                              "http_endpoint": "enabled" | "disabled"}}]
    "cloudtrails": [{"name", "is_multi_region", "is_logging"}]
    "kms_keys": [{"id", "key_manager": "CUSTOMER" | "AWS", "key_spec", "key_state", "rotation_enabled"}]
    "rds_instances": [{"id", "publicly_accessible"}]

Знахідка: `{"rule", "resource", "severity", "fix"}` і більше нічого; `fix` це непорожній рядок
(порада, як виправити; текст довільний). Порядок: severity від найтяжчої (`critical`, `high`,
`medium`, `low`), потім `rule`, потім `resource`. Одне правило для одного ресурсу не більше
одного разу.

Правила:
* `s3-public` (resource: імʼя бакета). Бакет ЕФЕКТИВНО публічний, якщо відкритий хоча б одним шляхом
  з двох (кожен шлях може бути нейтралізований Block Public Access, ефективний прапорець це
  OR прапорця акаунта і прапорця бакета):
  - через ACL: є grant для `AllUsers` або `AuthenticatedUsers` (будь-який permission), і ефективний
    `IgnorePublicAcls` НЕ ввімкнений;
  - через політику: є оператор `Effect: Allow` з публічним принципалом (`"*"` або `{"AWS": "*"}`,
    у тому числі в списку) БЕЗ обмежувальної умови, і ефективний `RestrictPublicBuckets` НЕ ввімкнений.
    Обмежувальна умова (будь-який оператор умов, регістр ключів неважливий): має хоча б один ключ із
    `aws:PrincipalOrgID`, `aws:SourceVpce`, `aws:SourceVpc`, `aws:PrincipalArn`, `aws:SourceAccount`,
    `aws:SourceArn`, `aws:PrincipalAccount`. `Statement` може бути словником або списком, `Action`
    рядком або списком. Оператори з `NotPrincipal`/`NotAction` не враховуй.
  Severity `critical`, якщо відкритий шлях дає запис: ACL з `WRITE`, `WRITE_ACP` чи `FULL_CONTROL`,
  або публічний `Allow` з дією `*`, `s3:*` чи такою, що починається з `s3:put` або `s3:delete`
  (без урахування регістру). Інакше `high`.
* `s3-bpa-incomplete` (resource: імʼя бакета, severity `low`): ефективні (OR акаунт/бакет) прапорці
  Block Public Access не всі чотири ввімкнені.
* `sg-open-all` (resource: id групи, severity `critical`): правило ingress відкрите для світу
  (`0.0.0.0/0` у `cidrs` або `::/0` у `ipv6_cidrs`) і охоплює ВСІ порти (`protocol` `-1`, або `tcp`/`udp`
  з портами 0..65535).
* `sg-open-admin-port` (resource: `<id групи>:<порт>`, severity `high`): ingress відкрите для світу
  і охоплює порт 22, 3389 чи 5432 за `protocol` `tcp` (діапазон `from_port <= порт <= to_port`).
  Для групи, що має хоча б одне правило `sg-open-all`, знахідок `sg-open-admin-port` не додавай
  взагалі (все вже сказано критичною знахідкою). Протокол `-1` без портів це `sg-open-all`.
* `imdsv1-enabled` (resource: id інстанса, severity `high`): `http_endpoint` не `disabled` і
  `http_tokens` не `required`. Без `metadata_options`: `optional` і `enabled`.
* `cloudtrail-missing` (resource: `account`, severity `high`): НЕМАЄ жодного trail, що водночас
  `is_multi_region` і `is_logging` (в тому числі коли trail'ів нема зовсім).
* `cloudtrail-not-logging` (resource: імʼя trail, severity `high`): trail існує, але `is_logging` не true.
* `kms-no-rotation` (resource: id ключа, severity `medium`): `key_manager` `CUSTOMER`, `key_spec`
  `SYMMETRIC_DEFAULT`, `key_state` `Enabled` і ротація не ввімкнена. Інші ключі (AWS-managed,
  асиметричні, вимкнені, на видаленні) пропускай.
* `rds-public` (resource: id інстанса, severity `critical`): `publicly_accessible` істинне.
"""


def scan_account(snapshot: dict) -> list[dict]:
    raise NotImplementedError
