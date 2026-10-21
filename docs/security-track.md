# Трек Security Engineering і етап «Архітектура ПЗ»: покриття і план

Навіщо: у 2026 році значну частину коду пише AI, і цінність розробника зміщується до архітектури, проєктування й насамперед безпеки. До цього в курсі безпеці був відведений один етап core-треку (10 понять). Не було криптографії, сучасної ідентичності (OAuth 2.1, passkeys), threat modeling як дисципліни, supply chain після атак 2025–2026, безпеки роботи з coding-агентами, детекцій і реагування на інциденти. Архітектура була розкидана по патернах і системному дизайні: не було DDD, модульного моноліту, ADR, еволюції схем подій і fitness functions.

Що зроблено:
- Новий трек «🛡 Security Engineering» (`track: "sec"`), 6 етапів, другий у перемикачі. Колишній етап «Безпека бекенду» (розділ D, id `security`, поняття без змін, тому прогрес користувачів зберігся) став етапом 1 «AppSec».
- Етап «🏛️ Архітектура ПЗ і проєктування» (розділ U, id `architecture`) у треку Backend + DevOps, шостий після API.
- 42 нові завдання (№222–263): 29 з `*Тип:* автотест`, 13 практик і документів із чеклістами. №165 (threat model) переїхав з D у W.
- 57 нових понять і 114 питань самоперевірки (`tools/quizzes/architecture.py`, `sec_*.py`).
- Capstone: нова віха M12 «Security review і готовність до інцидентів», доповнено M0, M2, M7, M10 (тепер етап «Архітектура»).

Безпека LLM-систем (prompt injection, guardrails, MCP, red teaming) лишилась в AI-треку, етап 6 (розділ R). Етап 5 треку Security це безпека процесу розробки з агентами, а не безпека AI-продукту.

| Трек | № | Етап | Розділ | Завдання |
|---|---|---|---|---|
| core | 6 | Архітектура ПЗ і проєктування | U | 222–230 |
| sec | 1 | AppSec: вебзастосунки й API | D | 50–62, 142–146, 157–164, 166–168 |
| sec | 2 | Ідентичність, доступ і криптографія | V | 231–238 |
| sec | 3 | Secure design і threat modeling | W | 165, 239–244 |
| sec | 4 | Supply chain і secure SDLC | X | 245–251 |
| sec | 5 | Безпечна розробка з AI-агентами | Y | 252–257 |
| sec | 6 | Безпека інфраструктури, detection і response | Z | 258–263 |

## Мапа тем (стан на жовтень 2026)

Позначення: S2.4 = трек Security, етап 2, поняття 4 (з 1); A.3 = етап «Архітектура», поняття 3.

| Тема | Де |
|---|---|
| Quality attributes, ADR, C4, design docs | A.1–A.3, №229, №230 |
| Модульний моноліт, fitness functions, import-linter | A.4, A.12, №222, №1 |
| Hexagonal / ports & adapters | A.5, №228 |
| DDD: bounded context, ACL, aggregate, доменні події | A.6–A.7, №223, №153, №148 |
| Еволюція схем подій, CQRS, event sourcing | A.8–A.9, №224, №225 |
| Мультитенантність, RLS (`FORCE`), fail closed | A.10, №226 |
| Strangler fig, shadow traffic | A.11, №227 |
| Review дизайну від AI | A.12, №230 |
| OWASP Top 10:2025 (A03 supply chain, A10 винятки), API Top 10 | S1.1, S3.7, S4.1 |
| AEAD, envelope encryption, KMS, crypto-shredding | S2.1–S2.2, №231 |
| Timing-атаки, nonce reuse, length extension, слабкі алгоритми | S2.3, №237 |
| mTLS, PQC-гібрид X25519MLKEM768, crypto-agility | S2.4, №238 |
| JWT: alg confusion, kid/JWKS, aud/iss | S2.5, №232 |
| OAuth 2.1, RFC 9700, PKCE, refresh rotation з reuse detection, DPoP | S2.6, №233, №234 |
| Passkeys/WebAuthn, NIST SP 800-63-4 | S2.7, №236 |
| ReBAC (Zanzibar, OpenFGA), policy-as-code (OPA, Cedar) | S2.8, №235 |
| Workload identity, SPIFFE, OIDC federation | S2.9, №238, №78, №213 |
| OWASP ASVS 5.0, Secure by Design (CISA) | S3.1, №244 |
| Threat modeling: STRIDE, LINDDUN, attack trees | S3.2–S3.3, №165, №242 |
| Abuse cases, бізнес-логіка | S3.4, №243, №168 |
| Race conditions, TOCTOU, limit overrun | S3.5, №239 |
| Fail closed, обробка винятків | S3.6–S3.7, №241 |
| Десеріалізація, eval, SSTI, ReDoS | S3.8, №240, №201 |
| SLSA, provenance, Sigstore/cosign, trusted publishing, PEP 740 | S4.1, S4.5, №249, №250 |
| Lockfile з хешами, pylock.toml (PEP 751), dependency confusion, cooldown | S4.2, №246, №212 |
| Інциденти: tj-actions, Shai-Hulud, s1ngularity, LiteLLM на PyPI | S4.3, №251 |
| GitHub Actions: pin на SHA, `pull_request_target`, script injection, cache poisoning | S4.4, №245 |
| SBOM, VEX, reachability | S4.6, №247 |
| Security gates, SARIF, baseline | S4.7, №248 |
| EU CRA, coordinated disclosure, security.txt | S4.9, №251 |
| Lethal trifecta coding-агента, rules-file backdoor, невидимий Unicode | S5.1–S5.2, №252 |
| Дозволи агента, devcontainer, hooks | S5.3, S5.7, №253, №257 |
| Агенти в CI (issue triage) | S5.4, №254 |
| Вразливості AI-коду, security review, security-тести як специфікація | S5.5–S5.6, №255, №256 |
| MCP і розширення IDE як supply chain | S5.8, №199 |
| Контейнери, Kubernetes, admission policies | S6.1–S6.2, №69, №93, №98 |
| Cloud misconfig, IMDSv2 | S6.3, №258, №263 |
| Детекції (A09), Sigma, Falco, honeytokens | S6.5–S6.6, №259, №261 |
| CVSS 4.0, EPSS, CISA KEV | S6.7, №260 |
| Incident response (NIST SP 800-61r3), GDPR 72 год, CRA 24 год | S6.8, №262 |

## Перевірені факти (жовтень 2026)

- OWASP Top 10:2025: A03 Software Supply Chain Failures, A10 Mishandling of Exceptional Conditions; SSRF увійшла в A01.
- OWASP ASVS 5.0.0 вийшов у травні 2025 (17 розділів).
- NIST SP 800-63-4 фінальна (2025): синхронізовані passkeys допустимі для AAL2, на AAL2 треба пропонувати phishing-resistant варіант.
- RFC 9700 (OAuth 2.0 Security BCP), січень 2025.
- OpenSSL 3.5 за замовчуванням пропонує X25519MLKEM768; підписи сертифікатів лишаються класичними.
- PEP 751 (`pylock.toml`) прийнятий у березні 2025; підтримка в pip і uv ще експериментальна.
- EU Cyber Resilience Act: звітування про активно експлуатовані вразливості й серйозні інциденти через ENISA Single Reporting Platform з 11.09.2026 (24 години, 72 години, 14 днів після виправлення); більшість інших вимог з 11.12.2027.
- Veracode 2025 GenAI Code Security Report: близько 45% зразків коду від понад 100 моделей мали вразливості, без покращення в нових моделях.
- 2026: LiteLLM на PyPI (березень), axios на npm (березень), Mini Shai-Hulud через GitHub Actions TanStack (травень), атаки на агентів у CI через назву issue. Цифри з блогів вендорів, у завданні №251 студент сам звіряє джерела.

## Нотатки до реалізації ризикових автотестів

- №231: потрібна залежність `cryptography` (додати в `tasks/requirements.txt` разом із завданням). KMS це клас-заглушка в тестах.
- №232, №234, №236, №249: асиметричні підписи не реалізуємо. Перевірка підпису приходить параметром `verify(key, data, sig) -> bool`, а тести перевіряють, що її викликали з правильними даними і що без неї нічого не приймається.
- №239: гонку не можна залишати на волю планувальника. Заготовка має точку `pause()` між перевіркою і записом, тест через `threading.Barrier` гарантує, що обидва потоки пройшли перевірку. На правильному рішенні (атомарний `UPDATE ... WHERE`) тест проходить при будь-якому порядку. Прогнати 20 разів поспіль.
- №240, №237: як №146, заготовка навмисно вразлива. Тест на ReDoS міряє не час, а кількість кроків (або ліміт довжини й відсутність вкладених квантифікаторів), щоб не флейкати на повільному CI.
- №222, №241, №255: аналіз через `ast`, код студента ніколи не виконується.
- №254: мок-LLM повертає заготовлені tool calls, у тому числі шкідливі (`run_shell`, лейбл поза allowlist). Тести перевіряють, що вони відхилені, і що текст issue не потрапив у аргументи інших інструментів.
- №245: YAML-фікстури, порівняння з очікуваними знахідками за (правило, рядок). zizmor не ставимо.

## План автотестів (партії)

1. Безпека коду: 237, 239, 240, 241 (найближче до наявних t146 і t162).
2. Ідентичність: 232, 233, 234, 235, 236, 231.
3. Supply chain: 245, 246, 247, 248, 249.
4. AI-агенти в розробці: 252, 253, 255, 254.
5. Детекції й хмара: 258, 259, 260, 242.
6. Архітектура: 222, 223, 224, 225, 226, 227.

Процес і Definition of Done: `docs/task-authoring.md`. Коміт на партію, наприклад `Section W: auto-checked tasks 239-241`.
