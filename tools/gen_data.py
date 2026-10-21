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
marker_re = re.compile(r"\*(Перевірка|CWE|Патерн|Кроки|Готово|Тип):\*")


def split_items(text):
    """Пункти списку в одному рядку каталогу розділені « | »."""
    return [x.strip() for x in text.split(" | ") if x.strip()]


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
        if "Кроки" in fields:
            task["steps"] = split_items(fields["Кроки"])
        if "Готово" in fields:
            task["done"] = split_items(fields["Готово"])
        if "Тип" in fields:
            task["kind"] = fields["Тип"].strip().rstrip(".")
        if group:
            task["group"] = group
        tasks_by_section[section].append(task)

JENKINS_TASKS = [
    {
        "id": "j1", "n": 0, "level": 2, "ai": False,
        "title": "Jenkins у Docker",
        "desc": "підняти Jenkins через docker compose, створити перший job, підключити агент",
        "check": "Jenkins відкривається локально, job проходить",
        "kind": "практика",
        "steps": ["написати docker-compose.yml з образом jenkins/jenkins:lts (порт 8080, том для jenkins_home)",
                  "пройти початкове налаштування (пароль із логів контейнера, рекомендовані плагіни)",
                  "створити freestyle job, що клонує твій репозиторій і запускає pytest",
                  "підключити агент: або вбудований вузол, або окремий контейнер-агент за SSH/inbound",
                  "перезапустити контейнер і перевірити, що job і налаштування збереглись"],
        "done": ["Jenkins відкривається на localhost:8080 після docker compose up",
                 "job клонує репозиторій і проходить зеленим",
                 "налаштування переживають перезапуск контейнера (том jenkins_home)",
                 "пароль адміністратора й токени не лежать у репозиторії"],
    },
    {
        "id": "j2", "n": 0, "level": 2, "ai": False,
        "title": "Jenkinsfile (declarative)",
        "desc": "перенести пайплайн із завдань 73–75 (lint, test, build образу) на Jenkinsfile і вебхук з Git",
        "check": "зелений пайплайн за пушем у репозиторій",
        "kind": "практика",
        "steps": ["створити Jenkinsfile (declarative) із stages: lint, test, build образу",
                  "створити Multibranch Pipeline job на свій репозиторій",
                  "налаштувати webhook із GitHub (або Poll SCM, якщо Jenkins недоступний ззовні) на push",
                  "додати post-блок: архівувати звіт тестів і повідомляти про падіння",
                  "порівняти з workflow GitHub Actions із завдань 73-75: що простіше, що складніше"],
        "done": ["push у гілку автоматично запускає пайплайн",
                 "stages lint, test, build виконуються в Docker-агенті, а не на самому контролері",
                 "падіння тесту робить білд червоним і видно в post-блоці",
                 "є 5-6 рядків порівняння з Actions (час, зручність, підтримка)"],
    },
    {
        "id": "j3", "n": 0, "level": 3, "ai": False,
        "title": "Shared Library і credentials",
        "desc": "винести спільні кроки в Shared Library, секрети тримати в Jenkins Credentials",
        "check": "два пайплайни використовують одну бібліотеку, секретів у коді немає",
        "kind": "практика",
        "steps": ["створити окремий репозиторій із Shared Library (каталог vars/, функція buildAndTest)",
                  "підключити бібліотеку в Jenkins (Manage Jenkins, Global Pipeline Libraries) і викликати її у двох Jenkinsfile",
                  "створити секрет у Jenkins Credentials (токен реєстру образів) і використати його через withCredentials",
                  "переконатись, що значення секрету маскується в логах білду",
                  "додати версіювання бібліотеки (тег) і підключати конкретну версію"],
        "done": ["два різні пайплайни використовують одну бібліотеку",
                 "у жодному Jenkinsfile чи репозиторії немає пароля або токена",
                 "у логах білду секрет показано як ****",
                 "бібліотека підключається за тегом, а не за гілкою main"],
    },
]

# ---- описи етапів ------------------------------------------------------------
R = lambda name, url, kind, level, free, note: {
    "name": name, "url": url, "kind": kind, "level": level, "free": free, "note": note,
}

TRACKS = [
    {"id": "core", "icon": "⚙️", "title": "Backend + DevOps",
     "intro": "Python і FastAPI у production, тестування, патерни й архітектура, бази даних, API, Linux, CI/CD, хмара, Kubernetes, observability і системний дизайн.",
     "order": "Етапи 1–5 дають базу. Архітектура (6) спирається на патерни й БД. DevOps-гілку (7–11) можна проходити паралельно з 5–6. Системний дизайн (12) корисно відкласти на момент, коли вже є досвід з БД і чергами. Безпеку не відкладай на потім: трек 🛡 Security Engineering починай паралельно вже після етапів 1 і 4. AI-трек можна починати після етапів 1, 2 і 4."},
    {"id": "sec", "icon": "🛡", "title": "Security Engineering",
     "intro": "Головна навичка 2026 року: коли все більше коду пише AI, розробник відповідає за те, щоб він був безпечним. AppSec вебзастосунків, ідентичність і криптографія, secure design і threat modeling, supply chain, безпечна робота з coding-агентами, безпека інфраструктури й реагування на інциденти. Безпека самих LLM-систем (prompt injection, guardrails, MCP) живе в AI-треку, етап 6.",
     "order": "Етапи 1 (AppSec) і 3 (secure design) це ядро: починай їх паралельно з Backend-треком після його етапів 1 і 4. Етап 2 (ідентичність і криптографія) після етапу API. Етапи 4 (supply chain) і 5 (AI-агенти в розробці) потрібні кожному, хто комітить код у 2026, тож не відкладай їх. Етап 6 (інфраструктура й реагування) після DevOps-гілки. Віхи capstone M2, M7 і M12 перевіряють безпеку наскрізного проєкту."},
    {"id": "ai", "icon": "🤖", "title": "AI Engineering",
     "intro": "Окремий трек рівня middle: як працюють LLM, API і context engineering, advanced RAG і grounding, агенти й harness, evals, AI security, LLMOps і governance. Спирається на етапи Python, тестування й БД Backend-треку.",
     "order": "Етапи 1 і 2 це основа. RAG (3) і агенти (4) будуються на них. Evals (5) і безпеку (6) починай разом із першим RAG, а не наприкінці: саме вони відрізняють middle від демо. LLMOps (7) і governance (8) знадобляться, коли є що викочувати. Етап 5 треку Security (безпечна розробка з AI-агентами) проходь разом з агентами (4). Наскрізний проєкт (віхи M3–M6 і M11) веде через увесь трек."},
]

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
            R("Python Tutor", "https://pythontutor.com", "Інтерактив", "🟢", "Безкоштовно", "Покрокова візуалізація виконання: стек, об'єкти, посилання"),
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
            R("explain.dalibo.com", "https://explain.dalibo.com", "Інтерактив", "🟡", "Безкоштовно", "Візуалізація плану EXPLAIN (ANALYZE) PostgreSQL: де час і рядки"),
            R("SQLBolt", "https://sqlbolt.com", "Інтерактив", "🟢", "Безкоштовно", "Інтерактивні уроки SQL прямо в браузері"),
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
        "id": "architecture",
        "icon": "🏛️",
        "title": "Архітектура ПЗ і проєктування",
        "sections": ["U"],
        "why": "AI пише функції швидше за людину, але не вирішує, де межі модулів, які інваріанти недоторканні й як система житиме роками. Саме ці рішення тепер відрізняють middle від того, хто лише приймає згенерований код.",
        "concepts": [
            "Quality attributes і компроміси: вимоги як вимірювані сценарії, ціна кожного рішення",
            "ADR, design docs і RFC: фіксувати рішення, альтернативи й наслідки",
            "C4-модель і діаграми як код (Structurizr, Mermaid)",
            "Модульний моноліт: межі модулів, публічний API модуля, правила залежностей",
            "Hexagonal / Clean architecture: ports & adapters, домен без фреймворку",
            "DDD стратегічний: bounded context, ubiquitous language, context map",
            "DDD тактичний: aggregate, інваріанти, доменні події, межа транзакції",
            "Event-driven архітектура: команди й події, контракти й еволюція схем",
            "CQRS і event sourcing: коли окупаються, а коли це зайва складність",
            "Мультитенантність: shared schema з RLS, schema чи база на tenant'а, fail closed",
            "Еволюція системи: strangler fig, технічний борг, міграції без big bang",
            "Архітектура в епоху AI-коду: fitness functions як огорожа, явні контракти, review дизайну від AI",
        ],
        "resources": [
            R("Cosmic Python (Architecture Patterns with Python)", "https://www.cosmicpython.com/book/preface.html", "Книга", "🟡", "Безкоштовно", "Repository, UoW, aggregates, події, CQRS саме на Python"),
            R("C4 model", "https://c4model.com", "Довідник", "🟢", "Безкоштовно", "Діаграми архітектури на 4 рівнях"),
            R("Architectural Decision Records", "https://adr.github.io", "Довідник", "🟢", "Безкоштовно", "Шаблони ADR і практики"),
            R("DDD Crew", "https://github.com/ddd-crew", "Шаблони", "🟡", "Безкоштовно", "Bounded Context Canvas, context mapping, Event Storming"),
            R("Martin Fowler: Software Architecture Guide", "https://martinfowler.com/architecture/", "Статті", "🟡", "Безкоштовно", "Strangler fig, мікросервіси, event-driven"),
            R("import-linter", "https://import-linter.readthedocs.io", "Інструмент", "🟡", "Безкоштовно", "Контракти залежностей між модулями Python у CI"),
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
            R("The Illustrated TLS 1.3 Connection", "https://tls13.xargs.org", "Інтерактив", "🟡", "Безкоштовно", "Кожен байт TLS-рукостискання з поясненням"),
            R("How DNS works", "https://howdns.works", "Інтерактив", "🟢", "Безкоштовно", "Комікс про шлях DNS-запиту від резолвера до authoritative"),
            R("explainshell", "https://explainshell.com", "Інтерактив", "🟢", "Безкоштовно", "Вставляєш команду, бачиш пояснення кожного прапорця"),
            R("Play with Docker", "https://labs.play-with-docker.com", "Інтерактив", "🟢", "Безкоштовно", "Docker у браузері, сесія 4 години, потрібен акаунт Docker Hub"),
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
            R("Learn Git Branching", "https://learngitbranching.js.org", "Інтерактив", "🟢–🟡", "Безкоштовно", "Візуальна гра: rebase, cherry-pick, remote, є українська"),
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
            R("Network Policy Editor", "https://editor.networkpolicy.io", "Інтерактив", "🟡", "Безкоштовно", "Будуєш NetworkPolicy візуально й бачиш, який трафік дозволено"),
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
            R("PromLens", "https://demo.promlens.com", "Інтерактив", "🟡", "Безкоштовно", "Розбір PromQL-запиту на дерево з поясненням кожного кроку"),
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
            R("The Secret Lives of Data: Raft", "https://thesecretlivesofdata.com/raft/", "Інтерактив", "🟢", "Безкоштовно", "Анімоване пояснення консенсусу Raft"),
            R("Raft: візуалізація", "https://raft.github.io", "Інтерактив", "🟡–🔴", "Безкоштовно", "Інтерактивний кластер: вимикай вузли й дивись вибори лідера"),
        ],
    },
    # ---- трек AI Engineering ----------------------------------------------------
    {
        "id": "security",
        "icon": "🔐",
        "track": "sec",
        "title": "AppSec: вебзастосунки й API",
        "sections": ["D"],
        "why": "Фундамент треку: як ламають вебзастосунки й API і як це закрити в коді FastAPI. OWASP Top 10:2025 і API Top 10 на практиці: доступ, ін'єкції, автентифікація, сесії, файли, заголовки. Одна така помилка коштує компанії репутації й грошей, а AI-асистенти охоче відтворюють їх, якщо код не перевіряти.",
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
            R("jwt.io", "https://www.jwt.io", "Інтерактив", "🟢", "Безкоштовно", "Декодування й перевірка JWT: заголовок, claims, підпис"),
            R("CSP Evaluator", "https://csp-evaluator.withgoogle.com", "Інтерактив", "🟡", "Безкоштовно", "Аналіз Content-Security-Policy від Google: де обхід"),
        ],
    },
    {
        "id": "sec-identity",
        "icon": "🔑",
        "track": "sec",
        "title": "Ідентичність, доступ і криптографія",
        "sections": ["V"],
        "why": "Більшість зламів починається з чужої ідентичності: вкраденого токена, слабкої перевірки JWT, фішингу MFA. Криптографію не пишуть самі, але мусять правильно вибрати й застосувати, і саме тут AI-код помиляється тихо.",
        "concepts": [
            "Криптографія для бекендера: хеш, MAC, AEAD, підпис; чому не винаходити власну схему",
            "Ключі: KMS, envelope encryption, ротація, crypto-shredding",
            "Пастки реалізації: випадковість, порівняння за сталий час, повтор nonce, застарілі алгоритми",
            "TLS, mTLS і постквантовий перехід: X25519MLKEM768, crypto-agility",
            "JWT без пасток: allowlist алгоритмів, kid і JWKS, aud та iss, ротація ключів",
            "OAuth 2.1 і RFC 9700: PKCE, точні redirect URI, ротація refresh, DPoP",
            "Passkeys і WebAuthn, NIST SP 800-63-4: phishing-resistant MFA, відновлення доступу",
            "Авторизація як окремий шар: policy-as-code (OPA, Cedar), ReBAC (Zanzibar, OpenFGA)",
            "Machine identity: workload identity, SPIFFE, OIDC federation, короткоживучі credentials",
        ],
        "resources": [
            R("CryptoHack", "https://cryptohack.org", "Лаби", "🟡–🔴", "Безкоштовно", "Інтерактивні задачі: AES, RSA, ECC, хеші, атаки на реалізації"),
            R("Cryptopals", "https://cryptopals.com", "Лаби", "🟡–🔴", "Безкоштовно", "Класичні атаки на криптографію своїми руками"),
            R("RFC 9700: OAuth 2.0 Security BCP", "https://www.rfc-editor.org/rfc/rfc9700", "Стандарт", "🟡", "Безкоштовно", "Актуальні вимоги до OAuth (січень 2025)"),
            R("passkeys.dev", "https://passkeys.dev", "Довідник", "🟡", "Безкоштовно", "Як впроваджувати passkeys на сервері й клієнті"),
            R("webauthn.io", "https://webauthn.io", "Інтерактив", "🟢", "Безкоштовно", "Реєстрація й вхід passkey з видимими параметрами"),
            R("OpenFGA Playground", "https://play.fga.dev", "Інтерактив", "🟡", "Безкоштовно", "Моделювання ReBAC у стилі Zanzibar"),
            R("NIST SP 800-63-4", "https://pages.nist.gov/800-63-4/", "Стандарт", "🟡", "Безкоштовно", "Автентифікація й рівні AAL (фінальна версія 2025)"),
        ],
    },
    {
        "id": "sec-design",
        "icon": "🧭",
        "track": "sec",
        "title": "Secure design і threat modeling",
        "sections": ["W"],
        "why": "Сканер знаходить SQL-ін'єкцію, але не помітить, що квоту обходять паралельними запитами чи що дизайн дає модулю доступ до всіх tenant'ів. Помилки дизайну (OWASP A06) не латаються одним рядком, тому безпеку закладають до коду.",
        "concepts": [
            "Secure by Design і вимоги безпеки; OWASP ASVS 5.0 як чекліст рівнів L1–L3",
            "Threat modeling: DFD, межі довіри, STRIDE, LINDDUN, attack trees; формат на одну фічу",
            "Ризик: ймовірність і вплив, чому CVSS ще не ризик, прийняття ризику з власником",
            "Abuse cases і вразливості бізнес-логіки, яких не бачить сканер",
            "Race conditions і TOCTOU: limit overrun, подвійне списання",
            "Defense in depth, zero trust, мінімальна поверхня атаки, fail closed",
            "Обробка помилок і винятків (OWASP A10:2025): fail open, витік деталей, часткові стани",
            "Інтерпретатори в коді: десеріалізація, eval, SSTI, ReDoS",
            "Privacy engineering: мінімізація, псевдонімізація, строки зберігання",
        ],
        "resources": [
            R("OWASP ASVS 5.0", "https://owasp.org/www-project-application-security-verification-standard/", "Стандарт", "🟡", "Безкоштовно", "Вимоги до безпеки застосунку на 3 рівнях (травень 2025)"),
            R("OWASP Cheat Sheet Series", "https://cheatsheetseries.owasp.org", "Довідник", "🟢–🔴", "Безкоштовно", "Короткі практичні гайди з кожної теми"),
            R("Threat Modeling Manifesto", "https://www.threatmodelingmanifesto.org", "Статті", "🟢", "Безкоштовно", "Чотири питання threat modeling і антипатерни"),
            R("OWASP Threat Dragon", "https://owasp.org/www-project-threat-dragon/", "Інструмент", "🟢", "Безкоштовно", "Діаграми потоків даних і STRIDE"),
            R("LINDDUN", "https://linddun.org", "Методика", "🟡", "Безкоштовно", "Threat modeling для приватності"),
            R("CISA Secure by Design", "https://www.cisa.gov/securebydesign", "Статті", "🟢", "Безкоштовно", "Принципи й зобовʼязання виробників ПЗ"),
        ],
    },
    {
        "id": "sec-supply",
        "icon": "📦",
        "track": "sec",
        "title": "Supply chain і secure SDLC",
        "sections": ["X"],
        "why": "У 2025–2026 атакують не код, а шлях до продакшну: залежності, GitHub Actions, реєстри пакетів (tj-actions, Shai-Hulud, LiteLLM на PyPI). OWASP Top 10:2025 виніс це на A03, а EU CRA з вересня 2026 вимагає звітувати про експлуатовані вразливості за 24 години.",
        "concepts": [
            "Модель загроз ланцюга постачання: SLSA, OWASP A03:2025, де саме атакують",
            "Залежності: lockfile з хешами (uv, pylock.toml), dependency confusion, cooldown нових версій",
            "Інциденти 2025–2026 як кейси: tj-actions, Shai-Hulud, s1ngularity, LiteLLM",
            "GitHub Actions hardening: pin на SHA, мінімальний GITHUB_TOKEN, pull_request_target, script injection",
            "Підпис і provenance: Sigstore і cosign, SLSA provenance, trusted publishing, attestations",
            "SBOM і VEX: CycloneDX, reachability, що робити з сотнею CVE",
            "Secure SDLC: security gates, baseline, винятки з терміном, без втоми від алертів",
            "Секрети: push protection, сканування історії, порядок дій після витоку",
            "EU Cyber Resilience Act, coordinated disclosure, SECURITY.md і security.txt",
        ],
        "resources": [
            R("SLSA", "https://slsa.dev", "Стандарт", "🟡", "Безкоштовно", "Рівні захисту збірки й provenance"),
            R("OpenSSF Scorecard", "https://scorecard.dev", "Інструмент", "🟢", "Безкоштовно", "Автоматична оцінка практик безпеки репозиторію"),
            R("zizmor", "https://docs.zizmor.sh", "Інструмент", "🟡", "Безкоштовно", "Статичний аналіз GitHub Actions: injection, pinning, permissions"),
            R("GitHub Security Lab: pwn requests", "https://securitylab.github.com/resources/github-actions-preventing-pwn-requests/", "Статті", "🟡", "Безкоштовно", "Чому pull_request_target небезпечний"),
            R("Sigstore docs", "https://docs.sigstore.dev", "Довідник", "🟡", "Безкоштовно", "cosign, keyless-підпис, перевірка ідентичності"),
            R("PyPI Trusted Publishers", "https://docs.pypi.org/trusted-publishers/", "Довідник", "🟢", "Безкоштовно", "Публікація з CI через OIDC без токенів"),
            R("OSV.dev", "https://osv.dev", "Інструмент", "🟢", "Безкоштовно", "База вразливостей відкритих пакетів і API"),
            R("ENISA Single Reporting Platform", "https://www.enisa.europa.eu/topics/product-security-and-certification/single-reporting-platform-srp", "Довідник", "🟡", "Безкоштовно", "Звітування за EU CRA з 11.09.2026"),
        ],
    },
    {
        "id": "sec-ai-dev",
        "icon": "🧑‍💻",
        "track": "sec",
        "title": "Безпечна розробка з AI-агентами",
        "sections": ["Y"],
        "why": "Coding-агент читає недовірений текст і має shell, git і твої секрети. Дослідження 2025 року (Veracode) знайшли вразливості в 45% зразків згенерованого коду, а атаки через issues і правила агента вже трапились наживо. Тут вчимося швидко працювати з агентом і не відкривати двері зловмиснику.",
        "concepts": [
            "Модель загроз coding-агента: lethal trifecta на машині розробника й у CI",
            "Prompt injection через репозиторій: rules-file backdoor, невидимий Unicode, шкідливі issues",
            "Дозволи й sandbox: allow/ask/deny, devcontainer, egress allowlist, без продових ключів",
            "Агенти в CI: недовірений ввід, мінімальний токен, людина затверджує зміни",
            "Типові вразливості AI-коду: небезпечні дефолти, вимкнений TLS, ін'єкції, вигадані пакети",
            "Review AI-коду: чекліст, security-тести як специфікація, «працює» ще не означає «безпечно»",
            "Правила безпеки для агента: AGENTS.md і CLAUDE.md, hooks, skills, pre-commit",
            "MCP-сервери й розширення IDE як ланцюг постачання",
            "Секрети й дані в контексті агента: .env, історія, логи промптів, zero data retention",
        ],
        "resources": [
            R("OpenSSF: Security-Focused Guide for AI Code Assistant Instructions", "https://best.openssf.org/Security-Focused-Guide-for-AI-Code-Assistant-Instructions", "Довідник", "🟢", "Безкоштовно", "Що писати в правила агента, щоб код був безпечнішим"),
            R("Claude Code: Security", "https://code.claude.com/docs/en/security", "Довідник", "🟢", "Безкоштовно", "Дозволи, sandbox, захист від prompt injection у coding-агенті"),
            R("Embrace The Red", "https://embracethered.com/blog/", "Статті", "🟡–🔴", "Безкоштовно", "Реальні атаки на coding-агентів і AI-асистентів"),
            R("OWASP WrongSecrets", "https://github.com/OWASP/wrongsecrets", "Лаби", "🟡", "Безкоштовно", "Як НЕ треба зберігати секрети: челенджі в Docker і K8s"),
        ],
    },
    {
        "id": "sec-ops",
        "icon": "🚨",
        "track": "sec",
        "title": "Безпека інфраструктури, detection і response",
        "sections": ["Z"],
        "why": "Ідеального захисту не буває, тому важливо швидко помітити атаку й правильно відреагувати. Хибні налаштування хмари досі головна причина витоків, а OWASP A09 нагадує: без журналів і детекцій про злам дізнаються від клієнтів.",
        "concepts": [
            "Контейнер як поверхня атаки: distroless, rootless, read-only FS, capabilities, seccomp",
            "Kubernetes security: Pod Security, NetworkPolicy, RBAC, admission policies",
            "Хмара: типові хибні налаштування, IMDSv2, CSPM, CloudTrail",
            "Zero trust мережа: сегментація, mTLS, контроль egress",
            "Security logging і детекції (OWASP A09:2025), Sigma-правила, SIEM",
            "Runtime detection і пастки: Falco і eBPF, GuardDuty, honeytokens",
            "Vulnerability management: CVSS 4.0, EPSS, CISA KEV, SLA виправлення",
            "Incident response: NIST SP 800-61r3, докази, повідомлення (GDPR, CRA)",
            "Pentest, bug bounty і coordinated disclosure: scope, звіт, як читати результати",
        ],
        "resources": [
            R("flAWS / flAWS2", "http://flaws.cloud", "Лаби", "🟢–🟡", "Безкоштовно", "Типові помилки AWS очима атакувальника"),
            R("CloudGoat", "https://github.com/RhinoSecurityLabs/cloudgoat", "Лаби", "🟡–🔴", "Безкоштовно", "Вразливі сценарії AWS у власному акаунті (стеж за витратами)"),
            R("Kubernetes Goat", "https://madhuakula.com/kubernetes-goat/", "Лаби", "🟡", "Безкоштовно", "Вразливий кластер із 20+ сценаріями"),
            R("Sigma rules", "https://github.com/SigmaHQ/sigma", "Довідник", "🟡", "Безкоштовно", "Відкритий формат детекцій для логів"),
            R("FIRST EPSS", "https://www.first.org/epss/", "Інструмент", "🟡", "Безкоштовно", "Ймовірність експлуатації CVE у найближчі 30 днів"),
            R("CVSS 4.0 calculator", "https://www.first.org/cvss/calculator/4-0", "Інтерактив", "🟢", "Безкоштовно", "Як складається оцінка серйозності"),
            R("CISA KEV", "https://www.cisa.gov/known-exploited-vulnerabilities-catalog", "Довідник", "🟢", "Безкоштовно", "Вразливості, які вже експлуатуються"),
            R("NIST SP 800-61r3", "https://csrc.nist.gov/pubs/sp/800/61/r3/final", "Стандарт", "🟡", "Безкоштовно", "Incident response (редакція 2025)"),
            R("Canarytokens", "https://canarytokens.org", "Інструмент", "🟢", "Безкоштовно", "Безкоштовні пастки: ключі, URL, документи"),
        ],
    },
    {
        "id": "ai-llm",
        "track": "ai",
        "icon": "🧮",
        "title": "Як працюють LLM: основи й математика",
        "sections": ["N"],
        "why": "Без моделі в голові LLM поводиться «магічно»: дивні збої, раптові рахунки, поганий пошук. Токени, sampling, геометрія векторів, ймовірності й автомати пояснюють, чому система поводиться саме так, і це мова решти треку.",
        "concepts": [
            "Transformer на рівні інженера: attention, KV-cache, MoE, чому довгий контекст дорогий",
            "Токени й ціна: токенізація, контекстне вікно, input/output/cached/reasoning токени",
            "Sampling: temperature, top-p, logprobs, seed; чому temperature 0 не гарантує детермінізм",
            "Reasoning-моделі: thinking budget, interleaved thinking, коли міркування не варте ціни",
            "Векторна геометрія: dot, cosine, нормалізація, розмірність; вибір embedding-моделі (MTEB)",
            "ANN-індекси: HNSW, IVF, PQ, DiskANN; recall проти латентності й пам'яті",
            "Ймовірності: Bayes, base rate, калібрування впевненості моделей і класифікаторів",
            "Графи й скінченні автомати як мова агентних систем; MDP на рівні ідеї",
            "Мультимодальність: зображення, PDF, аудіо й голос; vision-моделі для документів",
        ],
        "resources": [
            R("3Blue1Brown: Neural Networks (включно з Transformers)", "https://www.3blue1brown.com/topics/neural-networks", "Відео", "🟢–🟡", "Безкоштовно", "Найкраща візуальна інтуїція attention і embeddings"),
            R("Andrej Karpathy: Neural Networks: Zero to Hero", "https://karpathy.ai/zero-to-hero.html", "Курс", "🟡–🔴", "Безкоштовно", "GPT і токенізатор з нуля в коді"),
            R("Hugging Face: LLM Course", "https://huggingface.co/learn/llm-course", "Курс", "🟡", "Безкоштовно", "Transformers, токенізатори, fine-tuning"),
            R("Pinecone: Faiss і векторний пошук", "https://www.pinecone.io/learn/series/faiss/", "Гайд", "🟡", "Безкоштовно", "HNSW, IVF, PQ з ілюстраціями"),
            R("Mathematics for Machine Learning", "https://mml-book.github.io", "Книга", "🟡–🔴", "Безкоштовно", "Лінійна алгебра й ймовірності, PDF безкоштовно"),
            R("AI Fundamentals Sandbox", "https://ai-fundamentals-sandbox.vercel.app", "Інтерактив", "🟢", "Безкоштовно", "Українською: 22 пісочниці від контекстного вікна до attention і генерації"),
            R("Transformer Explainer", "https://poloclub.github.io/transformer-explainer/", "Інтерактив", "🟢–🟡", "Безкоштовно", "Живий GPT-2 у браузері: attention, temperature, top-k"),
            R("LLM Visualization (bbycroft)", "https://bbycroft.net/llm", "Інтерактив", "🟡–🔴", "Безкоштовно", "3D-прохід токена крізь усі шари трансформера"),
            R("Tiktokenizer", "https://tiktokenizer.vercel.app", "Інтерактив", "🟢", "Безкоштовно", "Як різні токенізатори ріжуть твій текст; порівняй українську й англійську"),
            R("Embedding Projector", "https://projector.tensorflow.org", "Інтерактив", "🟡", "Безкоштовно", "Embeddings у 3D: сусіди слів, PCA, t-SNE"),
            R("TensorFlow Playground", "https://playground.tensorflow.org", "Інтерактив", "🟢", "Безкоштовно", "Нейромережа в браузері: шари, активації, навчання наживо"),
            R("Seeing Theory", "https://seeing-theory.brown.edu", "Інтерактив", "🟢", "Безкоштовно", "Візуальні ймовірності й статистика: Bayes, розподіли, довірчі інтервали"),
        ],
    },
    {
        "id": "ai-api",
        "track": "ai",
        "icon": "🔌",
        "title": "LLM API, structured output і context engineering",
        "sections": ["L"],
        "why": "Це щоденна робота AI-бекендера: надійні виклики моделей, відповіді у валідованій структурі, інструменти, контроль витрат і правильний контекст. Якість системи у 2026 визначає не промпт, а те, що і в якому порядку потрапляє у вікно.",
        "concepts": [
            "LLM API: ролі повідомлень, streaming SSE, помилки, ретраї, 429",
            "Structured output: JSON Schema, strict mode, constrained decoding, валідація й повтор",
            "Tool calling: схеми, паралельні виклики, валідація аргументів, tool choice",
            "Prompt engineering як інженерія: шаблони, few-shot, версіонування, оптимізація (DSPy)",
            "Context engineering: що класти у вікно, порядок, компактизація, lost in the middle, long context проти RAG",
            "Кешування: prompt caching у провайдера, семантичний кеш, інвалідація",
            "Вартість: облік токенів, бюджети, batch API, routing за складністю, fallback",
            "LLM gateway: кілька провайдерів, ретраї, circuit breaker, deadline (LiteLLM, OpenRouter)",
            "Довгі генерації й UX: черги, SSE-прогрес, відновлення після розриву, скасування",
        ],
        "resources": [
            R("Claude Academy", "https://academy.claude.com", "Курс", "🟢–🟡", "Безкоштовно", "Building with the Claude API, prompt engineering, tool use"),
            R("Anthropic: Effective context engineering for AI agents", "https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents", "Стаття", "🟡", "Безкоштовно", "Компактизація, нотатки, субагенти, бюджет контексту"),
            R("OpenAI Cookbook", "https://cookbook.openai.com", "Приклади", "🟡", "Безкоштовно", "Structured outputs, function calling, batch"),
            R("LiteLLM: документація", "https://docs.litellm.ai", "Документація", "🟡", "Безкоштовно", "Gateway до 100+ провайдерів, бюджети, fallback"),
            R("DSPy", "https://dspy.ai", "Документація", "🟡–🔴", "Безкоштовно", "Програмування замість ручних промптів, оптимізатори"),
        ],
    },
    {
        "id": "ai-rag",
        "track": "ai",
        "icon": "📚",
        "title": "Advanced RAG і grounding",
        "sections": ["O"],
        "why": "Більшість корпоративних AI-продуктів це пошук по власних даних. Наївний RAG ламається на таблицях, multi-hop питаннях і правах доступу, а відповідь без grounding виглядає переконливо навіть тоді, коли вигадана.",
        "concepts": [
            "Інгест: парсинг PDF/HTML/таблиць, OCR, метадані, дедуплікація",
            "Чанкінг: за структурою, parent-child, contextual retrieval, late chunking",
            "Пошук: hybrid (BM25 + dense), sparse (SPLADE), late interaction (ColBERT), RRF, фільтри",
            "Reranking (cross-encoder), query rewriting, HyDE, multi-query",
            "Grounding: відповідь лише з джерел, цитати на рівні тверджень, відмова «не знаю»",
            "Faithfulness і галюцинації: перевірка тверджень проти контексту, метрики RAGAS",
            "GraphRAG: сутності, спільноти, local і global search; коли граф виграє у вектора",
            "Agentic RAG: агент вирішує, що й скільки шукати, multi-hop, self-RAG",
            "Структуровані дані: text-to-SQL і API як джерела, безпечне виконання",
            "Метрики retrieval: recall@k, MRR, nDCG, context precision і recall",
            "Продакшн-індекс: права доступу в запиті, інкрементальне оновлення, зміна embedding-моделі, pgvector чи Qdrant",
        ],
        "resources": [
            R("DataTalksClub: LLM Zoomcamp", "https://datatalks.club/docs/courses/llm-zoomcamp/", "Курс", "🟡–🔴", "Безкоштовно", "Agentic RAG, pgvector, evals, моніторинг. API коштуватиме $1–5"),
            R("Anthropic: Contextual Retrieval", "https://www.anthropic.com/news/contextual-retrieval", "Стаття", "🟡", "Безкоштовно", "Контекстні префікси чанків, BM25 + embeddings + rerank"),
            R("Microsoft GraphRAG", "https://microsoft.github.io/graphrag/", "Документація", "🔴", "Безкоштовно", "Спільноти, local і global search"),
            R("RAGAS: метрики RAG", "https://docs.ragas.io", "Документація", "🟡", "Безкоштовно", "Faithfulness, context precision/recall"),
            R("Jason Liu: Systematically improving RAG", "https://jxnl.co/writing/category/rag/", "Блог", "🟡–🔴", "Безкоштовно", "Як покращувати RAG через дані й метрики, а не інтуїцію"),
            R("ChunkViz", "https://chunkviz.up.railway.app", "Інтерактив", "🟢", "Безкоштовно", "Розмір чанка, overlap і сплітер на твоєму тексті наочно"),
        ],
    },
    {
        "id": "ai-agents",
        "track": "ai",
        "icon": "🦾",
        "title": "Агенти й harness engineering",
        "sections": ["P"],
        "why": "Агент це модель у циклі з інструментами, а надійним його робить harness: обмеження, верифікатори, пам'ять, пісочниця, чекпоінти й людина в потрібних точках. Саме harness, а не вибір моделі, відрізняє демо від продакшну.",
        "concepts": [
            "Workflows проти агентів: prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer",
            "Агентний цикл: план → інструмент → спостереження, ліміти кроків і зациклення",
            "Harness: оболонка навколо моделі (інструменти, контекст, верифікатори, ліміти, журнал); довгі задачі з прогрес-файлами",
            "Control patterns: FSM, бюджети, circuit breaker, human-in-the-loop гейти",
            "Пам'ять агента: короткострокова, довгострокова, епізодична; забування й конфлікти",
            "Sandbox і дозволи: ізоляція коду (контейнер, gVisor, Firecracker, E2B), allow/ask/deny для дій",
            "Durable execution: чекпоінти, replay, ідемпотентні інструменти (Temporal, LangGraph checkpointer)",
            "Multi-agent: ієрархія, peer-to-peer, swarm, handoffs; ізоляція контексту субагентів і коли одного агента досить",
            "MCP: tools, resources, prompts, Streamable HTTP, OAuth 2.1, elicitation",
            "A2A і AG-UI: agent cards, життєвий цикл задач, протокол агент ↔ інтерфейс",
            "Computer use, browser-агенти і голосові realtime-агенти",
            "Фреймворки: Claude Agent SDK, OpenAI Agents SDK, LangGraph, Pydantic AI, Google ADK; коли без них",
        ],
        "resources": [
            R("Anthropic: Building effective agents", "https://www.anthropic.com/engineering/building-effective-agents", "Стаття", "🟡", "Безкоштовно", "Workflows проти агентів, п'ять базових патернів"),
            R("Hugging Face: Agents Course", "https://huggingface.co/learn/agents-course", "Курс", "🟡", "Безкоштовно", "Агенти з нуля і на фреймворках"),
            R("Hugging Face: MCP Course", "https://huggingface.co/learn/mcp-course", "Курс", "🟡", "Безкоштовно", "Будуєш MCP-сервери, є сертифікат"),
            R("Model Context Protocol: специфікація", "https://modelcontextprotocol.io", "Документація", "🟡–🔴", "Безкоштовно", "Транспорти, авторизація, security best practices"),
            R("A2A Protocol", "https://a2a-protocol.org", "Документація", "🟡", "Безкоштовно", "Agent cards і життєвий цикл задач (Linux Foundation)"),
            R("LangChain Academy", "https://academy.langchain.com", "Курс", "🟡", "Безкоштовно", "LangGraph: стан, пам'ять, human-in-the-loop"),
            R("12-Factor Agents", "https://github.com/humanlayer/12-factor-agents", "Гайд", "🟡", "Безкоштовно", "Принципи надійних агентів у продакшні"),
        ],
    },
    {
        "id": "ai-evals",
        "track": "ai",
        "icon": "📊",
        "title": "Evals і AI observability",
        "sections": ["Q"],
        "why": "Ймовірнісну систему неможливо покрити звичайними unit-тестами. Evals тут замінюють тести, а трейси замінюють логи: без них кожна зміна промпту чи моделі стає лотереєю, яку видно лише зі скарг.",
        "concepts": [
            "Eval-driven development: аналіз помилок, датасет, базова лінія; capability проти regression evals",
            "Оцінювачі: код, LLM-as-judge, людина; калібрування судді та його упередження",
            "Evals агентів: outcome і trajectory, pass@k і pass^k, середовища й бенчмарки (SWE-bench, τ-bench)",
            "Статистика: довірчі інтервали, парне порівняння, розмір вибірки; гейти в CI",
            "Датасети: реальні збої з продакшну, синтетичні дані, стратифікація",
            "Трасування: OpenTelemetry GenAI semantic conventions, Langfuse, Phoenix; trace-based debugging",
            "Онлайн-моніторинг: зворотний зв'язок, behavioral drift, алерти на якість і вартість",
            "Оптимізація за метрикою: DSPy, A/B промптів, як не перенавчитись на eval",
        ],
        "resources": [
            R("Hamel Husain: Your AI product needs evals", "https://hamel.dev/blog/posts/evals/", "Стаття", "🟡", "Безкоштовно", "Аналіз помилок і eval-driven development на практиці"),
            R("Anthropic Engineering", "https://www.anthropic.com/engineering", "Блог", "🟡–🔴", "Безкоштовно", "Demystifying evals for AI agents, harness для довгих задач"),
            R("Langfuse: документація", "https://langfuse.com/docs", "Документація", "🟡", "Безкоштовно", "Self-hosted трасування, evals, датасети"),
            R("Arize Phoenix", "https://phoenix.arize.com", "Інструмент", "🟡", "Безкоштовно", "Open-source трасування і evals на OpenTelemetry"),
            R("OpenTelemetry: GenAI semantic conventions", "https://opentelemetry.io/docs/specs/semconv/gen-ai/", "Специфікація", "🟡", "Безкоштовно", "Стандартні атрибути для LLM-спанів"),
        ],
    },
    {
        "id": "ai-security",
        "track": "ai",
        "icon": "🛡️",
        "title": "AI Security і red teaming",
        "sections": ["R"],
        "why": "LLM виконує інструкції з будь-якого тексту, який читає, тому кожен документ, сторінка чи опис інструмента стає вектором атаки. Агент з доступом до даних і мережі без архітектурних захистів це вже готовий канал витоку.",
        "concepts": [
            "OWASP Top 10 for LLM Applications 2025 і OWASP Top 10 for Agentic Applications (ASI01–ASI10)",
            "Prompt injection: пряма й непряма, jailbreak, agent goal hijack; чому повного захисту немає",
            "Guardrails: input/output rails, класифікатори (Llama Guard, Prompt Guard), NeMo Guardrails, fail closed",
            "Архітектурні захисти: lethal trifecta, dual LLM, CaMeL (taint і capabilities), spotlighting",
            "Інструменти й MCP: tool poisoning, rug pull, confused deputy, token passthrough",
            "Ідентичність агента: делеговані права, короткоживучі токени, мінімальні права, excessive agency",
            "Витоки даних: system prompt leakage, PII, ізоляція tenants у RAG, ексфільтрація через Markdown",
            "Supply chain AI: pickle проти safetensors, отруєння даних і індексу, slopsquatting",
            "Red teaming: garak, PyRIT, promptfoo, MITRE ATLAS, attack success rate",
            "Моніторинг атак у проді: unbounded consumption, аномалії інструментів, rogue agents",
        ],
        "resources": [
            R("OWASP GenAI Security Project", "https://genai.owasp.org", "Гайд", "🟡", "Безкоштовно", "LLM Top 10 2025, Agentic Top 10, гайди з red teaming"),
            R("Simon Willison: The lethal trifecta", "https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/", "Стаття", "🟡", "Безкоштовно", "Приватні дані + недовірений контент + канал назовні"),
            R("CaMeL: Defeating Prompt Injections by Design", "https://arxiv.org/abs/2503.18813", "Стаття", "🔴", "Безкоштовно", "Taint tracking і capabilities замість фільтрів"),
            R("PortSwigger: Web LLM attacks", "https://portswigger.net/web-security/llm-attacks", "Лаби", "🟡", "Безкоштовно", "Лаби з indirect prompt injection і небезпечних tools"),
            R("Gandalf by Lakera", "https://gandalf.lakera.ai", "Гра", "🟢", "Безкоштовно", "Практика prompt injection"),
            R("promptfoo", "https://www.promptfoo.dev", "Інструмент", "🟡", "Безкоштовно", "Red teaming і evals у CI, плагіни OWASP"),
            R("MITRE ATLAS", "https://atlas.mitre.org", "Довідник", "🟡–🔴", "Безкоштовно", "Тактики й техніки атак на AI-системи"),
            R("Tensor Trust", "https://tensortrust.ai", "Інтерактив", "🟡", "Безкоштовно", "Атакуєш чужі промпти й захищаєш свій"),
            R("Prompt Airlines (Wiz)", "https://promptairlines.com", "Інтерактив", "🟡", "Безкоштовно", "CTF: змусити чат-бота авіакомпанії порушити правила"),
            R("GitHub Secure Code Game", "https://github.com/skills/secure-code-game", "Інтерактив", "🟡", "Безкоштовно", "Сезон 3: шість вразливих AI-асистентів, працює в Codespaces"),
            R("HackAPrompt", "https://www.hackaprompt.com", "Інтерактив", "🟡–🔴", "Безкоштовно", "Великі red-teaming челенджі, включно з агентами"),
            R("CyberChef", "https://gchq.github.io/CyberChef/", "Інтерактив", "🟢", "Безкоштовно", "Base64, hex, Unicode: як атаки обходять фільтри кодуванням"),
        ],
    },
    {
        "id": "ai-ops",
        "track": "ai",
        "icon": "🏭",
        "title": "LLMOps, inference і моделі",
        "sections": ["S"],
        "why": "Рано чи пізно постане питання: яку модель брати, чи хостити свою, чи донавчати і як безпечно викотити нову версію промпту. Тут же робота з AI-асистентами для коду, яка у 2026 стала частиною щоденного процесу.",
        "concepts": [
            "Вибір моделі: власні evals проти бенчмарків, ціна/якість/латентність, frontier проти малих моделей",
            "Self-hosting: vLLM, SGLang, Ollama, llama.cpp; OpenAI-сумісний API",
            "Inference-оптимізація: continuous batching, PagedAttention, prefix caching, квантизація, speculative decoding",
            "Метрики й capacity: TTFT, TPOT, throughput, GPU-пам'ять під KV-cache, беззбитковість проти API",
            "Адаптація моделей: коли fine-tuning (а коли промпт чи RAG), LoRA/QLoRA, дистиляція",
            "Як навчають моделі: pretraining, SFT, RLHF, DPO, RLVR і GRPO на рівні розуміння",
            "Agentic CI/CD: evals як гейт, canary для промптів і моделей, rollback, версіонування артефактів",
            "Хмарні AI-платформи: Bedrock, Azure AI Foundry, Vertex AI; квоти, регіони, дані не для навчання",
            "AI-асистенти в розробці: AGENTS.md/CLAUDE.md, skills, subagents, hooks, spec-driven development, агенти в CI",
        ],
        "resources": [
            R("vLLM: документація", "https://docs.vllm.ai", "Документація", "🟡–🔴", "Безкоштовно", "PagedAttention, batching, квантизація, OpenAI-сумісний сервер"),
            R("Ollama", "https://ollama.com", "Інструмент", "🟢", "Безкоштовно", "Локальні моделі на CPU/GPU одною командою"),
            R("Unsloth: документація", "https://docs.unsloth.ai", "Документація", "🟡", "Безкоштовно", "LoRA/QLoRA і RL у безкоштовному Colab"),
            R("Hugging Face: smol course", "https://github.com/huggingface/smol-course", "Курс", "🟡", "Безкоштовно", "SFT, DPO, evals на малих моделях"),
            R("DataTalksClub: AI Dev Tools Zoomcamp", "https://github.com/DataTalksClub", "Курс", "🟡", "Безкоштовно", "AI-асистенти, FastAPI, Docker, AWS, OpenTelemetry, MCP"),
            R("Claude Code: документація", "https://code.claude.com/docs", "Документація", "🟡", "Безкоштовно", "Skills, subagents, hooks, GitHub Actions"),
            R("Model Memory Calculator", "https://huggingface.co/spaces/hf-accelerate/model-memory-usage", "Інтерактив", "🟡", "Безкоштовно", "Скільки пам'яті GPU потрібно моделі для inference і навчання"),
            R("LMArena", "https://lmarena.ai", "Інтерактив", "🟢", "Безкоштовно", "Сліпе порівняння моделей і рейтинг за голосами людей"),
            R("Artificial Analysis", "https://artificialanalysis.ai", "Інтерактив", "🟢", "Безкоштовно", "Ціна, швидкість, TTFT і якість моделей та провайдерів"),
        ],
    },
    {
        "id": "ai-gov",
        "track": "ai",
        "icon": "⚖️",
        "title": "AI Governance і відповідальний AI",
        "sections": ["T"],
        "why": "З 2 серпня 2026 у ЄС діють обов'язки прозорості та вимоги до GPAI, а обов'язки для high-risk систем Digital Omnibus переніс на 2027–2028. Інженер перекладає ці вимоги в журнали, маркування, документацію й тести, і саме цього очікують від middle у продуктах для ЄС.",
        "concepts": [
            "EU AI Act: рівні ризику, заборонені практики, GPAI, провайдер і деплоєр, строки після Digital Omnibus (2026/1744)",
            "Прозорість: маркування AI-взаємодії й контенту (ст. 50), C2PA, system і model cards",
            "Privacy-by-Design: мінімізація даних, строки зберігання, zero data retention, GDPR і DPA з провайдером",
            "Audit trail: незмінний журнал рішень і дій агента: хто, що, від чийого імені",
            "Fairness: контрфактичні тести, різниця рішень між групами, людський нагляд",
            "Управління ризиками: NIST AI RMF, ISO/IEC 42001, AI-політика компанії",
            "Документація системи: PRD, System Design Document, V&V-звіт",
        ],
        "resources": [
            R("EU AI Act Explorer", "https://artificialintelligenceact.eu", "Довідник", "🟡", "Безкоштовно", "Текст акту, Digital Omnibus, compliance checker"),
            R("NIST AI Risk Management Framework", "https://www.nist.gov/itl/ai-risk-management-framework", "Стандарт", "🟡", "Безкоштовно", "Govern, Map, Measure, Manage; профіль для GenAI"),
            R("University of Helsinki: Ethics of AI", "https://ethics-of-ai.mooc.fi", "Курс", "🟢", "Безкоштовно", "Відповідальність, прозорість, fairness"),
            R("C2PA", "https://c2pa.org", "Специфікація", "🟡", "Безкоштовно", "Походження контенту і маркування згенерованого"),
        ],
    },
]

LEGACY = [
    ["ECMAScript 6, Node.js, Express, NestJS", "replace", "Python 3.12+, FastAPI (у тебе вже є), pydantic v2"],
    ["TypeScript", "replace", "Типізація Python: type hints, mypy"],
    ["SOLID, ООП, шаблони проєктування", "keep", "Лишається, але в Python акцент на композицію та прості модулі; додано етап «Архітектура ПЗ»: DDD, модульний моноліт, ADR, fitness functions"],
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
    ["OWASP Top 10, OAuth, JWT, RBAC", "keep", "Розширено до окремого треку Security Engineering: OWASP Top 10:2025 і ASVS 5.0, OAuth 2.1, passkeys, threat modeling, supply chain, безпека роботи з AI-агентами"],
    ["Kafka, RabbitMQ, Redis, CDN", "keep", "Лишається (етапи «БД» та «Системний дизайн»)"],
    ["Nginx, Apache", "replace", "Nginx або Caddy; Apache рідко потрібен"],
    ["Docker, Kubernetes", "keep", "Лишається, глибше: Helm, ArgoCD, KEDA"],
    ["AWS, Azure, GCP", "keep", "AWS вже знаєш; Terraform додатково; Azure/GCP за потреби"],
    ["Jenkins, GitLab, Bitbucket, GitHub", "replace", "Основа GitHub Actions та GitLab CI; Jenkins як опційний модуль"],
    ["Логи, телеметрія, моніторинг", "keep", "Підсилюємо: OpenTelemetry, Prometheus, Grafana, SLO"],
    ["(немає в оригіналі)", "new", "Окремий трек AI Engineering: LLM і математика, context engineering, advanced RAG і grounding, агенти й harness, evals, AI security, LLMOps, governance"],
]


CAPSTONE = {
    "title": "Наскрізний проєкт: AI-бекенд «Knowledge Assistant»",
    "intro": "Один сервіс, який росте разом з етапами: користувачі завантажують документи й ставлять питання, а бекенд відповідає з цитатами джерел. Це повний набір production-навичок у одному репозиторії й готове портфоліо.",
    "milestones": [
        {"id": "m0", "stage": "python", "title": "Скелет сервісу", "items": [
            "FastAPI-застосунок із шарами router → service → repository, конфіг через pydantic-settings",
            "ruff, mypy, pytest і pre-commit; перший тест і зелений CI",
            "Єдиний формат помилок (RFC 7807) та health-ендпоінти",
            "Coding-агент працює в захищеному середовищі (№257): правила безпеки в AGENTS.md/CLAUDE.md, deny для секретів, hook проти комітів із секретами, devcontainer без продових ключів"]},
        {"id": "m1", "stage": "db", "title": "Дані й пошук", "items": [
            "PostgreSQL + pgvector, міграції Alembic (без простою: expand → contract)",
            "Таблиці users, documents, chunks, chat_sessions; обґрунтовані індекси (EXPLAIN у README)",
            "Redis: кеш відповідей із захистом від cache stampede"]},
        {"id": "m2", "stage": "security", "title": "Доступ і захист", "items": [
            "JWT access/refresh, ролі (user, admin), перевірка власника документа (без IDOR)",
            "Rate limiter на Redis і idempotency key для POST /documents",
            "Маскування PII у логах, секрети лише з env/Secrets Manager, pip-audit у CI",
            "Паролі через scrypt/argon2 з перехешуванням (№157), сесії або refresh-токени з ротацією, відкликанням і абсолютним терміном (№160, №51); якщо є cookie, то CSRF-захист і прапорці (№143)",
            "Окремі pydantic-моделі запиту й відповіді з extra=forbid (№162); тест у CI, що ВСІ маршрути або захищені, або в явному списку публічних (№163)",
            "JWT перевіряється з allowlist алгоритмів, aud та iss (№232); поля з PII шифруються через envelope encryption (№231); ліміти й квоти витримують паралельні запити (№239)",
            "(Опційно) вхід через passkeys (№236) і спільний доступ до документів через ReBAC (№235)"]},
        {"id": "m3", "stage": "ai-rag", "title": "Інгест документів", "items": [
            "Завантаження файлу (потоково, ліміти розміру, presigned URL до S3)",
            "Тип за вмістом (magic bytes), безпечне ім'я файлу, шлях лише під контрольованою текою (№145, №144); якщо додаси завантаження за URL, то із захистом від SSRF (№58)",
            "Чанкінг, embeddings, запис у pgvector фоновим воркером (ARQ/Celery) з retry і DLQ",
            "Outbox для події document.indexed",
            "Структурний чанкінг із contextual prefix (№178), інкрементальна переіндексація за content hash і при зміні embedding-моделі (№182)"]},
        {"id": "m4", "stage": "ai-rag", "title": "RAG-відповіді", "items": [
            "POST /ask: hybrid search (BM25 + вектор), reranking, відповідь із цитатами",
            "Streaming через SSE, structured output із валідацією та повтором",
            "LLM підключається через LLM_BASE_URL / LLM_API_KEY / LLM_MODEL (твій проксі)",
            "Відповідь моделі екранується перед показом у вебі (№142), а все витягнуте з документів вважається недовіреним вмістом (prompt injection)",
            "OWASP LLM Top 10: системний промпт не містить секретів і його витік нічого не дає; відповіді й цитати показують лише документи, до яких користувач має доступ (фільтр за власником ще в пошуку, не після); ліміти токенів, розміру контексту й запитів (unbounded consumption); завантажений документ не може отруїти індекс інших користувачів",
            "Grounding: кожне твердження відповіді має цитату на знайдений чанк, без підтримки сервіс відповідає «не знаю» (№179); input/output guardrails з fail closed (№196)",
            "Менеджер контексту з бюджетом токенів і компактизацією історії чату (№175)"]},
        {"id": "m5", "stage": "ai-evals", "title": "Якість і витрати", "items": [
            "Еталонний набір із 30 питань, метрики recall@k, LLM-as-judge; eval у CI проти мок-моделі",
            "Облік токенів і бюджет на користувача, fallback на дешевшу модель",
            "Кешування однакових запитів та prompt caching там, де підтримується",
            "Синтетичний eval-набір зі стратифікацією (№216), довірчі інтервали в регресійному гейті (№192), суддя відкалібрований на людській розмітці (№193)",
            "Трасування в Langfuse або Phoenix (№195), монітор drift (№194), версії промптів у реєстрі з canary і rollback (№176, №204)"]},
        {"id": "m6", "stage": "ai-agents", "title": "Агент і MCP", "items": [
            "Агент з інструментами (пошук, статистика) і лімітами кроків",
            "Політика авторизації викликів інструментів і набір тестів на prompt injection",
            "MCP-сервер, що відкриває пошук по документах зовнішнім клієнтам",
            "Надмірні повноваження агента (excessive agency): інструменти лише з мінімальними правами, дії зі змінами потребують підтвердження людини, журнал кожного виклику з користувачем і аргументами; тест: документ із інструкцією «видали все» не запускає жодного інструмента запису",
            "Harness: агент як скінченний автомат з HITL-гейтом (№184), durable execution з чекпоінтами (№187), політика sandbox для інструментів (№186)",
            "Захист від lethal trifecta: жодна сесія не поєднує приватні дані, недовірений контент і канал назовні без підтвердження (№197, №198); агент діє з делегованими звуженими правами користувача (№213)",
            "MCP-сервер віддалений: Streamable HTTP, OAuth 2.1 без token passthrough (№217), визначення інструментів закріплені хешами (№199)"]},
        {"id": "m7", "stage": "cicd", "title": "Контейнери й CI/CD", "items": [
            "Multi-stage Dockerfile (non-root, образ < 200 МБ), docker compose: app, worker, postgres, redis",
            "GitHub Actions: lint → test → build → Trivy → push у GHCR, теги за версією й sha",
            "Безпека ланцюга постачання: gitleaks, bandit/semgrep і pip-audit у CI, дії закріплені на sha (№54, №55, №56, №73), Dockerfile проходить власний лінтер (№69)",
            "SBOM образу (syft або trivy sbom) зберігається як артефакт збірки; образ підписується cosign (keyless через OIDC), а деплой перевіряє підпис",
            "DAST: OWASP ZAP baseline-скан проти піднятого в CI застосунку (compose), звіт як артефакт, знахідки середньої серйозності й вище блокують merge або мають обґрунтований виняток",
            "Workflow проходять аудит (№245, або zizmor), залежності з хешами й cooldown для свіжих версій (№246), деплой перевіряє provenance образу (№249), security gate на SARIF з baseline (№248)",
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
        {"id": "m10", "stage": "architecture", "title": "Архітектура й документація", "items": [
            "ADR, C4 і quality attributes з числами (№229); межі модулів перевіряє fitness function у CI (№222)",
            "Ізоляція користувачів fail closed: запит без власника чи tenant'а неможливий (№226)",
            "Threat model за STRIDE (№165): межі довіри на діаграмі, 10 загроз з мітигаціями, перелік прийнятих ризиків",
            "Оцінка навантаження (RPS, обсяг даних, вартість), перелік режимів відмов і реакція на них",
            "README, за яким чужа людина запустить проєкт за 10 хвилин"]},
        {"id": "m11", "stage": "ai-gov", "title": "V&V і governance", "items": [
            "PRD (проблема, користувачі, метрики успіху) і System Design Document з рішеннями щодо моделі, RAG, агента й harness",
            "Red teaming власної системи (№202): звіт з attack success rate за категоріями OWASP LLM і Agentic Top 10 до і після виправлень",
            "V&V-звіт: що перевірено (evals, red team, навантаження), якими метриками, з якими довірчими інтервалами, і відомі обмеження",
            "System card (№210), класифікація ризику за EU AI Act (№208), маркування AI-відповідей у UI (ст. 50), audit trail дій агента на хеш-ланцюжку (№207)",
            "Захист проєкту: 20-хвилинна презентація рішень і відповіді на питання (рев'ю колеги або mock-інтерв'ю)"]},
        {"id": "m12", "stage": "sec-ops", "title": "Security review і готовність до інцидентів", "items": [
            "Самооцінка за OWASP ASVS 5.0 L1 з доказами (№244) і abuse cases з тестами для ключових фіч (№243)",
            "Security review коду, написаного агентом, з порівнянням «без правил / з правилами» (№256)",
            "Детекції за логами автентифікації (№259) і пріоритизація вразливостей залежностей і образу (№260)",
            "Runbook першої години інциденту й tabletop-вправа (№262); SECURITY.md з політикою розкриття (№251)"]},
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
            t.pop("kind", None)
        elif t.get("kind") not in (None, "практика", "документ", "автотест"):
            raise SystemExit(f"{t['id']}: *Тип:* має бути «практика», «документ» або «автотест», а не «{t['kind']}»")
    stage = {k: v for k, v in st.items() if k not in ("sections", "extra_tasks")}
    stage.setdefault("track", "core")
    stage["tasks"] = tasks
    stages.append(stage)

total = sum(len(s["tasks"]) for s in stages)
_manual = [t for s in stages for t in s["tasks"] if "auto" not in t]
_planned = [t["id"] for t in _manual if t.get("kind") == "автотест"]
_manual = [t for t in _manual if t.get("kind") != "автотест"]
_bare = [t["id"] for t in _manual if not t.get("done")]
print(f"завдання без автоперевірки: {len(_manual)}, з чеклістом «Готово»: {len(_manual) - len(_bare)}")
print(f"автотест готується: {len(_planned)}")
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
REPO = "https://github.com/ShumykR/skillbooster"
data = {"repo": REPO, "tracks": TRACKS, "stages": stages, "legacy": LEGACY, "capstone": CAPSTONE,
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

# ---- умови завдань для сайту (readmes.js, підвантажується за потреби) -------------------
_HEAD = re.compile(r"^\*\*(.+?)\*\*(.*)$")


def parse_readme(text):
    """Розбиває README на секції: нова секція починається з рядка `**Заголовок**...`."""
    secs, cur, fence = [], None, False
    for line in text.splitlines()[1:]:  # перший рядок `# №N ...` вже є на картці
        if line.startswith("```"):
            fence = not fence
        m = None if fence else _HEAD.match(line)
        if m:
            title = re.sub(r"[.:\s]+$", "", m.group(1)).strip()
            cur = {"title": title, "body": m.group(2).lstrip(" .:").rstrip()}
            secs.append(cur)
        elif cur is None:
            if line.strip():
                cur = {"title": "", "body": line}
                secs.append(cur)
        else:
            cur["body"] += "\n" + line
    for sec in secs:
        sec["body"] = sec["body"].strip("\n")
    return secs


_STD = ("Ситуація", "Що зробити", "Підказки", "Подумай", "Перевірка")
_readmes, _odd = {}, {}
for _tid, _dir in AUTO.items():
    _p = os.path.join(_tasks_dir, _dir, "README.md")
    if os.path.isfile(_p):
        _secs = parse_readme(open(_p, encoding="utf-8").read())
        _readmes[_tid] = _secs
        for _sec in _secs:
            if not _sec["title"].startswith(_STD):
                _k = _sec["title"] or "(без заголовка)"
                _odd[_k] = _odd.get(_k, 0) + 1
with open(os.path.join(HERE, "..", "readmes.js"), "w", encoding="utf-8") as f:
    f.write("// Згенеровано з tasks/*/README.md (tools/gen_data.py). Не правити руками.\n")
    f.write("window.SKILLBOOSTER_README = ")
    json.dump(_readmes, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")
if _odd:
    print("README: нестандартні секції (показуються як є):", ", ".join(f"{k} ×{v}" for k, v in sorted(_odd.items())))

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
