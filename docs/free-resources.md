# Безкоштовні advanced-ресурси з практикою (жовтень 2026)

Позначки:
- ✅ — безкоштовність і умови я перевірив на сайті 8.10.2026
- 📘 — ресурс добре відомий, але цього разу я його окремо не перевіряв
- **Інтерактив** — що саме ти робиш руками

Що найважливіше:
- Більшість по-справжньому глибоких інтерактивних платформ мають жорсткий free-ліміт (iximiuz, CodeCrafters, KodeKloud).
- Безкоштовна глибина є насамперед у трьох місцях: курсах DataTalksClub, PortSwigger Academy і Killercoda.
- Також безкоштовно глибоко можна вчитися на університетських лабах (MIT, CMU) і в челенджах на кшталт Gossip Glomers.

---

## 1. Python (просунутий рівень)

| Ресурс | Інтерактив | Безкоштовно? |
|---|---|---|
| 📘 [Exercism Python track](https://exercism.org/tracks/python) | ~140 задач з автотестами + **безкоштовний ментор-рев'ю від людини** | Повністю |
| ✅ [CodeCrafters](https://codecrafters.io) — Build your own Redis / HTTP server / Git / SQLite / Kafka | Пишеш реальну систему поетапно, автотести на кожен етап, Python підтримується | Інструкції читати можна всі, але **відправка рішень платна**. Безкоштовно доступний 1 челендж місяця (у жовтні 2026 це Shell). Можна робити локально за їхніми open-source інструкціями на GitHub без автоперевірки |
| 📘 [Advent of Code](https://adventofcode.com) | Алгоритмічні задачі з перевіркою відповіді | Повністю |
| 📘 [Fluent Python](https://www.fluentpython.com) — авторські нотатки та репозиторій з прикладами | Код з книги | Репозиторій безкоштовний, книга платна |

## 2. Бази даних і SQL

| Ресурс | Інтерактив | Безкоштовно? |
|---|---|---|
| 📘 [pgexercises.com](https://pgexercises.com) | SQL-задачі прямо на PostgreSQL у браузері: від join до window functions і рекурсивних CTE | Повністю |
| 📘 [Use The Index, Luke](https://use-the-index-luke.com) | Глибоко про індекси та плани запитів, з тестом на 5 питань | Повністю |
| 📘 [DataLemur](https://datalemur.com) | SQL-задачі рівня співбесід у FAANG | Більшість задач безкоштовні |
| 📘 [PostgreSQL Internals](https://postgrespro.com/community/books/internals) (Egor Rogov) | Книга про MVCC, WAL, блокування та планувальник; приклади запускаєш у своєму Postgres | Безкоштовний PDF |
| 📘 [CMU 15-445 Database Systems](https://15445.courses.cs.cmu.edu) | Лекції + проєкт BusTub (сам пишеш СУБД) | Безкоштовно, але проєкти на C++ |

## 3. Linux, контейнери, Kubernetes

| Ресурс | Інтерактив | Безкоштовно? |
|---|---|---|
| 📘 [Killercoda](https://killercoda.com) | Справжні VM у браузері: сценарії CKA/CKAD/CKS, Linux, Terraform, Helm, ArgoCD | **Повністю безкоштовно**, найкращий вибір для K8s |
| 📘 [SadServers](https://sadservers.com) | «LeetCode для Linux»: зламаний сервер, і ти маєш його полагодити (troubleshooting) | Більшість сценаріїв безкоштовні |
| ✅ [iximiuz Labs](https://labs.iximiuz.com) | Найглибше про внутрішню будову контейнерів і мережі: namespaces, cgroups, CNI | Free: 1 playground, 1 година на день, частина туторіалів. 150+ челенджів доступні лише в платному плані ($10/міс) |
| ✅ [KodeKloud 100 Days of DevOps / Cloud](https://kodekloud.com/100-days-of-devops) | 100 реальних задач у живих середовищах з автоперевіркою: Git, Docker, K8s, IaC, CI/CD, моніторинг; окремо 100 днів AWS/Azure | Безкоштовно, **1 задача на день** |
| 📘 [Kubernetes The Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way) | Піднімаєш кластер вручну, без інсталяторів | Безкоштовно (потрібні свої VM) |
| 📘 [OverTheWire Bandit](https://overthewire.org/wargames/bandit/) | Linux/SSH через гру з рівнями | Повністю |

## 4. Хмара, IaC, CI/CD, observability

| Ресурс | Інтерактив | Безкоштовно? |
|---|---|---|
| 📘 [AWS Workshops](https://workshops.aws) | Офіційні покрокові лаби (EKS, serverless, observability) | Безкоштовні, але запускаються **у твоєму акаунті**, тож стеж за Free Tier |
| 📘 [AWS Skill Builder](https://skillbuilder.aws) | Курси, частина лаб і AWS Cloud Quest | Базова частина безкоштовна |
| 📘 [HashiCorp Developer: Terraform tutorials](https://developer.hashicorp.com/terraform/tutorials) | Покрокові туторіали; інтерактивний Terraform також є на Killercoda | Безкоштовно |
| 📘 [GitHub Skills](https://skills.github.com) | Інтерактивні курси з GitHub Actions прямо в репозиторії | Безкоштовно |
| 📘 [Grafana Play](https://play.grafana.org) + [OpenTelemetry Demo](https://opentelemetry.io/docs/demo/) | Живі дашборди; повний мікросервісний стенд для практики трейсингу | Безкоштовно |

## 5. Системний дизайн і розподілені системи

| Ресурс | Інтерактив | Безкоштовно? |
|---|---|---|
| ✅ [Gossip Glomers (Fly.io)](https://fly.io/dist-sys/) | 6 челенджів з розподілених систем (gossip, CRDT-лічильник, Kafka-подібний лог, транзакції), перевіряються тестером Maelstrom (Jepsen). Офіційно на Go, але протокол JSON через stdin/stdout, тож можна писати й на Python | Повністю |
| 📘 [MIT 6.5840 Distributed Systems](https://pdos.csail.mit.edu/6.824/) | Лаби MapReduce, Raft, KV-сховище з автотестами | Безкоштовно (Go) |
| 📘 [System Design Primer](https://github.com/donnemartin/system-design-primer) | Теорія + Anki-картки + задачі з розв'язками | Безкоштовно |

## 6. Безпека

| Ресурс | Інтерактив | Безкоштовно? |
|---|---|---|
| 📘 [PortSwigger Web Security Academy](https://portswigger.net/web-security) | **250+ лаб** у вразливих застосунках: SQLi, SSRF, JWT, OAuth, API testing, race conditions, від початкового рівня до експертного | **Повністю безкоштовно**, золотий стандарт |
| 📘 [OWASP Juice Shop](https://owasp.org/www-project-juice-shop/) | Вразливий застосунок з 100+ челенджами, запускається в Docker | Безкоштовно |
| 📘 [crAPI](https://github.com/OWASP/crAPI) | Вразливий API за OWASP API Top 10 | Безкоштовно |

## 7. AI для бекендера

| Ресурс | Інтерактив | Безкоштовно? |
|---|---|---|
| ✅ [DataTalksClub AI Dev Tools Zoomcamp 2026](https://github.com/DataTalksClub) | **Найбільше підходить тобі**: AI-кодинг-асистенти, spec→FastAPI+tests→Postgres→Docker→AWS через GitHub Actions→OpenTelemetry/Grafana→MCP, skills, subagents | Безкоштовно. Когорта йде з 31.08.2026 (домашки до 19.10), self-paced доступний будь-коли |
| ✅ [DataTalksClub LLM Zoomcamp](https://datatalks.club/docs/courses/llm-zoomcamp/) | Agentic RAG, векторний пошук (pgvector), оцінювання, моніторинг, капстоун | Безкоштовно (API коштуватиме ~$1–5). Домашки оцінюються лише в живій когорті |
| ✅ [Claude Academy](https://academy.claude.com) | «Building with the Claude API» (67 уроків, квізи), Intro to MCP + MCP Advanced, Claude Code in Action, Subagents, Skills, Claude на Amazon Bedrock | Безкоштовно |
| ✅ [Hugging Face MCP Course](https://huggingface.co/learn/mcp-course) та [Agents Course](https://huggingface.co/learn/agents-course) | Будуєш MCP-сервери та агентів, є сертифікати | Безкоштовно |
| 📘 [LangChain Academy](https://academy.langchain.com) | LangGraph: агенти зі станом, пам'ять, human-in-the-loop | Безкоштовно |
| 📘 [Gandalf by Lakera](https://gandalf.lakera.ai) | Гра-практика з prompt injection, тобто безпека LLM | Безкоштовно |

## 8. Агрегатори та карти

- 📘 [roadmap.sh](https://roadmap.sh): роадмапи Backend, Python, DevOps, AI Engineer, кожен з **project ideas** (від початкового до просунутого рівня) і трекінгом прогресу.
- 📘 [devops-exercises (bregman-arie)](https://github.com/bregman-arie/devops-exercises): 2600+ питань і вправ з DevOps.

---

## Висновок: де є і глибина, і автоперевірка безкоштовно

1. **PortSwigger Academy**: безпека.
2. **Killercoda**: Kubernetes і Linux.
3. **KodeKloud 100 Days** (задача на день): DevOps та AWS.
4. **SadServers**: troubleshooting.
5. **pgexercises + Use The Index, Luke**: SQL і оптимізація.
6. **Gossip Glomers**: розподілені системи.
7. **DataTalksClub AI Dev Tools Zoomcamp + LLM Zoomcamp**: AI-бекенд.
8. **Exercism з ментором**: Python.

Прогалина, якої немає безкоштовно: **advanced Python-бекенд з автоперевіркою** (async, FastAPI під навантаженням, кешування, черги, idempotency). Таке закриває лише платний CodeCrafters або **власний репозиторій із завданнями та тестами в GitHub Actions** (варіант 3).
