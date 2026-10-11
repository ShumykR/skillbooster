"""Завдання №73: аудит workflow GitHub Actions.

`audit_workflow(text)` приймає YAML workflow і повертає відсортований список унікальних
кодів знайдених проблем.

Правила:
- GHA001  немає `permissions` на верхньому рівні І хоча б у одного job немає власного
          `permissions` (токен тоді отримує зайві права за замовчуванням);
- GHA002  сторонню дію (не `actions/*`, не `github/*`) не закріплено на повний 40-символьний
          sha коміту (`owner/repo@v3`, `@main` це порушення); локальні `./...` та
          `docker://...` пропускаємо;
- GHA003  у `run:` підставляється недовірений ввід: `${{ ... }}` із `github.event.` або
          `github.head_ref` всередині (інʼєкція команд через заголовок PR/гілку);
- GHA004  тригер `pull_request_target` разом із `actions/checkout`, у якого `with.ref`
          вказує на код з PR (`github.event.pull_request.head...` або `github.head_ref`);
- GHA005  довгоживучі ключі AWS: десь у кроці використано `secrets.AWS_SECRET_ACCESS_KEY`
          (замість OIDC і `role-to-assume`).
"""


def audit_workflow(text: str) -> list[str]:
    raise NotImplementedError
