"""Завдання №123: mutation testing: чи справді твої тести щось перевіряють.

100% покриття означає лише, що рядки виконались, а не що тести помітили б помилку. Mutation testing навмисно ламає код дрібними змінами
(мутаціями) і запускає тести: «вбитий» мутант означає, що тести помітили зміну, «вижив» означає діру в тестах. Реалізуй мінімальний
інструмент на AST (як mutmut/cosmic-ray, але в мініатюрі).

generate_mutants(source) -> list[dict]
    Парсить source (ast.parse) і для КОЖНОГО застосовного вузла робить окремий мутант (одна зміна на мутант). Оператори (поле "op"):
      "cmp"    у Compare кожен оператор окремо: < -> <=, <= -> <, > -> >=, >= -> >, == -> !=, != -> ==  (інші, як in/is, не чіпати);
      "arith"  у BinOp та AugAssign: + -> -, - -> +, * -> /, / -> *  (інші, як // чи %, не чіпати);
      "bool"   у BoolOp: and -> or, or -> and (весь вираз цілком);
      "not"    UnaryOp(Not): прибрати not (лишити операнд);
      "const"  ціла константа n (не bool) -> n + 1; булева True -> False, False -> True;
      "return" return <вираз> -> return None (лише якщо значення є і воно не константа None).
    Кожен мутант: {"id": 1, 2, ... за порядком, "line": номер рядка вузла, "op": імʼя оператора, "description": текст, "source": ast.unparse(мутоване дерево)}.
    description: "<старе> -> <нове>" для cmp/arith/bool/const (наприклад ">= -> >", "+ -> -", "and -> or", "18 -> 19", "True -> False"),
    "not removed" для not, "return -> return None" для return.
    Порядок: за ключем (line, col_offset вузла, op, індекс оператора всередині вузла; 0 для вузлів з одним оператором); якщо ключі повністю збігаються (вкладені вузли
    з однаковою позицією, напр. `a and b or c`), порядок визначає обхід ast.walk (спершу зовнішній вузол). Для Compare
    вузол це сам Compare, для BinOp/BoolOp відповідний вузол, для AugAssign весь оператор присвоєння.
    Мутант, чий source збігається з ast.unparse оригіналу, відкидається (ids нумеруються після відкидання).
    Синтаксична помилка в source: SyntaxError летить нагору.

mutation_report(source, test, *, max_steps=200_000) -> dict
    test(namespace) -> bool: namespace це словник після exec(compile(код)) у чистому словнику; тест повертає True, якщо всі перевірки пройшли.
    Спершу тест запускається на ОРИГІНАЛІ: якщо він повертає не True або кидає виняток, ValueError (мутувати нема сенсу).
    Для кожного мутанта: exec його коду й виклик test. Мутант «вбитий», якщо exec або test кинули Exception, або test повернув не True;
    «вижив», якщо test повернув True. Нескінченні цикли: тест виконується під лічильником (sys.settrace), що рахує події виконання;
    якщо їх більше max_steps, виконання переривається й мутант вважається вбитим (timeout). Попередній трасувальник (sys.gettrace()) відновлюється завжди,
    в тому числі після винятку.
    Результат: {"total": кількість мутантів, "killed": ..., "survived": ..., "score": round(killed / total, 4) (1.0, якщо мутантів немає),
                "survivors": [{"id", "line", "op", "description"}, ...] за порядком id}.
"""


def generate_mutants(source: str) -> list[dict]:
    raise NotImplementedError


def mutation_report(source: str, test, *, max_steps: int = 200_000) -> dict:
    raise NotImplementedError
