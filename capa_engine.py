"""
StatMind Session 5 — Rule-Based CAPA Engine
Semiconductor-specific decision trees. No API key required.
Deterministic, auditable, ISO/IATF-compliant logic.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class NormalityInput:
    column: str
    verdict: str          # "Normal" | "Likely Normal" | "Non-Normal"
    sw_pass: bool
    ad_pass: bool
    rj_pass: bool
    skewness: float = 0.0
    kurtosis: float = 0.0


@dataclass
class CapabilityInput:
    column: str
    cpk: float
    ppk: float
    cp: float
    pp: float
    within_sigma: float
    overall_sigma: float
    usl: float
    lsl: float
    mean: float
    ppm_expected: float = 0.0


@dataclass
class SPCInput:
    column: str
    chart_type: str       # "I-MR" | "Xbar-R" | "Xbar-S"
    alarm_count: int
    alarm_rules: list     # list of rule names triggered
    points_beyond_3s: int = 0
    run_count: int = 0
    trend_count: int = 0


@dataclass
class GRRInput:
    column: str
    grr_pct: float
    ev_pct: float         # repeatability %
    av_pct: float         # reproducibility %
    ndc: int
    verdict: str          # "Acceptable" | "Marginal" | "Unacceptable"
    interaction_significant: bool = False


@dataclass
class CAPAReport:
    generated_at: str
    column: str
    risk_level: str           # "Critical" | "High" | "Medium" | "Low"
    problem_statement: str
    data_evidence: list
    risk_assessment: dict
    root_cause_hypotheses: list
    immediate_actions: list
    corrective_actions: list
    preventive_actions: list
    verification_plan: list
    process_context_notes: str
    overall_score: int        # 0-100 process health


# ─── Helper Classifiers ───────────────────────────────────────────────────────

def _cpk_tier(cpk: float) -> str:
    if cpk < 1.0:   return "critical"
    if cpk < 1.33:  return "warning"
    if cpk < 1.67:  return "acceptable"
    return "excellent"


def _grr_tier(grr_pct: float) -> str:
    if grr_pct > 30: return "unacceptable"
    if grr_pct > 10: return "marginal"
    return "acceptable"


def _sigma_gap_pct(within: float, overall: float) -> float:
    if within == 0:
        return 0.0
    return abs(overall - within) / within * 100


def _detect_process_context(column: str) -> str:
    col = column.lower()
    if any(k in col for k in ["etch", "rate", "rf"]):
        return "etch"
    if any(k in col for k in ["cmp", "removal", "polish", "planar"]):
        return "cmp"
    if any(k in col for k in ["cd", "critical", "litho", "focus", "dose", "overlay"]):
        return "lithography"
    if any(k in col for k in ["thick", "dep", "cvd", "pvd", "film"]):
        return "deposition"
    if any(k in col for k in ["diff", "implant", "anneal", "temp"]):
        return "diffusion"
    if any(k in col for k in ["particle", "defect", "count"]):
        return "defect"
    if any(k in col for k in ["uniform", "wiwnu", "wtwnu"]):
        return "uniformity"
    return "general"


_PROCESS_CONTEXT_NOTES = {
    "etch": (
        "Etch process context: Check RF power delivery and match network stability. "
        "Verify endpoint detection (OES/interferometry) is triggering correctly. "
        "Review chamber seasoning cycles and helium backside pressure. "
        "Inspect focus ring erosion — replace at scheduled PE hours."
    ),
    "cmp": (
        "CMP process context: Verify slurry concentration, pH, and particle size distribution. "
        "Check pad conditioning rate and conditioner disc wear. "
        "Review carrier head pressure zones and retaining ring gap. "
        "Check platen temperature uniformity across polishing area."
    ),
    "lithography": (
        "Lithography process context: Verify scanner focus/dose recipe and lens heating compensation. "
        "Check reticle cleanliness and pellicle integrity. "
        "Review wafer stage alignment marks and overlay target offsets. "
        "Inspect BARC/TARC coat uniformity and develop temperature."
    ),
    "deposition": (
        "Deposition process context: Verify precursor flow rates and bubbler temperature. "
        "Check chamber pressure stability and RF matching network. "
        "Review susceptor/heater temperature uniformity via thermocouple calibration. "
        "Inspect showerhead for clogging or deposition buildup."
    ),
    "diffusion": (
        "Diffusion/Implant context: Verify furnace temperature uniformity across boat positions. "
        "Check source gas flow rates and bubbler levels. "
        "Review dopant activation anneal recipe ramp rates. "
        "Inspect quartz ware for cleanliness and devitrification."
    ),
    "defect": (
        "Defect/Particle context: Verify inline particle monitor baseline and detection threshold. "
        "Check chamber vent/pump cycles and pump exhaust filter condition. "
        "Review wet clean process (SC1/SC2 chemistry) freshness and megasonic power. "
        "Inspect robot arm and wafer handling for mechanical contact sources."
    ),
    "uniformity": (
        "Uniformity context: Verify measurement recipe (site map, exclusion zone) is consistent. "
        "Check chuck/susceptor flatness and clamp force uniformity. "
        "Review center-to-edge process gradient — adjust gas injection or RF zone tuning. "
        "Compare within-wafer vs. wafer-to-wafer uniformity to isolate source."
    ),
    "general": (
        "General manufacturing context: Verify measurement system is qualified (see GRR results). "
        "Review process recipe version and any recent ECO/recipe changes. "
        "Check incoming material lot traceability and supplier qualification status. "
        "Compare day/night shift splits to detect operator or environmental effects."
    ),
}

_SPC_RULE_INTERPRETATIONS = {
    "WE1": ("Point beyond 3σ — acute special cause", "Immediate containment required. Inspect for abrupt equipment event: RF arc, slurry starvation, recipe mis-load, hardware fault."),
    "WE2": ("9 consecutive same side — sustained process shift", "Process mean has shifted. Check recipe version change, PM activity log, consumable lot change, or APC correction drift."),
    "WE3": ("6 consecutive trend — gradual process drift", "Monotonic drift detected. Likely consumable wear: focus ring, conditioner disc, heater aging, or gas cylinder depletion."),
    "WE4": ("14 alternating points — systematic overcorrection", "APC or manual feed-forward corrections are oscillating. Detune APC gain or review operator adjustment frequency."),
    "NE2": ("9 consecutive same side (Nelson) — confirmed mean shift", "Sustained bias confirmed. Cross-reference with maintenance log and incoming lot changepoints."),
    "NE3": ("6 consecutive trend (Nelson) — confirmed drift", "Gradual drift pattern. Consumable wear or environmental trending (ambient temperature, humidity)."),
    "NE4": ("14 alternating (Nelson) — confirmed overcorrection", "Systematic feedback loop instability. Review APC model and update control limits."),
    "NE5": ("2 of 3 beyond 2σ — near-control-limit cluster", "Process approaching control limit. Increase sampling frequency and inspect for intermittent special cause."),
    "NE6": ("4 of 5 beyond 1σ — off-center process", "Process running off-center. Verify target recipe value and adjust setpoint."),
    "NE7": ("15 consecutive within 1σ — stratification", "Data may be stratified (mixed subgroups). Verify sampling strategy — not mixing chambers or shifts in one chart."),
    "NE8": ("8 consecutive beyond 1σ — bimodal distribution", "Bimodal pattern detected. Possible chamber-to-chamber mixing or two distinct process modes in dataset."),
}


# ─── Core CAPA Builder ───────────────────────────────────────────────────────

def generate_capa(
    normality: Optional[NormalityInput] = None,
    capability: Optional[CapabilityInput] = None,
    spc: Optional[SPCInput] = None,
    grr: Optional[GRRInput] = None,
) -> CAPAReport:

    # Determine primary column name
    column = (
        (capability and capability.column) or
        (spc and spc.column) or
        (grr and grr.column) or
        (normality and normality.column) or
        "Unknown Parameter"
    )

    process_ctx = _detect_process_context(column)
    evidence = []
    hypotheses = []
    immediate = []
    corrective = []
    preventive = []
    verification = []
    risk_score = 0   # 0 = best, 100 = worst

    # ── 1. Normality Evidence ─────────────────────────────────────────────────
    if normality:
        tests_failed = sum([not normality.sw_pass, not normality.ad_pass, not normality.rj_pass])
        if normality.verdict == "Non-Normal":
            evidence.append(f"Non-normal distribution detected ({tests_failed}/3 tests failed). "
                            f"Skewness={normality.skewness:.3f}, Kurtosis={normality.kurtosis:.3f}.")
            risk_score += 15
            if abs(normality.skewness) > 1.5:
                hypotheses.append({
                    "rank": 1,
                    "hypothesis": "Process has a physical lower/upper bound causing skewed distribution",
                    "likelihood": "High",
                    "rationale": f"Skewness of {normality.skewness:.2f} suggests a bounded or censored process (e.g., particle counts cannot be negative, film thickness has a deposition floor).",
                    "investigation": "Plot histogram on log scale. Apply Box-Cox or Johnson transformation. Evaluate if Pp/Ppk should use non-parametric percentile method."
                })
            if abs(normality.kurtosis) > 3:
                hypotheses.append({
                    "rank": 2,
                    "hypothesis": "Mixed population or multi-modal process (chamber mixing or lot mixing)",
                    "likelihood": "Medium",
                    "rationale": f"Excess kurtosis of {normality.kurtosis:.2f} is consistent with overlapping sub-populations.",
                    "investigation": "Stratify data by chamber, shift, operator, or lot and re-test normality on each stratum."
                })
        elif normality.verdict == "Likely Normal":
            evidence.append(f"Marginally normal ({3 - tests_failed}/3 tests passed). Proceed with caution on parametric indices.")
            risk_score += 5

    # ── 2. Capability Evidence ────────────────────────────────────────────────
    if capability:
        cpk_tier = _cpk_tier(capability.cpk)
        sg = _sigma_gap_pct(capability.within_sigma, capability.overall_sigma)
        tolerance = capability.usl - capability.lsl

        evidence.append(f"Cpk={capability.cpk:.3f}, Ppk={capability.ppk:.3f}, Cp={capability.cp:.3f}, Pp={capability.pp:.3f}.")
        evidence.append(f"Mean={capability.mean:.4f}, Spec window={tolerance:.4f} "
                        f"(LSL={capability.lsl:.4f}, USL={capability.usl:.4f}).")
        if capability.ppm_expected > 0:
            evidence.append(f"Expected defect rate: {capability.ppm_expected:,.0f} PPM ({capability.ppm_expected/10000:.2f}%).")

        if cpk_tier == "critical":
            risk_score += 40
            immediate.append("Initiate 100% inspection of in-process and outgoing lots. Place product on hold pending disposition.")
            immediate.append("Notify process engineering and quality immediately. Open formal non-conformance record (NCR).")
            corrective.append(f"Re-center process: current mean={capability.mean:.4f}, target={(capability.usl+capability.lsl)/2:.4f}. Adjust recipe setpoint.")
            corrective.append("Perform DOE (screening design) to identify critical process inputs driving capability loss.")
            hypotheses.append({
                "rank": 1,
                "hypothesis": "Process mean is significantly off-target or process spread exceeds spec tolerance",
                "likelihood": "Confirmed",
                "rationale": f"Cpk={capability.cpk:.3f} below 1.0 — process is actively producing out-of-spec material.",
                "investigation": "Compare Cp vs Cpk: if Cp>>Cpk, centering problem. If Cp≈Cpk<1.0, spread problem."
            })
        elif cpk_tier == "warning":
            risk_score += 25
            immediate.append("Increase sampling frequency to 2× current rate. Flag lot for enhanced incoming inspection at downstream.")
            corrective.append(f"Target Cpk ≥ 1.67 for semiconductor fab. Current gap: need {((1.67 - capability.cpk) * capability.within_sigma * 6 / tolerance * 100):.1f}% spread reduction.")
            corrective.append("Review and tighten process window. Evaluate APC closed-loop control to reduce within-lot variation.")

        if sg > 25:
            risk_score += 20
            evidence.append(f"Within/Overall sigma gap = {sg:.1f}% — significant special-cause variation present.")
            hypotheses.append({
                "rank": 2,
                "hypothesis": "Special-cause events (shifts, spikes) are inflating overall variation beyond natural process noise",
                "likelihood": "High",
                "rationale": f"Overall sigma is {sg:.1f}% larger than within-subgroup sigma. Control chart should show identifiable alarm signals.",
                "investigation": "Run I-MR or Xbar-R chart. Identify and stratify alarm points. Cross-reference with equipment event log."
            })
            corrective.append("Identify and eliminate root causes of special-cause variation before re-evaluating Pp/Ppk.")

        if capability.cp > 1.67 and capability.cpk < 1.33:
            hypotheses.append({
                "rank": 3,
                "hypothesis": "Process has sufficient natural spread capability but is off-center",
                "likelihood": "High",
                "rationale": f"Cp={capability.cp:.3f} >> Cpk={capability.cpk:.3f} indicates a centering issue, not a spread issue.",
                "investigation": "Adjust process mean toward target center. Recipe setpoint correction should be straightforward."
            })
            corrective.append(f"Centering correction: shift mean by {((capability.usl+capability.lsl)/2 - capability.mean):+.4f} units toward spec center.")

    # ── 3. SPC Evidence ───────────────────────────────────────────────────────
    if spc:
        if spc.alarm_count > 0:
            evidence.append(f"SPC ({spc.chart_type}): {spc.alarm_count} alarm(s) detected — rules triggered: {', '.join(spc.alarm_rules)}.")
            risk_score += min(30, spc.alarm_count * 5)

            for rule_id in spc.alarm_rules:
                if rule_id in _SPC_RULE_INTERPRETATIONS:
                    title, action = _SPC_RULE_INTERPRETATIONS[rule_id]
                    hypotheses.append({
                        "rank": len(hypotheses) + 1,
                        "hypothesis": f"{rule_id}: {title}",
                        "likelihood": "Confirmed (statistically)",
                        "rationale": f"Rule {rule_id} triggered on {spc.chart_type} chart.",
                        "investigation": action
                    })
                    corrective.append(f"[{rule_id}] {action}")

            if spc.points_beyond_3s > 0:
                immediate.append(f"Investigate {spc.points_beyond_3s} point(s) beyond 3σ: retrieve lot traveler and equipment event log for those run IDs.")

        else:
            evidence.append(f"SPC ({spc.chart_type}): Process in statistical control — no alarm signals detected.")

    # ── 4. GRR Evidence ───────────────────────────────────────────────────────
    if grr:
        grr_tier = _grr_tier(grr.grr_pct)
        evidence.append(f"Gauge R&R: {grr.grr_pct:.1f}% (EV={grr.ev_pct:.1f}%, AV={grr.av_pct:.1f}%), ndc={grr.ndc}.")

        if grr_tier == "unacceptable":
            risk_score += 30
            evidence.append("WARNING: Measurement system is unacceptable. All process data from this gauge is suspect.")
            immediate.append("Quarantine all data collected with this measurement system pending gauge qualification.")
            immediate.append("Do not make process decisions based on this data until GRR passes.")
            corrective.append("Recalibrate gauge and re-run full 10-part × 3-operator × 3-replicate study.")

            if grr.ev_pct > grr.av_pct:
                hypotheses.append({
                    "rank": 1,
                    "hypothesis": "Gauge repeatability (EV) is the dominant error source — equipment precision issue",
                    "likelihood": "Confirmed",
                    "rationale": f"EV={grr.ev_pct:.1f}% dominates AV={grr.av_pct:.1f}%. The gauge itself is inconsistent regardless of operator.",
                    "investigation": "Inspect gauge mechanism: worn contacts, fixture instability, vibration, or insufficient gauge resolution. Check calibration certificate."
                })
                corrective.append("Inspect gauge fixture and contact mechanism. Consider higher-precision instrument (optical vs. contact).")
            else:
                hypotheses.append({
                    "rank": 1,
                    "hypothesis": "Operator reproducibility (AV) is dominant — technique or training gap",
                    "likelihood": "Confirmed",
                    "rationale": f"AV={grr.av_pct:.1f}% dominates EV={grr.ev_pct:.1f}%. Operators are measuring differently.",
                    "investigation": "Observe each operator's measurement technique. Check gauge loading procedure, stabilization time, and fixture alignment."
                })
                corrective.append("Conduct measurement technique retraining. Standardize and document loading/fixturing procedure with photos/video.")

        elif grr_tier == "marginal":
            risk_score += 15
            corrective.append(f"Marginal GRR ({grr.grr_pct:.1f}%): Acceptable for go/no-go decisions only. Not suitable for process control or SPC charting.")
            corrective.append("Investigate dominant source (EV vs AV) and reduce by 50% to reach <10% target.")

        if grr.ndc < 5:
            risk_score += 10
            corrective.append(f"ndc={grr.ndc} is below the minimum of 5 — gauge cannot distinguish enough part-to-part variation categories for meaningful SPC.")
            corrective.append("Upgrade to a gauge with at least 5× better resolution than the process standard deviation.")

        if grr.interaction_significant:
            hypotheses.append({
                "rank": len(hypotheses) + 1,
                "hypothesis": "Significant Part × Operator interaction — measurement difficulty varies by part geometry",
                "likelihood": "Confirmed (p < 0.05)",
                "rationale": "Some operators measure certain part geometries differently. Interaction term is statistically significant in ANOVA.",
                "investigation": "Identify which parts and operators drive the interaction. Rewrite measurement procedure to standardize geometry-specific technique."
            })

    # ── 5. Risk Level Determination ───────────────────────────────────────────
    risk_score = min(100, risk_score)
    if risk_score >= 60:    risk_level = "Critical"
    elif risk_score >= 35:  risk_level = "High"
    elif risk_score >= 15:  risk_level = "Medium"
    else:                   risk_level = "Low"

    # ── 6. Risk Assessment Matrix ─────────────────────────────────────────────
    severity   = min(10, max(1, risk_score // 10))
    occurrence = min(10, max(1, (risk_score // 8)))
    detection  = 3 if (spc and spc.alarm_count > 0) else 7
    rpn        = severity * occurrence * detection

    risk_assessment = {
        "severity":   severity,
        "occurrence": occurrence,
        "detection":  detection,
        "rpn":        rpn,
        "rpn_note":   "RPN >200 requires immediate escalation per standard FMEA guidelines."
    }

    # ── 7. Standard Preventive Actions ────────────────────────────────────────
    preventive.append("Implement SPC charting with Western Electric rules on this parameter going forward.")
    preventive.append("Set up automated alarm escalation: email/SMS to process owner within 15 min of 3σ breach.")
    preventive.append("Add parameter to quarterly MSA/GRR re-qualification schedule.")
    preventive.append("Review PM schedule: verify measurement system calibration interval aligns with observed drift rate.")
    if process_ctx in ["etch", "cmp", "deposition"]:
        preventive.append(f"Include {column} in chamber-matching study. Establish chamber-to-chamber offset limits and correction protocol.")

    # ── 8. Verification Plan ─────────────────────────────────────────────────
    if capability and _cpk_tier(capability.cpk) in ["critical", "warning"]:
        verification.append({"step": 1, "action": "Re-run capability study after corrective actions", "metric": f"Cpk ≥ 1.67, Ppk ≥ 1.33", "timeline": "Within 5 working days"})
    if spc and spc.alarm_count > 0:
        verification.append({"step": 2, "action": "Run control chart for 25+ consecutive points post-correction", "metric": "Zero WE1/WE2/WE3 alarms", "timeline": "Within 10 working days"})
    if grr and grr.grr_pct > 10:
        verification.append({"step": 3, "action": "Re-run GRR study (10 parts × 3 operators × 3 reps)", "metric": "GRR% < 10%, ndc ≥ 5", "timeline": "Within 3 working days"})
    verification.append({"step": len(verification)+1, "action": "30-day monitoring review with process owner", "metric": "No recurrence of alarm conditions", "timeline": "30 days from close"})

    # ── 9. Problem Statement ──────────────────────────────────────────────────
    cpk_str = f"Cpk={capability.cpk:.3f}" if capability else ""
    spc_str = f"{spc.alarm_count} SPC alarm(s)" if spc else ""
    grr_str = f"GRR={grr.grr_pct:.1f}%" if grr else ""
    details = " | ".join(filter(None, [cpk_str, spc_str, grr_str]))
    problem_statement = (
        f"Parameter '{column}' exhibits a {risk_level.lower()} process risk condition "
        f"({details}). "
        f"Statistical analysis indicates the process is {'outside acceptable limits' if risk_level in ['Critical','High'] else 'at elevated risk'} "
        f"and requires {'immediate' if risk_level == 'Critical' else 'planned'} corrective action."
    )

    process_context_notes = _PROCESS_CONTEXT_NOTES.get(process_ctx, _PROCESS_CONTEXT_NOTES["general"])

    # De-duplicate hypotheses by rank
    seen = set()
    unique_hyp = []
    for h in hypotheses:
        key = h["hypothesis"][:60]
        if key not in seen:
            seen.add(key)
            unique_hyp.append(h)

    overall_score = max(0, 100 - risk_score)

    return CAPAReport(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        column=column,
        risk_level=risk_level,
        problem_statement=problem_statement,
        data_evidence=evidence,
        risk_assessment=risk_assessment,
        root_cause_hypotheses=unique_hyp,
        immediate_actions=list(dict.fromkeys(immediate)),
        corrective_actions=list(dict.fromkeys(corrective)),
        preventive_actions=list(dict.fromkeys(preventive)),
        verification_plan=verification,
        process_context_notes=process_context_notes,
        overall_score=overall_score,
    )
