"""Завдання №84: політики для Terraform plan (аналог conftest/OPA).

`evaluate_plan(plan)` приймає розібраний JSON від `terraform show -json tfplan` і повертає
відсортований список унікальних пар `(правило, адреса ресурсу)`.

Дивись на `plan["resource_changes"]`: кожен елемент має `address`, `type` і
`change = {"actions": [...], "after": {...}}`. Ресурс, що ВИДАЛЯЄТЬСЯ (`actions == ["delete"]`,
`after` це `None`), не перевіряємо.

Правила:
- `S3_PUBLIC`        `aws_s3_bucket_public_access_block`, де хоч один із прапорців
                     block_public_acls, block_public_policy, ignore_public_acls,
                     restrict_public_buckets не дорівнює True (відсутній теж порушення);
                     або `aws_s3_bucket` з `acl` = public-read / public-read-write;
- `SG_SSH_OPEN`      `aws_security_group`: правило в `ingress` відкриває порт 22 для
                     `0.0.0.0/0` (cidr_blocks) або `::/0` (ipv6_cidr_blocks). Порт 22 входить
                     у діапазон from_port..to_port; протокол "-1" означає всі порти.
                     Те саме для `aws_vpc_security_group_ingress_rule`
                     (поля cidr_ipv4 / cidr_ipv6 / from_port / to_port / ip_protocol);
- `RDS_UNENCRYPTED`  `aws_db_instance`, де `storage_encrypted` не True;
- `RDS_PUBLIC`       `aws_db_instance` з `publicly_accessible` = True;
- `MISSING_TAGS`     ресурси aws_s3_bucket, aws_instance, aws_db_instance, aws_security_group
                     без тегів `owner` і `env` (обидва обовʼязкові) у `tags`.
"""


def evaluate_plan(plan: dict) -> list[tuple[str, str]]:
    raise NotImplementedError
