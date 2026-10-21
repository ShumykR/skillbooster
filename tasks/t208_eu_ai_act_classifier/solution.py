"""Завдання №208: Класифікатор ризику за EU AI Act (навчальна спрощена модель, НЕ юридична порада).

Опис системи (dict) → категорія ризику, обов'язки за роллю та строки з урахуванням Digital Omnibus
(Регламент (ЄС) 2026/1744, чинний з 27.07.2026). Усі дати ISO `YYYY-MM-DD` (рядки, їх можна порівнювати як рядки).
Модель свідомо спрощена: реальні винятки (ст. 6(3), малі підприємства, судова практика) тут не моделюються.

classify(system: dict) -> dict

Вхід (ключі, невідомий ключ це ValueError; усі булеві поля мають бути саме `bool`):
    "role":                            "provider" | "deployer"            ОБОВ'ЯЗКОВО
    "practice":                        None | код забороненої практики (нижче); типово None
    "domain":                          None | область Annex III (нижче); типово None
    "annex_i_safety_component":        bool, безпековий компонент продукту з Annex I; типово False
    "interacts_with_humans":           bool, система взаємодіє з людьми (чат-бот); типово False
    "generates_content":               bool, генерує синтетичний звук, зображення, відео чи текст; типово False
    "deepfake":                        bool, створює чи змінює deepfake; типово False
    "is_gpai":                         bool, це модель загального призначення; типово False
    "gpai_systemic_risk":              bool, модель із системним ризиком (лише разом з is_gpai=True, інакше ValueError); типово False
    "on_market_before_2026_08_02":     bool, система вже на ринку до 02.08.2026; типово False
    Не dict, відсутня role, значення поза переліками, не-bool у булевому полі: ValueError.

Заборонені практики (ст. 5):
    з 2025-02-02: "manipulation", "exploiting_vulnerabilities", "social_scoring", "crime_risk_profiling", "face_scraping",
                  "emotion_inference_work_education", "biometric_categorisation_sensitive", "realtime_biometric_id_law_enforcement"
    з 2026-12-02 (нові заборони Omnibus): "csam_generation", "non_consensual_intimate_imagery"
Області Annex III: "biometrics", "critical_infrastructure", "education", "employment", "essential_services",
    "law_enforcement", "migration", "justice_democracy"

Категорія (перше, що підійшло):
    1. "prohibited": practice не None. Обов'язки: provider ["do-not-place-on-market"], deployer ["do-not-use"]; строк це дата
       практики. Інші категорії (high-risk, прозорість) для такої системи НЕ розглядаються.
    2. "high_risk": domain не None або annex_i_safety_component. Строк: domain дає "2027-12-02", annex_i_safety_component дає
       "2028-08-02"; якщо обидва, береться раніша. Обов'язки:
         provider: "risk-management", "data-governance", "technical-documentation", "record-keeping", "human-oversight-design",
                   "accuracy-robustness-cybersecurity", "conformity-assessment", "ce-marking-registration", "post-market-monitoring"
         deployer: "use-per-instructions", "assign-human-oversight", "monitor-and-keep-logs", "inform-affected-persons",
                   "fundamental-rights-impact-assessment"
    3. "transparency": interacts_with_humans або generates_content або deepfake.
    4. "minimal": решта (обов'язків немає).

Обов'язки прозорості (ст. 50) НАКЛАДАЮТЬСЯ на high_risk (категорія лишається "high_risk"), але не на prohibited. За прапорцями:
    interacts_with_humans: provider "disclose-ai-interaction"
    generates_content:     provider "mark-synthetic-output"
    deepfake:              deployer "disclose-deepfake"
  Роль фільтрує: deployer не отримує обов'язків provider і навпаки (категорія "transparency" лишається навіть тоді, коли
  для цієї ролі обов'язків немає). Строк прозорості "2026-08-02"; виняток: "mark-synthetic-output" при
  on_market_before_2026_08_02=True має строк "2026-12-02".

GPAI (додається незалежно від категорії, у тому числі до prohibited і minimal), лише для role == "provider" і is_gpai:
    "gpai-technical-documentation", "gpai-copyright-policy", "gpai-training-content-summary";
    плюс при gpai_systemic_risk: "gpai-systemic-risk-evaluation", "gpai-incident-reporting", "gpai-cybersecurity".
    Строк цих обов'язків "2025-08-02".

Результат:
    {"category": ...,
     "obligations": відсортований за алфавітом список унікальних кодів для ролі,
     "deadlines": {код: дата} для кожного коду з obligations,
     "applies_from": найраніша дата з deadlines або None, якщо обов'язків немає,
     "gpai": None, якщо is_gpai False; інакше {"applies_from": "2025-08-02", "enforcement_from": "2026-08-02",
             "systemic_risk": bool}  (для будь-якої ролі)}
    Кожен виклик повертає нові об'єкти (зміна результату не впливає на наступні виклики). Вхід не змінюється.
"""


def classify(system: dict) -> dict:
    raise NotImplementedError
