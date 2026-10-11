# Покриття OWASP Top 10:2025 і CWE (зіставлення з навчальним шляхом)

> Файл **генерується** командою `python tools/gen_data.py` з тегів `*CWE:*` у `docs/tasks-catalog.md` і довідника `tools/cwe_data.py`. Руками не правити.

Стан: 75 завдань з автоперевіркою, 171 завдань у каталозі, capstone M0–M10.

## Джерела й обмеження

- **OWASP Top 10:2025** (восьма редакція, листопад 2025): сторінки категорій на https://top10.owasp.org/2025, розділ «List of Mapped CWEs». Усього змаплено 249 записів (інші джерела пишуть 248; розбіжність не досліджувалась).
- **CWE Top 25 (MITRE, 2025)**: https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html. Це рейтинг MITRE, а не OWASP, але він найближчий до «найпоширеніших CWE».
- Списки CWE зчитані зі сторінок інструментом вибірки тексту; номери варто звіряти з першоджерелом перед цитуванням.
- Усі 249 CWE не розписані: частина це Java/ASP.NET/Struts-специфіка. Нижче **ключова вибірка** для Python + AWS + K8s + LLM; **вибір зроблено автором проєкту, не OWASP**.
- У OWASP Top 10:2025 SSRF більше не окрема категорія (злитий в A01), з'явилися A03 Software Supply Chain Failures і A10 Mishandling of Exceptional Conditions.

## Позначки

- ✅ є завдання з автоперевіркою, яке тренує захист або виявлення саме цієї слабкості
- 🟡 часткове або непряме покриття автоперевіреним завданням (лише детектор, побічний ефект)
- 📝 описано в каталозі, але ще не реалізовано (немає коду й автоперевірки)
- 🔗 лише посилання на зовнішню лабораторію (PortSwigger тощо)
- ❌ у репозиторії немає нічого
- ➖ не стосується Python-бекенду (керована пам'ять)

## Підсумок за категоріями OWASP Top 10:2025

| Категорія | CWE в категорії (owasp.org) | Ключових у вибірці | ✅ | 🟡 | 📝 | 🔗 | ❌ |
|---|---|---|---|---|---|---|---|
| A01 Broken Access Control | 40 | 15 | 12 | 3 | 0 | 0 | 0 |
| A02 Security Misconfiguration | 16 | 8 | 7 | 1 | 0 | 0 | 0 |
| A03 Software Supply Chain Failures | 6 | 3 | 1 | 2 | 0 | 0 | 0 |
| A04 Cryptographic Failures | 32 | 8 | 5 | 3 | 0 | 0 | 0 |
| A05 Injection | 37 | 8 | 5 | 3 | 0 | 0 | 0 |
| A06 Insecure Design | 39 | 13 | 10 | 2 | 1 | 0 | 0 |
| A07 Authentication Failures | 36 | 13 | 9 | 2 | 2 | 0 | 0 |
| A08 Software or Data Integrity Failures | 14 | 5 | 2 | 3 | 0 | 0 | 0 |
| A09 Security Logging and Alerting Failures | 5 | 4 | 2 | 2 | 0 | 0 | 0 |
| A10 Mishandling of Exceptional Conditions | 24 | 7 | 4 | 3 | 0 | 0 | 0 |
| **Разом** | 249 | **84** | **57** | **24** | **3** | **0** | **0** |

З 84 ключових CWE: повноцінно покрито 57 (68%), частково 24, лише в каталозі 3, лише зовнішня лабораторія 0, немає взагалі 0.

### A01:2025 Broken Access Control (40 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-22 | Path Traversal | ✅ | t144 |
| CWE-59 | Improper Link Resolution Before File Access (Link Following) | ✅ | t144 |
| CWE-200 | Exposure of Sensitive Information | 🟡 | ~t7, ~t57, ~t61, №62 |
| CWE-284 | Improper Access Control | ✅ | t52 |
| CWE-352 | Cross-Site Request Forgery | ✅ | t143 |
| CWE-359 | Exposure of Private Personal Information | 🟡 | ~t61, №62 |
| CWE-377 | Insecure Temporary File | 🟡 | ~t56 |
| CWE-601 | Open Redirect | ✅ | t158 |
| CWE-639 | Authorization Bypass Through User-Controlled Key (IDOR) | ✅ | t16, №50, t52, ~t162, №59, t137 |
| CWE-668 | Exposure of Resource to Wrong Sphere | ✅ | t71, t84, t86, t87, №98 |
| CWE-732 | Incorrect Permission Assignment for Critical Resource | ✅ | №60, t84, t87 |
| CWE-862 | Missing Authorization | ✅ | t16, №50, t52, ~t163, t137 |
| CWE-863 | Incorrect Authorization | ✅ | t52, t137 |
| CWE-918 | Server-Side Request Forgery | ✅ | №50, t58 |
| CWE-1275 | Sensitive Cookie with Improper SameSite Attribute | ✅ | t143, ~t167 |

### A02:2025 Security Misconfiguration (16 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-16 | Configuration | 🟡 | ~t69, ~t71, ~t164, ~t93 |
| CWE-260 | Password in Configuration File | ✅ | t71, t54 |
| CWE-489 | Active Debug Code | ✅ | t164 |
| CWE-611 | XML External Entity Reference (XXE) | ✅ | t161 |
| CWE-614 | Sensitive Cookie in HTTPS Session Without 'Secure' | ✅ | t143 |
| CWE-776 | XML Entity Expansion | ✅ | t161 |
| CWE-942 | Permissive Cross-domain Policy (CORS) | ✅ | t57 |
| CWE-1004 | Sensitive Cookie Without 'HttpOnly' | ✅ | t143 |

### A03:2025 Software Supply Chain Failures (6 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-1104 | Use of Unmaintained Third Party Components | 🟡 | №70, ~t55 |
| CWE-1357 | Reliance on Insufficiently Trustworthy Component | 🟡 | ~t69, ~t73 |
| CWE-1395 | Dependency on Vulnerable Third-Party Component | ✅ | ~t70, t55 |

### A04:2025 Cryptographic Failures (32 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-319 | Cleartext Transmission of Sensitive Information | 🟡 | №67, №68, ~t57, ~t86, ~t87 |
| CWE-321 | Use of Hard-coded Cryptographic Key | 🟡 | ~t54, №89 |
| CWE-327 | Broken or Risky Cryptographic Algorithm | 🟡 | ~t56 |
| CWE-330 | Insufficiently Random Values | ✅ | t157 |
| CWE-338 | Cryptographically Weak PRNG | ✅ | t157 |
| CWE-347 | Improper Verification of Cryptographic Signature | ✅ | t41, t51 |
| CWE-759 | One-Way Hash without a Salt | ✅ | t157 |
| CWE-916 | Password Hash With Insufficient Computational Effort | ✅ | t157 |

### A05:2025 Injection (37 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-20 | Improper Input Validation | ✅ | №5, ~t7, ~t153, t156, ~t146, ~t145, ~t127 |
| CWE-77 | Command Injection | 🟡 | ~t56 |
| CWE-78 | OS Command Injection | 🟡 | ~t73, ~t56 |
| CWE-79 | Cross-site Scripting | ✅ | №50, t142 |
| CWE-89 | SQL Injection | ✅ | ~t16, №50, t146, ~t56 |
| CWE-94 | Code Injection | 🟡 | ~t56 |
| CWE-113 | HTTP Response Splitting / CRLF in headers | ✅ | t167 |
| CWE-116 | Improper Encoding or Escaping of Output | ✅ | t142 |

### A06:2025 Insecure Design (39 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-73 | External Control of File Name or Path | ✅ | t144 |
| CWE-269 | Improper Privilege Management | ✅ | t73, t52, №60, t93, №98 |
| CWE-311 | Missing Encryption of Sensitive Data | 🟡 | ~t84, ~t86 |
| CWE-362 | Race Condition | ✅ | ~t25, t26, t27, t28 |
| CWE-434 | Unrestricted Upload of File with Dangerous Type | ✅ | №13, t145 |
| CWE-522 | Insufficiently Protected Credentials | ✅ | t157 |
| CWE-539 | Use of Persistent Cookies Containing Sensitive Information | ✅ | t143 |
| CWE-602 | Client-Side Enforcement of Server-Side Security | ✅ | t168 |
| CWE-657 | Violation of Secure Design Principles | 📝 | №165 |
| CWE-799 | Improper Control of Interaction Frequency | ✅ | t37, t53 |
| CWE-841 | Improper Enforcement of Behavioral Workflow | 🟡 | ~t151 |
| CWE-1021 | Improper Restriction of Rendered UI Layers or Frames | ✅ | t57 |
| CWE-1022 | Use of Web Link to Untrusted Target with window.opener Access | ✅ | t142 |

### A07:2025 Authentication Failures (36 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-259 | Use of Hard-coded Password | ✅ | t71, t54 |
| CWE-287 | Improper Authentication | 🟡 | №45, ~t51 |
| CWE-294 | Authentication Bypass by Capture-replay | ✅ | t41 |
| CWE-295 | Improper Certificate Validation | 🟡 | №68, ~t56 |
| CWE-306 | Missing Authentication for Critical Function | ✅ | t163 |
| CWE-307 | Excessive Authentication Attempts | ✅ | t53 |
| CWE-308 | Use of Single-factor Authentication (MFA) | 📝 | №53 |
| CWE-346 | Origin Validation Error | 📝 | №45 |
| CWE-384 | Session Fixation | ✅ | t160 |
| CWE-521 | Weak Password Requirements | ✅ | t157 |
| CWE-613 | Insufficient Session Expiration | ✅ | t51, t160 |
| CWE-640 | Weak Password Recovery Mechanism | ✅ | t166 |
| CWE-798 | Use of Hard-coded Credentials | ✅ | t71, t73, №78, t54, №89 |

### A08:2025 Software or Data Integrity Failures (14 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-345 | Insufficient Verification of Data Authenticity | ✅ | t41, t51 |
| CWE-494 | Download of Code Without Integrity Check | 🟡 | ~t73, ~t55 |
| CWE-502 | Deserialization of Untrusted Data | 🟡 | ~t56 |
| CWE-829 | Inclusion of Functionality from Untrusted Control Sphere | 🟡 | ~t73 |
| CWE-915 | Mass Assignment | ✅ | ~t156, t162 |

### A09:2025 Security Logging and Alerting Failures (5 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-117 | Improper Output Neutralization for Logs (log injection) | ✅ | t159 |
| CWE-223 | Omission of Security-relevant Information | 🟡 | ~t30 |
| CWE-532 | Insertion of Sensitive Information into Log File | ✅ | t61 |
| CWE-778 | Insufficient Logging | 🟡 | ~t30, №101, №104 |

### A10:2025 Mishandling of Exceptional Conditions (24 CWE на owasp.org)

| CWE | Назва | Статус | Де |
|---|---|---|---|
| CWE-209 | Error Message Containing Sensitive Information | ✅ | t7 |
| CWE-248 | Uncaught Exception | ✅ | t7 |
| CWE-460 | Improper Cleanup on Thrown Exception | 🟡 | ~t30, ~t31 |
| CWE-550 | Server-generated Error Message with Sensitive Info | ✅ | t7 |
| CWE-636 | Not Failing Securely ('Failing Open') | 🟡 | ~t153, ~t35, ~t52, №109 |
| CWE-703 | Improper Check or Handling of Exceptional Conditions | 🟡 | ~t7, ~t35, ~t43, №109 |
| CWE-756 | Missing Custom Error Page | ✅ | t7 |

## CWE Top 25 (MITRE, 2025)

| № | CWE | Назва | Статус | Де |
|---|---|---|---|---|
| 1 | CWE-79 | Cross-site Scripting | ✅ | №50, t142 |
| 2 | CWE-89 | SQL Injection | ✅ | ~t16, №50, t146, ~t56 |
| 3 | CWE-352 | CSRF | ✅ | t143 |
| 4 | CWE-862 | Missing Authorization | ✅ | t16, №50, t52, ~t163, t137 |
| 5 | CWE-787 | Out-of-bounds Write | ➖ | — |
| 6 | CWE-22 | Path Traversal | ✅ | t144 |
| 7 | CWE-416 | Use After Free | ➖ | — |
| 8 | CWE-125 | Out-of-bounds Read | ➖ | — |
| 9 | CWE-78 | OS Command Injection | 🟡 | ~t73, ~t56 |
| 10 | CWE-94 | Code Injection | 🟡 | ~t56 |
| 11 | CWE-120 | Classic Buffer Overflow | ➖ | — |
| 12 | CWE-434 | Unrestricted Upload | ✅ | №13, t145 |
| 13 | CWE-476 | NULL Pointer Dereference | ➖ | — |
| 14 | CWE-121 | Stack-based Buffer Overflow | ➖ | — |
| 15 | CWE-502 | Deserialization of Untrusted Data | 🟡 | ~t56 |
| 16 | CWE-122 | Heap-based Buffer Overflow | ➖ | — |
| 17 | CWE-863 | Incorrect Authorization | ✅ | t52, t137 |
| 18 | CWE-20 | Improper Input Validation | ✅ | №5, ~t7, ~t153, t156, ~t146, ~t145, ~t127 |
| 19 | CWE-284 | Improper Access Control | ✅ | t52 |
| 20 | CWE-200 | Exposure of Sensitive Information | 🟡 | ~t7, ~t57, ~t61, №62 |
| 21 | CWE-306 | Missing Authentication | ✅ | t163 |
| 22 | CWE-918 | SSRF | ✅ | №50, t58 |
| 23 | CWE-77 | Command Injection | 🟡 | ~t56 |
| 24 | CWE-639 | Authorization Bypass via User-Controlled Key | ✅ | t16, №50, t52, ~t162, №59, t137 |
| 25 | CWE-770 | Allocation of Resources Without Limits | ✅ | t31, t37, №67, t93, ~t135 |

З 25 слабкостей 7 стосуються пам'яті C/C++ (➖, для Python не актуальні). З решти 18: ✅ 13, 🟡 5, 📝 0, 🔗 0, ❌ 0.

## Прогалини й пропоновані завдання

| Пріоритет | Що закриває | Ідея завдання з автоперевіркою |
|---|---|---|
| P3 | Threat modeling (A06 Insecure Design, CWE-657) | Завдання №165 описане, але це документ без автоперевірки: STRIDE-розбір capstone (діаграма довіри, 10 загроз, мітигації) оформити як `docs/threat-model.md` у проєкті |

## Прогалини в наскрізному проєкті (capstone)

| Віха | Чого бракує |
|---|---|
| M10 | threat model входить до критеріїв, але сам документ (завдання №165) пише студент для свого проєкту: готового зразка в репозиторії навмисно немає, щоб не спойлерити |

