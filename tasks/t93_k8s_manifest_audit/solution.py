"""Завдання №93: аудит маніфестів Kubernetes.

`audit_manifests(text)` приймає YAML з кількома документами (`---`) і повертає
відсортований список унікальних рядків `правило:Kind/name`.

Перевіряються Deployment, StatefulSet, DaemonSet (pod лежить у `spec.template.spec`).
Правила рахуються на рівні обʼєкта (одне порушення в будь-якому з `containers` дає один рядок):
- `latest_tag`           образ без тегу або з `:latest` (digest `@sha256:` не рахується);
- `no_resources`         у контейнері немає ВСІХ чотирьох значень:
                         requests.cpu, requests.memory, limits.cpu, limits.memory;
- `no_readiness_probe`   немає `readinessProbe`;
- `no_liveness_probe`    немає `livenessProbe`;
- `privileged`           `securityContext.privileged: true` у контейнері;
- `may_run_as_root`      `runAsNonRoot` не True ні у контейнері, ні на рівні pod
                         (значення контейнера має пріоритет над pod);
- `single_replica`       лише для Deployment: `replicas` менше 2 (за замовчуванням 1).

Додатково для Service:
- `orphan_service:Service/<name>`  непорожній `spec.selector` не збігається з жодним набором
                         міток pod (`spec.template.metadata.labels`) у цьому файлі:
                         усі пари селектора мають бути серед міток pod.

Порожні документи (`---` без вмісту) та обʼєкти інших видів ігноруємо.
"""


def audit_manifests(text: str) -> list[str]:
    raise NotImplementedError
