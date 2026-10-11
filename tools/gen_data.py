#!/usr/bin/env python3
"""Генерує data.js для SkillBooster із tasks-catalog.md + ручних описів етапів."""
import json
import re
import sys

import os
HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "docs", "tasks-catalog.md")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "data.js")

LEVELS = {"🟢": 1, "🟡": 2, "🔴": 3}

# ---- парсинг каталогу завдань ------------------------------------------------
tasks_by_section = {}
section = None
group = None
item_re = re.compile(r"^(\d+)\.\s+(🟢|🟡|🔴)\s+(🤖\s+)?\*\*(.+?)\*\*\s*(.*)$")
marker_re = re.compile(r"\*(Перевірка|CWE|Патерн):\*")


def split_tags(text):
    return [x.strip() for x in text.replace(";", ",").split(",") if x.strip()]


for line in open(CATALOG, encoding="utf-8"):
    line = line.rstrip("\n")
    m = re.match(r"^## ([A-Z])\. ", line)
    if m:
        section = m.group(1)
        group = None
        tasks_by_section.setdefault(section, [])
        continue
    if line.startswith("## "):
        section = None
        continue
    m = re.match(r"^### (.+)$", line)
    if m and section:
        group = m.group(1).strip()
        continue
    m = item_re.match(line)
    if m and section:
        n, lvl, ai, title, rest = m.groups()
        title = title.strip().rstrip(":")
        parts = marker_re.split(rest)  # [опис, ключ, значення, ключ, значення ...]
        rest = parts[0]
        fields = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
        task = {
            "id": f"t{n}",
            "n": int(n),
            "level": LEVELS[lvl],
            "ai": bool(ai),
            "title": title,
            "desc": rest.strip().lstrip(":").strip().rstrip("."),
            "check": fields.get("Перевірка", "").rstrip("."),
        }
        if "CWE" in fields:
            task["cwe"] = split_tags(fields["CWE"])
        if "Патерн" in fields:
            task["pattern"] = split_tags(fields["Патерн"])
        if group:
            task["group"] = group
        tasks_by_section[section].append(task)

JENKINS_TASKS = [
    {
        "id": "j1", "n": 0, "level": 2, "ai": False,
        "title": "Jenkins у Docker",
        "desc": "підняти Jenkins через docker compose, створити перший job, підключити агент",
        "check": "Jenkins відкривається локально, job проходить",
    },
    {
        "id": "j2", "n": 0, "level": 2, "ai": False,
        "title": "Jenkinsfile (declarative)",
        "desc": "перенести пайплайн із завдань 73–75 (lint, test, build образу) на Jenkinsfile і вебхук з Git",
        "check": "зелений пайплайн за пушем у репозиторій",
    },
    {
        "id": "j3", "n": 0, "level": 3, "ai": False,
        "title": "Shared Library і credentials",
        "desc": "винести спільні кроки в Shared Library, секрети тримати в Jenkins Credentials",
        "check": "два пайплайни використовують одну бібліотеку, секретів у коді немає",
    },
]

# ---- описи етапів ------------------------------------------------------------
R = lambda name, url, kind, level, free, note: {
    "name": name, "url": url, "kind": kind, "level": level, "free": free, "note": note,
}

STAGES = [
    {
        "id": "python",
        "icon": "🐍",
        "title": "Python і FastAPI в production",
        "sections": ["A"],
        "why": "Ти вже пишеш на FastAPI. Різниця між джуніором і мідлом тут у тому, як код поводиться під навантаженням, при падіннях і при деплої: async, таймаути, graceful shutdown, профілювання.",
        "concepts": [
            "event loop, async/await, коли блокуючий код ламає async",
            "asyncio.gather, semaphore, таймаути та скасування задач",
            "Dependency Injection у FastAPI і підміна залежностей у тестах",
            "pydantic v2: валідація, налаштування (pydantic-settings), серіалізація",
            "Шарова архітектура: router → service → repository",
            "Єдиний формат помилок (RFC 7807) і коректні HTTP-статуси",
            "Background tasks, черги (Celery / ARQ / RQ) і коли що вибирати",
            "Профілювання: cProfile, py-spy; пошук витоків пам'яті",
            "Типізація (mypy), ruff, pre-commit",
            "Потокові відповіді, WebSocket, SSE",
        ],
        "resources": [
            R("Exercism: Python track", "https://exercism.org/tracks/python", "Практика", "🟢–🟡", "Безкоштовно", "Задачі з автотестами та ментор-рев'ю від людини"),
            R("Fluent Python (репозиторій прикладів)", "https://www.fluentpython.com", "Книга", "🟡–🔴", "Частково", "Репозиторій безкоштовний, книга платна"),
            R("FastAPI: офіційна документація", "https://fastapi.tiangolo.com", "Документація", "🟢–🟡", "Безкоштовно", "Розділи Advanced User Guide й Deployment"),
            R("CodeCrafters: Build your own HTTP server / Redis", "https://codecrafters.io", "Практика", "🔴", "Частково", "Відправка рішень платна, один челендж місяця безкоштовний"),
        ],
    },
    {
        "id": "testing",
        "icon": "🧪",
        "title": "Тестування і якість коду",
        "sections": ["K"],
        "why": "Тести — це запобіжник, який дозволяє змінювати код і не боятися. Без них неможливо ні рефакторити, ні безпечно користуватися AI-асистентами для коду.",
        "concepts": [
            "Піраміда тестів: unit, інтеграційні, e2e",
            "pytest: фікстури, параметризація, моки, покриття",
            "testcontainers: реальний Postgres і Redis у тестах",
            "Контрактні тести між сервісами",
            "Property-based тести (Hypothesis)",
            "Mutation testing: чи справді тести щось ловлять",
            "Характеризаційні тести для legacy-коду",
            "Code review: на що дивитися в PR",
        ],
        "resources": [
            R("pytest: документація", "https://docs.pytest.org", "Документація", "🟢–🟡", "Безкоштовно", "Фікстури, parametrize, плагіни"),
            R("Hypothesis", "https://hypothesis.readthedocs.io", "Документація", "🟡–🔴", "Безкоштовно", "Property-based тестування для Python"),
            R("testcontainers-python", "https://testcontainers-python.readthedocs.io", "Документація", "🟡", "Безкоштовно", "Контейнери з реальними залежностями прямо в тестах"),
        ],
    },
    {
        "id": "patterns",
        "icon": "🧩",
        "title": "Патерни проєктування (Python-стиль)",
        "sections": ["M"],
        "why": "Патерни це спільна мова для обговорення коду та готові відповіді на типові проблеми: як додати варіант поведінки, не чіпаючи старий код, як не дати створити невалідний стан, як ізолювати чужий API. У Python більшість із них записується функціями, декораторами й протоколами, без церемоній Java. Частина патернів (Repository, Outbox, Circuit Breaker, Cache-Aside) уже зустрічається в завданнях інших етапів і позначена тегом.",
        "concepts": [
            "Strategy, Observer, Decorator: поведінка як функції й підписки",
            "Repository та Unit of Work: де закінчується транзакція",
            "State machine: стани й переходи як дані",
            "Chain of Responsibility: middleware і порядок обробників",
            "Adapter та Anti-corruption layer: межа з чужими системами",
            "Specification: правила, що складаються з операторів",
            "Factory і реєстр плагінів: `__init_subclass__`, entry points",
            "Value Object і «parse, don't validate»: невалідний стан не існує",
            "Secure design (A06): fail closed, allowlist, мінімум довіри на межах",
            "Коли патерн зайвий: YAGNI і правило трьох",
        ],
        "resources": [
            R("Architecture Patterns with Python (Cosmic Python)", "https://www.cosmicpython.com", "Книга", "🟡–🔴", "Безкоштовно", "Repository, Unit of Work, події та Outbox на Python з тестами"),
            R("Refactoring.Guru: Design Patterns", "https://refactoring.guru/design-patterns/python", "Довідник", "🟢–🟡", "Частково", "Каталог патернів із прикладами на Python; книга платна, сайт читається безкоштовно"),
            R("python-patterns (faif)", "https://github.com/faif/python-patterns", "Репозиторій", "🟡", "Безкоштовно", "Короткі приклади патернів у стилі Python"),
            R("Parse, don't validate", "https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/", "Стаття", "🟡", "Безкоштовно", "Ідея завдання №156; приклади на Haskell, але принцип універсальний"),
        ],
    },
    {
        "id": "db",
        "icon": "🗄️",
        "title": "Бази даних: SQL, PostgreSQL, Redis",
        "sections": ["B"],
        "why": "Більшість production-проблем бекенду живуть у базі: повільні запити, блокування, міграції, що кладуть сайт. Це найвигідніша область для поглиблення.",
        "concepts": [
            "Нормалізація до 3NF (шість нормальних форм вчити не потрібно)",
            "ACID, рівні ізоляції, аномалії (lost update, non-repeatable read)",
            "Індекси: B-tree, композитні, часткові, покриваючі, GIN",
            "EXPLAIN ANALYZE: як читати план запиту",
            "Міграції без простою (expand → backfill → contract)",
            "Блокування, deadlock, optimistic і pessimistic locking",
            "N+1 у SQLAlchemy",
            "Connection pooling, PgBouncer",
            "Redis: cache-aside, TTL, інвалідація, cache stampede",
            "pgvector і повнотекстовий пошук",
            "Бекапи, PITR, read replica",
        ],
        "resources": [
            R("pgexercises.com", "https://pgexercises.com", "Практика", "🟢–🟡", "Безкоштовно", "SQL-задачі прямо на PostgreSQL у браузері"),
            R("Use The Index, Luke", "https://use-the-index-luke.com", "Книга/Практика", "🟡–🔴", "Безкоштовно", "Глибоко про індекси та плани запитів"),
            R("PostgreSQL Internals (Egor Rogov)", "https://postgrespro.com/community/books/internals", "Книга", "🔴", "Безкоштовно", "MVCC, WAL, блокування, планувальник"),
            R("CMU 15-445 Database Systems", "https://15445.courses.cs.cmu.edu", "Курс", "🔴", "Безкоштовно", "Лекції та проєкти, проєкти на C++"),
            R("DataLemur", "https://datalemur.com", "Практика", "🟡", "Частково", "SQL-задачі рівня співбесід"),
        ],
    },
    {
        "id": "api",
        "icon": "🔌",
        "title": "API-дизайн та інтеграції",
        "sections": ["C"],
        "why": "Бекенд рідко живе сам: вебхуки, платежі, OAuth, сторонні API. Тут потрібно вміти робити інтеграції, які не ламаються від чужих збоїв.",
        "concepts": [
            "REST: ресурси, статуси, ідемпотентність, версіонування",
            "OpenAPI як контракт; лінтинг специфікації",
            "Вебхуки: підпис HMAC, replay-захист, швидка відповідь + черга",
            "Retries, експоненційний backoff, jitter, circuit breaker",
            "Rate limits і заголовок Retry-After",
            "OAuth2 / OIDC: authorization code + PKCE",
            "GraphQL і DataLoader (N+1)",
            "gRPC і protobuf: бачити, коли доречний",
        ],
        "resources": [
            R("Microsoft REST API Guidelines", "https://github.com/microsoft/api-guidelines", "Гайд", "🟡", "Безкоштовно", "Практичні правила дизайну API"),
            R("Stripe API docs (webhooks, idempotency)", "https://docs.stripe.com/webhooks", "Документація", "🟡", "Безкоштовно", "Еталонні приклади вебхуків та idempotency keys"),
            R("OAuth 2.0 Simplified", "https://www.oauth.com", "Книга", "🟡", "Безкоштовно", "Зрозуміле пояснення OAuth"),
        ],
    },
    {
        "id": "linux",
        "icon": "🐧",
        "title": "Linux, мережа і Docker",
        "sections": ["E"],
        "why": "Коли сервіс «не працює», проблема часто не в коді, а в сервері, мережі чи контейнері. Це основа для DevOps.",
        "concepts": [
            "Командний рядок: grep, awk, sed, find, xargs, пайпи",
            "Процеси, сигнали, systemd, journald",
            "Диск, пам'ять, OOM killer, ліміти файлових дескрипторів",
            "DNS, TCP, TLS: що відбувається за curl -v",
            "Nginx як reverse proxy; HTTPS і Let's Encrypt",
            "Dockerfile: multi-stage, non-root, кеш шарів, .dockerignore",
            "docker compose: healthchecks і залежності",
            "Сканування образів (Trivy)",
        ],
        "resources": [
            R("SadServers", "https://sadservers.com", "Практика", "🟡–🔴", "Безкоштовно", "Зламаний сервер, який треба полагодити"),
            R("OverTheWire: Bandit", "https://overthewire.org/wargames/bandit/", "Гра", "🟢", "Безкоштовно", "Linux і SSH через рівні"),
            R("iximiuz Labs", "https://labs.iximiuz.com", "Лаби", "🔴", "Частково", "Free: 1 playground, 1 година на день. 150+ челенджів у платному плані ($10/міс)"),
            R("KodeKloud 100 Days of DevOps", "https://kodekloud.com/100-days-of-devops", "Лаби", "🟡", "Безкоштовно", "Одна реальна задача на день з автоперевіркою"),
        ],
    },
    {
        "id": "cicd",
        "icon": "⚙️",
        "title": "CI/CD (GitHub Actions, Jenkins)",
        "sections": ["F"],
        "extra_tasks": JENKINS_TASKS,
        "why": "Автоматичні збірки, тести й деплой — це те, що відрізняє команду з культурою інженерії. Основа — GitHub Actions; Jenkins — необов'язковий модуль для legacy.",
        "concepts": [
            "Пайплайн: lint → test → build → publish → deploy",
            "GitHub Actions: workflows, матриці, кеш, secrets, environments",
            "Теги образів за версією та sha; реєстри GHCR / ECR",
            "OIDC до AWS замість довгоживучих ключів",
            "Стратегії релізів: rolling, blue-green, canary, відкат",
            "Preview-середовища на PR",
            "Semantic versioning, автоматичний changelog",
            "(Опційно) Jenkins: Jenkinsfile, агенти, Shared Libraries",
        ],
        "resources": [
            R("GitHub Skills", "https://skills.github.com", "Курси", "🟢–🟡", "Безкоштовно", "Інтерактивні курси з Actions прямо в репозиторії"),
            R("GitHub Actions: документація", "https://docs.github.com/actions", "Документація", "🟡", "Безкоштовно", "Workflows, OIDC, reusable workflows"),
            R("Jenkins: Pipeline документація", "https://www.jenkins.io/doc/book/pipeline/", "Документація", "🟡", "Безкоштовно", "Для необов'язкового модуля Jenkins"),
        ],
    },
    {
        "id": "security",
        "icon": "🔐",
        "title": "Безпека бекенду",
        "sections": ["D"],
        "why": "Одна помилка в безпеці може коштувати компанії репутації та грошей. Це одна з тем з відео 2023 року, яка не застаріла.",
        "concepts": [
            "OWASP Top 10 і OWASP API Top 10",
            "JWT: access/refresh, ротація, відкликання",
            "RBAC і ABAC; broken access control, IDOR",
            "Паролі: argon2, throttling, MFA (TOTP)",
            "Секрети: Secrets Manager, SOPS, не тримати в git",
            "Залежності: pip-audit, Dependabot, lockfile з хешами",
            "SAST/DAST: bandit, semgrep, OWASP ZAP",
            "CORS, CSP, заголовки безпеки",
            "SSRF і захист metadata-ендпоінта хмари",
            "Мінімальні права в IAM",
        ],
        "resources": [
            R("PortSwigger Web Security Academy", "https://portswigger.net/web-security", "Лаби", "🟢–🔴", "Безкоштовно", "250+ лаб: SQLi, SSRF, JWT, OAuth, API testing"),
            R("OWASP Juice Shop", "https://owasp.org/www-project-juice-shop/", "Лаби", "🟡", "Безкоштовно", "Вразливий застосунок з 100+ челенджами, запускається в Docker"),
            R("OWASP crAPI", "https://github.com/OWASP/crAPI", "Лаби", "🟡–🔴", "Безкоштовно", "Вразливий API за OWASP API Top 10"),
        ],
    },
    {
        "id": "cloud",
        "icon": "☁️",
        "title": "Хмара (AWS) та Terraform",
        "sections": ["G"],
        "why": "Ти вже працював з AWS. Тут піднімаємо рівень: інфраструктура як код, мережа, мінімальні права, відмовостійкість і контроль витрат.",
        "concepts": [
            "VPC: підмережі, NAT, security groups, route tables",
            "Terraform: модулі, remote state з блокуванням, workspaces",
            "ECS Fargate / EKS, ALB, автомасштабування",
            "RDS: Multi-AZ, бекапи, приватні підмережі",
            "S3: політики, версіонування, lifecycle, CloudFront",
            "Lambda + SQS + DLQ, ідемпотентність",
            "Secrets Manager та Parameter Store",
            "Budget alerts і розбір витрат",
            "Disaster recovery: RTO, RPO",
        ],
        "resources": [
            R("AWS Workshops", "https://workshops.aws", "Лаби", "🟡–🔴", "Безкоштовно", "Запускаються у твоєму акаунті, стеж за Free Tier"),
            R("AWS Skill Builder", "https://skillbuilder.aws", "Курси", "🟢–🟡", "Частково", "Базова частина безкоштовна"),
            R("Terraform tutorials (HashiCorp)", "https://developer.hashicorp.com/terraform/tutorials", "Курси", "🟡", "Безкоштовно", "Покрокові туторіали"),
            R("KodeKloud 100 Days of Cloud", "https://kodekloud.com/100-days-of-cloud", "Лаби", "🟡", "Безкоштовно", "AWS і Azure, одна задача на день"),
        ],
    },
    {
        "id": "k8s",
        "icon": "☸️",
        "title": "Kubernetes",
        "sections": ["H"],
        "why": "Kubernetes — стандарт для запуску контейнерів у компаніях. Для бекендера достатньо впевнено деплоїти, налагоджувати і розуміти ресурси.",
        "concepts": [
            "Pod, Deployment, Service, Ingress, ConfigMap, Secret",
            "Probes: readiness, liveness, startup",
            "requests і limits; OOMKilled, CrashLoopBackOff",
            "Helm-чарти й values для dev/prod",
            "HPA і KEDA: масштабування за навантаженням і чергою",
            "RBAC, NetworkPolicy, PodSecurity",
            "GitOps: ArgoCD",
            "Rolling update без втрат: PDB, preStop",
        ],
        "resources": [
            R("Killercoda", "https://killercoda.com", "Лаби", "🟡–🔴", "Безкоштовно", "Справжні VM у браузері: сценарії CKA/CKAD/CKS, Helm, ArgoCD"),
            R("Kubernetes The Hard Way", "https://github.com/kelseyhightower/kubernetes-the-hard-way", "Лаби", "🔴", "Безкоштовно", "Кластер вручну, потрібні власні VM"),
            R("Kubernetes: офіційні tutorials", "https://kubernetes.io/docs/tutorials/", "Документація", "🟢–🟡", "Безкоштовно", "Інтерактивні модулі для початку"),
        ],
    },
    {
        "id": "observability",
        "icon": "📈",
        "title": "Observability і надійність",
        "sections": ["I"],
        "why": "Коли щось ламається о третій ночі, виручають логи, метрики й траси. Цей етап вчить помічати проблему раніше за клієнтів.",
        "concepts": [
            "Структуровані логи й correlation id",
            "Метрики: RED/USE, Prometheus, PromQL",
            "Трейсинг: OpenTelemetry, Tempo/Jaeger",
            "Дашборди й алерти в Grafana; алерти за SLO",
            "SLI, SLO, error budget",
            "Incident response і postmortem",
            "Sentry для помилок",
            "Навантажувальні тести (k6, Locust) і chaos-тести",
        ],
        "resources": [
            R("Grafana Play", "https://play.grafana.org", "Пісочниця", "🟡", "Безкоштовно", "Живі дашборди для практики"),
            R("OpenTelemetry Demo", "https://opentelemetry.io/docs/demo/", "Лаби", "🟡–🔴", "Безкоштовно", "Повний мікросервісний стенд для трейсингу"),
            R("Google SRE Book", "https://sre.google/sre-book/table-of-contents/", "Книга", "🟡–🔴", "Безкоштовно", "SLO, моніторинг, incident response"),
        ],
    },
    {
        "id": "sysdesign",
        "icon": "🏗️",
        "title": "Системний дизайн і розподілені системи",
        "sections": ["J"],
        "why": "Мікросервіси, черги, кеші, масштабування: з відео 2023 року ця тема лишається актуальною. Тут вчимося проєктувати й міркувати про компроміси.",
        "concepts": [
            "Моноліт vs мікросервіси vs serverless",
            "Горизонтальне й вертикальне масштабування, балансування навантаження",
            "Черги й брокери: Kafka, RabbitMQ, SQS; гарантії доставки",
            "Консистентність: CAP, eventual consistency",
            "Saga, outbox, idempotency",
            "Кешування і CDN",
            "Шардування й реплікація",
            "Backpressure, circuit breaker, load shedding",
        ],
        "resources": [
            R("Gossip Glomers (Fly.io)", "https://fly.io/dist-sys/", "Челенджі", "🔴", "Безкоштовно", "Розподілені системи з тестером Maelstrom, на Python теж можна"),
            R("System Design Primer", "https://github.com/donnemartin/system-design-primer", "Гайд", "🟡–🔴", "Безкоштовно", "Теорія, картки Anki, задачі"),
            R("MIT 6.5840 Distributed Systems", "https://pdos.csail.mit.edu/6.824/", "Курс", "🔴", "Безкоштовно", "Лаби Raft і KV-сховище, мова Go"),
        ],
    },
    {
        "id": "ai",
        "icon": "🤖",
        "title": "AI-інженерія для бекенду",
        "sections": ["L"],
        "why": "Нова обов'язкова навичка 2025–2026: вбудовувати LLM у бекенд, будувати RAG, агентів і MCP-сервери, контролювати витрати та безпеку, і ефективно працювати з AI-асистентами для коду.",
        "concepts": [
            "LLM API: повідомлення, streaming, tool calling, structured output",
            "Embeddings і векторний пошук (pgvector)",
            "RAG: чанкінг, hybrid search, reranking, цитування",
            "Evals: еталонні набори, LLM-as-judge, регресії промптів у CI",
            "Агенти: цикл план → інструмент → спостереження, ліміти кроків",
            "MCP: сервери, tools, resources",
            "Безпека LLM: prompt injection, небезпечні tool-виклики, PII",
            "Витрати: облік токенів, кешування, fallback на дешевшу модель",
            "Робота з AI-асистентами: AGENTS.md / CLAUDE.md, малі кроки, тести як запобіжник",
        ],
        "resources": [
            R("DataTalksClub: AI Dev Tools Zoomcamp 2026", "https://github.com/DataTalksClub", "Курс", "🟡", "Безкоштовно", "AI-асистенти, FastAPI, Docker, AWS, OpenTelemetry, MCP. Self-paced доступний завжди"),
            R("DataTalksClub: LLM Zoomcamp", "https://datatalks.club/docs/courses/llm-zoomcamp/", "Курс", "🟡–🔴", "Безкоштовно", "Agentic RAG, pgvector, evals, моніторинг. API коштуватиме $1–5"),
            R("Claude Academy", "https://academy.claude.com", "Курс", "🟢–🟡", "Безкоштовно", "Building with the Claude API, Intro to MCP, Claude Code in Action"),
            R("Hugging Face: MCP Course", "https://huggingface.co/learn/mcp-course", "Курс", "🟡", "Безкоштовно", "Будуєш MCP-сервери, є сертифікат"),
            R("Hugging Face: Agents Course", "https://huggingface.co/learn/agents-course", "Курс", "🟡", "Безкоштовно", "Агенти з нуля"),
            R("LangChain Academy", "https://academy.langchain.com", "Курс", "🟡", "Безкоштовно", "LangGraph: стан, пам'ять, human-in-the-loop"),
            R("Gandalf by Lakera", "https://gandalf.lakera.ai", "Гра", "🟢", "Безкоштовно", "Практика prompt injection"),
        ],
    },
]

LEGACY = [
    ["ECMAScript 6, Node.js, Express, NestJS", "replace", "Python 3.12+, FastAPI (у тебе вже є), pydantic v2"],
    ["TypeScript", "replace", "Типізація Python: type hints, mypy"],
    ["SOLID, ООП, шаблони проєктування", "keep", "Лишається, але в Python акцент на композицію та прості модулі"],
    ["ESLint, Prettier, SonarQube", "replace", "ruff, mypy, pre-commit; SonarQube опційно"],
    ["NPM, аудит вразливостей", "replace", "uv / pip, pip-audit, Dependabot, lockfile"],
    ["Events, callbacks, проміси, async/await", "replace", "asyncio, структура конкурентності, блокуючий код в async"],
    ["HTTP/HTTPS, headers, статуси, DNS, TLS, TCP", "keep", "Базова основа, залишається повністю (етап «Linux і Docker»)"],
    ["WebSocket", "keep", "WebSocket і SSE у FastAPI"],
    ["Сесії, cookies, form-data", "keep", "Cookies для сесій у вебі; для API частіше токени"],
    ["Шаблонизація, SSR", "skip", "Для API-бекенду не потрібно"],
    ["Буфери, стріми, XML", "skip", "Потокові відповіді лишаємо; XML майже не вживається"],
    ["Треди, child-процеси", "replace", "GIL, multiprocessing, asyncio, черги завдань"],
    ["Нормальні форми: шість", "replace", "Достатньо до 3NF, далі індекси та плани запитів"],
    ["ACID, індекси, транзакції, міграції", "keep", "Лишається та поглиблюється (етап «Бази даних»)"],
    ["Sequelize / ORM", "replace", "SQLAlchemy 2.0, Alembic"],
    ["REST, GraphQL, RPC, Swagger/OpenAPI", "keep", "Лишається; додаємо gRPC для порівняння"],
    ["HATEOAS", "skip", "Майже не зустрічається на практиці"],
    ["OWASP Top 10, OAuth, JWT, RBAC", "keep", "Лишається, додаємо OWASP API Top 10 та безпеку LLM"],
    ["Kafka, RabbitMQ, Redis, CDN", "keep", "Лишається (етапи «БД» та «Системний дизайн»)"],
    ["Nginx, Apache", "replace", "Nginx або Caddy; Apache рідко потрібен"],
    ["Docker, Kubernetes", "keep", "Лишається, глибше: Helm, ArgoCD, KEDA"],
    ["AWS, Azure, GCP", "keep", "AWS вже знаєш; Terraform додатково; Azure/GCP за потреби"],
    ["Jenkins, GitLab, Bitbucket, GitHub", "replace", "Основа GitHub Actions та GitLab CI; Jenkins як опційний модуль"],
    ["Логи, телеметрія, моніторинг", "keep", "Підсилюємо: OpenTelemetry, Prometheus, Grafana, SLO"],
    ["(немає в оригіналі)", "new", "LLM API, RAG, агенти, MCP, evals, безпека LLM, AI-асистенти для коду"],
]


CAPSTONE = {
    "title": "Наскрізний проєкт: AI-бекенд «Knowledge Assistant»",
    "intro": "Один сервіс, який росте разом з етапами: користувачі завантажують документи й ставлять питання, а бекенд відповідає з цитатами джерел. Це повний набір production-навичок у одному репозиторії й готове портфоліо.",
    "milestones": [
        {"id": "m0", "stage": "python", "title": "Скелет сервісу", "items": [
            "FastAPI-застосунок із шарами router → service → repository, конфіг через pydantic-settings",
            "ruff, mypy, pytest і pre-commit; перший тест і зелений CI",
            "Єдиний формат помилок (RFC 7807) та health-ендпоінти"]},
        {"id": "m1", "stage": "db", "title": "Дані й пошук", "items": [
            "PostgreSQL + pgvector, міграції Alembic (без простою: expand → contract)",
            "Таблиці users, documents, chunks, chat_sessions; обґрунтовані індекси (EXPLAIN у README)",
            "Redis: кеш відповідей із захистом від cache stampede"]},
        {"id": "m2", "stage": "security", "title": "Доступ і захист", "items": [
            "JWT access/refresh, ролі (user, admin), перевірка власника документа (без IDOR)",
            "Rate limiter на Redis і idempotency key для POST /documents",
            "Маскування PII у логах, секрети лише з env/Secrets Manager, pip-audit у CI",
            "Паролі через scrypt/argon2 з перехешуванням (№157), сесії або refresh-токени з ротацією, відкликанням і абсолютним терміном (№160, №51); якщо є cookie, то CSRF-захист і прапорці (№143)",
            "Окремі pydantic-моделі запиту й відповіді з extra=forbid (№162); тест у CI, що ВСІ маршрути або захищені, або в явному списку публічних (№163)"]},
        {"id": "m3", "stage": "ai", "title": "Інгест документів", "items": [
            "Завантаження файлу (потоково, ліміти розміру, presigned URL до S3)",
            "Тип за вмістом (magic bytes), безпечне ім'я файлу, шлях лише під контрольованою текою (№145, №144); якщо додаси завантаження за URL, то із захистом від SSRF (№58)",
            "Чанкінг, embeddings, запис у pgvector фоновим воркером (ARQ/Celery) з retry і DLQ",
            "Outbox для події document.indexed"]},
        {"id": "m4", "stage": "ai", "title": "RAG-відповіді", "items": [
            "POST /ask: hybrid search (BM25 + вектор), reranking, відповідь із цитатами",
            "Streaming через SSE, structured output із валідацією та повтором",
            "LLM підключається через LLM_BASE_URL / LLM_API_KEY / LLM_MODEL (твій проксі)",
            "Відповідь моделі екранується перед показом у вебі (№142), а все витягнуте з документів вважається недовіреним вмістом (prompt injection)",
            "OWASP LLM Top 10: системний промпт не містить секретів і його витік нічого не дає; відповіді й цитати показують лише документи, до яких користувач має доступ (фільтр за власником ще в пошуку, не після); ліміти токенів, розміру контексту й запитів (unbounded consumption); завантажений документ не може отруїти індекс інших користувачів"]},
        {"id": "m5", "stage": "ai", "title": "Якість і витрати", "items": [
            "Еталонний набір із 30 питань, метрики recall@k, LLM-as-judge; eval у CI проти мок-моделі",
            "Облік токенів і бюджет на користувача, fallback на дешевшу модель",
            "Кешування однакових запитів та prompt caching там, де підтримується"]},
        {"id": "m6", "stage": "ai", "title": "Агент і MCP", "items": [
            "Агент з інструментами (пошук, статистика) і лімітами кроків",
            "Політика авторизації викликів інструментів і набір тестів на prompt injection",
            "MCP-сервер, що відкриває пошук по документах зовнішнім клієнтам",
            "Надмірні повноваження агента (excessive agency): інструменти лише з мінімальними правами, дії зі змінами потребують підтвердження людини, журнал кожного виклику з користувачем і аргументами; тест: документ із інструкцією «видали все» не запускає жодного інструмента запису"]},
        {"id": "m7", "stage": "cicd", "title": "Контейнери й CI/CD", "items": [
            "Multi-stage Dockerfile (non-root, образ < 200 МБ), docker compose: app, worker, postgres, redis",
            "GitHub Actions: lint → test → build → Trivy → push у GHCR, теги за версією й sha",
            "Безпека ланцюга постачання: gitleaks, bandit/semgrep і pip-audit у CI, дії закріплені на sha (№54, №55, №56, №73), Dockerfile проходить власний лінтер (№69)",
            "SBOM образу (syft або trivy sbom) зберігається як артефакт збірки; образ підписується cosign (keyless через OIDC), а деплой перевіряє підпис",
            "DAST: OWASP ZAP baseline-скан проти піднятого в CI застосунку (compose), звіт як артефакт, знахідки середньої серйозності й вище блокують merge або мають обґрунтований виняток",
            "(Опційно) той самий пайплайн на Jenkinsfile"]},
        {"id": "m8", "stage": "cloud", "title": "Хмара та Kubernetes", "items": [
            "Terraform: VPC, RDS, ECS або EKS, Secrets Manager; remote state із блокуванням",
            "Деплой за merge у main через OIDC, ручне підтвердження для prod",
            "Helm-чарт, probes, requests/limits, HPA або KEDA за довжиною черги воркера",
            "Аудит перед деплоєм: політики для Terraform plan (№84), маніфести Kubernetes (№93), конфігурація prod без debug/docs/CORS * (№164)"]},
        {"id": "m9", "stage": "observability", "title": "Спостережуваність", "items": [
            "Структуровані логи з correlation id, метрики RED у Prometheus, трасування OpenTelemetry",
            "Дашборд Grafana, SLO та алерт за error budget; Sentry",
            "Логи проходять екранування керуючих символів (№159) і маскування PII (№61); є алерти на безпекові події (сплески 401/403, перебір паролів)",
            "Навантажувальний тест (k6), chaos-експеримент (вимкнути Redis) і короткий postmortem"]},
        {"id": "m10", "stage": "sysdesign", "title": "Архітектурна документація", "items": [
            "ADR: чому саме ці технології; діаграма системи",
            "Threat model за STRIDE (№165): межі довіри на діаграмі, 10 загроз з мітигаціями, перелік прийнятих ризиків",
            "Оцінка навантаження (RPS, обсяг даних, вартість), перелік режимів відмов і реакція на них",
            "README, за яким чужа людина запустить проєкт за 10 хвилин"]},
    ],
}

# ---- завдання з автоперевіркою ----------------------------------------------
AUTO = {}
_tasks_dir = os.path.join(HERE, "..", "tasks")
if os.path.isdir(_tasks_dir):
    for _name in sorted(os.listdir(_tasks_dir)):
        _m = re.match(r"t(\d+)_", _name)
        if _m and os.path.isdir(os.path.join(_tasks_dir, _name)):
            AUTO["t" + _m.group(1).lstrip("0")] = _name

# ---- збір --------------------------------------------------------------------
stages = []
for st in STAGES:
    tasks = []
    for sec in st["sections"]:
        tasks.extend(tasks_by_section.get(sec, []))
    tasks.extend(st.get("extra_tasks", []))
    for t in tasks:
        if t["id"] in AUTO:
            t["auto"] = AUTO[t["id"]]
    stage = {k: v for k, v in st.items() if k not in ("sections", "extra_tasks")}
    stage["tasks"] = tasks
    stages.append(stage)

total = sum(len(s["tasks"]) for s in stages)
all_tasks = [t for s in stages for t in s["tasks"]]
sys.path.insert(0, HERE)
import quiz_data  # noqa: E402

# ---- поняття → завдання і самоперевірка ------------------------------------------
_ids = {t["id"] for t in all_tasks}
for s in stages:
    links = quiz_data.PRACTICE.get(s["id"], [])
    assert len(links) == len(s["concepts"]), f"PRACTICE[{s['id']}]: {len(links)} != {len(s['concepts'])}"
    s["practice"] = [[x if isinstance(x, str) else f"t{x}" for x in row] for row in links]
    for tid in (x for row in s["practice"] for x in row):
        assert tid in _ids, f"PRACTICE[{s['id']}]: невідоме завдання {tid}"
    quiz = quiz_data.QUIZ.get(s["id"], {})
    for i, qs in quiz.items():
        assert 0 <= i < len(s["concepts"]), f"QUIZ[{s['id']}]: немає поняття {i}"
        for q in qs:
            assert 0 <= q["answer"] < len(q["options"]) >= 2, f"QUIZ[{s['id']}][{i}]: {q['q']}"
    if quiz:
        s["quiz"] = {str(i): qs for i, qs in quiz.items()}
        # правильний варіант не має вгадуватися за довжиною
        _qs = [q for qs in quiz.values() for q in qs]
        _longest = sum(1 for q in _qs if len(q["options"][q["answer"]]) > 1.15 * max(
            len(o) for j, o in enumerate(q["options"]) if j != q["answer"]))
        if _longest > len(_qs) * 0.2:
            print(f"УВАГА: QUIZ[{s['id']}]: правильний варіант помітно довший у {_longest} з {len(_qs)} питань")

import cwe_data  # noqa: E402
import gen_coverage  # noqa: E402
_names = gen_coverage.cwe_names()
_used = {re.sub(r"^[~?@]", "", tag) for t in all_tasks for tag in t.get("cwe", [])}
data = {"stages": stages, "legacy": LEGACY, "capstone": CAPSTONE,
        "cwe": {k: _names[k] for k in sorted(_used, key=int) if k in _names}}
with open(OUT, "w", encoding="utf-8") as f:
    f.write("// Згенеровано з tasks-catalog.md. Редагуй каталог і перегенеруй, або правь тут вручну.\n")
    f.write("window.SKILLBOOSTER = ")
    json.dump(data, f, ensure_ascii=False, indent=1)
    f.write(";\n")
md = [f"# {CAPSTONE['title']}", "", CAPSTONE["intro"], ""]
_titles = {x["id"]: x["title"] for x in STAGES}
for m in CAPSTONE["milestones"]:
    md.append(f"## {m['id'].upper()}. {m['title']}  (етап: {_titles[m['stage']]})")
    md.extend(f"- [ ] {i}" for i in m["items"])
    md.append("")
with open(os.path.join(HERE, "..", "docs", "capstone.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md))

# ---- звіт покриття CWE ------------------------------------------------------------
with open(os.path.join(HERE, "..", "docs", "security-coverage.md"), "w", encoding="utf-8") as f:
    f.write(gen_coverage.build(all_tasks, len(AUTO), total) + "\n")


# ---- таблиця в tasks/README.md (з заголовків README кожного завдання) ----------------
def _task_rows():
    rows = []
    for name in sorted(AUTO.values(), key=lambda x: int(re.match(r"t(\d+)_", x).group(1))):
        first = open(os.path.join(_tasks_dir, name, "README.md"), encoding="utf-8").readline().strip()
        m = re.match(r"^#\s+№(\d+)\s+·\s+(.+)$", first)
        if m:
            title = m.group(2).strip()
            level = next((c for c in "🟢🟡🔴" if c in title), "")
            title = title.replace(level, "").strip()
            rows.append(f"| {m.group(1)} | {title} | {level} |")
    return rows


_readme = os.path.join(_tasks_dir, "README.md")
if os.path.isfile(_readme):
    _text = open(_readme, encoding="utf-8").read()
    _block = (
        "<!-- TASKS:START -->\n| № | Завдання | Рівень |\n|---|---|---|\n"
        + "\n".join(_task_rows())
        + "\n<!-- TASKS:END -->"
    )
    if "<!-- TASKS:START -->" in _text:
        _text = re.sub(r"<!-- TASKS:START -->.*?<!-- TASKS:END -->", lambda _m: _block, _text, flags=re.S)
    else:
        _text = re.sub(
            r"\| № \| Завдання \| Рівень \|\n\|---\|---\|---\|\n(?:\|.*\n)+",
            lambda _m: _block + "\n",
            _text,
            count=1,
        )
    open(_readme, "w", encoding="utf-8").write(_text)

print(f"stages={len(stages)} tasks={total}")
for s in stages:
    print(s["id"], len(s["tasks"]))
