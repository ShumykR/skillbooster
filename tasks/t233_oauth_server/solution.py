"""Завдання №233: сервер авторизації за OAuth 2.1 і RFC 9700 (Security BCP).

Потрібен лише потік Authorization Code + PKCE для ПУБЛІЧНИХ клієнтів (SPA, мобільний застосунок)
і ротація refresh-токенів. Усе в памʼяті, без HTTP. Годинник і генератор токенів передаються ззовні,
тому тести детерміновані.

`OAuthError(error, description="")`: уже написаний, `.error` це код з RFC 6749:
`invalid_request`, `invalid_client`, `invalid_grant`, `invalid_scope`, `unsupported_response_type`,
`unsupported_grant_type`.

`AuthorizationServer(clients, clock, token_factory, code_ttl=60, access_ttl=300, refresh_ttl=86400)`
    `clients`: `{client_id: {"redirect_uris": [str, ...], "scopes": [str, ...]}}`.
    `clock()` повертає секунди (число). `token_factory()` повертає новий унікальний рядок для
    кожного коду й токена (у production це `secrets.token_urlsafe`).
    Конструктор перевіряє реєстрацію (`ValueError`): `redirect_uris` непорожній список; кожен URI
    це `https://...` або loopback `http://127.0.0.1...`/`http://localhost...`; без `*`, без
    fragment (`#`). Wildcard і префікси в production це open redirect (CWE-601).

`authorize(client_id, redirect_uri, response_type, code_challenge, code_challenge_method,
           scope, user_id, state=None) -> str`
    Користувач уже автентифікований і погодився; метод видає код. Повертає URL для редіректу:
    `redirect_uri` + `?code=...` (+ `&state=...`, якщо `state` не `None`; значення
    URL-кодуються через `urllib.parse.urlencode`). Якщо в `redirect_uri` уже є `?`, додавай з `&`.
    Перевірки в такому порядку, помилка це `OAuthError`:
    1. невідомий `client_id`: `invalid_client`;
    2. `redirect_uri` НЕ збігається ТОЧНО (порівняння рядків, без нормалізації, без префіксів,
       без урахування регістру) з одним із зареєстрованих: `invalid_request`;
    3. `response_type != "code"` (зокрема `token`, тобто implicit): `unsupported_response_type`;
    4. PKCE обовʼязковий: `code_challenge` відсутній, або метод не рівно `"S256"` (`plain`, `s256`,
       `None`), або challenge не 43 символи base64url `[A-Za-z0-9_-]`: `invalid_request`;
    5. `scope` (рядок через пробіл або `None`) має бути підмножиною `scopes` клієнта, інакше
       `invalid_scope`. Збережений scope це відсортований рядок унікальних значень (`None` це `""`).
    Код живе `code_ttl` секунд: валідний, поки `clock() < issued + code_ttl`.

`token(grant_type, client_id, **params) -> dict`
    `grant_type="authorization_code"`, параметри `code`, `redirect_uri`, `code_verifier`.
    `grant_type="refresh_token"`, параметри `refresh_token`, необовʼязковий `scope`.
    Будь-який інший `grant_type` (`password`, `implicit`, `client_credentials`, `None`...):
    `unsupported_grant_type`. Успіх повертає
    `{"access_token", "token_type": "Bearer", "expires_in": access_ttl, "refresh_token", "scope"}`.

    authorization_code:
    * невідомий код, або код іншого клієнта: `invalid_grant` (код іншого клієнта НЕ втрачається);
    * код ОДНОРАЗОВИЙ. Після будь-якої спроби обміну, що знайшла код цього клієнта (успішної чи
      ні), код більше не діє. Повторне пред'явлення вже використаного коду це `invalid_grant`
      І відкликання всіх токенів, виданих за цим кодом (access і уся родина refresh, RFC 6749
      §4.1.2). Прострочений код: `invalid_grant`;
    * `redirect_uri` має ТОЧНО збігатися з тим, що був в `authorize`: інакше `invalid_grant`;
    * PKCE: `code_verifier` 43..128 символів `[A-Za-z0-9._~-]`, і `base64url(sha256(verifier))` без `=`
      дорівнює збереженому challenge (порівняння за постійний час): інакше `invalid_grant`.

    refresh_token (ротація, RFC 9700 §4.14):
    * кожен refresh-токен діє `refresh_ttl` секунд від видачі: валідний, поки `clock() < expiry`;
    * успішне використання повертає НОВИЙ refresh-токен і новий access-токен; старий refresh
      більше не діє. Усі токени, що походять від одного коду, це одна «родина»;
    * повторне пред'явлення вже використаного (ротованого) refresh-токена: `invalid_grant` і
      відкликання ВСІЄЇ родини (усі refresh і access цієї родини, зокрема новий, який уже в чесного
      клієнта). Це сигнал, що токен вкрали. Інші родини не чіпати;
    * невідомий чи прострочений токен: `invalid_grant`; токен іншого клієнта: `invalid_grant` без
      побічних ефектів (родина не відкликається);
    * `scope` (необовʼязковий) може лише звузити початковий: інакше `invalid_scope`, токен при цьому
      НЕ витрачається. Без `scope` лишається початковий.

`introspect(access_token) -> dict`
    Активний: `{"active": True, "client_id", "user_id", "scope", "exp"}`, де `exp = issued + access_ttl`.
    Активний, поки `clock() < exp` і родина не відкликана. Усе інше (невідомий, прострочений,
    відкликаний) це рівно `{"active": False}`.
"""


class OAuthError(Exception):
    def __init__(self, error: str, description: str = ""):
        super().__init__(f"{error}: {description}")
        self.error = error
        self.description = description


class AuthorizationServer:
    def __init__(self, clients: dict, clock, token_factory, code_ttl: int = 60, access_ttl: int = 300,
                 refresh_ttl: int = 86400):
        raise NotImplementedError

    def authorize(self, client_id, redirect_uri, response_type, code_challenge, code_challenge_method,
                  scope, user_id, state=None) -> str:
        raise NotImplementedError

    def token(self, grant_type, client_id, **params) -> dict:
        raise NotImplementedError

    def introspect(self, access_token) -> dict:
        raise NotImplementedError
