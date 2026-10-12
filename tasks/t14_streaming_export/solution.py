"""Завдання №14: Експорт великих даних потоком.

Адмінка вивантажує замовлення у CSV і NDJSON. Зараз усе збирається у списки й
склеюється в один рядок: на 5 млн рядків сервіс падає з нестачею пам'яті.

Перепиши так, щоб відповідь віддавалась ПОТОКОМ:
- `export_csv(rows, columns)` та `export_ndjson(rows)` це генератори рядків: не читають
  `rows` наперед і не накопичують результат. Віддавай порціями (наприклад, до 500 рядків
  в одному шматку), а не по символу;
- CSV: перший шматок починається із заголовка; коми, лапки й переноси рядків у значеннях
  екрануються за правилами CSV (RFC 4180: поле в лапках, лапки подвоюються), роздільник рядків `\\r\\n`;
  значення None це порожнє поле; значення, що починаються з `=`, `+`, `-`, `@`, потрібно
  нейтралізувати префіксом `'` (CSV/formula injection: Excel виконає формулу);
- NDJSON: один JSON-обʼєкт на рядок (`\\n` в кінці кожного), кирилиця не екранується (`ensure_ascii=False`),
  `datetime`/`date` це ISO-рядок, `Decimal` це рядок;
- `build_app(rows_factory)` дає FastAPI-застосунок із `GET /export.csv` та `GET /export.ndjson`
  (StreamingResponse, правильні `Content-Type` і `Content-Disposition: attachment`).
  `rows_factory()` повертає свіжий ітератор рядків на кожен запит.
"""
import csv
import io
import json
from typing import Any, Callable, Iterable, Iterator

from fastapi import FastAPI

Row = dict[str, Any]


def export_csv(rows: Iterable[Row], columns: list[str]) -> Iterator[str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(c) for c in columns])
    yield buf.getvalue()


def export_ndjson(rows: Iterable[Row]) -> Iterator[str]:
    yield "".join(json.dumps(row) + "\n" for row in list(rows))


def build_app(rows_factory: Callable[[], Iterable[Row]]) -> FastAPI:
    app = FastAPI()
    return app
