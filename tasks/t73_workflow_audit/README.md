# №73 · Аудит GitHub Actions workflow 🟡

**Ситуація.** Workflow із `lint + test + build` працює, але в ньому: стороння дія на `@main` (її власник може підмінити код), `${{ github.event.pull_request.title }}` прямо в `run:` (команда в заголовку PR виконається на runner'і), довгоживучі ключі AWS у secrets. Саме так компрометують CI/CD.

**Що зробити** у `audit_workflow` (правила GHA001–GHA005 у докстрингу): розібрати YAML та знайти ці проблеми. Те, що ти напишеш, по суті простий [actionlint](https://github.com/rhysd/actionlint) + [zizmor](https://github.com/woodruffw/zizmor).

**Підказки (без розв'язку):**
- ключ `on:` у PyYAML (YAML 1.1) може прочитатись як булеве `True`, а не рядок `"on"`;
- тригери бувають рядком, списком або мапою;
- `steps` у job може бути відсутнім (reusable workflow викликається через `uses` на рівні job).

**Перевірка:** `python check.py t73`. Потрібен `pyyaml` (є в `requirements.txt`).

**Далі:** реально закріпи свої дії на sha (Dependabot/Renovate оновлюють їх самі) і перейди на OIDC до AWS (завдання №78).
