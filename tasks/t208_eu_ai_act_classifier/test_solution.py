import copy

import pytest

from solution import classify

OLD_PRACTICES = ["manipulation", "exploiting_vulnerabilities", "social_scoring", "crime_risk_profiling", "face_scraping",
                 "emotion_inference_work_education", "biometric_categorisation_sensitive",
                 "realtime_biometric_id_law_enforcement"]
NEW_PRACTICES = ["csam_generation", "non_consensual_intimate_imagery"]
DOMAINS = ["biometrics", "critical_infrastructure", "education", "employment", "essential_services", "law_enforcement",
           "migration", "justice_democracy"]
HIGH_PROVIDER = ["risk-management", "data-governance", "technical-documentation", "record-keeping",
                 "human-oversight-design", "accuracy-robustness-cybersecurity", "conformity-assessment",
                 "ce-marking-registration", "post-market-monitoring"]
HIGH_DEPLOYER = ["use-per-instructions", "assign-human-oversight", "monitor-and-keep-logs", "inform-affected-persons",
                 "fundamental-rights-impact-assessment"]
GPAI = ["gpai-technical-documentation", "gpai-copyright-policy", "gpai-training-content-summary"]
GPAI_SYSTEMIC = ["gpai-systemic-risk-evaluation", "gpai-incident-reporting", "gpai-cybersecurity"]


def provider(**kw):
    return {"role": "provider", **kw}


def deployer(**kw):
    return {"role": "deployer", **kw}


# --- заборонені практики -----------------------------------------------------------------------

@pytest.mark.parametrize("practice", OLD_PRACTICES)
def test_prohibited_practices_apply_from_feb_2025(practice):
    r = classify(provider(practice=practice))
    assert r["category"] == "prohibited"
    assert r["obligations"] == ["do-not-place-on-market"]
    assert r["deadlines"] == {"do-not-place-on-market": "2025-02-02"}
    assert r["applies_from"] == "2025-02-02" and r["gpai"] is None


@pytest.mark.parametrize("practice", NEW_PRACTICES)
def test_new_omnibus_prohibitions_apply_from_dec_2026(practice):
    r = classify(deployer(practice=practice))
    assert r["category"] == "prohibited"
    assert r["obligations"] == ["do-not-use"]
    assert r["deadlines"] == {"do-not-use": "2026-12-02"} and r["applies_from"] == "2026-12-02"


def test_prohibited_ignores_other_categories_but_keeps_gpai():
    r = classify(provider(practice="social_scoring", domain="employment", interacts_with_humans=True, is_gpai=True))
    assert r["category"] == "prohibited"
    assert r["obligations"] == sorted(["do-not-place-on-market"] + GPAI)
    assert r["deadlines"]["do-not-place-on-market"] == "2025-02-02"
    assert r["applies_from"] == "2025-02-02"


# --- high-risk ---------------------------------------------------------------------------------

@pytest.mark.parametrize("domain", DOMAINS)
def test_annex_iii_domains_are_high_risk_from_dec_2027(domain):
    p = classify(provider(domain=domain))
    assert p["category"] == "high_risk"
    assert p["obligations"] == sorted(HIGH_PROVIDER)
    assert set(p["deadlines"].values()) == {"2027-12-02"} and p["applies_from"] == "2027-12-02"
    d = classify(deployer(domain=domain))
    assert d["category"] == "high_risk"
    assert d["obligations"] == sorted(HIGH_DEPLOYER)
    assert set(d["deadlines"].values()) == {"2027-12-02"}


def test_annex_i_product_component_is_high_risk_from_aug_2028():
    r = classify(provider(annex_i_safety_component=True))
    assert r["category"] == "high_risk"
    assert r["obligations"] == sorted(HIGH_PROVIDER)
    assert set(r["deadlines"].values()) == {"2028-08-02"} and r["applies_from"] == "2028-08-02"


def test_both_annex_iii_and_annex_i_take_the_earlier_date():
    r = classify(deployer(domain="education", annex_i_safety_component=True))
    assert r["category"] == "high_risk" and set(r["deadlines"].values()) == {"2027-12-02"}


def test_high_risk_with_chatbot_adds_transparency_duties_with_their_own_dates():
    r = classify(provider(domain="employment", interacts_with_humans=True, generates_content=True))
    assert r["category"] == "high_risk"
    assert r["obligations"] == sorted(HIGH_PROVIDER + ["disclose-ai-interaction", "mark-synthetic-output"])
    assert r["deadlines"]["disclose-ai-interaction"] == "2026-08-02"
    assert r["deadlines"]["mark-synthetic-output"] == "2026-08-02"
    assert r["deadlines"]["risk-management"] == "2027-12-02"
    assert r["applies_from"] == "2026-08-02"


# --- прозорість (ст. 50) -----------------------------------------------------------------------

def test_chatbot_provider_must_disclose_interaction():
    r = classify(provider(interacts_with_humans=True))
    assert r["category"] == "transparency"
    assert r["obligations"] == ["disclose-ai-interaction"]
    assert r["deadlines"] == {"disclose-ai-interaction": "2026-08-02"} and r["applies_from"] == "2026-08-02"


def test_synthetic_content_provider_must_mark_output():
    r = classify(provider(generates_content=True))
    assert r["category"] == "transparency"
    assert r["deadlines"] == {"mark-synthetic-output": "2026-08-02"}


def test_systems_already_on_market_get_until_dec_2026_to_mark_content():
    r = classify(provider(generates_content=True, on_market_before_2026_08_02=True))
    assert r["deadlines"] == {"mark-synthetic-output": "2026-12-02"} and r["applies_from"] == "2026-12-02"
    both = classify(provider(generates_content=True, interacts_with_humans=True, on_market_before_2026_08_02=True))
    assert both["deadlines"] == {"disclose-ai-interaction": "2026-08-02", "mark-synthetic-output": "2026-12-02"}
    assert both["applies_from"] == "2026-08-02"


def test_on_market_flag_changes_nothing_else():
    assert classify(provider(interacts_with_humans=True, on_market_before_2026_08_02=True))["deadlines"] == \
        {"disclose-ai-interaction": "2026-08-02"}
    assert classify(deployer(deepfake=True, on_market_before_2026_08_02=True))["deadlines"] == \
        {"disclose-deepfake": "2026-08-02"}
    assert classify(provider(domain="education", on_market_before_2026_08_02=True))["applies_from"] == "2027-12-02"


def test_deepfake_duty_belongs_to_the_deployer():
    d = classify(deployer(deepfake=True))
    assert d["category"] == "transparency" and d["obligations"] == ["disclose-deepfake"]
    p = classify(provider(deepfake=True))
    assert p["category"] == "transparency" and p["obligations"] == [] and p["applies_from"] is None


def test_role_filters_transparency_duties_but_category_stays():
    d = classify(deployer(interacts_with_humans=True, generates_content=True))
    assert d["category"] == "transparency"
    assert d["obligations"] == [] and d["deadlines"] == {} and d["applies_from"] is None
    p = classify(provider(interacts_with_humans=True, generates_content=True, deepfake=True))
    assert p["obligations"] == ["disclose-ai-interaction", "mark-synthetic-output"]


# --- мінімальний ризик і GPAI ------------------------------------------------------------------

@pytest.mark.parametrize("role", ["provider", "deployer"])
def test_minimal_risk(role):
    r = classify({"role": role})
    assert r == {"category": "minimal", "obligations": [], "deadlines": {}, "applies_from": None, "gpai": None}


def test_gpai_provider_obligations():
    r = classify(provider(is_gpai=True))
    assert r["category"] == "minimal"
    assert r["obligations"] == sorted(GPAI)
    assert set(r["deadlines"].values()) == {"2025-08-02"} and r["applies_from"] == "2025-08-02"
    assert r["gpai"] == {"applies_from": "2025-08-02", "enforcement_from": "2026-08-02", "systemic_risk": False}


def test_gpai_with_systemic_risk():
    r = classify(provider(is_gpai=True, gpai_systemic_risk=True))
    assert r["obligations"] == sorted(GPAI + GPAI_SYSTEMIC)
    assert r["gpai"]["systemic_risk"] is True


def test_gpai_deployer_has_no_model_provider_duties_but_gets_info():
    r = classify(deployer(is_gpai=True, gpai_systemic_risk=True))
    assert r["obligations"] == [] and r["applies_from"] is None
    assert r["gpai"] == {"applies_from": "2025-08-02", "enforcement_from": "2026-08-02", "systemic_risk": True}


def test_gpai_combined_with_high_risk_and_transparency():
    r = classify(provider(is_gpai=True, domain="essential_services", interacts_with_humans=True))
    assert r["category"] == "high_risk"
    assert r["obligations"] == sorted(HIGH_PROVIDER + GPAI + ["disclose-ai-interaction"])
    assert r["applies_from"] == "2025-08-02"
    assert r["deadlines"]["gpai-copyright-policy"] == "2025-08-02"
    assert r["deadlines"]["conformity-assessment"] == "2027-12-02"


def test_obligations_are_sorted_and_deadlines_match():
    r = classify(provider(domain="migration", is_gpai=True, generates_content=True, interacts_with_humans=True))
    assert r["obligations"] == sorted(r["obligations"])
    assert list(sorted(r["deadlines"])) == r["obligations"]
    assert r["applies_from"] == min(r["deadlines"].values())


# --- вхід і вихід ------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    None, [], "provider", {}, {"role": "operator"}, {"role": None}, {"practice": "social_scoring"},
    provider(practice="unknown"), provider(practice=""), provider(domain="gaming"), provider(domain="Employment"),
    provider(deepfake="yes"), provider(interacts_with_humans=1), provider(is_gpai=None), provider(generates_content=0),
    provider(unknown_flag=True), provider(gpai_systemic_risk=True), provider(on_market_before_2026_08_02="no"),
])
def test_invalid_input_is_value_error(bad):
    with pytest.raises(ValueError):
        classify(bad)


def test_explicit_none_and_false_equal_defaults():
    explicit = provider(practice=None, domain=None, annex_i_safety_component=False, interacts_with_humans=False,
                        generates_content=False, deepfake=False, is_gpai=False, gpai_systemic_risk=False,
                        on_market_before_2026_08_02=False)
    assert classify(explicit) == classify(provider())


def test_input_is_not_modified():
    system = provider(domain="education", interacts_with_humans=True, is_gpai=True)
    snapshot = copy.deepcopy(system)
    classify(system)
    assert system == snapshot


def test_results_do_not_share_state_between_calls():
    first = classify(provider(domain="education", is_gpai=True))
    first["obligations"].append("x")
    first["deadlines"]["x"] = "2000-01-01"
    first["gpai"]["systemic_risk"] = True
    second = classify(provider(domain="education", is_gpai=True))
    assert "x" not in second["obligations"] and "x" not in second["deadlines"]
    assert second["gpai"]["systemic_risk"] is False
    assert second["obligations"] == sorted(HIGH_PROVIDER + GPAI)
