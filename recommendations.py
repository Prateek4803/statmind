"""
recommendations.py — Next-step recommendation engine for StatMind.

Given an analysis type and its computed verdict, returns the single most
important next analysis to run, with a reason and a button label.

DESIGN PRINCIPLES
-----------------
* Deterministic and rules-based — NO LLM, NO randomness. Every recommendation
  is inspectable and unit-tested. This keeps the feature inside StatMind's
  trust boundary: it can only ever suggest a next step the verified engines
  support, and the reasoning is auditable.
* The rules encode the correct quality-engineering workflow order:
      Measurement system (GRR)  →  Stability (SPC)  →  Distribution (Normality)
      →  Capability (Cpk)  →  Corrective action (CAPA)
* Exactly ONE recommendation per result (product decision): the single best
  next move, never a menu.

Each recommendation maps to a real StatMind tab id so the frontend can wire a
"Run this next" button directly to switchAnalysis(tool_id).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


# Canonical tab ids used by the frontend switchAnalysis()/runTool dispatch.
TOOL_CAPABILITY = "capability"
TOOL_SPC = "spc"
TOOL_NORMALITY = "normality"
TOOL_GRR = "grr"
TOOL_TRANSFORM = "transformation"
TOOL_CAPA = "capa"


@dataclass
class NextStep:
    """A single next-step recommendation attached to an analysis result."""
    next_tool: str          # tab id the button should open
    title: str              # short label, e.g. "Run a Control Chart"
    reason: str             # one-sentence justification (the 'why')
    priority: str           # "info" | "action" | "critical" — drives styling
    # Optional flag the frontend can use to carry data forward (e.g. transform)
    carry_data: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Capability  (verdict: Excellent | Capable | Marginal | Not Capable)
# Optional context: normality_verdict, so a non-normal Cpk routes to transform.
# ─────────────────────────────────────────────────────────────────────────────

def _capability_next(verdict: str, normality_verdict: Optional[str] = None) -> NextStep:
    # Cross-analysis guard: if we know the data is non-normal, standard Cpk is
    # suspect regardless of its value — fixing the distribution comes first.
    if normality_verdict == "Non-Normal":
        return NextStep(
            TOOL_TRANSFORM,
            "Transform the data first",
            "These Cpk values assume a normal distribution, but the data is "
            "non-normal. Transform it (or use a non-normal method) for a valid Cpk.",
            "critical",
            carry_data=True,
        )

    if verdict in ("Excellent", "Capable"):
        return NextStep(
            TOOL_SPC,
            "Monitor with a Control Chart",
            "The process is capable. Now confirm it stays that way over time — "
            "capability only holds if the process is in statistical control.",
            "info",
        )
    if verdict == "Marginal":
        return NextStep(
            TOOL_SPC,
            "Check stability with a Control Chart",
            "Capability is borderline. Verify the process is in control before "
            "improving it — an unstable process can't be reliably tuned.",
            "action",
        )
    # Not Capable
    return NextStep(
        TOOL_CAPA,
        "Launch the CAPA engine",
        "The process is not capable. Start corrective action to find and "
        "eliminate the root causes of variation.",
        "critical",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SPC / Control chart  (in_control: bool)
# ─────────────────────────────────────────────────────────────────────────────

def _spc_next(in_control: bool) -> NextStep:
    if in_control:
        return NextStep(
            TOOL_CAPABILITY,
            "Run a Capability study",
            "The process is stable. Now quantify whether it actually meets "
            "spec by computing Cp/Cpk.",
            "info",
        )
    return NextStep(
        TOOL_CAPA,
        "Launch the CAPA engine",
        "The process shows out-of-control signals. Investigate the assignable "
        "causes before assessing capability — Cpk on an unstable process is invalid.",
        "critical",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Normality  (overall_verdict: Normal | Likely Normal | Non-Normal)
# ─────────────────────────────────────────────────────────────────────────────

def _normality_next(verdict: str, all_positive: Optional[bool] = None) -> NextStep:
    if verdict in ("Normal", "Likely Normal"):
        return NextStep(
            TOOL_CAPABILITY,
            "Run a Capability study",
            "The data is normal, so standard capability indices (Cpk) apply "
            "directly. Enter your spec limits to assess capability.",
            "info",
        )
    # Non-Normal. The right transformation depends on the data's sign:
    # Box-Cox requires strictly positive data; with zeros/negatives it is
    # mathematically invalid, so steer toward a non-parametric method instead.
    if all_positive is False:
        return NextStep(
            TOOL_TRANSFORM,
            "Use a non-parametric capability method",
            "The data is non-normal and contains zero or negative values, so a "
            "Box-Cox transformation cannot be applied. Use a percentile-based "
            "(non-parametric) capability method instead of transforming.",
            "action",
            carry_data=True,
        )
    return NextStep(
        TOOL_TRANSFORM,
        "Transform the data (Box-Cox)",
        "The data is non-normal but all-positive, so a Box-Cox transformation "
        "can normalize it. Apply it before computing Cpk, or the indices will "
        "mislead.",
        "action",
        carry_data=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gauge R&R  (verdict: Acceptable | Marginal | Unacceptable)
# ─────────────────────────────────────────────────────────────────────────────

def _grr_next(verdict: str) -> NextStep:
    if verdict == "Acceptable":
        return NextStep(
            TOOL_CAPABILITY,
            "Run a Capability study",
            "The measurement system is sound. You can trust the data — proceed "
            "to capability analysis.",
            "info",
        )
    if verdict == "Marginal":
        return NextStep(
            TOOL_CAPABILITY,
            "Proceed to Capability — with caution",
            "The measurement system is marginal (10–30% GRR). You can proceed, "
            "but treat borderline capability results carefully.",
            "action",
        )
    # Unacceptable
    return NextStep(
        TOOL_CAPA,
        "Fix the measurement system first",
        "Measurement error is too high (>30% GRR) to trust the data. Improve "
        "the gauge before running any process analysis.",
        "critical",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def recommend_next_step(
    analysis_type: str,
    verdict: Optional[str] = None,
    *,
    in_control: Optional[bool] = None,
    normality_verdict: Optional[str] = None,
    all_positive: Optional[bool] = None,
) -> Optional[NextStep]:
    """Return the single best next step for a completed analysis, or None if
    the analysis type isn't covered yet (caller should simply show nothing).

    Args:
        analysis_type: one of "capability", "spc", "normality", "grr".
        verdict:       the analysis verdict string (not needed for spc).
        in_control:    required for analysis_type == "spc".
        normality_verdict: optional context for capability (routes non-normal
                       data to transformation instead of SPC).
    """
    at = (analysis_type or "").strip().lower()

    if at == "capability":
        if verdict is None:
            return None
        return _capability_next(verdict, normality_verdict)

    if at == "spc":
        if in_control is None:
            return None
        return _spc_next(in_control)

    if at == "normality":
        if verdict is None:
            return None
        return _normality_next(verdict, all_positive)

    if at == "grr":
        if verdict is None:
            return None
        return _grr_next(verdict)

    # Unknown analysis type — no recommendation (frontend shows nothing).
    return None
