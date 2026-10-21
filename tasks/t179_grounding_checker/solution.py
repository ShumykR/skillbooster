"""Завдання №179: grounding checker. Чи підтверджує знайдений контекст кожне твердження відповіді?

RAG-відповідь із цитатами ще не означає, що цитати правдиві: модель може послатись на [2] і написати те,
чого в [2] немає, або вигадати [7] при трьох джерелах. Перевірка розбиває відповідь на твердження й
зіставляє кожне з процитованими чанками: спершу дешевий лексичний фільтр, потім NLI-суддя (мок: звичайна
функція). Якщо підтримки бракує, система відповідає «не знаю».

Дані. `chunks`: знайдені чанки у порядку промпта, `[{"id": str, "text": str}, ...]`; цитата `[n]` це
chunks[n - 1] (нумерація з 1). `nli(claim, chunk_text) -> "supported" | "contradicted" | "unknown"`
(будь-яке інше значення вважається "unknown"). `claim` це текст твердження БЕЗ маркерів цитат.

split_claims(answer) -> list[str]
    Твердження це речення. Різати після `.`, `!` або `?`, за якими йде пробільний символ (отже "3.5" не
    ріжеться). Шматок, що складається лише з маркерів цитат (`[1]`, `[1, 2]`, `[1][2]`), приєднується
    через пробіл до попереднього речення ("Paris is in France. [1]" це одне твердження). Шматки обрізати
    (strip); порожні відкинути. Маркери цитат у реченнях лишаються. Порожня відповідь: [].

extract_citations(sentence) -> list[int]
    Унікальні номери з маркерів `[n]` і `[n, m]` (регулярний вираз \\[(\\d+(?:\\s*,\\s*\\d+)*)\\]) за зростанням.
    Маркер із буквами (`[a]`, `[1a]`) маркером не є.

claim_text(sentence) -> str
    Речення без маркерів цитат: маркери видалити, пробіли звести до одного (`" ".join(s.split())`), потім
    прибрати пробіли перед знаками `. , ; : ! ?`.
    ("Paris is in France [1]." -> "Paris is in France.")

overlap(claim, chunk_text) -> float
    Лексичне перекриття: токени = множина слів re.findall(r"\\w+", text.lower()) довжиною >= 3 символи.
    Частка токенів твердження, що є серед токенів чанка: |A & B| / |A|. Порожнє A: 0.0. Не округляти.

check_grounding(answer, chunks, nli, min_overlap=0.5) -> dict
    Для кожного твердження (split_claims) за порядком, вердикт (перше правило, що спрацювало):
      1. немає жодного маркера цитати                       -> "uncited"
      2. є номер < 1 або > len(chunks)                      -> "invented-citation" (навіть якщо інші валідні)
      3. для кожного процитованого чанка (за зростанням номера), у якого overlap(claim, chunk) >= min_overlap,
         викликати nli(claim_text, chunk["text"]) РІВНО один раз (чанки нижче порога NLI не викликають);
         - є хоч один "contradicted"                        -> "contradicted"
         - інакше є хоч один "supported"                    -> "supported"
         - інакше (усі "unknown" або жоден чанк не пройшов фільтр) -> "unsupported"
    Результат:
      {"claims": [{"sentence": оригінальне речення, "text": claim_text, "citations": [усі номери за зростанням,
                   у т.ч. вигадані], "verdict": ..., "overlap": найбільше overlap серед ВАЛІДНИХ процитованих
                   чанків, round(, 4), 0.0 якщо таких немає}, ...],
       "supported_ratio": supported / всіх тверджень, round(, 4); тверджень немає: 0.0}
    min_overlap поза [0, 1]: ValueError.

guarded_answer(answer, chunks, nli, threshold=0.8, min_overlap=0.5, idk=IDK) -> dict
    {"answer": answer або idk, "abstained": bool, "report": check_grounding(...)}.
    Відповісти "не знаю" (answer = idk, abstained = True), якщо виконується хоч одне: тверджень немає;
    supported_ratio < threshold; є твердження з вердиктом "contradicted" або "invented-citation".
    Інакше answer без змін, abstained = False. threshold поза [0, 1]: ValueError.
"""

IDK = "I don't know based on the provided sources."


def split_claims(answer: str) -> list[str]:
    raise NotImplementedError


def extract_citations(sentence: str) -> list[int]:
    raise NotImplementedError


def claim_text(sentence: str) -> str:
    raise NotImplementedError


def overlap(claim: str, chunk_text: str) -> float:
    raise NotImplementedError


def check_grounding(answer: str, chunks: list[dict], nli, min_overlap: float = 0.5) -> dict:
    raise NotImplementedError


def guarded_answer(answer: str, chunks: list[dict], nli, threshold: float = 0.8, min_overlap: float = 0.5,
                   idk: str = IDK) -> dict:
    raise NotImplementedError
