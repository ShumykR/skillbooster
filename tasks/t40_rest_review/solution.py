"""Завдання №40: REST-рев'ю: лінтер OpenAPI.

`review_openapi(spec)` отримує OpenAPI 3 як словник і повертає відсортований список
унікальних рядків-зауважень `"<код> <деталі>"`. Порожній список означає «зауважень немає».

Терміни:
- параметр шляху: сегмент `{id}`; «сторінка елемента»: шлях, що закінчується параметром (`/v1/users/{id}`);
- «колекція»: шлях, що НЕ закінчується параметром і для якого в spec є шлях, що починається з нього
  плюс `/{` (`/v1/users` при наявному `/v1/users/{id}`).

Правила (деталі в дужках це формат рядка):
- R001  дієслово в шляху (`R001 <path>`): будь-який сегмент (не параметр) збігається з
        `^(get|create|delete|update|add|remove|fetch|list|set|save)([A-Z_-]|$)`: `getUsers`, `create-user`, `list`;
        але `settings`, `listings` це нормально;
- R002  сегмент (не параметр) містить велику літеру або `_` (`R002 <path>`): шляхи пишемо у kebab-case;
- R003  POST на колекцію, що має успішні (2xx) відповіді, але жодної з `201`/`202` (`R003 POST <path>`);
- R004  DELETE без відповіді `204` (`R004 DELETE <path>`);
- R005  GET із `requestBody` (`R005 GET <path>`);
- R006  GET/PUT/PATCH/DELETE на сторінці елемента без відповіді `404` (`R006 <METHOD> <path>`);
- R007  GET на колекцію без жодного параметра пагінації з імен `limit`, `page`, `page_size`, `per_page`,
        `cursor`, `offset` (`R007 GET <path>`); параметри бувають на рівні шляху або операції, і як
        `{"$ref": "#/components/parameters/Name"}`;
- R008  відповідь 4xx/5xx/`default` без `content` або без медіатипу `application/problem+json` (RFC 9457)
        (`R008 <METHOD> <path> <код>`);
- R009  POST/PUT/PATCH/DELETE без ефективної автентифікації (`R009 <METHOD> <path>`): береться
        `security` операції, а якщо його немає, то глобальне `security`; порожнє/відсутнє це порушення;
- R010  шлях закінчується на `/`, окрім самого `/` (`R010 <path>`);
- R011  шлях не починається з версії `/v<число>/` (`R011 <path>`).

Методи: get, put, post, delete, patch (інші ключі шляху, як `parameters`, не операції).
"""

METHODS = ("get", "put", "post", "delete", "patch")


def review_openapi(spec: dict) -> list[str]:
    raise NotImplementedError
