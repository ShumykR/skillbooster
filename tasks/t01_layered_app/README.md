# №1 · Структура проєкту 🟢

**Ситуація.** Сервіс нотаток працює, але весь код лежить в одному `main.py`: HTTP, бізнес-правила, SQL і читання `os.getenv` перемішані. Додати кеш чи замінити SQLite на Postgres, не зачепивши роути, неможливо; бізнес-правило не перевірити без HTTP і бази.

**Що зробити:** розклади `notes_app/main.py` на шари, не змінюючи поведінку API (його контракт уже покритий тестами).

```
notes_app/
├── config.py                 Settings(BaseSettings): database_path, env NOTES_DATABASE_PATH, за замовчуванням "notes.db"
├── repositories/notes.py     NoteRepository(database_path): add(title, body), get(id) -> dict | None, list()
├── services/notes.py         NoteService(repo): create / get / list; винятки InvalidNote, NoteNotFound
├── routers/notes.py          APIRouter: HTTP-статуси (422, 404) і схеми запиту
└── main.py                   create_app(): збирає Settings → репозиторій → сервіс → роутер
```

**Правила залежностей** (їх перевіряють тести, читаючи імпорти кожного файлу):
- `routers` не імпортує SQL (`sqlite3`, `sqlalchemy`) і `repositories`;
- `services` не імпортує `fastapi`/`starlette`, SQL, `routers` і конкретний `repositories`: репозиторій приходить у конструктор;
- `repositories` не імпортує `fastapi`, `services`, `routers`;
- `os.getenv` / `os.environ` є лише в `config.py`; `main.py` не працює з БД напряму.

**Поведінка не змінюється:** `POST /notes` (201, назва обрізається, порожня назва 422), `GET /notes`, `GET /notes/{id}` (404, якщо немає).

**Перевірка:** `python check.py t01`. Спершу частина тестів червона, і це нормально: на старому `main.py` падають усі архітектурні перевірки. Потрібні `fastapi`, `httpx`, `pydantic-settings` (є в `requirements.txt`).

**Підказки (без розв'язку):**
- сервіс отримує репозиторій як параметр, тож тест підставляє фейк без БД; помилки він повідомляє своїми винятками, а в HTTP-статуси їх перетворює роутер;
- `pydantic_settings.BaseSettings` + `SettingsConfigDict(env_prefix="NOTES_")` читає змінну оточення сам; `Settings()` створюй у `create_app()`, а не на рівні модуля, інакше тести не зможуть підмінити змінну;
- як роутер отримує сервіс: `Depends` + `request.app.state`, або фабрика `create_router(service)`; обидва варіанти проходять тести;
- імпорти всередині пакета пиши повним шляхом (`from notes_app.services.notes import ...`): так їх бачить перевірка.

**Подумай (тести цього не покривають):**
- чому тут `NoteRepository` конкретний клас у `repositories`, а сервіс знає лише його «форму»? Що змінилось би, якби сервіс імпортував клас напряму?
- що саме треба змінити, щоб замінити SQLite на Postgres? Скільки файлів це зачепить?
- коли така структура надлишкова (скрипт на 50 рядків) і коли без неї не обійтись?
