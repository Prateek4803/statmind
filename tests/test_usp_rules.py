"""Tests for USP compendial acceptance evaluators (cited general-chapter defaults)."""
import pytest
from usp_rules import evaluate_dissolution, evaluate_uniformity, evaluate_particulates


# ── USP <711> Dissolution ──
def test_dissolution_s1_pass():
    v = evaluate_dissolution([88, 90, 86, 92, 85, 89], Q=80)
    assert v.passed and v.stage_reached == "S1" and not v.oos


def test_dissolution_s1_fail_advances_not_oos():
    v = evaluate_dissolution([82, 90, 86, 92, 85, 89], Q=80)
    assert not v.passed and not v.oos  # advance to S2, not OOS yet


def test_dissolution_s2_pass():
    v = evaluate_dissolution([82, 90, 86, 92, 85, 89], Q=80,
                             s2_results=[81, 83, 79, 84, 80, 82])
    assert v.passed and v.stage_reached == "S2"


def test_dissolution_s3_oos_opens_capa():
    v = evaluate_dissolution([70]*6, Q=80, s2_results=[70]*6, s3_results=[50]*12)
    assert v.oos and not v.passed
    assert "CAPA" in v.capa_action or "deviation" in v.capa_action


def test_dissolution_defaults_flag_present():
    v = evaluate_dissolution([88, 90, 86, 92, 85, 89], Q=80)
    assert v.defaults_used and "monograph" in v.verify_monograph.lower()


def test_dissolution_requires_six_units():
    with pytest.raises(ValueError):
        evaluate_dissolution([88, 90, 86], Q=80)


# ── USP <905> Uniformity ──
def test_uniformity_stage1_pass_tight():
    v = evaluate_uniformity([99, 100, 101, 100, 99, 101, 100, 100, 99, 101])
    assert v.passed and not v.oos


def test_uniformity_stage1_fail_spread():
    v = evaluate_uniformity([80, 120, 85, 115, 90, 110, 95, 105, 100, 100])
    assert not v.passed


def test_uniformity_requires_10_or_30():
    with pytest.raises(ValueError):
        evaluate_uniformity([100, 100, 100])


# ── USP <788>/<789> Particulates ──
def test_particulates_svp_within():
    v = evaluate_particulates(count_10um=5000, count_25um=500, product_type="SVP")
    assert v.passed and not v.oos


def test_particulates_svp_over_limit():
    v = evaluate_particulates(count_10um=7000, count_25um=500, product_type="SVP")
    assert v.oos and v.chapter == "USP <788>"


def test_particulates_ophthalmic_over_limit():
    v = evaluate_particulates(count_10um=60, count_25um=2, product_type="ophthalmic", count_50um=0)
    assert v.oos and v.chapter == "USP <789>"


def test_particulates_invalid_type():
    with pytest.raises(ValueError):
        evaluate_particulates(count_10um=1, count_25um=1, product_type="bogus")
