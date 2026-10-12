"""Завдання №130: Покращення RAG: hybrid search (BM25 + вектор), RRF, reranking, query rewriting, метрики до/після.

Вектор шукає за змістом, але плутає рідкісні точні терміни («ERR-4012», артикул). BM25 шукає за словами, але не знає синонімів
(«автомобіль» проти «машина»). Гібрид зливає обидва списки.

STOPWORDS = {"a", "an", "the", "is", "are", "to", "of", "in", "on", "for", "and", "or", "how", "do", "i", "my", "what", "does"}
tokenize(text, drop_stopwords=True) -> list[str]     re.findall(r"\w+", text.lower()) без стоп-слів (якщо drop_stopwords).

BM25(docs, k1=1.5, b=0.75)         docs: список текстів. Токени через tokenize. avgdl = середня довжина документа в токенах.
    .scores(query) -> list[float]  для кожного документа: сума по УНІКАЛЬНИХ токенах запиту
        idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl)),   idf = ln(1 + (N - n + 0.5) / (n + 0.5)),
        де N кількість документів, n скільки документів містять токен, tf частота токена в документі, dl довжина документа в токенах.
        Токен, якого немає ні в одному документі, дає 0. Порожній корпус або avgdl == 0: усі нулі. Без округлення.

rrf(rankings, k=60) -> list[tuple[id, float]]
    Reciprocal rank fusion: rankings це списки id від найкращого; внесок id у списку з позиції r (з 1) дорівнює 1 / (k + r).
    Результат за спаданням сумарного score (без округлення), при рівності за id за зростанням. Дубль id в одному списку рахується один раз
    (за першою позицією; наступні позиції нумеруються як є, тобто ["a", "a", "b"] дає b позицію 3).

HybridIndex(embed)                  embed(text) -> нормалізований вектор (list[float]).
    .add(doc_id, text)              doc_id унікальний; повтор: ValueError.
    .search(query, k=3, method="hybrid", pool=20) -> list[doc_id]
        "bm25": id за спаданням BM25-score, лише score > 0; "vector": за спаданням скалярного добутку з embed(query), лише > 0;
        рівні значення за порядком додавання. Обидва береться top pool. "hybrid": rrf двох списків (bm25, vector) і перші k.
        Невідомий method: ValueError. k < 1: ValueError.

rewrite_query(llm, question, history) -> str
    Робить із питання, що залежить від контексту («а скільки це коштує?»), самостійний пошуковий запит. llm(prompt) -> str.
    prompt (рядки через "\n"): "Rewrite the last question as a standalone search query. Reply with the query only.", "History:",
    по рядку на кожне повідомлення історії f"{role}: {content}" (history це список {"role", "content"}), f"Question: {question}", "Query:".
    Відповідь: перший непорожній рядок, обрізаний по краях і без однієї пари зовнішніх лапок ("..." або '...'). Якщо відповідь порожня,
    довша за 200 символів, або llm кинула Exception, повертається вихідне question.

rerank(scorer, query, candidates, top=None) -> list[id]
    candidates: [(doc_id, text), ...]; scorer(query, text) -> float (cross-encoder). Повертає id за спаданням score, при рівності у
    початковому порядку (стабільно); top обмежує довжину (None = усі).

evaluate_ranking(search, dataset, k=3) -> dict
    search(question) -> list[id]; dataset: [{"question", "relevant": {id, ...}}, ...] (порожній: ValueError). Беруться перші k id.
      recall = частка питань, де серед перших k є релевантний id;  mrr = середнє 1 / (позиція першого релевантного, з 1) або 0.
    {"recall": .., "mrr": ..} округлені до 4 знаків.
"""

import math  # noqa: F401  (може знадобитись)

STOPWORDS = {"a", "an", "the", "is", "are", "to", "of", "in", "on", "for", "and", "or", "how", "do", "i", "my", "what", "does"}


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    raise NotImplementedError


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        raise NotImplementedError

    def scores(self, query: str) -> list[float]:
        raise NotImplementedError


def rrf(rankings: list[list], k: int = 60) -> list[tuple]:
    raise NotImplementedError


class HybridIndex:
    def __init__(self, embed) -> None:
        raise NotImplementedError

    def add(self, doc_id, text: str) -> None:
        raise NotImplementedError

    def search(self, query: str, k: int = 3, method: str = "hybrid", pool: int = 20) -> list:
        raise NotImplementedError


def rewrite_query(llm, question: str, history: list[dict]) -> str:
    raise NotImplementedError


def rerank(scorer, query: str, candidates: list[tuple], top: int | None = None) -> list:
    raise NotImplementedError


def evaluate_ranking(search, dataset: list[dict], k: int = 3) -> dict:
    raise NotImplementedError
