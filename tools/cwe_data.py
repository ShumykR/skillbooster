# -*- coding: utf-8 -*-
"""Довідкові дані для звіту покриття CWE (docs/security-coverage.md).

Джерела:
- OWASP Top 10:2025: https://top10.owasp.org/2025 (розділ «List of Mapped CWEs» кожної категорії);
- MITRE CWE Top 25 (2025): https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html.

СТАТУС CWE НЕ ПИШЕТЬСЯ ТУТ: він обчислюється з тегів `*CWE:*` у docs/tasks-catalog.md.
Тут лише вибірка «ключових» CWE (мій вибір для Python-бекенду + AWS + K8s + LLM, а не OWASP),
Top 25, і текстові блоки про прогалини.
"""

# (id категорії, назва, к-сть змаплених CWE за owasp.org, [(cwe, назва)])
CATS = [
    ("A01", "Broken Access Control", 40, [
        (22, "Path Traversal"),
        (59, "Improper Link Resolution Before File Access (Link Following)"),
        (200, "Exposure of Sensitive Information"),
        (284, "Improper Access Control"),
        (352, "Cross-Site Request Forgery"),
        (359, "Exposure of Private Personal Information"),
        (377, "Insecure Temporary File"),
        (601, "Open Redirect"),
        (639, "Authorization Bypass Through User-Controlled Key (IDOR)"),
        (668, "Exposure of Resource to Wrong Sphere"),
        (732, "Incorrect Permission Assignment for Critical Resource"),
        (862, "Missing Authorization"),
        (863, "Incorrect Authorization"),
        (918, "Server-Side Request Forgery"),
        (1275, "Sensitive Cookie with Improper SameSite Attribute"),
    ]),
    ("A02", "Security Misconfiguration", 16, [
        (16, "Configuration"),
        (260, "Password in Configuration File"),
        (489, "Active Debug Code"),
        (611, "XML External Entity Reference (XXE)"),
        (614, "Sensitive Cookie in HTTPS Session Without 'Secure'"),
        (776, "XML Entity Expansion"),
        (942, "Permissive Cross-domain Policy (CORS)"),
        (1004, "Sensitive Cookie Without 'HttpOnly'"),
    ]),
    ("A03", "Software Supply Chain Failures", 6, [
        (1104, "Use of Unmaintained Third Party Components"),
        (1357, "Reliance on Insufficiently Trustworthy Component"),
        (1395, "Dependency on Vulnerable Third-Party Component"),
    ]),
    ("A04", "Cryptographic Failures", 32, [
        (319, "Cleartext Transmission of Sensitive Information"),
        (321, "Use of Hard-coded Cryptographic Key"),
        (327, "Broken or Risky Cryptographic Algorithm"),
        (330, "Insufficiently Random Values"),
        (338, "Cryptographically Weak PRNG"),
        (347, "Improper Verification of Cryptographic Signature"),
        (759, "One-Way Hash without a Salt"),
        (916, "Password Hash With Insufficient Computational Effort"),
    ]),
    ("A05", "Injection", 37, [
        (20, "Improper Input Validation"),
        (77, "Command Injection"),
        (78, "OS Command Injection"),
        (79, "Cross-site Scripting"),
        (89, "SQL Injection"),
        (94, "Code Injection"),
        (113, "HTTP Response Splitting / CRLF in headers"),
        (116, "Improper Encoding or Escaping of Output"),
    ]),
    ("A06", "Insecure Design", 39, [
        (73, "External Control of File Name or Path"),
        (269, "Improper Privilege Management"),
        (311, "Missing Encryption of Sensitive Data"),
        (362, "Race Condition"),
        (434, "Unrestricted Upload of File with Dangerous Type"),
        (522, "Insufficiently Protected Credentials"),
        (539, "Use of Persistent Cookies Containing Sensitive Information"),
        (602, "Client-Side Enforcement of Server-Side Security"),
        (657, "Violation of Secure Design Principles"),
        (799, "Improper Control of Interaction Frequency"),
        (841, "Improper Enforcement of Behavioral Workflow"),
        (1021, "Improper Restriction of Rendered UI Layers or Frames"),
        (1022, "Use of Web Link to Untrusted Target with window.opener Access"),
    ]),
    ("A07", "Authentication Failures", 36, [
        (259, "Use of Hard-coded Password"),
        (287, "Improper Authentication"),
        (294, "Authentication Bypass by Capture-replay"),
        (295, "Improper Certificate Validation"),
        (306, "Missing Authentication for Critical Function"),
        (307, "Excessive Authentication Attempts"),
        (308, "Use of Single-factor Authentication (MFA)"),
        (346, "Origin Validation Error"),
        (384, "Session Fixation"),
        (521, "Weak Password Requirements"),
        (613, "Insufficient Session Expiration"),
        (640, "Weak Password Recovery Mechanism"),
        (798, "Use of Hard-coded Credentials"),
    ]),
    ("A08", "Software or Data Integrity Failures", 14, [
        (345, "Insufficient Verification of Data Authenticity"),
        (494, "Download of Code Without Integrity Check"),
        (502, "Deserialization of Untrusted Data"),
        (829, "Inclusion of Functionality from Untrusted Control Sphere"),
        (915, "Mass Assignment"),
    ]),
    ("A09", "Security Logging and Alerting Failures", 5, [
        (117, "Improper Output Neutralization for Logs (log injection)"),
        (223, "Omission of Security-relevant Information"),
        (532, "Insertion of Sensitive Information into Log File"),
        (778, "Insufficient Logging"),
    ]),
    ("A10", "Mishandling of Exceptional Conditions", 24, [
        (209, "Error Message Containing Sensitive Information"),
        (248, "Uncaught Exception"),
        (460, "Improper Cleanup on Thrown Exception"),
        (550, "Server-generated Error Message with Sensitive Info"),
        (636, "Not Failing Securely ('Failing Open')"),
        (703, "Improper Check or Handling of Exceptional Conditions"),
        (756, "Missing Custom Error Page"),
    ]),
]

# CWE, які тегуються, але не входять до вибірки (потрібні лише імена для підказок на сайті)
EXTRA_NAMES = {
    23: "Relative Path Traversal",
    36: "Absolute Path Traversal",
    80: "Basic XSS (script-related HTML tags)",
    83: "Script in Attributes",
    285: "Improper Authorization",
    315: "Cleartext Storage of Sensitive Information in a Cookie",
    646: "Reliance on File Name or Extension of Externally-Supplied File",
    807: "Reliance on Untrusted Inputs in a Security Decision",
    770: "Allocation of Resources Without Limits or Throttling",
    564: "SQL Injection: Hibernate",
}

TOP25_NA = {787, 416, 125, 120, 121, 122, 476}  # пам'ять C/C++ та NULL-вказівники

# (місце, CWE, назва)
TOP25 = [
    (1, 79, "Cross-site Scripting"),
    (2, 89, "SQL Injection"),
    (3, 352, "CSRF"),
    (4, 862, "Missing Authorization"),
    (5, 787, "Out-of-bounds Write"),
    (6, 22, "Path Traversal"),
    (7, 416, "Use After Free"),
    (8, 125, "Out-of-bounds Read"),
    (9, 78, "OS Command Injection"),
    (10, 94, "Code Injection"),
    (11, 120, "Classic Buffer Overflow"),
    (12, 434, "Unrestricted Upload"),
    (13, 476, "NULL Pointer Dereference"),
    (14, 121, "Stack-based Buffer Overflow"),
    (15, 502, "Deserialization of Untrusted Data"),
    (16, 122, "Heap-based Buffer Overflow"),
    (17, 863, "Incorrect Authorization"),
    (18, 20, "Improper Input Validation"),
    (19, 284, "Improper Access Control"),
    (20, 200, "Exposure of Sensitive Information"),
    (21, 306, "Missing Authentication"),
    (22, 918, "SSRF"),
    (23, 77, "Command Injection"),
    (24, 639, "Authorization Bypass via User-Controlled Key"),
    (25, 770, "Allocation of Resources Without Limits"),
]

# Пріоритет: P1 = у Top 25 або A01/A05 і відсутнє; P2 = важливо для Python/FastAPI; P3 = процес і дизайн.
GAPS = [
    ("P3", "Threat modeling (A06 Insecure Design, CWE-657)", "Завдання №165 описане, але це документ без автоперевірки: STRIDE-розбір capstone (діаграма довіри, 10 загроз, мітигації) оформити як `docs/threat-model.md` у проєкті"),
]

CAPSTONE_GAPS = [
    ("M10", "threat model входить до критеріїв, але сам документ (завдання №165) пише студент для свого проєкту: готового зразка в репозиторії навмисно немає, щоб не спойлерити"),
]
