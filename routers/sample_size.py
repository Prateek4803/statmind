"""
StatMind N2 — Sample Size Calculator
Covers all major quality engineering sample size needs:
1. Capability study (demonstrate Cpk ≥ target with confidence)
2. Hypothesis test (t-test, ANOVA) — detect a given effect size
3. GRR study — minimum parts/operators/replicates
4. Attribute sampling — AQL/LTPD (ISO 2859 / ANSI Z1.4)
5. Control chart — detect shift in k sigma units
References: AIAG SPC 2nd Ed, Montgomery SPC 7th Ed, ISO 2859-1
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class SampleSizeResult:
    study_type: str
    n_required: int
    n_recommendation: str   # "Minimum N, recommended N is X"
    # Inputs
    parameters: dict
    # Outputs
    explanation: str
    interpretation: str
    sensitivity_table: list  # [{n, power_or_precision}]
    chart_data: dict


# ── 1. Capability Study ───────────────────────────────────────────────────────

def sample_size_capability(
    target_cpk: float = 1.33,
    confidence: float = 0.95,
    precision: float = 0.10,   # desired half-width of Cpk CI as fraction of target_cpk
) -> SampleSizeResult:
    """
    How many parts to measure to demonstrate Cpk ≥ target_cpk with given confidence?
    Uses Bissell's approximation for Cpk confidence interval width.
    """
    # Bissell CI: Cpk ± z * Cpk * sqrt(1/(9n) + 1/(2(n-1)))
    # We want CI half-width ≤ precision * target_cpk
    # Solve: z * target_cpk * sqrt(1/(9n) + 1/(2n)) ≤ precision * target_cpk
    # Simplify: z * sqrt(1/(9n) + 1/(2n)) ≤ precision
    z = float(stats.norm.ppf((1 + confidence) / 2))
    eps = precision

    # Binary search for n
    for n in range(10, 5001):
        ci_half = z * target_cpk * math.sqrt(1/(9*n) + 1/(2*(n-1)))
        if ci_half <= eps * target_cpk:
            break

    # Sensitivity table
    sens = []
    for test_n in [30, 50, 75, 100, 125, 150, 200, 300, 500]:
        if test_n >= 10:
            half = z * target_cpk * math.sqrt(1/(9*test_n) + 1/(2*(test_n-1)))
            pct_of_cpk = round(half / target_cpk * 100, 1)
            sens.append({"n": test_n, "ci_half_width": round(half, 4), "pct_of_cpk": pct_of_cpk})

    return SampleSizeResult(
        study_type="Process Capability Study",
        n_required=n,
        n_recommendation=f"Minimum {n} parts. Industry standard for Cpk studies is 30–50 parts minimum; 125 parts for ±10% precision on Cpk.",
        parameters={"target_cpk": target_cpk, "confidence": confidence, "precision": precision},
        explanation=(
            f"To demonstrate Cpk ≥ {target_cpk} with {confidence*100:.0f}% confidence "
            f"and ±{precision*100:.0f}% precision on the Cpk estimate, "
            f"you need n ≥ {n} measurements. "
            f"This ensures the lower {confidence*100:.0f}% confidence bound on Cpk ≥ {target_cpk*(1-precision):.3f}."
        ),
        interpretation=(
            f"PPAP requirement (Cpk ≥ 1.67, 95% confidence): ~{_ppap_n(1.67):.0f} parts. "
            f"Ongoing monitoring (Cpk ≥ 1.33, 95% confidence): ~{_ppap_n(1.33):.0f} parts."
        ),
        sensitivity_table=sens,
        chart_data={"n_values": [s["n"] for s in sens],
                    "ci_widths": [s["ci_half_width"] for s in sens],
                    "required_n": n,
                    "study_type": "capability"},
    )

def _ppap_n(cpk_target):
    z = float(stats.norm.ppf(0.975))
    for n in range(10, 2001):
        half = z * cpk_target * math.sqrt(1/(9*n) + 1/(2*(n-1)))
        if half <= 0.1 * cpk_target:
            return n
    return 2000


# ── 2. Hypothesis Test (t-test) ───────────────────────────────────────────────

def sample_size_ttest(
    effect_size: float = 0.5,   # Cohen's d (0.2=small, 0.5=medium, 0.8=large)
    alpha: float = 0.05,
    power: float = 0.80,
    two_tailed: bool = True,
    two_sample: bool = True,    # True = two-sample, False = one-sample
) -> SampleSizeResult:
    """
    Sample size for t-test to detect a given effect size with desired power.
    """
    from scipy.stats import norm
    z_alpha = norm.ppf(1 - alpha / (2 if two_tailed else 1))
    z_beta  = norm.ppf(power)

    if two_sample:
        n_per_group = math.ceil(2 * ((z_alpha + z_beta) / effect_size)**2)
        n_total = 2 * n_per_group
    else:
        n_total = math.ceil(((z_alpha + z_beta) / effect_size)**2)
        n_per_group = n_total

    # Power curve
    ns = list(range(5, 200, 5))
    powers = []
    for test_n in ns:
        nc = effect_size * math.sqrt(test_n / 2 if two_sample else test_n)
        p = 1 - stats.nct.cdf(stats.t.ppf(1-alpha/2, df=(2*test_n-2 if two_sample else test_n-1)),
                               df=(2*test_n-2 if two_sample else test_n-1), nc=nc)
        powers.append(round(float(p), 4))

    effect_label = "small" if effect_size <= 0.2 else "medium" if effect_size <= 0.5 else "large"
    sens = [{"n_per_group": n, "power": p} for n, p in zip(ns, powers)]

    return SampleSizeResult(
        study_type=f"{'Two-Sample' if two_sample else 'One-Sample'} t-Test",
        n_required=n_per_group,
        n_recommendation=f"{n_per_group} {'per group ('+str(n_total)+' total)' if two_sample else 'total'}. Collect 10–20% more to buffer for missing data.",
        parameters={"effect_size_cohens_d": effect_size, "alpha": alpha, "power": power},
        explanation=(
            f"To detect a {effect_label} effect (d={effect_size}) with {power*100:.0f}% power "
            f"at α={alpha} ({'two-tailed' if two_tailed else 'one-tailed'}), "
            f"need {n_per_group} {'observations per group' if two_sample else 'total observations'}."
        ),
        interpretation=(
            f"Cohen's d benchmarks: 0.2=small (subtle process difference), "
            f"0.5=medium (detectable in practice), 0.8=large (obvious difference). "
            f"For semiconductor CD: 1nm shift on 5nm σ → d=0.2 → needs {_n_for_d(0.2, alpha, power)}/group."
        ),
        sensitivity_table=sens,
        chart_data={"n_values": [s["n_per_group"] for s in sens],
                    "powers": [s["power"] for s in sens],
                    "required_n": n_per_group,
                    "target_power": power,
                    "study_type": "ttest"},
    )

def _n_for_d(d, alpha, power):
    z_a = stats.norm.ppf(1-alpha/2)
    z_b = stats.norm.ppf(power)
    return math.ceil(2*((z_a+z_b)/d)**2)


# ── 3. GRR Study ─────────────────────────────────────────────────────────────

def sample_size_grr(
    target_grr_pct: float = 10.0,   # target %GRR
    n_operators: int = 3,
    n_replicates: int = 2,
    confidence: float = 0.90,
) -> SampleSizeResult:
    """
    Minimum number of parts for a GRR study to achieve desired precision.
    AIAG MSA 4th Ed recommendation: 10 parts, 3 operators, 2 replicates minimum.
    """
    # AIAG minimum: ndc >= 5 requires approx n_parts such that
    # part variation >> gauge variation. Conservative estimate.
    # Standard AIAG: 10 parts × 3 operators × 2 replicates = 60 measurements
    # For high precision (%GRR < 10%): recommend 15-20 parts

    if target_grr_pct <= 10:
        n_parts_min = 15
        reason = "For %GRR ≤ 10% (excellent), AIAG MSA recommends ≥ 15 parts to achieve ndc ≥ 10."
    elif target_grr_pct <= 30:
        n_parts_min = 10
        reason = "For %GRR ≤ 30% (acceptable), AIAG MSA minimum is 10 parts."
    else:
        n_parts_min = 8
        reason = "For %GRR ≤ 30%, 8 parts minimum; increase if ndc < 5."

    n_total = n_parts_min * n_operators * n_replicates

    sens = []
    for np_ in [5, 8, 10, 12, 15, 20, 25]:
        total = np_ * n_operators * n_replicates
        ndc_approx = int(1.41 * math.sqrt(max(1, np_-1)) / math.sqrt(2))  # rough estimate
        sens.append({"n_parts": np_, "n_total": total, "ndc_estimate": ndc_approx})

    return SampleSizeResult(
        study_type="Gauge R&R Study",
        n_required=n_parts_min,
        n_recommendation=f"{n_parts_min} parts × {n_operators} operators × {n_replicates} replicates = {n_total} total measurements.",
        parameters={"target_grr_pct": target_grr_pct, "n_operators": n_operators, "n_replicates": n_replicates},
        explanation=(
            f"For a GRR study targeting %GRR ≤ {target_grr_pct}%, "
            f"with {n_operators} operators and {n_replicates} replicates per part: "
            f"need {n_parts_min} parts = {n_total} total measurements. "
            f"{reason}"
        ),
        interpretation=(
            f"AIAG MSA 4th Ed standard: 10×3×2 = 60 measurements. "
            f"Parts should span the full measurement range (not just nominal). "
            f"Include parts known to be at both spec limits if possible."
        ),
        sensitivity_table=sens,
        chart_data={"n_parts": [s["n_parts"] for s in sens],
                    "n_total": [s["n_total"] for s in sens],
                    "required_n": n_parts_min,
                    "study_type": "grr"},
    )


# ── 4. Attribute Sampling (AQL) ───────────────────────────────────────────────

def sample_size_attribute(
    lot_size: int = 1000,
    aql: float = 1.0,           # acceptable quality level (%)
    inspection_level: str = "II",   # I, II, III (II is standard)
    sampling_type: str = "normal",  # normal, tightened, reduced
) -> SampleSizeResult:
    """
    AQL attribute sampling per ISO 2859-1 / ANSI Z1.4.
    Returns sample size letter code and sample size.
    """
    # ISO 2859-1 Table 1: Sample size code letters
    lot_ranges = [
        (2, 8, "A"), (9, 15, "B"), (16, 25, "C"), (26, 50, "D"),
        (51, 90, "E"), (91, 150, "F"), (151, 280, "G"), (281, 500, "H"),
        (501, 1200, "J"), (1201, 3200, "K"), (3201, 10000, "L"),
        (10001, 35000, "M"), (35001, 150000, "N"), (150001, 500000, "P"),
        (500001, float('inf'), "Q"),
    ]
    level_offsets = {"I": -1, "II": 0, "III": 1}
    letters = "ABCDEFGHJKLMNPQR"

    code_letter = "J"  # default
    for lo, hi, letter in lot_ranges:
        if lo <= lot_size <= hi:
            idx = letters.index(letter)
            adj_idx = max(0, min(len(letters)-1, idx + level_offsets.get(inspection_level, 0)))
            code_letter = letters[adj_idx]
            break

    # ISO 2859-1 Table 2A (normal inspection) sample sizes
    code_to_n = {"A":2,"B":3,"C":5,"D":8,"E":13,"F":20,"G":32,"H":50,
                 "J":80,"K":125,"L":200,"M":315,"N":500,"P":800,"Q":1250,"R":2000}

    # AQL to accept/reject numbers (simplified for common AQL values)
    # Format: {code_letter: {aql: (ac, re)}}
    aql_table = {
        "J": {0.65:(1,2), 1.0:(2,3), 1.5:(3,4), 2.5:(5,6), 4.0:(7,8), 6.5:(10,11)},
        "H": {0.65:(1,2), 1.0:(1,2), 1.5:(2,3), 2.5:(3,4), 4.0:(5,6), 6.5:(7,8)},
        "G": {0.65:(0,1), 1.0:(1,2), 1.5:(1,2), 2.5:(2,3), 4.0:(3,4), 6.5:(5,6)},
        "K": {0.65:(2,3), 1.0:(3,4), 1.5:(5,6), 2.5:(7,8), 4.0:(10,11), 6.5:(14,15)},
        "L": {0.65:(3,4), 1.0:(5,6), 1.5:(7,8), 2.5:(10,11), 4.0:(14,15), 6.5:(21,22)},
    }

    n = code_to_n.get(code_letter, 80)
    aql_key = min(aql_table.get(code_letter, {1.0:(2,3)}).keys(), key=lambda x: abs(x-aql))
    ac_re = aql_table.get(code_letter, {}).get(aql_key, (2,3))

    # Sensitivity table: OC curve points
    sens = []
    for pct_def in [0.1, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]:
        p = pct_def / 100
        prob_accept = float(sum(stats.binom.pmf(k, n, p) for k in range(ac_re[0]+1)))
        sens.append({"percent_defective": pct_def, "prob_accept": round(prob_accept, 4)})

    return SampleSizeResult(
        study_type="Attribute Sampling (AQL)",
        n_required=n,
        n_recommendation=f"Code letter {code_letter}: n={n} samples. Accept if ≤{ac_re[0]} defective, reject if ≥{ac_re[1]}.",
        parameters={"lot_size": lot_size, "aql": aql, "inspection_level": inspection_level},
        explanation=(
            f"ISO 2859-1 / ANSI Z1.4 normal inspection, Level {inspection_level}: "
            f"Lot size {lot_size} → Code Letter {code_letter} → n={n}. "
            f"AQL={aql}%: Accept if ≤{ac_re[0]} defects found, Reject if ≥{ac_re[1]}."
        ),
        interpretation=(
            f"AQL={aql}% means lots with {aql}% defective have a high probability of acceptance. "
            f"LTPD (lot tolerance percent defective, Pβ=10%) is approximately {aql*10:.1f}% for this plan."
        ),
        sensitivity_table=sens,
        chart_data={"pct_defective": [s["percent_defective"] for s in sens],
                    "prob_accept": [s["prob_accept"] for s in sens],
                    "required_n": n, "aql": aql,
                    "study_type": "attribute"},
    )


# ── 5. SPC Chart — Shift Detection ────────────────────────────────────────────

def sample_size_spc(
    shift_sigma: float = 1.0,   # shift to detect in sigma units
    alpha: float = 0.0027,      # false alarm rate (0.0027 = 3-sigma rule)
    power: float = 0.80,        # probability of detection
    chart_type: str = "Shewhart",  # "Shewhart", "CUSUM", "EWMA"
) -> SampleSizeResult:
    """
    How many subgroups until the chart detects a shift of delta sigma?
    Uses ARL (Average Run Length) calculations.
    """
    # ARL for Shewhart chart: ARL = 1/p where p = P(alarm | shift)
    z3 = stats.norm.ppf(1 - alpha/2)  # ≈ 3

    if chart_type == "Shewhart":
        # P(alarm) when mean shifts by delta*sigma
        p_alarm = 1 - stats.norm.cdf(z3 - shift_sigma) + stats.norm.cdf(-z3 - shift_sigma)
        arl_shifted = 1 / max(p_alarm, 0.0001)
        n_to_detect = int(math.ceil(-math.log(1 - power) / p_alarm))
    elif chart_type == "CUSUM":
        # CUSUM k=0.5: ARL for shift of δσ (Montgomery Table 9.4 approximation)
        # For δ=1σ: ARL≈10.4, δ=0.5σ: ARL≈26.6, δ=2σ: ARL≈4.0
        arl_lookup = {0.25:74, 0.5:27, 0.75:15, 1.0:10, 1.5:5, 2.0:4, 2.5:3}
        closest = min(arl_lookup.keys(), key=lambda x: abs(x - shift_sigma))
        arl_shifted = arl_lookup[closest]
        n_to_detect = int(arl_shifted * (-math.log(1-power)))
    else:  # EWMA λ=0.2
        # EWMA λ=0.2, L=3: ARL for shift δσ
        arl_lookup = {0.25:48, 0.5:18, 0.75:11, 1.0:8, 1.5:5, 2.0:4}
        closest = min(arl_lookup.keys(), key=lambda x: abs(x - shift_sigma))
        arl_shifted = arl_lookup.get(closest, 10)
        n_to_detect = int(arl_shifted * (-math.log(1-power)))

    # Comparison table
    sens = []
    for delta in [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]:
        p = 1 - stats.norm.cdf(z3 - delta) + stats.norm.cdf(-z3 - delta)
        arl_sh = round(1/max(p,0.0001), 1)
        arl_cs = {0.25:74, 0.5:27, 0.75:15, 1.0:10, 1.5:5, 2.0:4, 2.5:3, 3.0:2}.get(delta, arl_sh/3)
        arl_ew = {0.25:48, 0.5:18, 0.75:11, 1.0:8, 1.5:5, 2.0:4, 2.5:3, 3.0:2}.get(delta, arl_sh/4)
        sens.append({"shift_sigma": delta, "arl_shewhart": arl_sh,
                     "arl_cusum": arl_cs, "arl_ewma": arl_ew})

    return SampleSizeResult(
        study_type=f"SPC Chart — Shift Detection ({chart_type})",
        n_required=n_to_detect,
        n_recommendation=f"Expected {arl_shifted:.1f} subgroups until alarm. Need {n_to_detect} subgroups for {power*100:.0f}% detection probability.",
        parameters={"shift_sigma": shift_sigma, "chart_type": chart_type, "power": power},
        explanation=(
            f"{chart_type} chart will detect a {shift_sigma}σ shift in an average of {arl_shifted:.1f} subgroups (ARL₁). "
            f"For {power*100:.0f}% probability of detection: {n_to_detect} subgroups needed. "
            f"In-control ARL (false alarm rate): {'370' if chart_type=='Shewhart' else '465' if chart_type=='CUSUM' else '390'} subgroups."
        ),
        interpretation=(
            f"CUSUM (k=0.5) detects {shift_sigma}σ shifts in ~{sens[min(range(len(sens)), key=lambda i: abs(sens[i]['shift_sigma']-shift_sigma))]['arl_cusum']:.0f} subgroups vs "
            f"Shewhart {sens[min(range(len(sens)), key=lambda i: abs(sens[i]['shift_sigma']-shift_sigma))]['arl_shewhart']:.0f}. "
            f"Use CUSUM/EWMA when detecting shifts < 1.5σ is important."
        ),
        sensitivity_table=sens,
        chart_data={"shifts": [s["shift_sigma"] for s in sens],
                    "arl_shewhart": [s["arl_shewhart"] for s in sens],
                    "arl_cusum": [s["arl_cusum"] for s in sens],
                    "arl_ewma": [s["arl_ewma"] for s in sens],
                    "target_shift": shift_sigma,
                    "study_type": "spc"},
    )
