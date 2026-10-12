"""Завдання №13: Потокове завантаження великих файлів.

`save_upload` приймає тіло запиту як асинхронний потік шматків (так віддає
`request.stream()` у FastAPI/Starlette) і зберігає його у `dest`.

Зараз усе читається в пам'ять, а ліміт розміру перевіряється вже після цього:
файл на 2 ГБ спершу з'їсть 2 ГБ RAM і лише потім буде відхилений.

Вимоги:
- пам'ять не залежить від розміру файлу: шматок записується на диск одразу;
- ліміт `max_bytes` перевіряється на льоту: щойно загальний розмір перевищив ліміт,
  читання зупиняється (`UploadTooLarge`), решту потоку не споживаємо;
- файл у `dest` з'являється лише після повного успішного завантаження
  (пиши у тимчасовий файл поряд і перейменовуй); при будь-якій помилці
  (ліміт, обрив з'єднання) тимчасових файлів не лишається;
- повертає кількість записаних байтів; порожнє завантаження допустиме (0).
"""
from pathlib import Path
from typing import AsyncIterator


class UploadTooLarge(Exception):
    pass


async def save_upload(chunks: AsyncIterator[bytes], dest: Path, *, max_bytes: int) -> int:
    data = b"".join([chunk async for chunk in chunks])
    if len(data) > max_bytes:
        raise UploadTooLarge(f"{len(data)} > {max_bytes}")
    dest.write_bytes(data)
    return len(data)
