"""Завдання №245: аудит GitHub Actions (як zizmor, але маленький).

`audit_workflow(text: str) -> list[dict]` приймає ТЕКСТ workflow (YAML) і повертає знахідки
`{"rule": str, "line": int, "fix": str}`: `line` це 1-based рядок КЛЮЧА, на який вказує правило
(у таблиці нижче), `fix` це непорожня порада українською чи англійською. Список без дублікатів
за `(rule, line)`, відсортований за `(line, rule)`. Порожній текст чи корінь не-мапа це `[]`.
Некоректний YAML це `ValueError`. Номери рядків дає `yaml.compose` (вузли мають `start_mark`).
Ключ `on:` YAML 1.1 читає як `True`: працюй з вузлами (`compose`), а не з `safe_load`.

Тригери: `on` може бути рядком, списком чи мапою (береться набір імен подій).

| rule                      | рядок | коли |
|---------------------------|-------|------|
| `unpinned-action`         | ключ `uses` | `uses` кроку чи job (reusable workflow) не закріплено на повний 40-символьний hex sha (`owner/repo@v4`, `@main`, без `@`). Шляхи `./...` і `docker://...` пропускаємо. Це стосується й `actions/*` |
| `missing-permissions`     | ключ job-а у `jobs` | на верхньому рівні немає `permissions` І в цьому job теж немає |
| `broad-permissions`       | ключ `permissions` | значення `write-all` (будь-де), або `permissions` на ВЕРХНЬОМУ рівні має хоч один дозвіл `write` |
| `pr-target-checkout`      | ключ `uses` | є тригер `pull_request_target`, а `actions/checkout` (будь-який ref) має `with.ref` чи `with.repository` із `github.event.pull_request.head.`, `github.head_ref` або `github.event.workflow_run.head_` |
| `script-injection`        | ключ `run` або `script` | у `run:` кроку чи у `with.script` дії `actions/github-script` є `${{ ... }}`, вираз якого містить недовірений контекст (нижче) |
| `secrets-in-workflow-env` | ключ `env` верхнього рівня | значення в `env` верхнього рівня містить `secrets.` (секрет бачить кожен крок кожного job) |
| `self-hosted-pr`          | ключ `runs-on` | `runs-on` (рядок, список чи мапа, усі скаляри) містить `self-hosted` (без урахування регістру), а тригери містять `pull_request` або `pull_request_target` |
| `cache-key-injection`     | ключ `key` або `restore-keys` | крок `actions/cache` (також `/restore`, `/save`) має в `with.key`/`with.restore-keys` недовірений контекст |

Недовірені контексти (усередині `${{ ... }}`, у будь-якому місці виразу):
- `github.head_ref`;
- `github.event.{issue,pull_request,discussion,comment,review,review_comment}.{title,body}`;
- `github.event.pull_request.head.{ref,label}`;
- `github.event.{head_commit,commits[N]}.{message,author.name,author.email}`;
- `github.event.pages[N].page_name`;
- `github.event.workflow_run.{head_branch,head_commit.message,head_commit.author.name,head_commit.author.email}`.
Безпечні (не знахідка): `github.sha`, `github.event.pull_request.number`, `github.run_id`, `secrets.*`
у `run` (це інше правило), будь-який вираз в `env:` кроку.
"""


def audit_workflow(text: str) -> list[dict]:
    raise NotImplementedError
