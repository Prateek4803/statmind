"""
tests/test_recommendations.py — coverage for the next-step recommendation engine.

Verifies every (analysis, verdict) rule maps to the correct next tool, that the
cross-analysis guard (non-normal capability -> transform) fires, and that
unknown/insufficient inputs return None instead of guessing.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from recommendations import (
    recommend_next_step,
    TOOL_CAPABILITY, TOOL_SPC, TOOL_NORMALITY, TOOL_GRR,
    TOOL_TRANSFORM, TOOL_CAPA,
)


# ── Capability ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("verdict,expected_tool", [
    ("Excellent", TOOL_SPC),
    ("Capable", TOOL_SPC),
    ("Marginal", TOOL_SPC),
    ("Not Capable", TOOL_CAPA),
])
def test_capability_routing(verdict, expected_tool):
    ns = recommend_next_step("capability", verdict)
    assert ns is not None
    assert ns.next_tool == expected_tool


def test_capability_capable_is_info_priority():
    ns = recommend_next_step("capability", "Capable")
    assert ns.priority == "info"


def test_capability_not_capable_is_critical():
    ns = recommend_next_step("capability", "Not Capable")
    assert ns.priority == "critical"
    assert ns.next_tool == TOOL_CAPA


def test_capability_nonnormal_guard_overrides_to_transform():
    """The most important cross-analysis rule: if the data is non-normal,
    Cpk is suspect REGARDLESS of its value -> route to transformation."""
    # Even a 'Capable' verdict must redirect when normality failed
    ns = recommend_next_step("capability", "Capable", normality_verdict="Non-Normal")
    assert ns.next_tool == TOOL_TRANSFORM
    assert ns.priority == "critical"
    assert ns.carry_data is True


def test_capability_normal_context_does_not_override():
    ns = recommend_next_step("capability", "Capable", normality_verdict="Normal")
    assert ns.next_tool == TOOL_SPC  # normal data -> standard routing


# ── SPC ──────────────────────────────────────────────────────────────────────

def test_spc_in_control_routes_to_capability():
    ns = recommend_next_step("spc", in_control=True)
    assert ns.next_tool == TOOL_CAPABILITY
    assert ns.priority == "info"


def test_spc_out_of_control_routes_to_capa():
    ns = recommend_next_step("spc", in_control=False)
    assert ns.next_tool == TOOL_CAPA
    assert ns.priority == "critical"


def test_spc_without_in_control_returns_none():
    """SPC needs the in_control flag; without it, don't guess."""
    assert recommend_next_step("spc") is None


# ── Normality ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("verdict,expected_tool", [
    ("Normal", TOOL_CAPABILITY),
    ("Likely Normal", TOOL_CAPABILITY),
    ("Non-Normal", TOOL_TRANSFORM),
])
def test_normality_routing(verdict, expected_tool):
    ns = recommend_next_step("normality", verdict)
    assert ns.next_tool == expected_tool


def test_normality_nonnormal_carries_data():
    ns = recommend_next_step("normality", "Non-Normal")
    assert ns.carry_data is True


def test_nonnormal_all_positive_recommends_boxcox():
    """All-positive non-normal data -> Box-Cox is valid."""
    ns = recommend_next_step("normality", "Non-Normal", all_positive=True)
    assert ns.next_tool == TOOL_TRANSFORM
    assert "box-cox" in ns.title.lower() or "box-cox" in ns.reason.lower()


def test_nonnormal_with_negatives_recommends_nonparametric():
    """Non-positive non-normal data -> Box-Cox invalid, steer non-parametric."""
    ns = recommend_next_step("normality", "Non-Normal", all_positive=False)
    assert ns.next_tool == TOOL_TRANSFORM
    assert "non-parametric" in ns.reason.lower() or "percentile" in ns.reason.lower()
    # must NOT recommend Box-Cox on data where it can't work
    assert "box-cox" not in ns.title.lower()


def test_nonnormal_unknown_positivity_falls_back_safely():
    """No positivity info -> generic transform recommendation, still valid."""
    ns = recommend_next_step("normality", "Non-Normal", all_positive=None)
    assert ns.next_tool == TOOL_TRANSFORM
    assert ns.carry_data is True


# ── Gauge R&R ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("verdict,expected_tool,priority", [
    ("Acceptable", TOOL_CAPABILITY, "info"),
    ("Marginal", TOOL_CAPABILITY, "action"),
    ("Unacceptable", TOOL_CAPA, "critical"),
])
def test_grr_routing(verdict, expected_tool, priority):
    ns = recommend_next_step("grr", verdict)
    assert ns.next_tool == expected_tool
    assert ns.priority == priority


# ── Robustness / edge cases ──────────────────────────────────────────────────

def test_unknown_analysis_returns_none():
    assert recommend_next_step("weibull", "Wear-out") is None
    assert recommend_next_step("", None) is None


def test_missing_verdict_returns_none():
    assert recommend_next_step("capability") is None
    assert recommend_next_step("grr") is None


def test_case_insensitive_analysis_type():
    ns = recommend_next_step("CAPABILITY", "Capable")
    assert ns is not None
    assert ns.next_tool == TOOL_SPC


def test_every_recommendation_has_required_fields():
    """No recommendation may ship with an empty title/reason/tool."""
    cases = [
        ("capability", "Excellent", {}),
        ("capability", "Not Capable", {}),
        ("spc", None, {"in_control": True}),
        ("spc", None, {"in_control": False}),
        ("normality", "Normal", {}),
        ("normality", "Non-Normal", {}),
        ("grr", "Acceptable", {}),
        ("grr", "Unacceptable", {}),
    ]
    for at, verdict, kw in cases:
        ns = recommend_next_step(at, verdict, **kw)
        assert ns is not None
        assert ns.next_tool and ns.title and ns.reason
        assert ns.priority in ("info", "action", "critical")
        d = ns.to_dict()
        assert set(d) >= {"next_tool", "title", "reason", "priority", "carry_data"}
