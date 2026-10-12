"""Завдання №67: Nginx: аудит конфігурації reverse proxy.

Аналог `nginx -t` для безпеки й надійності: `audit_nginx(text)` повертає відсортований список унікальних
кодів порушень. Розбір конфігу вже є: `parse_nginx(text)` дає список вузлів
`{"name": str, "args": [str, ...], "block": list | None}`: звичайна директива має `block = None`, контекст
(`http`, `server`, `location`, `upstream`...) має список вкладених вузлів. Коментарі `#` та лапки оброблено.

Успадкування в nginx: директива діє там, де вона задана, і нижче, поки її не перевизначено. «Ефективне»
значення директиви для контексту береться з найближчого рівня зі шляху `location -> server -> http`, де вона є
(якщо на рівні кілька разів, остання). Окремо ДВІ групи директив працюють інакше: `proxy_set_header` та `add_header`
НЕ зливаються, а ЗАМІНЮЮТЬСЯ повністю: якщо на найближчому рівні є хоч один `proxy_set_header`
(`add_header`), то все, що задано вище, на цьому рівні вже не діє.

Контекст «TLS-сервер»: `server`, де є `listen` з аргументом `ssl` або директива `ssl_certificate`.
«Листові» контексти сервера: усі його `location`, а якщо їх немає, то сам `server`.

Правила:
- NG001  для якогось `server` ефективний `server_tokens` не `off` (відсутній = порушення);
- NG002  для якогось TLS-сервера немає ефективного `ssl_protocols`, або серед його значень є TLSv1, TLSv1.1, SSLv2
         чи SSLv3 (без урахування регістру);
- NG003  `server` з `listen` без `ssl` на порту 80 (`80`, `0.0.0.0:80`, `[::]:80`, `*:80`), у якому немає директиви
         `return` рівня server з кодом 301/302/307/308 і адресою на `https://`;
- NG004  у конфігу немає жодного `limit_req` (rate limiting не застосовано), або якийсь `limit_req zone=NAME`
         посилається на зону, не оголошену `limit_req_zone ... zone=NAME:розмір`;
- NG005  для якогось `location` із `proxy_pass` ефективний набір `proxy_set_header` (за правилом заміни) не містить
         усіх трьох: `Host`, `X-Forwarded-For`, `X-Forwarded-Proto` (імена без урахування регістру);
- NG006  для листового контексту TLS-сервера ефективний набір `add_header` (за правилом заміни) не містить
         `Strict-Transport-Security`;
- NG007  для якогось `location` із `proxy_pass` ефективний `client_max_body_size` відсутній або `0`;
- NG008  для якогось `server` ефективний `gzip` не `on`, або `gzip on` без ефективного `gzip_types`;
- NG009  якийсь `upstream` без директиви `keepalive`;
- NG010  будь-де є `autoindex on`.
"""
import re


def parse_nginx(text: str) -> list[dict]:
    tokens: list[str] = []
    for m in re.finditer(r"""#[^\n]*|"([^"\\]|\\.)*"|'([^'\\]|\\.)*'|[{};]|[^\s{};#"']+""", text):
        tok = m.group(0)
        if tok.startswith("#"):
            continue
        if tok[0] in "\"'":
            tok = tok[1:-1]
        tokens.append(("lit", tok) if m.group(0)[0] in "\"'" else ("raw", tok))

    def block(i: int) -> tuple[list[dict], int]:
        nodes: list[dict] = []
        words: list[str] = []
        while i < len(tokens):
            kind, tok = tokens[i]
            i += 1
            if kind == "raw" and tok == ";":
                if words:
                    nodes.append({"name": words[0], "args": words[1:], "block": None})
                words = []
            elif kind == "raw" and tok == "{":
                inner, i = block(i)
                nodes.append({"name": words[0], "args": words[1:], "block": inner})
                words = []
            elif kind == "raw" and tok == "}":
                return nodes, i
            else:
                words.append(tok)
        return nodes, i

    return block(0)[0]


def audit_nginx(text: str) -> list[str]:
    raise NotImplementedError
