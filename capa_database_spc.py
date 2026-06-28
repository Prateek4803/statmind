"""
StatMind — SPC Pattern Fallback Rules
=====================================

Process-agnostic CAPA rules keyed PURELY on SPC alarm patterns (Western
Electric WE1–WE4 + Nelson N2–N8). These are intentionally low-weight FALLBACKS:
when a control chart is unstable but no process-specific rule (Etch, CMP, torque,
dissolution, ...) matches the full statistical fingerprint, the engine still
returns actionable, standard-cited guidance instead of nothing.

Design notes
------------
* SPC patterns are process-agnostic — the SAME pattern means different physical
  things on different processes — so these carry low `weight` (0.4–0.6). Any
  real process-specific rule that also matches will outrank them, which is the
  intended precedence.
* Alarm codes here use the DETECTOR vocabulary emitted by control_charts.py:
  WE1–WE4 and N2–N8. (The engine also normalizes NE#↔N#, so either form works,
  but we use the detector's native form to avoid relying on normalization.)
* Each rule maps one pattern → its statistically-meaning root cause class →
  generic-but-correct corrective/preventive actions. Citations reference the
  published rule sets, not paywalled clauses.

References
----------
Western Electric Company, "Statistical Quality Control Handbook" (1956) — WE zone rules.
Nelson, L.S. (1984), "The Shewhart Control Chart — Tests for Special Causes",
    Journal of Quality Technology 16(4):237-239 — Nelson run rules.
NIST/SEMATECH e-Handbook of Statistical Methods, §6.3 (public domain, US Gov).
"""

from capa_database import CAPARule, CAPAAction, PreventiveAction


def _ca(action, owner, timeline, priority, impact):
    return CAPAAction(action, owner, timeline, priority, impact)


def _pa(action, owner, timeline, system):
    return PreventiveAction(action, owner, timeline, system)


SPC_PATTERN_RULES = [

    # ── WE1 / N1: single point beyond 3σ ────────────────────────────────────
    CAPARule(
        rule_id="SPC-WE1", process="General", parameter="Any",
        fault_pattern="Point Beyond 3σ — Gross Special Cause",
        description="One or more points fall beyond the ±3σ control limits, signalling a large assignable cause.",
        severity="Critical", spc_rules=["WE1"],
        root_cause="A single large assignable (special) cause: equipment fault, setup error, material change, or measurement error.",
        root_cause_detail=(
            "A point beyond 3σ has <0.3% chance of occurring from common-cause variation alone. "
            "It almost always reflects a discrete event rather than normal process noise."
        ),
        alternative_causes=["Data-entry / unit error", "Sensor or gauge malfunction", "Operator or setup change"],
        corrective_actions=[
            _ca("Stop the process. Identify the assignable cause for the out-of-limit point before resuming.", "Process Engineer", "Immediate", "P1", "Prevents continued production of non-conforming output"),
            _ca("Verify the measurement (re-measure / check gauge) to rule out a measurement-system error.", "Quality", "Immediate", "P1", "Confirms the signal is real, not a gauge artifact"),
            _ca("Quarantine product made since the last in-control point pending disposition.", "Quality", "Immediate", "P1", "Contains potentially non-conforming material"),
        ],
        preventive_actions=[
            _pa("Add the identified cause to the reaction plan / control plan so recurrence is auto-flagged.", "Quality", "2 weeks", "Control Plan"),
        ],
        containment="Hold output back to the last verified in-control subgroup.", disposition="Hold",
        standard_reference="Western Electric SQC Handbook (1956), Rule 1", weight=0.6,
    ),

    # ── WE2 / N5: 2 of 3 beyond 2σ (same side) ──────────────────────────────
    CAPARule(
        rule_id="SPC-WE2", process="General", parameter="Any",
        fault_pattern="2 of 3 Beyond 2σ — Emerging Shift",
        description="Two of three consecutive points fall beyond ±2σ on the same side, an early shift signal.",
        severity="Major", spc_rules=["WE2", "N5"],
        root_cause="An emerging process-mean shift or increased short-term variation not yet large enough to break the 3σ limit.",
        root_cause_detail="The 2-of-3-beyond-2σ pattern catches moderate shifts earlier than the 3σ rule and is a leading indicator of drift.",
        alternative_causes=["Incoming material lot change", "Tool warm-up / thermal drift", "Partial setup change"],
        corrective_actions=[
            _ca("Investigate for a recent process change correlated with the shift onset (±1 shift window).", "Process Engineer", "Immediate", "P2", "Locates the assignable cause early"),
            _ca("Increase sampling frequency until stability is re-confirmed.", "Quality", "Immediate", "P2", "Tightens detection while cause is found"),
        ],
        preventive_actions=[
            _pa("Add an EWMA (λ=0.2) or CUSUM chart for sensitive small-shift detection on this parameter.", "Process Engineer", "2 weeks", "SPC"),
        ],
        containment="Heighten inspection on recent output.", disposition="Conditional Release",
        standard_reference="Western Electric SQC Handbook (1956), Rule 2", weight=0.5,
    ),

    # ── WE3 / N6: 4 of 5 beyond 1σ (same side) ──────────────────────────────
    CAPARule(
        rule_id="SPC-WE3", process="General", parameter="Any",
        fault_pattern="4 of 5 Beyond 1σ — Small Sustained Shift",
        description="Four of five consecutive points fall beyond ±1σ on the same side, indicating a small sustained shift.",
        severity="Major", spc_rules=["WE3", "N6"],
        root_cause="A small but persistent shift in the process mean — gradual degradation, slow drift, or a minor setpoint change.",
        root_cause_detail="Small sustained shifts inflate long-term variation and erode Ppk even while individual points stay inside 3σ.",
        alternative_causes=["Consumable wear", "Slow thermal/seasonal drift", "Calibration offset"],
        corrective_actions=[
            _ca("Compare current mean to the established centerline; quantify the shift magnitude in σ units.", "Process Engineer", "Immediate", "P2", "Sizes the shift for a recentering decision"),
            _ca("Check for consumable wear or calibration offset introduced near the shift onset.", "Equipment", "1 week", "P2", "Identifies a recoverable mechanical cause"),
        ],
        preventive_actions=[
            _pa("Schedule preventive recalibration / consumable replacement at the interval matching observed drift.", "Equipment", "1 month", "PM"),
        ],
        containment="Verify recent output against spec.", disposition="Conditional Release",
        standard_reference="Western Electric SQC Handbook (1956), Rule 3", weight=0.5,
    ),

    # ── WE4 / N2: 8–9 consecutive same side of centerline ───────────────────
    CAPARule(
        rule_id="SPC-WE4", process="General", parameter="Any",
        fault_pattern="Run on One Side of Centerline — Mean Shift",
        description="A run of consecutive points stays on one side of the centerline (WE: 8; Nelson: 9), indicating the process mean has shifted.",
        severity="Major", spc_rules=["WE4", "N2"],
        root_cause="The process mean has moved off the historical centerline — a step change or a new steady-state level.",
        root_cause_detail="A sustained one-sided run is the classic mean-shift signature; the centerline no longer represents the process.",
        alternative_causes=["New material / supplier", "Recipe or setpoint edit", "Fixture or tooling change"],
        corrective_actions=[
            _ca("Identify the change that coincides with the start of the run; review change/maintenance logs.", "Process Engineer", "Immediate", "P2", "Pinpoints the assignable cause of the shift"),
            _ca("Decide: recenter the process to target, or re-baseline control limits if the new level is intended.", "Process Engineer", "1 week", "P2", "Restores a valid, centered control state"),
        ],
        preventive_actions=[
            _pa("Require control-limit re-validation after any recipe, material, or tooling change.", "Quality", "2 weeks", "Control Plan"),
        ],
        containment="Confirm shifted output still meets spec.", disposition="Conditional Release",
        standard_reference="Western Electric SQC Handbook (1956), Rule 4 / Nelson (1984) Rule 2", weight=0.5,
    ),

    # ── N3: 6 consecutive monotonic trend ───────────────────────────────────
    CAPARule(
        rule_id="SPC-N3", process="General", parameter="Any",
        fault_pattern="6-Point Monotonic Trend — Drift",
        description="Six consecutive points trend steadily up or down, indicating progressive drift.",
        severity="Major", spc_rules=["N3"],
        root_cause="Progressive, directional drift: tool wear, reagent depletion, temperature ramp, or accumulating contamination.",
        root_cause_detail="A monotonic trend signals a continuously-acting cause rather than a one-time event; left unchecked it will eventually breach a spec limit.",
        alternative_causes=["Tool / electrode wear", "Bath or reagent depletion", "Ambient temperature ramp"],
        corrective_actions=[
            _ca("Extrapolate the trend to estimate time-to-spec-breach; schedule intervention before that point.", "Process Engineer", "Immediate", "P2", "Prevents a future out-of-spec excursion"),
            _ca("Identify the wearing/depleting element driving the trend and restore it (replace/refresh/recalibrate).", "Equipment", "1 week", "P2", "Removes the drift source"),
        ],
        preventive_actions=[
            _pa("Convert the time-to-breach estimate into a preventive replacement interval on the PM schedule.", "Equipment", "1 month", "PM"),
        ],
        containment="Verify the most recent points against spec.", disposition="Conditional Release",
        standard_reference="Nelson (1984), Rule 3", weight=0.5,
    ),

    # ── N4: 14 alternating (sawtooth) ───────────────────────────────────────
    CAPARule(
        rule_id="SPC-N4", process="General", parameter="Any",
        fault_pattern="14-Point Alternating Sawtooth — Overcontrol / Mixture",
        description="Fourteen consecutive points alternate up/down, suggesting overadjustment or two alternating sources.",
        severity="Minor", spc_rules=["N4"],
        root_cause="Systematic alternation: operator overcontrol (tampering), or two alternating streams (machines, fixtures, shifts).",
        root_cause_detail="Sawtooth oscillation typically means the process is being adjusted in response to common-cause noise, or two interleaved sources are charted together.",
        alternative_causes=["Operator overadjustment", "Alternating machines/spindles", "Two interleaved measurement devices"],
        corrective_actions=[
            _ca("Confirm whether operators are adjusting between subgroups; stop adjustment for common-cause variation.", "Process Engineer", "Immediate", "P3", "Eliminates tampering-induced variation"),
            _ca("Check for two alternating sources; if present, chart them separately (stratify).", "Quality", "1 week", "P3", "Separates mixed streams for valid SPC"),
        ],
        preventive_actions=[
            _pa("Train operators on common- vs special-cause reaction rules to prevent overcontrol.", "Quality", "1 month", "Training"),
        ],
        containment="None typically required (pattern is variation-structure, not a shift).", disposition="Release",
        standard_reference="Nelson (1984), Rule 4", weight=0.4,
    ),

    # ── N7: 15 within 1σ (stratification) ───────────────────────────────────
    CAPARule(
        rule_id="SPC-N7", process="General", parameter="Any",
        fault_pattern="15 Within 1σ — Stratification / Understated Limits",
        description="Fifteen consecutive points hug within ±1σ, indicating stratification or incorrectly wide limits.",
        severity="Minor", spc_rules=["N7"],
        root_cause="Reduced variation that is 'too good': stratified sampling, or control limits computed from an inflated sigma.",
        root_cause_detail="Points clustering near the centerline often mean the limits were derived from between-subgroup variation, or samples were drawn to mask real variation.",
        alternative_causes=["Limits computed from wrong sigma source", "Stratified / non-random sampling", "Recent genuine variation reduction (recompute limits)"],
        corrective_actions=[
            _ca("Verify control limits were computed from within-subgroup variation, not pooled/overall sigma.", "Quality", "Immediate", "P3", "Corrects invalid limits that hide signals"),
            _ca("Review the sampling scheme for stratification (e.g. one unit per stream forced into a subgroup).", "Quality", "1 week", "P3", "Restores rational subgrouping"),
        ],
        preventive_actions=[
            _pa("Document the rational-subgrouping scheme so limits are recomputed correctly after process changes.", "Quality", "1 month", "Control Plan"),
        ],
        containment="None (data-integrity pattern, not a product risk).", disposition="Release",
        standard_reference="Nelson (1984), Rule 7", weight=0.4,
    ),

    # ── N8: 8 outside 1σ both sides (mixture) ───────────────────────────────
    CAPARule(
        rule_id="SPC-N8", process="General", parameter="Any",
        fault_pattern="8 Outside 1σ Both Sides — Mixture / Bimodality",
        description="Eight consecutive points fall outside ±1σ on both sides with none near the center, indicating a mixture.",
        severity="Major", spc_rules=["N8"],
        root_cause="Two or more distinct distributions mixed on one chart: multiple machines, materials, cavities, or operators.",
        root_cause_detail="A bimodal 'avoid-the-center' pattern is the signature of pooling multiple populations; capability indices on mixed data are invalid.",
        alternative_causes=["Multiple cavities / spindles / heads", "Two material lots", "Shift-to-shift difference"],
        corrective_actions=[
            _ca("Stratify the data by source (machine, cavity, lot, operator) and re-chart each stream separately.", "Process Engineer", "Immediate", "P2", "Reveals the per-stream behaviour hidden by pooling"),
            _ca("Quantify the between-source difference; address the worst-performing stream first.", "Process Engineer", "1 week", "P2", "Targets the dominant variation source"),
        ],
        preventive_actions=[
            _pa("Require source identifiers in data collection so streams are never silently pooled.", "Quality", "1 month", "Control Plan"),
        ],
        containment="Re-assess capability per stream before releasing any capability-based disposition.", disposition="Conditional Release",
        standard_reference="Nelson (1984), Rule 8", weight=0.5,
    ),
]
