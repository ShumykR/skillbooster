"""Завдання №236: passkeys: перевірка WebAuthn на сервері.

Браузер і автентифікатор (Face ID, ключ Yubikey, менеджер паролів) роблять складну частину.
Але ВСІ рішення «пускати чи ні» приймає сервер, і саме тут роблять типові помилки: challenge
використовують двічі, не звіряють origin і `rpIdHash`, ігнорують прапорець UV, не помічають
клонування ключа за лічильником, а для «відновлення доступу» вмикають SMS (завдання з NIST SP
800-63-4: passkey має бути phishing-resistant, а SMS ні).

CBOR, COSE і справжні підписи не реалізуємо: відповіді приходять уже розібраними словниками,
а підпис перевіряє функція-параметр `verify(public_key, signed_data: bytes, signature: bytes)
-> bool` (лише строго `True` це успіх, виняток це невдача). Годинник `clock()` теж параметр.

Прапорці authenticator data (один байт): `UP = 0x01` (присутність користувача), `UV = 0x04`
(верифікація: PIN/біометрія), `BE = 0x08` (credential може бути синхронізований, backup
eligible), `BS = 0x10` (зараз синхронізований, backup state).

Формат `authenticator_data` (bytes): `rp_id_hash (32 байти, SHA-256 від rp_id) + flags (1 байт)
+ sign_count (4 байти, big-endian)`; довшим бути можна (розширення ігноруються), коротшим ні.

Відповіді (словники):
    реєстрація: {"client_data_json": bytes, "authenticator_data": bytes,
                 "credential_id": str, "public_key": bytes}
    автентифікація: {"client_data_json": bytes, "authenticator_data": bytes,
                     "credential_id": str, "signature": bytes, "user_handle": str | None}
`client_data_json` це JSON-обʼєкт у UTF-8 з полями `type` (`webauthn.create` для реєстрації,
`webauthn.get` для входу), `challenge` (рядок), `origin` (рядок) і необовʼязковим
`crossOrigin` (bool). Підписаним є `authenticator_data + SHA-256(client_data_json)`.

`class WebAuthnError(Exception)`: має атрибут `code` (рядок).

`class WebAuthnServer(rp_id, origins, *, clock, verify, new_challenge=None,
new_recovery_code=None, challenge_ttl=300, require_user_verification=True)`
    `origins`: допустимі origin (точний збіг рядка: `https://example.com`, а не
    `https://example.com/`, не `http://...`, не піддомен). `new_challenge()` повертає
    новий унікальний challenge (за замовчуванням криптографічно випадковий); `new_recovery_code()`
    повертає один код відновлення (за замовчуванням випадковий).

`begin_registration(user_id) -> dict` і `begin_authentication(user_id=None) -> dict`
    Видають challenge й запамʼятовують: призначення («register»/«auth»), `user_id`, час видачі.
    Реєстрація: `{"challenge", "rp_id", "user_verification"}`; вхід: те саме плюс
    `"allow_credentials"` (відсортований список id ключів користувача, а для `user_id=None`,
    «вхід без імені», порожній список). `user_verification` це `"required"`, якщо
    `require_user_verification`, інакше `"preferred"`.

`finish_registration(response) -> dict`
    Порядок перевірок (перша невдала дає `WebAuthnError.code`):
    1. `malformed`: немає/некоректні `client_data_json` (не JSON-обʼєкт, немає рядкових
       `type`/`challenge`/`origin`), `authenticator_data` (не bytes або коротша за 37 байтів),
       `credential_id` (не непорожній рядок) чи `public_key` (не непорожні bytes).
    2. `unknown_challenge`: такого challenge не видавали, він уже використаний, або видавали
       для іншого призначення. `challenge_expired`: `now - issued >= challenge_ttl`.
       Challenge ОДНОРАЗОВИЙ: він витрачається в момент пошуку, навіть якщо наступні перевірки
       провалилися (повторити ту саму відповідь не вдасться).
    3. `bad_type`: `type` не `webauthn.create`.
    4. `bad_origin`: `origin` не з `origins`, або `crossOrigin` це `True`.
    5. `bad_rp_id`: `rp_id_hash` не дорівнює `SHA-256(rp_id)`.
    6. `user_not_present`: нема UP. `user_not_verified`: потрібен UV, а його нема.
       `bad_flags`: BS без BE (така комбінація неможлива).
    7. `duplicate_credential`: цей `credential_id` уже зареєстровано (будь-ким).
    Успіх: зберігає ключ за `user_id` з challenge (початкові `sign_count`, `backup_eligible`,
    `backup_state` беруться з відповіді) і повертає `{"credential_id", "user_id",
    "backup_eligible", "backup_state", "sign_count"}`.

`finish_authentication(response) -> dict`
    Кроки 1, 2 (призначення «auth»), 3 (`webauthn.get`), 4, 5, 6 ті самі, далі:
    7. `unknown_credential`: `credential_id` не зареєстровано.
    8. `wrong_user`: challenge видавали для конкретного `user_id`, а ключ чужий; або
       `user_handle` задано й він не дорівнює власнику ключа.
    9. `bad_signature`: `verify(public_key, authenticator_data + SHA-256(client_data_json),
       signature)` не `True`. Підпис перевіряється ДО лічильника: підробка не має «спалювати»
       чесний ключ.
    10. `backup_eligibility_changed`: прапорець BE у відповіді не збігається з тим, що
        записано при реєстрації (BE незмінний).
    11. `cloned_credential`: лічильник підписів не зріс. Правило: або і збережений, і новий
        рівні 0 (автентифікатори, що не лічать, зокрема синхронізовані passkeys), або новий
        СТРОГО більший за збережений. Інакше можливе клонування ключа.
    Успіх: оновлює `sign_count` і `backup_state` і повертає `{"user_id", "credential_id",
    "user_verified": bool, "backed_up": bool}` (`backed_up` це BS з відповіді). Невдача не
    змінює збережений стан ключа.

Відновлення доступу БЕЗ SMS (одноразові коди):
`create_recovery_codes(user_id, count=8) -> list[str]`
    `count` викликів `new_recovery_code()`. Нові коди скасовують усі попередні коди
    користувача. Сервер зберігає лише ХЕШІ (SHA-256 від нормалізованого коду), не самі коди.
`use_recovery_code(user_id, code) -> bool`
    Нормалізація: нижній регістр, без `-` і пробілів. Правильний код спрацьовує один раз
    (повторно `False`); код іншого користувача, не-рядок, сміття це `False`. Порівняння за
    постійний час (`hmac.compare_digest`).
`list_credentials(user_id) -> list[str]`: відсортовані id ключів користувача.
`remove_credential(user_id, credential_id) -> None`
    Чужий чи невідомий id це `WebAuthnError("unknown_credential")`. Не можна видалити ОСТАННІЙ
    ключ користувача, якщо в нього немає невикористаних кодів відновлення:
    `WebAuthnError("last_credential")` (інакше людина лишається без входу).
"""
UP, UV, BE, BS = 0x01, 0x04, 0x08, 0x10


class WebAuthnError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


class WebAuthnServer:
    def __init__(self, rp_id, origins, *, clock, verify, new_challenge=None, new_recovery_code=None,
                 challenge_ttl=300, require_user_verification=True):
        raise NotImplementedError

    def begin_registration(self, user_id) -> dict:
        raise NotImplementedError

    def begin_authentication(self, user_id=None) -> dict:
        raise NotImplementedError

    def finish_registration(self, response) -> dict:
        raise NotImplementedError

    def finish_authentication(self, response) -> dict:
        raise NotImplementedError

    def create_recovery_codes(self, user_id, count=8) -> list:
        raise NotImplementedError

    def use_recovery_code(self, user_id, code) -> bool:
        raise NotImplementedError

    def list_credentials(self, user_id) -> list:
        raise NotImplementedError

    def remove_credential(self, user_id, credential_id) -> None:
        raise NotImplementedError
