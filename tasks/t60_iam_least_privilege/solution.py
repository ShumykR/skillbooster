"""Завдання №60: Мінімальні права в AWS IAM.

Дві частини: симулятор політики (як IAM вирішує «дозволити чи ні») і генератор мінімальної політики
за журналом реальних викликів (так працює IAM Access Analyzer: "generate policy from CloudTrail").

is_allowed(policy, action, resource) -> bool
    `policy`: {"Version": ..., "Statement": [ ... ]} або один statement-словник у "Statement".
    Statement: {"Effect": "Allow"|"Deny", "Action": str|list, "Resource": str|list}.
    Правила IAM:
    * за замовчуванням заборонено (implicit deny);
    * явний Deny завжди сильніший за будь-який Allow;
    * збіг дії та ресурсу з шаблоном: `*` це будь-яка кількість будь-яких символів, `?` рівно один;
      назва дії порівнюється БЕЗ урахування регістру ("S3:GetObject" == "s3:getobject"), ARN ресурсу з урахуванням;
    * statement із ключем "Condition" або "NotAction"/"NotResource" не підтримується: Allow-statement
      із такими ключами ігнорується (безпечніше), а Deny-statement із ними діє БЕЗ умови (теж безпечніше).

generate_policy(events) -> dict
    `events`: список пар (action, resource_arn) з журналу. Результат: {"Version": "2012-10-17", "Statement": [...]}.
    * жодних `*` у Action; ресурси це точні ARN із журналу (без шаблонів);
    * дії, які не вимагають ресурсу, йдуть в окремий statement із Resource "*":
      "sts:GetCallerIdentity", "s3:ListAllMyBuckets" і будь-яка "ec2:Describe*" (за префіксом `ec2:describe`, без
      урахування регістру), навіть якщо в журналі вони мали якийсь ARN;
    * решта групується за сервісом (частина дії до ":", нижній регістр), а всередині сервісу ресурси з ОДНАКОВИМ
      набором дій об'єднуються в один statement: Action це відсортований список унікальних дій цього набору,
      Resource це відсортований список унікальних ARN;
    * statement-и впорядковані за (сервіс, кортеж дій), "Resource: '*'"-statement-и йдуть після решти;
      Effect завжди "Allow"; порожній журнал це порожній "Statement".
    Дії записуй у тому вигляді, як вони в журналі.
"""
import re  # noqa: F401


def is_allowed(policy: dict, action: str, resource: str) -> bool:
    raise NotImplementedError


def generate_policy(events: list[tuple[str, str]]) -> dict:
    raise NotImplementedError
