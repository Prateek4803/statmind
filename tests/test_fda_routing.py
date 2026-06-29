"""Tests for FDA recall classification + CFR citation routing."""
from fda_routing import (classify_recall, correction_removal_reportable,
                         route_cfr_citation)


def test_recall_class_i_highest():
    r = classify_recall(serious_or_death=True)
    assert r.recall_class == "Class I" and r.severity_multiplier == 3.0


def test_recall_class_ii():
    r = classify_recall(serious_or_death=False, reversible_or_remote=True)
    assert r.recall_class == "Class II" and r.severity_multiplier == 2.0


def test_recall_class_iii_default():
    r = classify_recall(serious_or_death=False)
    assert r.recall_class == "Class III" and r.severity_multiplier == 1.0


def test_correction_removal_clock():
    r = correction_removal_reportable()
    assert "806" in r.standard_reference and "10-working-day" in r.capa_action


def test_cfr_211_routing():
    r = route_cfr_citation("211.192")
    assert r and r.capa_category == "Laboratory Investigation"
    assert "211" in r.framework


def test_cfr_820_routing():
    r = route_cfr_citation("820.100")
    assert r and r.capa_category == "CAPA System Itself"


def test_cfr_handles_prefixed_forms():
    for form in ("21 CFR 211.192", "§211.192", "211.192"):
        r = route_cfr_citation(form)
        assert r and r.citation == "211.192", f"failed on {form}"


def test_cfr_unknown_returns_none():
    assert route_cfr_citation("999.999") is None
    assert route_cfr_citation("") is None
