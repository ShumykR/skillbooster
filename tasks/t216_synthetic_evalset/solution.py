"""Завдання №216: синтетичний eval-датасет з корпусу через мок-LLM.

Щоб міряти RAG (№129-131), потрібні пари «питання -> еталонна відповідь -> чанк-джерело». Писати їх вручну довго, тож їх генерує LLM, а ви
відсіюєте брак: питання, що не мають відповіді в джерелі, перефразування одного й того самого, та вирівнюєте набір за типами.
Усе на мок-LLM: `llm(prompt: str) -> str` (звичайна функція; може кинути Exception).

Корпус: corpus = [{"id": str, "text": str}, ...]. Порожній корпус, дублікати id, не-рядки чи порожній id це `ValueError`.

Типи (TYPES = ("fact", "comparison", "multi_hop", "no_answer")):
    "fact"        одне питання на ОДИН чанк (юніт = [id])
    "comparison"  питання на ПАРУ сусідніх чанків корпусу (юніти = [corpus[i].id, corpus[i+1].id] для i = 0..n-2)
    "multi_hop"   те саме, пара сусідніх чанків
    "no_answer"   питання на один чанк, на яке в чанку відповіді НЕМАЄ (юніт = [id]; очікується answer = null)
Корпус з одного чанка не має юнітів для comparison/multi_hop (викликів немає).

generate_dataset(corpus, llm, *, types=TYPES, per_type=None, dedup_threshold=0.8, seed=0) -> dict
    Конвеєр, у ТАКОМУ порядку:
    1. ГЕНЕРАЦІЯ. Для кожного типу з `types` (у заданому порядку), для кожного його юніта (у порядку корпусу) один виклик
       llm(prompt), де prompt це рядки через "\\n":
         "You write evaluation questions for a RAG system."
         f"TYPE: {type}"
         f"CHUNK_IDS: {id1},{id2}"            (для юніта з одного чанка просто id1)
         f"CHUNK[{id1}]: {text1}"             (по рядку на чанк юніта)
         'Reply with JSON only: {"question": "...", "answer": "..."} (answer null if the chunks do not contain it).'
       Відповідь: JSON-обʼєкт, можливо в огорожі ```/```json (зніми її). Кандидат:
         {"id": f"{type}:{id1}+{id2}" (або f"{type}:{id1}"), "type", "question", "answer", "sources": [id, ...], "answerable": type != "no_answer"}
       Виняток llm: лічильник rejected["llm_error"] += 1, юніт пропускається. Не JSON або не обʼєкт: rejected["bad_json"] += 1.
       Невалідний кандидат: rejected["invalid"] += 1, якщо question не рядок або без жодного символу \\w; для відповідних типів answer не
       непорожній рядок (після strip); для no_answer answer не null.
    2. ДЕДУПЛІКАЦІЯ ПЕРЕФРАЗУВАНЬ (до дорогої перевірки). Слова питання це set(re.findall(r"\\w+", question.lower())). Кандидат
       відкидається (rejected["duplicate"] += 1), якщо Jaccard-подібність |A∩B| / |A∪B| >= dedup_threshold з БУДЬ-ЯКИМ уже залишеним
       кандидатом (будь-якого типу); залишається той, що раніше в порядку генерації.
    3. ПЕРЕВІРКА ВІДПОВІДНОСТІ ДЖЕРЕЛУ. Для кожного ще живого кандидата один виклик llm(prompt) з рядками через "\\n":
         "You verify evaluation questions."
         f"QUESTION: {question}"
         f"ANSWER: {answer}"                  (для no_answer: "ANSWER: (none)")
         f"SOURCE[{id}]: {text}"              (по рядку на чанк-джерело)
         "Can the question be answered from the SOURCE alone? Reply YES or NO."
       Відповідь судді: strip().upper(); для відповідних типів кандидат лишається, ЛИШЕ якщо вона починається з "YES"
       (інакше rejected["unanswerable"] += 1). Для no_answer лишається, ЛИШЕ якщо починається з "NO" (інакше rejected["answerable_leak"] += 1).
       Незрозуміла відповідь судді це відхилення (fail closed). Виняток судді: rejected["llm_error"] += 1, кандидат відхилено.
    4. СТРАТИФІКАЦІЯ. Якщо per_type задано (int >= 1) і кандидатів типу більше, лишається рівно per_type: відсортуй кандидатів типу за `id`,
       візьми random.Random(seed).sample(...) і знову відсортуй за `id`. Різниця додається до dropped_by_stratification.
    Результат:
      {"items": [...] (типи в порядку `types`, усередині за id),
       "report": {"generated": кількість кандидатів після кроку 1 (валідних і ні, але без bad_json/llm_error),
                  "rejected": {"llm_error", "bad_json", "invalid", "duplicate", "unanswerable", "answerable_leak"} (усі ключі завжди є),
                  "by_type": {type: кількість у items для КОЖНОГО типу з `types`},
                  "dropped_by_stratification": int,
                  "short_types": відсортований список типів із `types`, де у items менше per_type (порожній, якщо per_type не задано)}}
    Невідомий тип, порожній `types` чи дубль у `types`, per_type не int >= 1, dedup_threshold не в (0, 1]: ValueError (до будь-яких викликів llm).
    Вхідний корпус не змінюється; те саме вхідне (корпус, llm-відповіді, seed) дає той самий результат.
"""
import json  # noqa: F401
import random  # noqa: F401
import re  # noqa: F401

TYPES = ("fact", "comparison", "multi_hop", "no_answer")


def generate_dataset(corpus: list[dict], llm, *, types: tuple = TYPES, per_type: int | None = None,
                     dedup_threshold: float = 0.8, seed: int = 0) -> dict:
    raise NotImplementedError
