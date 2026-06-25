"""
capa_engine/state_machine.py — The universal CAPA lifecycle.

Encodes Section 2 of the CAPA Engine Specification: one state machine that every
industry pack maps onto, gated differently per pack.

    INTAKE -> TRIAGE -> CONTAINMENT -> INVESTIGATION -> ACTION_PLAN
    -> IMPLEMENTATION -> EFFECTIVENESS_CHECK -> CLOSURE
            (effectiveness fail) -> re-open / escalate

DESIGN NOTES
------------
* This module defines the *shape* of the lifecycle and validates transitions.
  It is deterministic: the engine decides transitions, never an LLM (spec §1).
* It does NOT implement persistence, audit trails, e-signatures, or RBAC — those
  are the infrastructure layers (spec §6) that a real deployment needs and that
  StatMind does not yet have. This is the lifecycle skeleton only.
* Hard rules that hold in EVERY framework (spec §2) are enforced here so no pack
  can accidentally weaken them:
    - containment / corrective / preventive are distinct (modelled as fields elsewhere)
    - CLOSURE requires a passed effectiveness check
    - every transition is meant to write an immutable audit record (hook provided)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CAPAState(str, Enum):
    INTAKE = "INTAKE"
    TRIAGE = "TRIAGE"
    CONTAINMENT = "CONTAINMENT"
    INVESTIGATION = "INVESTIGATION"
    ACTION_PLAN = "ACTION_PLAN"
    IMPLEMENTATION = "IMPLEMENTATION"
    EFFECTIVENESS_CHECK = "EFFECTIVENESS_CHECK"
    CLOSURE = "CLOSURE"
    # Terminal-ish off-ramps
    REOPENED = "REOPENED"
    ESCALATED = "ESCALATED"


# The canonical forward lifecycle. Each state lists the states it may move to.
# CONTAINMENT is optional in some flows (low-severity correction-only), so TRIAGE
# can route forward to INVESTIGATION directly — but only when the triage gate
# permits (enforced by the pack, not here).
ALLOWED_TRANSITIONS: dict[CAPAState, set[CAPAState]] = {
    CAPAState.INTAKE: {CAPAState.TRIAGE},
    CAPAState.TRIAGE: {CAPAState.CONTAINMENT, CAPAState.INVESTIGATION, CAPAState.CLOSURE},
    CAPAState.CONTAINMENT: {CAPAState.INVESTIGATION},
    CAPAState.INVESTIGATION: {CAPAState.ACTION_PLAN},
    CAPAState.ACTION_PLAN: {CAPAState.IMPLEMENTATION},
    CAPAState.IMPLEMENTATION: {CAPAState.EFFECTIVENESS_CHECK},
    CAPAState.EFFECTIVENESS_CHECK: {CAPAState.CLOSURE, CAPAState.REOPENED, CAPAState.ESCALATED},
    CAPAState.CLOSURE: set(),                       # terminal
    CAPAState.REOPENED: {CAPAState.INVESTIGATION},  # re-enter the loop
    CAPAState.ESCALATED: {CAPAState.INVESTIGATION},
}

# TRIAGE -> CLOSURE is ONLY valid as "correction / nonconformance only" and the
# spec (§3) requires a documented justification. The engine must not allow a
# silent close. We mark which transitions demand a justification field.
TRANSITIONS_REQUIRING_JUSTIFICATION: set[tuple[CAPAState, CAPAState]] = {
    (CAPAState.TRIAGE, CAPAState.CLOSURE),
}

# CLOSURE is gated on a passed effectiveness check in every framework (spec §2).
# So the only legitimate path into CLOSURE for a full CAPA is from
# EFFECTIVENESS_CHECK. (TRIAGE->CLOSURE is the correction-only exception above.)
CLOSURE_REQUIRES_EFFECTIVENESS_FROM = {CAPAState.EFFECTIVENESS_CHECK}


@dataclass
class TransitionResult:
    allowed: bool
    reason: str = ""
    requires_justification: bool = False
    requires_effectiveness_pass: bool = False


def can_transition(
    current: CAPAState,
    target: CAPAState,
    *,
    effectiveness_passed: Optional[bool] = None,
    justification: Optional[str] = None,
) -> TransitionResult:
    """Validate a single state transition against the universal rules.

    This is the deterministic core: it answers "is this move structurally legal,
    and what does it require?" Pack-specific gates (mandatory fields, roles,
    timers) are layered on top by the pack — this only enforces the lifecycle
    invariants that hold for everyone.
    """
    allowed_targets = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed_targets:
        return TransitionResult(
            allowed=False,
            reason=f"Illegal transition {current.value} -> {target.value}. "
                   f"Allowed: {sorted(t.value for t in allowed_targets) or 'none (terminal)'}.",
        )

    needs_just = (current, target) in TRANSITIONS_REQUIRING_JUSTIFICATION
    if needs_just and not (justification and justification.strip()):
        return TransitionResult(
            allowed=False,
            reason=f"{current.value} -> {target.value} requires a documented "
                   f"justification (correction-only routing must be justified, spec §3).",
            requires_justification=True,
        )

    # CLOSURE gate: a full-CAPA closure must come from a passed effectiveness check.
    if target == CAPAState.CLOSURE and current in CLOSURE_REQUIRES_EFFECTIVENESS_FROM:
        if effectiveness_passed is not True:
            return TransitionResult(
                allowed=False,
                reason="Closure blocked: effectiveness check must PASS before "
                       "closure (non-negotiable across FDA/ISO 13485/IATF/AS9100/NQA-1, spec §2).",
                requires_effectiveness_pass=True,
            )

    return TransitionResult(
        allowed=True,
        requires_justification=needs_just,
        requires_effectiveness_pass=(target == CAPAState.CLOSURE),
    )


def lifecycle_order() -> list[CAPAState]:
    """The canonical forward path, for display / progress UI."""
    return [
        CAPAState.INTAKE, CAPAState.TRIAGE, CAPAState.CONTAINMENT,
        CAPAState.INVESTIGATION, CAPAState.ACTION_PLAN, CAPAState.IMPLEMENTATION,
        CAPAState.EFFECTIVENESS_CHECK, CAPAState.CLOSURE,
    ]
