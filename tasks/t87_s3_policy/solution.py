"""Завдання №87: аудит політики бакета S3 (bucket policy).

`analyze_bucket_policy(policy)` приймає розібраний JSON політики і повертає відсортований
список унікальних рядків `правило:ідентифікатор` або просто `правило`.

Ідентифікатор оператора (statement) це його поле `Sid`; якщо `Sid` немає, то `#<індекс>`
(індекс у списку Statement з нуля, наприклад `#2`).

Правила:
- `public_access:<sid>`   оператор `Effect: Allow` для ПУБЛІЧНОГО принципала (`"*"` або
                          `{"AWS": "*"}`, у тому числі в списку `{"AWS": ["*", ...]}`) і БЕЗ
                          обмежувальної умови. Обмежувальною вважається умова (в будь-якому
                          операторі умов, регістр ключів неважливий), що містить хоча б один
                          із ключів: aws:PrincipalOrgID, aws:SourceVpce, aws:SourceVpc,
                          aws:PrincipalArn, aws:SourceAccount, aws:SourceArn,
                          aws:PrincipalAccount. Решта умов (наприклад, aws:UserAgent) ні;
- `wildcard_action:<sid>` оператор `Effect: Allow`, у `Action` якого є `"*"` або `"s3:*"`
                          (`"s3:Get*"` це нормально);
- `missing_tls_deny`      у політиці НЕМАЄ оператора, що забороняє нешифрований доступ:
                          `Effect: Deny`, публічний принципал, `Action` містить `"*"` або
                          `"s3:*"`, і `Condition` має `Bool` з `aws:SecureTransport` рівним
                          `"false"` (рядок будь-якого регістру або булеве false).

`Statement` може бути одним словником або списком; `Action` і `Principal.AWS` рядком або
списком. Політика без операторів дає лише `missing_tls_deny`.
"""


def analyze_bucket_policy(policy: dict) -> list[str]:
    raise NotImplementedError
