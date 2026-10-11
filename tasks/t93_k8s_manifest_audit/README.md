# №93 · Аудит Kubernetes-маніфестів 🟡

**Ситуація.** Pod без `resources` з'їдає всю ноду, без `readinessProbe` отримує трафік ще до готовності, під `:latest` ніхто не скаже, що саме працює, а Service із помилкою в `selector` просто нікуди не веде і мовчить.

**Що зробити** у `audit_manifests` (правила у докстрингу): розібрати багатодокументний YAML і знайти ці проблеми. Це спрощена версія того, що роблять [kubeconform](https://github.com/yannh/kubeconform) (схема), [kube-linter](https://github.com/stackrox/kube-linter) і [kube-score](https://github.com/zegl/kube-score) (практики).

**Підказки (без розв'язку):**
- `yaml.safe_load_all` віддає документи по одному, а порожній документ дає `None`;
- `securityContext` буває на двох рівнях (pod і контейнер), і контейнер перекриває pod;
- «усі пари селектора є в мітках» це перевірка, що одна мапа міститься в іншій;
- `replicas` може бути відсутнім.

**Перевірка:** `python check.py t93`. Кластер не потрібен, потрібен `pyyaml`.

**Далі:** прожени справжні `kubeconform` і `kube-linter` на тих самих файлах, а потім розгорни маніфест на [Killercoda](https://killercoda.com/) і зламай readiness-проб, щоб побачити, як pod випадає з Service.
