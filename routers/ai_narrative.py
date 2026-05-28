"""
StatMind N17 — AI Report Narrative Generator
Converts analysis results into written plain-English paragraphs
for inclusion in PDF reports and executive summaries.
"Cpk=1.21 below PPAP target. Primary cause: centering.
 Recommend adjusting etch time setpoint by -3 seconds."
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class NarrativeReport:
    parameter: str
    process_type: str
    generated_at: str
    # Section narratives
    executive_summary: str      # 2-3 sentence high-level verdict
    normality_narrative: str    # what the distribution looks like
    capability_narrative: str   # what Cpk means in plain English
    spc_narrative: str          # what the control charts show
    grr_narrative: str          # measurement system adequacy
    capa_narrative: str         # root cause and recommended actions
    # Full combined narrative
    full_narrative: str
    # Word count
    word_count: int


def _norm_narrative(norm_result: dict, param: str) -> str:
    if not norm_result:
        return ""
    verdict = norm_result.get("overall_verdict", "Unknown")
    # Handle both flat and nested descriptive structures
    desc = norm_result.get("descriptive") or {}
    mean = desc.get("mean") or norm_result.get("mean", 0)
    std  = desc.get("std")  or norm_result.get("std", 0)
    n    = desc.get("n")    or norm_result.get("n", 0)
    skew = desc.get("skewness") or norm_result.get("skewness", 0)
    sw   = norm_result.get("shapiro_wilk") or {}
    sw_p = sw.get("p_value") if isinstance(sw, dict) else 0

    skew_dir = "right" if skew > 0.5 else "left" if skew < -0.5 else ""
    skew_desc = f" with a {skew_dir}-skewed tail (skewness = {skew:.3f})" if skew_dir else f" (skewness = {skew:.3f}, approximately symmetric)"

    if verdict == "Non-Normal":
        dist_desc = (
            f"The {param} data (n={n}) does not follow a normal distribution "
            f"(Shapiro-Wilk p={sw_p:.4f}){skew_desc}. "
            f"The mean is {mean:.4f} with a standard deviation of {std:.4f}. "
            f"Standard Cpk calculations assume normality and will be unreliable for this data. "
            f"A Box-Cox transformation or non-normal capability method (ISO 22514-2) is recommended."
        )
    else:
        dist_desc = (
            f"The {param} data (n={n}) is consistent with a normal distribution "
            f"(Shapiro-Wilk p={sw_p:.4f}){skew_desc}. "
            f"The process mean is {mean:.4f} with a standard deviation of {std:.4f}. "
            f"Standard capability indices (Cp, Cpk) are valid for this data."
        )
    return dist_desc


def _cap_narrative(cap_result: dict, param: str, industry: str = "") -> str:
    if not cap_result:
        return ""
    cpk = cap_result.get("cpk")
    cp  = cap_result.get("cp")
    ppk = cap_result.get("ppk")
    ppm = cap_result.get("ppm_within", cap_result.get("ppm_total"))
    sigma = cap_result.get("sigma_level")
    usl = cap_result.get("usl")
    lsl = cap_result.get("lsl")
    mean = cap_result.get("mean")

    if cpk is None:
        return ""

    # Centering interpretation
    centering = ""
    if cp and cpk and cp > 0:
        gap = cp - cpk
        if gap > 0.15:
            # Determine direction
            if usl and lsl and mean:
                mid = (usl + lsl) / 2
                direction = "above" if mean > mid else "below"
                by_pct = abs(mean - mid) / ((usl - lsl) / 2) * 100
                centering = (
                    f"The primary limitation is centering: the process mean ({mean:.4f}) is "
                    f"{direction} the specification midpoint by {by_pct:.1f}% of the tolerance band. "
                    f"Cp = {cp:.3f} indicates the process spread is adequate — "
                    f"shifting the mean to target would improve Cpk to approximately {cp:.3f}."
                )
            else:
                centering = (
                    f"The gap between Cp ({cp:.3f}) and Cpk ({cpk:.3f}) indicates the process "
                    f"is off-center. Centering improvement would raise Cpk toward {cp:.3f}."
                )
        else:
            centering = (
                f"The process is well-centered (Cp = {cp:.3f} ≈ Cpk = {cpk:.3f}). "
                f"Improving capability requires reducing process variation, not centering."
            )

    # Threshold context
    ppap_req = 1.67
    ongoing_req = 1.33
    if "automotive" in industry.lower() or "iatf" in industry.lower():
        threshold_context = f"For IATF 16949 / AIAG PPAP, the minimum Cpk is {ppap_req} for new part approval and {ongoing_req} for ongoing production."
    elif "medical" in industry.lower() or "fda" in industry.lower():
        threshold_context = "For ISO 13485 / FDA-regulated processes, Cpk ≥ 1.33 is the typical minimum; critical-to-patient-safety parameters require Cpk ≥ 1.67."
    elif "semiconductor" in industry.lower():
        threshold_context = "For semiconductor manufacturing, Cpk ≥ 1.33 is the standard for SPC monitoring; Cpk ≥ 1.67 is targeted for critical dimension control."
    else:
        threshold_context = f"Industry standard minimum is Cpk ≥ {ongoing_req} for production and Cpk ≥ {ppap_req} for PPAP submission."

    # Verdict
    if cpk >= 1.67:
        verdict = f"The process is highly capable (Cpk = {cpk:.3f} ≥ 1.67). {threshold_context}"
    elif cpk >= 1.33:
        verdict = f"The process meets the ongoing production requirement (Cpk = {cpk:.3f} ≥ 1.33) but does not meet PPAP threshold (Cpk ≥ 1.67). {threshold_context}"
    elif cpk >= 1.0:
        verdict = f"The process is marginally capable (Cpk = {cpk:.3f}), falling below the standard minimum of 1.33. {threshold_context}"
    else:
        verdict = f"The process is not capable (Cpk = {cpk:.3f} < 1.00). Defects are actively being produced. {threshold_context}"

    ppm_text = f" At the current performance level, approximately {ppm:,.0f} parts per million are expected to fall outside specification." if ppm else ""
    sigma_text = f" The process operates at {sigma:.2f} sigma." if sigma else ""

    return f"{verdict}{ppm_text}{sigma_text} {centering}".strip()


def _spc_narrative(spc_result: dict, param: str) -> str:
    if not spc_result:
        return ""
    in_ctrl = spc_result.get("in_control", True)
    alarms = spc_result.get("total_alarms", 0)
    chart_type = spc_result.get("chart_type", "I-MR")
    ucl = spc_result.get("primary_ucl")
    cl  = spc_result.get("primary_cl")
    lcl = spc_result.get("primary_lcl")
    we_alarms = spc_result.get("western_electric_alarms", [])
    nelson_alarms = spc_result.get("nelson_alarms", [])

    limits_text = f"Control limits: UCL = {ucl:.4f}, Mean = {cl:.4f}, LCL = {lcl:.4f}." if ucl else ""

    if in_ctrl:
        return (
            f"The {chart_type} control chart shows {param} is in a state of statistical control. "
            f"No special cause variation was detected across all monitored observations. "
            f"{limits_text} "
            f"The process is predictable and operating consistently within its natural variation."
        )

    # Describe alarm types
    alarm_types = {}
    for a in we_alarms + nelson_alarms:
        rule = a.get("rule", "Unknown")
        alarm_types[rule] = alarm_types.get(rule, 0) + 1

    alarm_desc = ", ".join(f"{cnt} {rule} violation(s)" for rule, cnt in alarm_types.items())
    alarm_interp = {
        "WE1": "one or more points beyond the 3-sigma control limits (a large shift or extreme event)",
        "WE2": "a run of 9 consecutive points on the same side of the centerline (sustained process shift)",
        "WE3": "6 consecutive points trending in one direction (systematic drift or wear)",
        "WE4": "14 alternating points (two alternating process sources or over-adjustment)",
        "NE1": "a point beyond 3 sigma (same as WE1)",
        "NE2": "9 points on one side (process shift)",
        "NE3": "6 points trending (drift)",
    }
    first_rule = list(alarm_types.keys())[0] if alarm_types else ""
    interp = alarm_interp.get(first_rule, "a statistically unlikely pattern")

    return (
        f"The {chart_type} control chart detected {alarms} special cause signal(s) in {param}: {alarm_desc}. "
        f"The primary signal indicates {interp}. "
        f"{limits_text} "
        f"The process is not in a state of statistical control. "
        f"An assignable cause investigation is required before capability indices can be interpreted as predictive."
    )


def _grr_narrative(grr_result: dict, param: str) -> str:
    if not grr_result:
        return ""
    grr_data = grr_result.get("gauge_rr", {})
    pct_sv = grr_data.get("pct_study_var")
    pct_tol = grr_data.get("pct_tolerance")
    ndc = grr_result.get("ndc")
    ev = grr_data.get("ev")
    av = grr_data.get("av")

    if pct_sv is None:
        return ""

    if pct_sv < 10:
        verdict = f"The measurement system for {param} is excellent (%GRR = {pct_sv:.1f}% < 10%)."
    elif pct_sv < 30:
        verdict = f"The measurement system for {param} is marginal (%GRR = {pct_sv:.1f}%, between 10–30%). May be acceptable depending on application importance and cost of gauge improvement."
    else:
        verdict = f"The measurement system for {param} is unacceptable (%GRR = {pct_sv:.1f}% > 30%). The gauge is contributing too much variation and capability indices are unreliable."

    dominant = ""
    if ev and av:
        if ev > av * 2:
            dominant = " Equipment variation (repeatability) is the dominant component — the gauge itself is inconsistent between repeated measurements on the same part."
        elif av > ev * 2:
            dominant = " Appraiser variation (reproducibility) dominates — different operators are measuring differently. Standardized technique and training is the primary corrective action."
        else:
            dominant = " Equipment and appraiser variation are roughly equal contributors."

    ndc_text = f" The number of distinct categories (ndc = {ndc}) {'meets' if ndc >= 5 else 'does not meet'} the minimum of 5 required for SPC." if ndc else ""

    return f"{verdict}{dominant}{ndc_text}"


def _capa_narrative(capa_result: dict, param: str) -> str:
    if not capa_result:
        return ""
    primary = capa_result.get("primary_capa", {})
    if not primary:
        return "Insufficient analysis data for automated root cause identification. Complete normality, capability, SPC, and GRR analyses to enable CAPA matching."

    pattern = primary.get("fault_pattern", "")
    root_cause = primary.get("root_cause", "")
    actions = primary.get("corrective_actions", [])
    severity = primary.get("severity", "")
    confidence = primary.get("match_score", 0)

    action_text = ""
    if actions:
        p1_actions = [a.get("action","") for a in actions if a.get("priority","") == "P1"][:2]
        if p1_actions:
            action_text = f" Recommended immediate actions: {' '.join(p1_actions[:1])}"

    return (
        f"Root cause analysis identified the primary fault pattern as '{pattern}' "
        f"(confidence: {confidence*100:.0f}%, severity: {severity}). "
        f"The most probable root cause is: {root_cause[:200]}."
        f"{action_text}"
    )


def generate_narrative(
    parameter: str,
    process_type: str = "",
    normality_result: dict = None,
    capability_result: dict = None,
    spc_result: dict = None,
    grr_result: dict = None,
    capa_result: dict = None,
) -> NarrativeReport:
    """Generate a full written narrative from all available analysis results."""

    norm_text = _norm_narrative(normality_result, parameter)
    cap_text  = _cap_narrative(capability_result, parameter, process_type)
    spc_text  = _spc_narrative(spc_result, parameter)
    grr_text  = _grr_narrative(grr_result, parameter)
    capa_text = _capa_narrative(capa_result, parameter)

    # Executive summary — synthesizes key findings
    cpk = capability_result.get("cpk") if capability_result else None
    in_ctrl = spc_result.get("in_control", True) if spc_result else True
    grr_pct = grr_result.get("gauge_rr", {}).get("pct_study_var") if grr_result else None
    norm_verdict = normality_result.get("overall_verdict", "Unknown") if normality_result else "Unknown"

    # Build executive summary
    issues = []
    if cpk is not None and cpk < 1.33:
        issues.append(f"below-target capability (Cpk = {cpk:.3f})")
    if not in_ctrl:
        issues.append("out-of-control SPC signals")
    if grr_pct and grr_pct > 30:
        issues.append(f"unacceptable measurement system (%GRR = {grr_pct:.1f}%)")
    if norm_verdict == "Non-Normal":
        issues.append("non-normal distribution")

    if not issues:
        exec_summary = (
            f"The {parameter} process demonstrates acceptable statistical performance. "
            f"{'Capability is adequate (Cpk = ' + str(cpk) + ').' if cpk else ''} "
            f"{'The process is in statistical control.' if spc_result else ''} "
            f"No critical quality issues were identified."
        ).strip()
    else:
        issue_str = " and ".join(issues)
        exec_summary = (
            f"The {parameter} process requires attention due to {issue_str}. "
            + (_cap_narrative(capability_result, parameter, process_type)[:100] + "..." if cap_text else "")
        ).strip()

    # Combine into full narrative
    sections = [s for s in [norm_text, cap_text, spc_text, grr_text, capa_text] if s]
    full = f"\n\n".join(sections)
    word_count = len(full.split())

    return NarrativeReport(
        parameter=parameter,
        process_type=process_type or "General",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        executive_summary=exec_summary,
        normality_narrative=norm_text,
        capability_narrative=cap_text,
        spc_narrative=spc_text,
        grr_narrative=grr_text,
        capa_narrative=capa_text,
        full_narrative=full,
        word_count=word_count,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# StatMind N17 — In-House Narrative Engine Architecture Stub
# ═══════════════════════════════════════════════════════════════════════════════
#
# DESIGN PHILOSOPHY:
# StatMind generates plain-English narratives using DETERMINISTIC RULES,
# not external LLM APIs. This ensures:
# 1. No data leaves StatMind servers (critical for fab confidentiality)
# 2. Narratives are auditable and reproducible (required for regulated industries)
# 3. Domain accuracy guaranteed — rules are written by quality engineers
# 4. Zero API cost, zero latency from external calls
# 5. Can be fine-tuned/extended without retraining an external model
#
# ARCHITECTURE (current: rule-based → future: StatMind-GPT fine-tuned):
#
# Phase 1 (live): Deterministic rule engine in ai_narrative.py
#   Input: structured analysis results (Cpk, alarms, GRR%, etc.)
#   Output: human-readable paragraphs
#   Method: conditional logic on threshold values + f-string templates
#
# Phase 2 (6 months): Fine-tuned small transformer
#   Base: DistilGPT-2 or Mistral-7B (small enough to self-host)
#   Training data: quality engineering textbooks, AIAG manuals,
#                  SEMI standards, historical CAPA reports (anonymised)
#   Fine-tuning: 10,000+ (input_json → narrative_paragraph) pairs
#   Hosting: self-hosted on Railway with GPU tier
#
# Phase 3 (12 months): StatMind-QE-7B
#   Purpose-built for quality engineering narrative generation
#   Trained on: PPAP submissions, audit findings, engineering memos,
#               process qualification reports, NCR root cause analyses
#   Evaluation metric: reviewed by 5+ senior quality engineers
#
# ═══════════════════════════════════════════════════════════════════════════════

class StatMindNarrativeEngine:
    """
    StatMind N17 Rule-Based Narrative Engine
    Stub for future fine-tuned transformer model.
    All logic is deterministic and auditable.
    """

    # Training data categories for future fine-tuning
    TRAINING_DOMAINS = [
        "semiconductor_process_qualification",
        "automotive_ppap_narratives",
        "aerospace_first_article_inspection",
        "medical_device_process_validation",
        "gauge_rnr_msa_reports",
        "control_chart_alarm_investigation",
        "capa_root_cause_analysis",
        "doe_experiment_summary",
    ]

    # Template registry — each maps a statistical condition to narrative text
    # Future: these become training examples for the fine-tuned model
    CAPABILITY_TEMPLATES = {
        "excellent_centered":       "The {param} process demonstrates excellent capability (Cpk={cpk:.3f}, Cp={cp:.3f}). "
                                    "The process is well-centered and the spread is well within specification. "
                                    "Expected defect rate of {ppm:,.0f} PPM meets {industry} requirements.",
        "capable_shifted":          "The {param} process is capable (Cpk={cpk:.3f}) but shows a mean shift of {shift:.4f} {units} "
                                    "from the specification midpoint. Centering the process could improve Cpk by ~{delta:.3f} "
                                    "to approach the potential Cp={cp:.3f}.",
        "marginal":                 "The {param} process is marginally capable (Cpk={cpk:.3f}). "
                                    "With {ppm:,.0f} PPM estimated defect rate, process improvement is recommended "
                                    "before full production release.",
        "not_capable_centering":    "The {param} process is not capable (Cpk={cpk:.3f}). "
                                    "The primary contributor is mean offset from specification center. "
                                    "Recipe or setpoint adjustment is the first corrective action.",
        "not_capable_spread":       "The {param} process is not capable (Cpk={cpk:.3f}, Cp={cp:.3f}). "
                                    "Both Cp and Cpk are below 1.0, indicating that spread reduction — "
                                    "not centering — is the primary improvement lever.",
    }

    @classmethod
    def get_training_example(cls, input_result: dict, ground_truth_narrative: str) -> dict:
        """
        Generate a training example pair for future fine-tuning.
        Collect these to build the StatMind-QE training dataset.
        """
        return {
            "input": input_result,
            "output": ground_truth_narrative,
            "domain": cls._classify_domain(input_result),
            "quality_score": None,  # To be rated by engineer
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
        }

    @classmethod
    def _classify_domain(cls, result: dict) -> str:
        proc = (result.get("process_type") or "").lower()
        if "semi" in proc or "litho" in proc or "etch" in proc:
            return "semiconductor_process_qualification"
        elif "iatf" in proc or "automotive" in proc:
            return "automotive_ppap_narratives"
        elif "aerospace" in proc or "as9100" in proc:
            return "aerospace_first_article_inspection"
        elif "fda" in proc or "medical" in proc:
            return "medical_device_process_validation"
        return "general_quality_engineering"


# Instantiate the engine (used by the endpoint)
narrative_engine = StatMindNarrativeEngine()
