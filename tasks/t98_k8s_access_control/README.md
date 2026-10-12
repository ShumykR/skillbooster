# №98 · NetworkPolicy, RBAC, Pod Security: мінімальні права 🔴

**Ситуація.** У новому кластері кожен pod може постукати в кожен інший, `default` ServiceAccount має більше прав, ніж треба, а в одному Deployment лишився `privileged: true` «щоб запрацювало». Три механізми закривають це, і в усіх трьох чимало неочевидних правил: політики лише *додають* дозволи, `RoleBinding` на `ClusterRole` діє в одному namespace, «`podSelector` + `namespaceSelector`» в одному елементі це AND, а в двох елементах OR.

**Що зробити** у `solution.py` (формати даних і правила в докстрингу), три частини:
- **NetworkPolicy:** `isolation` та `connection_allowed` обчислюють, чи пройде зʼєднання з урахуванням egress джерела й ingress призначення;
- **RBAC:** `rbac_allowed` відповідає на `kubectl auth can-i`, а `rbac_audit` знаходить ризикові binding'и (wildcard, читання secrets, `pods/exec`, escalate/bind/impersonate, `default` ServiceAccount);
- **Pod Security Standards:** `pod_security_violations` повертає порушення рівнів `baseline` і `restricted`.

**Підказки (без розв'язку):**
- «ізольований» це властивість напрямку: пустий список правил з типом `Ingress` забороняє все, а відсутність політик дозволяє все;
- namespace мають автоматичну мітку `kubernetes.io/metadata.name`, на неї зручно вибирати namespace за імʼям;
- RBAC дозволів не забороняє: достатньо одного правила в одному binding, а `resourceNames` не діє на запити без імені (list, create);
- рівень `restricted` це `baseline` плюс жорсткі вимоги до контейнера; ефективне значення береться з контейнера, а якщо воно не задане, то з pod'а.

**Подумай:**
- чому default-deny + явні дозволи надійніше за «заборонити відомо погане» (і чому DNS на порту 53 теж треба дозволити в egress);
- чим `view` ClusterRole із секретами небезпечніша за `edit` без них (пригадай №59, 60 про IAM);
- що NetworkPolicy працює лише якщо CNI її підтримує (Calico, Cilium), інакше об'єкт створюється й нічого не робить;
- як Pod Security Admission вмикається міткою namespace (`pod-security.kubernetes.io/enforce=restricted`) і чим відрізняється режим `warn` від `enforce`.

**Перевірка:** `python check.py t98`. Лише стандартна бібліотека. Далі: на kind з Calico застосуй default-deny і перевір `kubectl exec ... -- wget`, потім `kubectl auth can-i --as=system:serviceaccount:shop:ci delete deployments -n shop`.
