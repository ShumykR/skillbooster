# №57 · Заголовки безпеки та CORS 🟡

**Ситуація.** API віддає `Access-Control-Allow-Origin: *`, сторінки відкриваються в чужому iframe, браузер вгадує типи файлів, а `Server: nginx/1.18.0` підказує, які CVE пробувати. Усе це виправляють кілька заголовків.

**Що зробити** у `check_headers` (правила у докстрингу): прийняти заголовки відповіді та повернути знайдені проблеми. Це те, що перевіряють [securityheaders.com](https://securityheaders.com/) і [Mozilla Observatory](https://developer.mozilla.org/en-US/observatory).

**Подумай:**
- `Access-Control-Allow-Origin: *` разом із `Allow-Credentials: true` браузер і так заблокує, але список дозволених origin краще вести явно;
- `'unsafe-inline'` у CSP зводить захист від XSS майже нанівець; замінюється nonce або hash;
- у FastAPI ці заголовки додають middleware (наприклад, власний або `secure`), а HSTS часто ставить reverse proxy.

**Перевірка:** `python check.py t57`.
