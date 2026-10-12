"""Завдання №129: RAG з нуля: чанкінг, векторний пошук, відповідь із цитатами і метрики якості пошуку.

Справжні embeddings потребують моделі, тому тут вони детерміновані: «мішок слів» з хешуванням. Логіка RAG від цього не змінюється.

chunk_words(text, size=50, overlap=10) -> list[dict]
    words = text.split(). Чанки по `size` слів з кроком size - overlap: start = 0, step, 2*step, ...; чанк = слова [start, start + size).
    Зупинитись одразу після чанка, що дійшов до кінця тексту (хвіст, повністю вкладений у попередній чанк, не створюється).
    Чанк {"start": індекс першого слова, "text": " ".join(слів)}. Порожній текст: []. size < 1 або overlap не в [0, size): ValueError.

embed(text, dim=256) -> list[float]
    токени = re.findall(r"\w+", text.lower()); для кожного: h = int(md5(токен.encode()).hexdigest(), 16); i = h % dim;
    знак = +1, якщо (h >> 64) & 1 == 0, інакше -1; vec[i] += знак. Потім L2-нормалізація (нульовий вектор лишається нульовим).
cosine(a, b) -> float                  скалярний добуток (для нормалізованих векторів це косинус); різна довжина: ValueError.

VectorIndex(dim=256)
    .add_document(source, text, size=50, overlap=10) -> int       чанкує й додає; повертає кількість доданих чанків.
        Чанк в індексі {"id": наскрізний номер з 0, "source", "start", "text"}.
    .search(query, k=3, min_score=0.0) -> list[dict]
        [{"score": round(cosine, 4), "chunk": чанк}, ...] за спаданням score (при рівності за id), до k штук, лише з cosine > min_score.
        k < 1: ValueError. Порожній індекс: [].

build_prompt(question, hits) -> str
    Рядки, відокремлені одним "\n":
      "Answer using only the sources below. Cite sources as [1], [2]. If the answer is not in the sources, say \"I don't know\"."
      "" (порожній рядок)
      по одному рядку на джерело: f"[{n}] ({source}) {text}" де n = 1, 2, ... за порядком hits
      "" (порожній рядок)
      f"Question: {question}"
    Без hits блок джерел порожній (між двома порожніми рядками нічого немає).
extract_citations(answer) -> list[int]       унікальні числа з шаблонів [n] (одне або кілька цифр) за зростанням.
check_citations(answer, n_sources) -> dict   {"valid": [...], "invalid": [...]}: валідні 1..n_sources; решта (включно з 0) вигадані.

evaluate(index, dataset, k=3) -> dict
    dataset: [{"question": str, "relevant": {source, ...}}, ...]; порожній: ValueError. Для кожного питання беруться top-k search.
      recall      частка питань, де серед top-k є хоч один чанк із relevant-джерела;
      precision   середня по питаннях частка чанків top-k, що з relevant-джерел (якщо знайдено 0 чанків, для питання це 0);
      mrr         середнє 1 / (позиція першого релевантного чанка, з 1), 0 якщо немає.
    Усі три округлені до 4 знаків.
"""


def chunk_words(text: str, size: int = 50, overlap: int = 10) -> list[dict]:
    raise NotImplementedError


def embed(text: str, dim: int = 256) -> list[float]:
    raise NotImplementedError


def cosine(a: list[float], b: list[float]) -> float:
    raise NotImplementedError


class VectorIndex:
    def __init__(self, dim: int = 256) -> None:
        raise NotImplementedError

    def add_document(self, source: str, text: str, size: int = 50, overlap: int = 10) -> int:
        raise NotImplementedError

    def search(self, query: str, k: int = 3, min_score: float = 0.0) -> list[dict]:
        raise NotImplementedError


def build_prompt(question: str, hits: list[dict]) -> str:
    raise NotImplementedError


def extract_citations(answer: str) -> list[int]:
    raise NotImplementedError


def check_citations(answer: str, n_sources: int) -> dict:
    raise NotImplementedError


def evaluate(index: VectorIndex, dataset: list[dict], k: int = 3) -> dict:
    raise NotImplementedError
