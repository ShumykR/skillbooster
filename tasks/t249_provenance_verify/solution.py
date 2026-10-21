"""Завдання №249: перевірка provenance перед деплоєм (SLSA + in-toto + DSSE).

Перед деплоєм образу pipeline має довести: «саме цей digest зібрано саме з цього
репозиторію, цієї гілки/тега, цим workflow і на довіреному builder, а не на форку».
Це аналог `cosign verify-attestation --certificate-identity ... --type slsaprovenance1`.
Асиметричні підписи тут не реалізуємо: перевірку підпису виконує функція-параметр
`verify(key, data: bytes, sig: bytes) -> bool` (у production це Sigstore/cosign).

Формат (спрощений DSSE envelope, словник):
    {"payloadType": "application/vnd.in-toto+json",
     "payload": "<base64 (стандартний алфавіт, з padding) від JSON statement>",
     "signatures": [{"keyid": "k1", "sig": "<base64 підпису>"}, ...]}

Statement (in-toto v1 зі SLSA provenance v1), потрібні поля:
    {"_type": "https://in-toto.io/Statement/v1",
     "subject": [{"name": "app", "digest": {"sha256": "<64 малих hex>"}}, ...],
     "predicateType": "https://slsa.dev/provenance/v1",
     "predicate": {
       "buildDefinition": {
         "externalParameters": {"workflow": {"repository": "https://github.com/acme/app",
                                              "ref": "refs/heads/main",
                                              "path": ".github/workflows/release.yml"}},
         "internalParameters": {"github": {"event_name": "push"}},
         "resolvedDependencies": [{"uri": "git+https://github.com/acme/app@refs/heads/main",
                                    "digest": {"gitCommit": "..."}}]},
       "runDetails": {"builder": {"id": "https://github.com/acme/builder/.github/workflows/b.yml@refs/tags/v1"}}}}

`pae(payload_type: str, payload: bytes) -> bytes`
    DSSE Pre-Authentication Encoding, саме ці байти підписуються:
    `b"DSSEv1 " + len(type) + b" " + type + b" " + len(payload) + b" " + payload`, довжини
    це десяткові числа в ASCII, `type` кодується UTF-8 (довжина в БАЙТАХ), `payload` це сирі
    байти ПІСЛЯ base64-декодування (не перезбірний JSON).

`verify_provenance(envelope, *, artifact_digest, policy, trusted_keys, verify) -> Decision`
    * `artifact_digest`: `"sha256:<64 малих hex>"`, те, що ДЕПЛОЇТЬСЯ (взяте з реєстру, не зі
      statement).
    * `policy` (словник): `allowed_builders` (непорожній список точних builder id, без `*`),
      `repository` (точний URL), `allowed_refs` (непорожній СПИСОК; елемент це точний ref або
      префікс із `*` ЛИШЕ в кінці, напр. `refs/tags/v*`), `workflow_path` (точний шлях),
      необовʼязково `allowed_events` (за замовчуванням `push`, `release`, `workflow_dispatch`).
      Неповна або хибна політика це `ValueError` (до будь-яких перевірок і викликів `verify`).
    * `trusted_keys`: `{keyid: key}`.
    * Повертає `Decision(allowed: bool, reasons: list[str])`. `allowed` лише коли `reasons`
      порожній. Функція НІКОЛИ не кидає виняток на кривих даних (крім хибної політики):
      будь-яка аномалія це відмова з кодом причини.

    Порядок і коди (fail closed):
    1. `artifact_digest` не формату вище: `["bad-artifact-digest"]`, `verify` не викликається.
    2. Envelope не словник; `payloadType` не `application/vnd.in-toto+json`; `payload` не
       коректний base64; `signatures` не непорожній список: `["bad-envelope"]`.
    3. Підпис. Для кожного запису з `signatures`, чий `keyid` є в `trusted_keys` (невідомі
       `keyid` ігноруються і `verify` для них не викликається), `sig` base64-декодується й
       викликається `verify(trusted_keys[keyid], pae(payloadType, сирий payload), sig)`.
       Достатньо одного запису, де `verify` повернув РІВНО `True`; виняток чи інше значення це
       «не пройшов». Жодного не пройшло: `["signature-invalid"]` і НІЧОГО більше (вміст
       непідписаного statement не аналізується й не розкривається).
    4. Statement: payload не JSON-обʼєкт чи `_type` не `https://in-toto.io/Statement/v1`:
       `["bad-statement"]`; `predicateType` не `https://slsa.dev/provenance/v1`:
       `["wrong-predicate-type"]`.
    5. Далі ЗБИРАЮТЬСЯ всі причини, у такому порядку (без дублікатів); відсутнє поле це теж
       порушення відповідної перевірки:
       `subject-mismatch`: жоден `subject` не має `digest.sha256`, що дорівнює hex з
           `artifact_digest` (інші алгоритми не рахуються; регістр має значення);
       `builder-not-allowed`: `runDetails.builder.id` не входить у `allowed_builders` ТОЧНО;
       `repository-mismatch`: `workflow.repository` не дорівнює `policy.repository` (форк);
       `ref-not-allowed`: `workflow.ref` не підпадає під `allowed_refs`;
       `workflow-path-mismatch`: `workflow.path` не дорівнює `policy.workflow_path`;
       `event-not-allowed`: `internalParameters.github.event_name` відсутній чи не з
           `allowed_events` (так відсікаються `pull_request` і `pull_request_target`);
       `source-mismatch`: жоден `resolvedDependencies[].uri` не дорівнює
           `git+<policy.repository>@<workflow.ref>`.
    Вхідні дані не мутуються.
"""
from typing import Callable, NamedTuple


class Decision(NamedTuple):
    allowed: bool
    reasons: list


def pae(payload_type: str, payload: bytes) -> bytes:
    raise NotImplementedError


def verify_provenance(envelope, *, artifact_digest: str, policy: dict, trusted_keys: dict,
                      verify: Callable[[object, bytes, bytes], bool]) -> Decision:
    raise NotImplementedError
