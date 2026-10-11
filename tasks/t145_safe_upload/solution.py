"""Завдання №145: безпечне завантаження файлів.

Користувач завантажує «аватар». Якщо довіряти імені й розширенню, він завантажить `shell.php`,
HTML з JavaScript під виглядом `.png` або `.htaccess`, і сервер віддасть це як код чи сторінку
(CWE-434, **№12 у MITRE CWE Top 25**; CWE-646 довіра до імені/розширення).

`validate_upload(filename, content, *, max_size=5*1024*1024, name_factory=...) -> dict`
    `filename` це рядок від клієнта, `content` це `bytes`. При успіху повертає словник
    `{"stored_name", "content_type", "original_name"}`; при відмові піднімає
    `UploadRejected(reason)` (підклас `ValueError`, атрибут `.reason`).

    Перевірки виконуються ЗА ЦИМ ПОРЯДКОМ (перша, що спрацювала, дає причину):
    1. `too_large`            `len(content) > max_size`;
    2. `empty`                `content` порожній;
    3. `bad_filename`         після відкидання каталогів ім'я порожнє, починається з `.`
                              (`.htaccess`, `..`), має пробіл на початку/кінці або крапку в
                              кінці (`a.png.`; Windows їх відкидає), містить керуючі символи
                              (коди < 32 або 127; сюди й NUL), довше за 100 символів;
    4. `dangerous_extension`   БУДЬ-ЯКЕ з розширень (після кожної крапки, без урахування
                              регістру) входить у DANGEROUS: php, phtml, phar, py, pl, cgi, sh,
                              bash, exe, dll, bat, cmd, com, js, mjs, html, htm, xhtml, svg, jsp,
                              asp, aspx, msi, jar, war (так ловиться `shell.php.png`;
                              SVG небезпечний, бо може містити скрипти);
    5. `extension_not_allowed` розширення немає або останнє не з allowlist: png, jpg, jpeg,
                              gif, pdf, txt;
    6. `content_mismatch`     вміст не відповідає розширенню (magic bytes):
                              png: `\\x89PNG\\r\\n\\x1a\\n`; jpg/jpeg: `\\xff\\xd8\\xff`;
                              gif: `GIF87a` або `GIF89a`; pdf: `%PDF-`; txt: валідний UTF-8
                              без NUL-байтів.
    Каталоги з імені відкидаються за обома роздільниками (`/` і `\\`): `C:\\fakepath\\a.png`
    це `a.png`, `../../x.png` це `x.png`. `original_name` це ім'я після цього (регістр
    збережено, Unicode дозволено).

    Збережене ім'я НЕ містить нічого від клієнта, крім нормалізованого розширення:
    `f"{name_factory()}.{ext}"`, де `ext` нижнього регістру і `jpeg` перетворюється на `jpg`.
    `content_type` визначається за розширенням: image/png, image/jpeg, image/gif,
    application/pdf, text/plain.
"""
import uuid
from typing import Callable


class UploadRejected(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def validate_upload(
    filename: str,
    content: bytes,
    *,
    max_size: int = 5 * 1024 * 1024,
    name_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> dict:
    raise NotImplementedError
