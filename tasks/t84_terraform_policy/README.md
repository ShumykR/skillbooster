# №84 · Політики для Terraform plan 🟡

**Ситуація.** Хтось відкрив SSH на `0.0.0.0/0`, забув шифрування RDS і залишив бакет публічним. `terraform validate` це пропустить, бо код *синтаксично* правильний. Такі помилки ловлять політиками над планом: [conftest](https://www.conftest.dev/) (OPA/Rego), [Checkov](https://www.checkov.io/), [tfsec/Trivy](https://trivy.dev/).

**Що зробити** у `evaluate_plan` (правила у докстрингу): прочитати JSON плану (`terraform show -json tfplan`) і повернути порушення як пари `(правило, адреса)`. Працювати треба зі словником, Terraform не потрібен.

**Підказки (без розв'язку):**
- у плані ресурси лежать плоским списком `resource_changes`, навіть якщо вони з модулів: адреса містить `module.x.`;
- для видалення `after` дорівнює `None`;
- порт 22 може бути всередині діапазону (`from_port=0, to_port=65535`) або під протоколом `-1`;
- `cidr_blocks` / `ipv6_cidr_blocks` у правилі можуть бути відсутніми або `None`.

**Перевірка:** `python check.py t84`.

**Далі:** згенеруй справжній план для свого `.tf` (`terraform plan -out tfplan && terraform show -json tfplan > plan.json`) і запусти на ньому свою функцію, потім перепиши ті самі правила на Rego для `conftest test plan.json`.
