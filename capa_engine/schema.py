"""
capa_engine/schema.py — Rule-pack schema + gate primitives.

Encodes Section 4 (gate primitives) and Section 7 (rules-as-data) of the spec.
A "pack" is a config object loaded by tenant.industry that parameterises the
universal state machine with industry-specific gates, fields, timers, roles, and
clause citations — without changing code (spec §7: "keep rules as data, not code
so quality SMEs can edit and audit them").

This module provides:
  * the dataclasses that define a valid pack,
  * a validator that checks a pack dict against the schema and against the
    universal state machine (so a pack can't reference a non-existent state),
  * the five gate primitives as evaluable structures.

IMPORTANT — REGULATORY DISCLAIMER (carried from the source spec):
Clause citations encoded in packs are summarised for engineering reference and
are NOT legal advice or a guarantee of current regulation. Every pack and every
cited clause carries a `verify_against_current_regulation` flag set True. Do not
treat encoded timers/clauses as authoritative compliance facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .state_machine import CAPAState


# ── Gate primitives (spec §4) ────────────────────────────────────────────────

@dataclass
class MandatoryFieldGate:
    """Cannot advance from `state` until all `fields` are present."""
    state: str
    fields: list[str]
    kind: str = "mandatory_field"


@dataclass
class RoleGate:
    """Only listed roles may approve the transition out of `state`
    (segregation of duties)."""
    state: str
    roles_allowed: list[str]
    kind: str = "role"


@dataclass
class TimerGate:
    """SLA clock for `state`; breach triggers escalation. Days as stated in the
    pack — carries the verify flag because SLAs are regulation-derived."""
    state: str
    sla_days: int
    on_breach: str = "escalate"
    citation: str = ""
    verify_against_current_regulation: bool = True
    kind: str = "timer"


@dataclass
class EvidenceGate:
    """`state` cannot close without a recognised method output attached
    (e.g. an RCA result)."""
    state: str
    required_evidence: list[str]
    kind: str = "evidence"


@dataclass
class EffectivenessGate:
    """Closure blocked until verification passes after a defined waiting period."""
    min_wait_days: int
    preventive_policy: str = "required_or_justified"  # ISO "where appropriate"
    kind: str = "effectiveness"


@dataclass
class BlockRule:
    """A hard validation that blocks a transition when its condition holds.
    e.g. root_cause == 'human_error' && !system_cause_ruled_out."""
    state: str
    condition: str
    message: str


@dataclass
class RulePack:
    """A complete industry rule pack."""
    pack_id: str
    industry: str
    standards: list[str]                          # e.g. ["ISO 13485:2016", "EU MDR"]
    effective_from: str                           # ISO date; packs are effective-dated
    triage_force_capa_if: list[str]               # e.g. ["recurrence==true", "rpn>=125"]
    mandatory_field_gates: list[MandatoryFieldGate] = field(default_factory=list)
    role_gates: list[RoleGate] = field(default_factory=list)
    timer_gates: list[TimerGate] = field(default_factory=list)
    evidence_gates: list[EvidenceGate] = field(default_factory=list)
    effectiveness_gate: Optional[EffectivenessGate] = None
    block_rules: list[BlockRule] = field(default_factory=list)
    rca_methods: list[str] = field(default_factory=list)
    clause_notes: dict = field(default_factory=dict)
    verify_against_current_regulation: bool = True


# ── Validation ───────────────────────────────────────────────────────────────

_VALID_STATES = {s.value for s in CAPAState}


def validate_pack(pack: RulePack) -> list[str]:
    """Return a list of problems with a pack (empty list == valid).

    Checks structural integrity AND consistency with the universal state machine:
    a pack may not attach a gate to a state that doesn't exist.
    """
    errors: list[str] = []

    if not pack.pack_id:
        errors.append("pack_id is required")
    if not pack.industry:
        errors.append("industry is required")
    if not pack.standards:
        errors.append("at least one standard/citation is required")
    if not pack.effective_from:
        errors.append("effective_from date is required (packs are effective-dated)")

    # Every gate must reference a real lifecycle state
    def _check_state(s: str, where: str):
        if s not in _VALID_STATES:
            errors.append(f"{where} references unknown state '{s}'. "
                          f"Valid: {sorted(_VALID_STATES)}")

    for g in pack.mandatory_field_gates:
        _check_state(g.state, "mandatory_field_gate")
        if not g.fields:
            errors.append(f"mandatory_field_gate on {g.state} has no fields")
    for g in pack.role_gates:
        _check_state(g.state, "role_gate")
        if not g.roles_allowed:
            errors.append(f"role_gate on {g.state} has no roles")
    for g in pack.timer_gates:
        _check_state(g.state, "timer_gate")
        if g.sla_days <= 0:
            errors.append(f"timer_gate on {g.state} has non-positive sla_days")
    for g in pack.evidence_gates:
        _check_state(g.state, "evidence_gate")
    for b in pack.block_rules:
        _check_state(b.state, "block_rule")

    # Spec §2 hard rule: closure must be gated on effectiveness. A pack with no
    # effectiveness gate is invalid for a full-CAPA framework.
    if pack.effectiveness_gate is None:
        errors.append("effectiveness_gate is required (closure must be gated on "
                      "a passed effectiveness check, spec §2)")
    elif pack.effectiveness_gate.min_wait_days < 0:
        errors.append("effectiveness_gate.min_wait_days cannot be negative")

    return errors


def evaluate_mandatory_fields(gate: MandatoryFieldGate, record: dict) -> list[str]:
    """Return the list of missing required fields for this gate (empty == pass)."""
    return [f for f in gate.fields if not record.get(f)]


def evaluate_role(gate: RoleGate, actor_role: str) -> bool:
    """True if the actor's role may approve the transition out of gate.state."""
    return actor_role in gate.roles_allowed
