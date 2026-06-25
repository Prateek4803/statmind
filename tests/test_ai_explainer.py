"""
tests/test_ai_explainer.py — safety tests for the grounded LLM explainer.

These verify the GROUNDING LAYER's guarantees without calling any model:
  * only safe scalar facts are extracted (no raw data arrays leak to the LLM)
  * the strict system contract is always present
  * the verified verdict is passed through, never invented
  * unsupported analysis types decline cleanly (no guessing)
  * the provider abstraction selects correctly and never needs a key to fail safe
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ai_explainer.grounding import (
    build_messages, build_grounding, SYSTEM_INSTRUCTION,
)
from ai_explainer.provider import (
    get_provider, HostedAnthropicProvider, LocalModelProvider, ExplainResult,
)
from ai_explainer import explain_result


# ── Grounding: safe fact extraction ──────────────────────────────────────────

_CAP_RESULT = {
    "column": "EtchDepth", "n": 40, "mean": 212.0, "cpk": 0.65, "cp": 1.40,
    "ppm_within": 18000, "usl": 240, "lsl": 180, "verdict": "Not Capable",
    "verdict_detail": "Cpk 0.65 < 1.0 — process not capable",
    # Raw arrays that must NOT reach the model:
    "histogram_data": {"counts": list(range(9999))},
    "capability_curve_data": {"x": list(range(9999)), "y_within": list(range(9999))},
}


def test_grounding_extracts_scalar_facts():
    g = build_grounding("capability", _CAP_RESULT)
    assert g is not None
    assert g.facts["cpk"] == 0.65
    assert g.verdict == "Not Capable"


def test_grounding_excludes_raw_data_arrays():
    """The model must never receive raw histogram / curve arrays."""
    msgs = build_messages("capability", _CAP_RESULT)
    blob = msgs[1]["content"].lower()
    assert "histogram" not in blob
    assert "curve" not in blob
    assert "9999" not in blob  # no raw array contents
    assert "9998" not in blob


def test_system_instruction_has_hard_constraints():
    assert "NEVER invent" in SYSTEM_INSTRUCTION
    assert "Do not recompute" in SYSTEM_INSTRUCTION
    assert "NEVER contradict the provided verdict" in SYSTEM_INSTRUCTION


def test_messages_include_system_and_user():
    msgs = build_messages("capability", _CAP_RESULT)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_verdict_passed_through_not_invented():
    msgs = build_messages("capability", _CAP_RESULT)
    assert "Not Capable" in msgs[1]["content"]


def test_user_question_is_included():
    msgs = build_messages("capability", _CAP_RESULT,
                          user_question="Why is my Cpk so low?")
    assert "Why is my Cpk so low?" in msgs[1]["content"]


def test_default_explanation_when_no_question():
    msgs = build_messages("capability", _CAP_RESULT)
    assert "plain language" in msgs[1]["content"].lower()


# ── Each supported analysis type grounds ─────────────────────────────────────

def test_spc_grounding():
    r = {"column": "X", "in_control": False, "ucl": 5, "lcl": 1, "total_alarms": 3}
    g = build_grounding("spc", r)
    assert g is not None
    assert g.verdict == "Out of Control"


def test_normality_grounding():
    r = {"column": "X", "shapiro_p": 0.01, "overall_verdict": "Non-Normal"}
    g = build_grounding("normality", r)
    assert g.verdict == "Non-Normal"


def test_grr_grounding():
    r = {"gauge_rr": {"pct_study_var": 42.0}, "verdict": "Unacceptable", "ndc": 2}
    g = build_grounding("grr", r)
    assert g.facts["gauge_rr_%study_var"] == 42.0
    assert g.verdict == "Unacceptable"


# ── Unsupported types decline cleanly ────────────────────────────────────────

def test_unsupported_type_returns_none():
    assert build_grounding("weibull", {}) is None
    assert build_messages("weibull", {}) is None


def test_explain_result_declines_unsupported():
    res = explain_result("weibull", {})
    assert res.ok is False
    assert "not available" in res.error.lower()


# ── Provider selection ───────────────────────────────────────────────────────

def test_default_provider_is_hosted():
    os.environ.pop("LLM_PROVIDER", None)
    p = get_provider()
    assert isinstance(p, HostedAnthropicProvider)


def test_local_provider_selected_by_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    p = get_provider()
    assert isinstance(p, LocalModelProvider)


def test_hosted_provider_fails_safe_without_key(monkeypatch):
    """No API key -> clean failure, never a crash, never a leaked key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = HostedAnthropicProvider()
    res = p.complete([{"role": "user", "content": "hi"}])
    assert res.ok is False
    assert "API_KEY" in res.error


def test_local_provider_fails_safe_without_endpoint(monkeypatch):
    monkeypatch.delenv("LOCAL_LLM_ENDPOINT", raising=False)
    p = LocalModelProvider()
    res = p.complete([{"role": "user", "content": "hi"}])
    assert res.ok is False
