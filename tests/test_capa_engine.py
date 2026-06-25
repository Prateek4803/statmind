"""
tests/test_capa_engine.py — coverage for the CAPA workflow engine foundation.

Verifies the spec's NON-NEGOTIABLE hard rules are actually enforced in code:
  * closure is gated on a passed effectiveness check (spec §2)
  * correction-only routing (TRIAGE->CLOSURE) requires documented justification (§3)
  * illegal lifecycle transitions are blocked
  * every pack must reference real states and carry an effectiveness gate
  * the medical-device pack validates and carries the regulatory verify flag
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from capa_engine.state_machine import (
    CAPAState, can_transition, lifecycle_order,
)
from capa_engine.schema import (
    RulePack, validate_pack, MandatoryFieldGate, RoleGate,
    EffectivenessGate, evaluate_mandatory_fields, evaluate_role,
)
from capa_engine.packs.medical_device import build_medical_device_pack


# ── State machine: legal/illegal transitions ─────────────────────────────────

def test_legal_forward_transition():
    r = can_transition(CAPAState.INTAKE, CAPAState.TRIAGE)
    assert r.allowed


def test_illegal_transition_blocked():
    # Can't jump INTAKE straight to CLOSURE
    r = can_transition(CAPAState.INTAKE, CAPAState.CLOSURE)
    assert not r.allowed
    assert "Illegal transition" in r.reason


def test_skipping_states_blocked():
    # INVESTIGATION can't jump to IMPLEMENTATION (must pass ACTION_PLAN)
    r = can_transition(CAPAState.INVESTIGATION, CAPAState.IMPLEMENTATION)
    assert not r.allowed


# ── Hard rule: closure gated on effectiveness (spec §2) ───────────────────────

def test_closure_blocked_without_effectiveness_pass():
    r = can_transition(CAPAState.EFFECTIVENESS_CHECK, CAPAState.CLOSURE,
                       effectiveness_passed=False)
    assert not r.allowed
    assert "effectiveness" in r.reason.lower()
    assert r.requires_effectiveness_pass


def test_closure_blocked_when_effectiveness_unknown():
    r = can_transition(CAPAState.EFFECTIVENESS_CHECK, CAPAState.CLOSURE,
                       effectiveness_passed=None)
    assert not r.allowed


def test_closure_allowed_with_effectiveness_pass():
    r = can_transition(CAPAState.EFFECTIVENESS_CHECK, CAPAState.CLOSURE,
                       effectiveness_passed=True)
    assert r.allowed


# ── Hard rule: correction-only routing must be justified (spec §3) ────────────

def test_triage_to_closure_requires_justification():
    r = can_transition(CAPAState.TRIAGE, CAPAState.CLOSURE)
    assert not r.allowed
    assert r.requires_justification
    assert "justification" in r.reason.lower()


def test_triage_to_closure_allowed_with_justification():
    r = can_transition(CAPAState.TRIAGE, CAPAState.CLOSURE,
                       justification="Below RPN threshold; single non-systemic unit.")
    assert r.allowed


def test_effectiveness_fail_can_reopen():
    r = can_transition(CAPAState.EFFECTIVENESS_CHECK, CAPAState.REOPENED)
    assert r.allowed


def test_reopened_returns_to_investigation():
    r = can_transition(CAPAState.REOPENED, CAPAState.INVESTIGATION)
    assert r.allowed


def test_closure_is_terminal():
    r = can_transition(CAPAState.CLOSURE, CAPAState.TRIAGE)
    assert not r.allowed


def test_lifecycle_order_is_complete():
    order = lifecycle_order()
    assert order[0] == CAPAState.INTAKE
    assert order[-1] == CAPAState.CLOSURE
    assert CAPAState.EFFECTIVENESS_CHECK in order


# ── Schema validation ────────────────────────────────────────────────────────

def test_medical_device_pack_validates():
    pack = build_medical_device_pack()
    assert validate_pack(pack) == []


def test_medical_device_pack_carries_verify_flag():
    """Every regulatory claim must be flagged as needing verification (honesty
    requirement from the spec's own disclaimer)."""
    pack = build_medical_device_pack()
    assert pack.verify_against_current_regulation is True
    for t in pack.timer_gates:
        assert t.verify_against_current_regulation is True


def test_pack_without_effectiveness_gate_is_invalid():
    """Spec §2: closure must be gated on effectiveness — a pack without that
    gate must fail validation."""
    bad = RulePack(
        pack_id="bad", industry="x", standards=["Z"], effective_from="2026-01-01",
        triage_force_capa_if=[], effectiveness_gate=None,
    )
    errs = validate_pack(bad)
    assert any("effectiveness" in e.lower() for e in errs)


def test_pack_with_unknown_state_is_invalid():
    bad = RulePack(
        pack_id="bad", industry="x", standards=["Z"], effective_from="2026-01-01",
        triage_force_capa_if=[],
        mandatory_field_gates=[MandatoryFieldGate(state="NOT_A_STATE", fields=["f"])],
        effectiveness_gate=EffectivenessGate(min_wait_days=30),
    )
    errs = validate_pack(bad)
    assert any("unknown state" in e.lower() for e in errs)


# ── Gate primitive evaluation ────────────────────────────────────────────────

def test_mandatory_field_gate_detects_missing():
    gate = MandatoryFieldGate(state="INVESTIGATION",
                              fields=["rca_method", "root_cause"])
    missing = evaluate_mandatory_fields(gate, {"rca_method": "5-Whys"})
    assert missing == ["root_cause"]


def test_mandatory_field_gate_passes_when_complete():
    gate = MandatoryFieldGate(state="INVESTIGATION", fields=["rca_method"])
    assert evaluate_mandatory_fields(gate, {"rca_method": "5-Whys"}) == []


def test_role_gate_enforces_segregation():
    gate = RoleGate(state="INVESTIGATION", roles_allowed=["quality_engineer"])
    assert evaluate_role(gate, "quality_engineer") is True
    assert evaluate_role(gate, "operator") is False
