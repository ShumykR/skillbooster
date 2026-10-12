"""Завдання №78: OIDC до AWS замість довгоживучих ключів: аудит trust policy ролі.

GitHub Actions отримує тимчасові ключі AWS, обмінюючи свій OIDC-токен на роль (`sts:AssumeRoleWithWebIdentity`).
Уся безпека тримається на **trust policy** ролі: якщо в ній не обмежено, *чий* токен приймається, то роль може
отримати будь-який репозиторій на GitHub. Реалізуй аудит такої політики.

audit_trust_policy(policy, repo) -> list[str]
    `policy`: trust policy (словник), `repo`: "owner/name" репозиторію, якому роль призначена. Повертає відсортований
    список унікальних кодів. Для кожного statement з `Effect: Allow`:

    * OIDC006  Principal це "*" або будь-яке з полів Principal ("AWS", "Federated", "Service") дорівнює "*" або містить "*"
               як окреме значення: роль може отримати будь-хто. (Перевіряється для всіх Allow-statement-ів.)
    Далі лише для «GitHub-statement-ів»: тих, де `Principal.Federated` (рядок або список) містить ARN, що закінчується на
    `:oidc-provider/token.actions.githubusercontent.com`. Решту statement-ів (інші Principal) пропускаємо.
    * OIDC005  Action (рядок або список, без урахування регістру) не складається ЛИШЕ з "sts:AssumeRoleWithWebIdentity";
    * OIDC001  у Condition (в `StringEquals` або `StringLike`) немає ключа `token.actions.githubusercontent.com:sub`
               (тоді довіряємо токенам будь-яких репозиторіїв GitHub);
    * OIDC004  немає ключа `token.actions.githubusercontent.com:aud` зі значенням "sts.amazonaws.com", або воно інше
               (значення може бути рядком або списком; усі значення мають дорівнювати "sts.amazonaws.com");
    * для кожного значення `v` ключа `...:sub` (рядок або список, з обох операторів):
        OIDC002  `v` це "*", "repo:*" або починається з "repo:" і НЕ містить конкретного репозиторію, тобто після
                 "repo:" і до наступного ":" (або кінця) є `*` або немає "/" (наприклад, "repo:acme/*", "repo:*/shop:*");
        OIDC003  `v` вказує на конкретний, але ІНШИЙ репозиторій, ніж `repo`, тобто owner/name до ":" без `*`,
                 не рівний `repo` (порівняння без урахування регістру);
        OIDC007  `v` належить `repo`, але суфікс після "repo:<repo>:" занадто широкий: суфікс порожній або "*", починається
                 з "pull_request", або містить `*` і не починається з "ref:refs/tags/" (наприклад,
                 "ref:refs/heads/*", "environment:*", "*").
    Допустимі суфікси: точні ("ref:refs/heads/main", "environment:production") і теги з маскою ("ref:refs/tags/v*").
    Deny-statement-и не аналізуються. Порожня Condition і відсутність Condition це відсутність ключів.
"""


def audit_trust_policy(policy: dict, repo: str) -> list[str]:
    raise NotImplementedError
