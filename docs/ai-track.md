# Трек AI Engineering: покриття і план

Окремий трек на сайті (перемикач «Backend + DevOps / Security Engineering / AI Engineering»), 8 етапів, 69 завдань (№126–141 і №169–221), 75 понять, по 2 питання самоперевірки на кожне.
Етапи, поняття й ресурси: `STAGES` у `tools/gen_data.py` (поле `track: "ai"`); завдання: розділи L, N–T у `docs/tasks-catalog.md`.

| № | Етап | Розділ | Завдання |
|---|---|---|---|
| 1 | Як працюють LLM: основи й математика | N | 169–174 |
| 2 | LLM API, structured output і context engineering | L | 126–128, 132–134, 139, 175–177 |
| 3 | Advanced RAG і grounding | O | 129, 130, 178–182, 211 |
| 4 | Агенти й harness engineering | P | 135, 136, 183–190, 214, 215, 217 |
| 5 | Evals і AI observability | Q | 131, 140, 191–195, 216, 218 |
| 6 | AI Security і red teaming | R | 137, 138, 196–202, 212, 213 |
| 7 | LLMOps, inference і моделі | S | 141, 203–206, 219–221 |
| 8 | AI Governance і відповідальний AI | T | 207–210 |

Capstone: віхи M3–M6 доповнено (grounding, guardrails, context manager, harness, lethal trifecta, віддалений MCP), нова віха M11 «V&V і governance» (PRD, SDD, red team, V&V-звіт, system card, EU AI Act, audit trail).

## Мапа термінів (стан на жовтень 2026)

Етап.поняття у дужках (наприклад, 4.3 = етап 4, поняття 3 з 1), далі завдання.

| Тема | Де |
|---|---|
| Transformer, attention, KV-cache, MoE | 1.1 |
| Токенізація, ціна токенів (input/output/cached/reasoning) | 1.2, №169 |
| Sampling, temperature, top-p, logprobs, недетермінізм | 1.3, №170 |
| Reasoning-моделі, thinking budget | 1.4, №221 |
| Embeddings: cosine/dot, нормалізація, вибір моделі (MTEB) | 1.5, №172, №129 |
| ANN: HNSW, IVF, PQ, DiskANN, квантизація, Matryoshka | 1.6, №171, №172, №39 |
| Bayes, base rate, калібрування | 1.7, №173 |
| Графи, FSM, MDP | 1.8, №177, №184 |
| Мультимодальність, vision для документів, голос | 1.9, №174, №215 |
| LLM API, streaming, 429, ретраї | 2.1, №126, №134 |
| Structured output, strict mode, constrained decoding | 2.2, №127, №177 |
| Tool calling, паралельні виклики | 2.3, №128 |
| Prompt engineering, версіонування промптів, DSPy | 2.4, №176, №218 |
| Context engineering, компактизація, lost in the middle, long context проти RAG | 2.5, №175 |
| Prompt caching, семантичний кеш | 2.6, №132 |
| Вартість, бюджети, batch API, routing, fallback | 2.7, №133 |
| LLM gateway (LiteLLM, OpenRouter), circuit breaker | 2.8, №134 |
| Довгі генерації, SSE, скасування | 2.9, №139 |
| Інгест, парсинг PDF/таблиць, OCR | 3.1, №174, №178 |
| Чанкінг, parent-child, contextual retrieval, late chunking | 3.2, №178 |
| Hybrid, sparse (SPLADE), ColBERT, RRF | 3.3, №130 |
| Reranking, query rewriting, HyDE | 3.4, №130 |
| **Grounding**, цитати, abstain | 3.5, №179 |
| Faithfulness, галюцинації, RAGAS | 3.6, №179, №131 |
| GraphRAG | 3.7, №180 |
| Agentic RAG, multi-hop, self-RAG | 3.8, №181 |
| Text-to-SQL | 3.9, №211 |
| Метрики retrieval: recall@k, MRR, nDCG | 3.10, №129 |
| Права доступу в індексі, інкрементальна індексація, зміна embedding-моделі | 3.11, №182 |
| Workflows проти агентів, evaluator-optimizer, orchestrator-workers | 4.1, №183, №188 |
| Агентний цикл, ліміти, зациклення | 4.2, №135 |
| **Harness engineering**, довгі задачі, прогрес-файли | 4.3, №183 |
| Control patterns, HITL-гейти | 4.4, №184 |
| Пам'ять агента | 4.5, №185 |
| Sandbox (контейнер, gVisor, Firecracker, E2B), permissions | 4.6, №186 |
| Durable execution (Temporal, checkpointer) | 4.7, №187 |
| Multi-agent, handoffs, субагенти, swarm | 4.8, №188 |
| MCP: tools/resources/prompts, Streamable HTTP, OAuth 2.1, elicitation | 4.9, №136, №217 |
| A2A, AG-UI | 4.10, №189 |
| Computer use, browser-агенти, голосові realtime-агенти | 4.11, №214, №215 |
| Фреймворки: Claude Agent SDK, OpenAI Agents SDK, LangGraph, Pydantic AI, Google ADK | 4.12, №190 |
| Eval-driven development, capability і regression evals | 5.1, №131 |
| LLM-as-judge, калібрування, position/length bias | 5.2, №193 |
| Evals агентів: trajectory, pass@k, pass^k, SWE-bench, τ-bench | 5.3, №191 |
| Статистика evals, гейти в CI | 5.4, №192 |
| Синтетичні датасети | 5.5, №216 |
| OTel GenAI semconv, Langfuse, Phoenix, trace-based debugging | 5.6, №140, №195 |
| Behavioral drift, онлайн-моніторинг | 5.7, №194 |
| OWASP LLM Top 10 2025, OWASP Agentic Top 10 (ASI01–ASI10) | 6.1, №200 |
| **Prompt injection**: пряма, непряма, jailbreak, goal hijack | 6.2, №137 |
| **Guardrails**: input/output rails, Llama Guard, Prompt Guard, NeMo | 6.3, №196 |
| Lethal trifecta, dual LLM, CaMeL, spotlighting | 6.4, №197, №198 |
| MCP security: tool poisoning, rug pull, confused deputy, token passthrough | 6.5, №199, №217 |
| Ідентичність агента, делеговані права (RFC 8693), excessive agency | 6.6, №213, №137 |
| System prompt leakage, PII, ізоляція tenants, Markdown-ексфільтрація | 6.7, №138, №196, №182 |
| Supply chain AI: pickle/safetensors, data poisoning, slopsquatting | 6.8, №201, №212 |
| Red teaming: garak, PyRIT, promptfoo, MITRE ATLAS, ASR | 6.9, №200, №202 |
| Unbounded consumption, моніторинг атак, rogue agents | 6.10, №133, №194 |
| Вибір моделі за власним eval | 7.1, №221 |
| Self-hosting: vLLM, SGLang, Ollama, llama.cpp | 7.2, №205 |
| Inference: continuous batching, PagedAttention, prefix caching, квантизація, speculative decoding | 7.3, №205 |
| TTFT, TPOT, capacity, беззбитковість | 7.4, №203 |
| Fine-tuning, LoRA/QLoRA, дистиляція | 7.5, №206 |
| RLHF, DPO, RLVR, GRPO | 7.6, №206 |
| Agentic CI/CD, canary промптів і моделей | 7.7, №204, №192 |
| Bedrock, Azure AI Foundry, Vertex AI | 7.8 |
| AI-асистенти: AGENTS.md/CLAUDE.md, skills, subagents, hooks, spec-driven, агенти в CI | 7.9, №141, №219, №220 |
| EU AI Act, Digital Omnibus (2026/1744) | 8.1, №208 |
| Прозорість (ст. 50), C2PA, system/model cards | 8.2, №210 |
| Privacy-by-Design, ZDR, GDPR | 8.3, №138, №62 |
| Audit trail | 8.4, №207 |
| Fairness, контрфактичні тести | 8.5, №209 |
| NIST AI RMF, ISO/IEC 42001 | 8.6 |
| PRD, SDD, V&V-звіт | 8.7, №210, M11 |

## Зіставлення з магістратурою Neoversity «Engineering of Autonomous AI Systems»

Джерело: https://neoversity.com.ua/engineering-autonomous (18 місяців, Middle/Senior). Конкретних фреймворків у програмі не названо, тому технології тут обрано за станом ринку.

| Дисципліна Neoversity | Наш трек |
|---|---|
| Bridge: AI-specific validation patterns | 2.2, №127, №177 |
| Bridge: Bayes, векторна геометрія, графи, feedback loops | 1.5–1.8, №171–173 |
| Bridge: FSM, ANN, індексні структури | 1.6, 1.8, №171, №177, №184 |
| Bridge: Harness як архітектурна основа | 4.3, №183 |
| Generative and Agentic AI: structured outputs, agentic loops, operational constraints | 2.2, 4.2, №127, №135 |
| Advanced RAG: hybrid, GraphRAG, agentic retrieval | етап 3 |
| Harness Engineering: evaluator-optimizer, guardrails, sandboxes, trace-based debugging | 4.1, 4.3, 4.6, 6.3, 5.6 |
| AI Security: prompt injection, behavior hijacking, adversarial monitoring | етап 6 |
| ML System Design: agent як orchestration hub, MCP, enterprise data integration | 4.8, 4.9, 3.9, 3.11 |
| Multi-Agent: hierarchical, P2P, swarm; MARL, RLHF | 4.8, 7.6 (MARL на рівні поняття) |
| MLOps для AI: agentic CI/CD, behavioral drift, inference optimization | 7.3, 7.7, 5.7 |
| Control Patterns: feedback loops, MDP, circuit breakers, HITL | 1.8, 4.4, 2.8 |
| AI Governance: EU AI Act, Privacy-by-Design, audit trails, value alignment | етап 8 |
| Capstone: PRD, SDD, MVP, V&V Report, захист | M11 |

Чого в нас свідомо немає: глибокої математики навчання моделей і MARL з кодом (для бекенд-інженера це рівень розуміння, а не реалізації).

## Перевірені факти (жовтень 2026)

Агент, що реалізує завдання, може мати старіший knowledge cutoff. Не пиши в README, тестах чи докстрингах фактів про регуляції й специфікації з пам'яті: бери їх звідси або перевір у першоджерелі (WebFetch) і допиши сюди.

- **EU AI Act + Digital Omnibus**, Регламент (ЄС) 2026/1744 (OJ 24.07.2026, чинний з 27.07.2026). Заборонені практики: з 02.02.2025. GPAI: з 02.08.2025, повноваження AI Office щодо примусу з 02.08.2026. Прозорість ст. 50: з 02.08.2026 (маркування для систем, що вже на ринку, до 02.12.2026). High-risk Annex III: **02.12.2027** (було 02.08.2026). High-risk Annex I (продукти): **02.08.2028**. Системи публічних органів: 02.08.2030. Нові заборони (CSAM, інтимні зображення без згоди): з 02.12.2026. Джерела: artificialintelligenceact.eu/ai-act-explorer/digital-omnibus/, огляди Orrick (07.2026) і Morgan Lewis (06.2026).
- **OWASP Top 10 for Agentic Applications 2026**, опубліковано 09.12.2025 (OWASP GenAI Security Project), коди ASI01–ASI10, доповнює LLM Top 10 2025. Перевірено: ASI01 Agent Goal Hijack, ASI02 Tool Misuse and Exploitation, ASI09 Human-Agent Trust Exploitation, ASI10 Rogue Agents. Решту назв перед використанням звір на genai.owasp.org.
- **OWASP Top 10 for LLM Applications 2025**: LLM01 Prompt Injection, LLM02 Sensitive Information Disclosure, LLM03 Supply Chain, LLM04 Data and Model Poisoning, LLM05 Improper Output Handling, LLM06 Excessive Agency, LLM07 System Prompt Leakage, LLM08 Vector and Embedding Weaknesses, LLM09 Misinformation, LLM10 Unbounded Consumption.
- **A2A**: під Linux Foundation з 06.2025, v1.0 у 2026. Agent card за адресою `/.well-known/agent-card.json` (до v0.3 `agent.json`). Стани задачі: submitted, working, input-required, completed, failed, canceled (також auth-required, rejected, unknown; звір зі специфікацією на a2a-protocol.org перед тестами).
- **MCP**: транспорти stdio і Streamable HTTP (SSE-транспорт застарів). Авторизація OAuth 2.1, сервер публікує protected resource metadata (RFC 9728) і перевіряє audience токена. Token passthrough заборонений у security best practices специфікації.

## Нотатки до реалізації (ризикові завдання)

Загальні правила й процес: `docs/task-authoring.md`. Тут лише специфічне.

- **169 BPE:** навчання на байтах UTF-8 (як GPT-2), щоб будь-який текст кодувався без `unk`. Порівняння «укр/англ» на фіксованому паралельному корпусі в тестах, межа «укр щонайменше в 1,3 раза дорожча», а не точне число.
- **170 Sampling:** API приймає `rng: random.Random`. Перевірки розподілу: χ² або межі частот на 10 000 вибірках з seed, з запасом. Temperature 0 = argmax, рівні значення за індексом.
- **171 HNSW:** дані генерує `random.Random(seed)` у тестах (~2000 векторів, dim 16). Перевіряти recall@10 ≥ 0.9 при `ef_search=64` і монотонність середнього recall за ef, а не точні сусіди. Час не міряти, міряти кількість обчислень відстані (лічильник у класі).
- **172 Квантизація:** int8 зі scale на вимір, бінарна через знак. Пам'ять рахувати байтами масивів. Matryoshka імітувати «embeddings», де перші виміри несуть більше сигналу (генерувати так у фікстурі), бо справжньої моделі немає.
- **175 Контекст:** токени рахувати простою функцією (слова × 1.3 або символи / 4), яку передають параметром `count_tokens`. Компактизація через `summarize=fake_llm`, перевіряти поріг і що закріплені інструкції не стискаються.
- **177 Constrained decoding:** обмежити підмножиною JSON Schema (object з required-полями типів string/integer/boolean/enum, без вкладеності). Словник «токенів» це рядки по 1–3 символи. Інакше завдання стане тижневим.
- **179 Grounding:** «твердження» це речення. Мок-NLI це функція `(claim, chunk) -> "supported"|"contradicted"|"unknown"` з фікстури. Тестувати вигадані номери цитат, цитати на незнайдений чанк і поріг для abstain.
- **180 GraphRAG:** екстрактор сутностей це функція з фікстури (словник «чанк → сутності/зв'язки»). Label propagation детермінована: порядок вузлів за id, нічиї за найменшою міткою.
- **186 Sandbox:** канонізація через `os.path.realpath` / `Path.resolve()`. Symlink-тести з `skipif`, якщо `os.symlink` недоступний (Windows без прав). Порівняння регістру залежить від ОС: явно задати в докстрингу, що політика чутлива до регістру, а нормалізація лише `..` і symlink.
- **187 Durable:** інструменти рахують побічні ефекти в спільному лічильнику. Тест «падає після кожного кроку N»: для кожного N симулювати падіння винятком і replay, побічних ефектів має бути рівно по одному.
- **189 A2A:** не реалізовувати весь протокол. Валідація картки (обов'язкові поля name, url, version, skills[].id), вибір агента за тегами skill і автомат станів задачі з забороною недопустимих переходів.
- **192 Статистика evals:** bootstrap з `random.Random(seed)`, 2000 ресемплів. Тести: на однакових даних гейт не падає, на справжньому погіршенні на 15 п.п. з n=200 падає.
- **196 Guardrails:** класифікатор jailbreak це функція-параметр (мок). Тестувати порядок rails, fail closed при винятку класифікатора, redact замість block для PII і блок Markdown-зображень на домени поза allowlist.
- **197 CaMeL:** значення як обгортка `Tainted(value, sources)`. Операції над tainted дають tainted (конкатенація, f-string через хелпер). Політика: аргумент `to` у `send_email` не може бути tainted з недовіреного джерела. Не намагатись перехопити довільний Python, лише API завдання.
- **199 MCP poisoning:** невидимі символи це категорія Unicode `Cf` (zero-width, Tags U+E0000–U+E007F, bidi). Pinning: SHA-256 від канонічного JSON (`sort_keys=True, separators=(",", ":")`) визначення інструмента.
- **200 Red team:** «система» це мок-функція з відомими вразливостями (пропускає base64, ловить лише англійське «ignore previous»). ASR рахувати за категоріями. Тест: після «виправлення» системи (друга мок-функція) ASR падає, і гейт це фіксує.
- **201 Pickle:** `pickletools.genops`, небезпечні GLOBAL і STACK_GLOBAL (для STACK_GLOBAL модуль і ім'я беруться з попередніх рядкових опкодів). Фікстури генерувати `pickle.dumps` безпечних об'єктів і вручну зібраних байтів зі шкідливими імпортами. **Ніколи не викликати `pickle.loads` у тестах.**
- **207 Audit trail:** «видалення PII без зламу ланцюжка» робиться так: у хеш іде не PII, а його HMAC або окремий хеш поля; видалення стирає значення й залишає хеш поля. Тест: після видалення `verify()` проходить, а значення недоступне.
- **208 EU AI Act:** використовувати лише дати й категорії з розділу «Перевірені факти». Вхід це структура з полями (practice, domain з переліку Annex III, interacts_with_humans, generates_content, is_gpai, role provider|deployer). Вихід: категорія, обов'язки, дата застосування. У README чітко: навчальна спрощена модель, не юридична порада.
- **211 Text-to-SQL:** `sqlite3.Connection.set_authorizer`, дозволити SQLITE_SELECT, SQLITE_READ для allowlist (таблиця, колонка), SQLITE_FUNCTION для безпечних функцій. Кілька statement відсікаються через `sqlite3.complete_statement` / виконання лише одного `execute`. LIMIT додавати через обгортку `SELECT * FROM (<запит>) LIMIT n`.
- **212 Slopsquatting:** знімок реєстру це фікстура (JSON: назва → дата першого релізу, кількість релізів). Нормалізація назв за PEP 503 (`re.sub(r"[-_.]+", "-", name).lower()`).
- **213 Token exchange:** не JWT-криптографія, а модель токена (dict) з полями `sub`, `act` (вкладений ланцюжок), `aud`, `scope`, `exp`. Годинник параметром. Тести: scope = перетин, заборона розширення, aud прив'язаний, ланцюжок `act` росте при делегуванні, протермінований токен відхиляється.

## План автотестів (виконано: усі 39 завдань мають автотести)

Партіями по етапу, кожна окремим комітом, за правилами з `CLAUDE.md` (заглушка червона, еталон зелений і не в репозиторії, мутанти ловляться):

1. Безпека (етап 6): 196, 197, 198, 199, 200, 201, 212, 213
2. RAG (етап 3): 178, 179, 180, 181, 182, 211
3. Агенти (етап 4): 183, 184, 185, 186, 187, 188, 189
4. Evals (етап 5): 191, 192, 193, 194, 216
5. Основи (етап 1): 169, 170, 171, 172, 173
6. API (етап 2): 175, 176, 177
7. LLMOps і governance (етапи 7–8): 203, 204, 207, 208, 209

Коли з'являється папка `tasks/tNNN_...`, генератор сам знімає позначку «готується» (тип «автотест» ігнорується). Рядок `*Тип:* автотест` після цього варто прибрати з каталогу для чистоти.
