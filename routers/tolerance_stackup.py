"""
StatMind P1-B — Tolerance Stack-Up Analysis
RSS (Root Sum Square) + Worst Case for GD&T assemblies.
Apple MQE explicit requirement. No free tool exists.
Answers: "Will my assembly fit together across all tolerance combinations?"
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StackupDimension:
    name: str
    nominal: float
    plus_tol: float       # +tolerance (positive)
    minus_tol: float      # -tolerance (positive, represents -)
    direction: int        # +1 = additive, -1 = subtractive in loop
    distribution: str     # "uniform", "normal", "bilateral"
    process_sigma: float  # sigma level of the tolerance (default 3)
    # Computed
    bilateral_tol: float = 0.0
    mean_shift: float = 0.0


@dataclass
class StackupResult:
    title: str
    # Dimensions
    dimensions: list
    n_dimensions: int
    # Nominal gap/condition
    nominal_gap: float
    # Worst Case Analysis
    wc_min_gap: float
    wc_max_gap: float
    wc_verdict: str
    wc_within_requirement: bool
    # RSS Statistical Analysis
    rss_mean_gap: float
    rss_std_gap: float
    rss_min_gap_3sigma: float
    rss_max_gap_3sigma: float
    rss_cpk: Optional[float]
    rss_ppm: Optional[float]
    rss_sigma_level: Optional[float]
    rss_verdict: str
    rss_within_requirement: bool
    # Requirements
    min_gap_required: Optional[float]
    max_gap_required: Optional[float]
    # Contributor analysis
    top_contributors: list  # [{name, pct_contribution, std_contribution}]
    # Sensitivity
    sensitivity: list       # [{name, delta_per_sigma}]
    # Chart data
    chart_data: dict
    # Conclusions
    conclusion: str
    recommendation: str


def analyze_stackup(
    title: str,
    dimensions: list,          # list of dicts: {name, nominal, plus_tol, minus_tol, direction}
    min_gap: float = None,     # minimum required gap (e.g. clearance minimum)
    max_gap: float = None,     # maximum required gap (e.g. interference maximum)
    sigma_level: float = 3.0,  # process sigma for RSS
    confidence: float = 0.9973,  # 99.73% for 3σ
) -> StackupResult:
    """
    Perform tolerance stack-up analysis using both
    Worst Case and RSS (Statistical) methods.
    """
    # Parse dimensions
    parsed_dims = []
    for d in dimensions:
        name      = d.get("name", "Dim")
        nominal   = float(d.get("nominal", 0))
        plus_tol  = float(d.get("plus_tol", 0))
        minus_tol = float(d.get("minus_tol", 0))
        direction = int(d.get("direction", 1))
        dist      = d.get("distribution", "bilateral")
        proc_sigma= float(d.get("process_sigma", sigma_level))

        # Bilateral tolerance = average of +/- (for asymmetric tolerances)
        bilateral = (plus_tol + minus_tol) / 2
        mean_shift = (plus_tol - minus_tol) / 2  # shift if asymmetric

        parsed_dims.append(StackupDimension(
            name=name, nominal=nominal,
            plus_tol=plus_tol, minus_tol=minus_tol,
            direction=direction, distribution=dist,
            process_sigma=proc_sigma,
            bilateral_tol=bilateral,
            mean_shift=mean_shift,
        ))

    # ── Nominal gap ────────────────────────────────────────────────────────────
    nominal_gap = sum(d.nominal * d.direction for d in parsed_dims)

    # ── Worst Case Analysis ───────────────────────────────────────────────────
    # Worst case min: all dims that increase gap at minimum, decrease gap at maximum
    wc_max_tol = sum(d.plus_tol if d.direction > 0 else d.minus_tol for d in parsed_dims)
    wc_min_tol = sum(d.minus_tol if d.direction > 0 else d.plus_tol for d in parsed_dims)
    wc_max_gap = nominal_gap + wc_max_tol
    wc_min_gap = nominal_gap - wc_min_tol

    # ── RSS Statistical Analysis ──────────────────────────────────────────────
    # RSS standard deviation of the assembly gap
    # σ_assembly = sqrt(Σ (bilateral_tol_i / process_sigma_i)²)
    rss_variance = sum((d.bilateral_tol / d.process_sigma) ** 2 for d in parsed_dims)
    rss_std = float(np.sqrt(rss_variance))

    # Mean gap (accounting for asymmetric mean shifts)
    rss_mean = nominal_gap + sum(d.mean_shift * d.direction for d in parsed_dims)

    # 3σ limits on the assembly gap
    rss_min = rss_mean - sigma_level * rss_std
    rss_max = rss_mean + sigma_level * rss_std

    # Cpk and PPM if requirements given
    rss_cpk = rss_ppm = rss_sigma = None
    if min_gap is not None and max_gap is not None and rss_std > 0:
        cpu = (max_gap - rss_mean) / (3 * rss_std)
        cpl = (rss_mean - min_gap) / (3 * rss_std)
        rss_cpk = round(float(min(cpu, cpl)), 4)
        rss_ppm = float((
            stats.norm.cdf(min_gap, rss_mean, rss_std) +
            (1 - stats.norm.cdf(max_gap, rss_mean, rss_std))
        ) * 1e6)
        rss_sigma = round(float(rss_cpk * 3), 3)
    elif min_gap is not None and rss_std > 0:
        cpl = (rss_mean - min_gap) / (3 * rss_std)
        rss_cpk = round(float(cpl), 4)
        rss_ppm = float(stats.norm.cdf(min_gap, rss_mean, rss_std) * 1e6)
        rss_sigma = round(float(rss_cpk * 3), 3)

    # ── Contributor Analysis ─────────────────────────────────────────────────
    total_rss_var = rss_variance if rss_variance > 0 else 1e-12
    contributors = []
    for d in parsed_dims:
        var_i = (d.bilateral_tol / d.process_sigma) ** 2
        pct = round(float(var_i / total_rss_var * 100), 1)
        contributors.append({
            "name": d.name,
            "nominal": round(d.nominal, 6),
            "plus_tol": round(d.plus_tol, 6),
            "minus_tol": round(d.minus_tol, 6),
            "bilateral": round(d.bilateral_tol, 6),
            "std_contribution": round(float(d.bilateral_tol / d.process_sigma), 6),
            "variance_contribution": round(float(var_i), 8),
            "pct_contribution": pct,
        })
    contributors.sort(key=lambda x: x["pct_contribution"], reverse=True)

    # ── Sensitivity ──────────────────────────────────────────────────────────
    sensitivity = []
    for d in parsed_dims:
        # How much does a 1σ change in this dim change the gap?
        delta = float(d.direction * d.bilateral_tol / d.process_sigma)
        sensitivity.append({
            "name": d.name,
            "direction": d.direction,
            "sensitivity": round(delta, 6),
            "pct_of_total_std": round(abs(delta) / (rss_std + 1e-12) * 100, 1),
        })
    sensitivity.sort(key=lambda x: abs(x["sensitivity"]), reverse=True)

    # ── Verdicts ─────────────────────────────────────────────────────────────
    wc_ok = True
    if min_gap is not None and wc_min_gap < min_gap:
        wc_ok = False
    if max_gap is not None and wc_max_gap > max_gap:
        wc_ok = False

    rss_ok = True
    if min_gap is not None and rss_min < min_gap:
        rss_ok = False
    if max_gap is not None and rss_max > max_gap:
        rss_ok = False

    wc_verdict = "PASSES worst case" if wc_ok else "FAILS worst case — interference in all combinations"
    rss_verdict = f"PASSES RSS at {sigma_level:.0f}σ ({confidence*100:.2f}%)" if rss_ok else f"FAILS RSS at {sigma_level:.0f}σ — {rss_ppm:.0f} PPM predicted"

    # ── Chart Data ────────────────────────────────────────────────────────────
    x = np.linspace(rss_mean - 5*rss_std, rss_mean + 5*rss_std, 300)
    y = stats.norm.pdf(x, rss_mean, rss_std).tolist() if rss_std > 0 else [0.0]*300

    chart_data = {
        "nominal_gap": round(nominal_gap, 6),
        "rss_mean": round(rss_mean, 6),
        "rss_std": round(rss_std, 6),
        "rss_min_3s": round(rss_min, 6),
        "rss_max_3s": round(rss_max, 6),
        "wc_min": round(wc_min_gap, 6),
        "wc_max": round(wc_max_gap, 6),
        "min_gap": min_gap,
        "max_gap": max_gap,
        "distribution_x": [round(float(v), 6) for v in x],
        "distribution_y": [round(float(v), 8) for v in y],
        "contributors": contributors[:8],
    }

    # ── Conclusion ────────────────────────────────────────────────────────────
    top = contributors[0] if contributors else {}
    conclusion = (
        f"Nominal gap = {nominal_gap:.5f}. "
        f"Worst case: [{wc_min_gap:.5f}, {wc_max_gap:.5f}] — {wc_verdict}. "
        f"RSS (3σ): [{rss_min:.5f}, {rss_max:.5f}] — {rss_verdict}. "
        + (f"Cpk = {rss_cpk:.3f}, PPM = {rss_ppm:.0f}. " if rss_cpk else "")
        + (f"Largest contributor: {top.get('name','')} ({top.get('pct_contribution',0)}% of variance)." if top else "")
    )

    rec_parts = []
    if not rss_ok and rss_cpk and rss_cpk < 1.33:
        worst = contributors[0]["name"] if contributors else "top dimension"
        rec_parts.append(f"Tighten tolerance on '{worst}' first — it contributes {contributors[0]['pct_contribution']}% of assembly variance.")
    if wc_ok and rss_ok:
        rec_parts.append("Assembly meets both worst-case and statistical requirements. Consider relaxing the largest contributor's tolerance to reduce cost.")
    if not wc_ok and rss_ok:
        rec_parts.append("RSS passes but worst case fails — consider 100% inspection or tighter tolerances on top contributors to eliminate all interference.")

    return StackupResult(
        title=title,
        dimensions=contributors,
        n_dimensions=len(parsed_dims),
        nominal_gap=round(nominal_gap, 6),
        wc_min_gap=round(wc_min_gap, 6),
        wc_max_gap=round(wc_max_gap, 6),
        wc_verdict=wc_verdict,
        wc_within_requirement=wc_ok,
        rss_mean_gap=round(rss_mean, 6),
        rss_std_gap=round(rss_std, 6),
        rss_min_gap_3sigma=round(rss_min, 6),
        rss_max_gap_3sigma=round(rss_max, 6),
        rss_cpk=rss_cpk,
        rss_ppm=round(rss_ppm, 1) if rss_ppm else None,
        rss_sigma_level=rss_sigma,
        rss_verdict=rss_verdict,
        rss_within_requirement=rss_ok,
        min_gap_required=min_gap,
        max_gap_required=max_gap,
        top_contributors=contributors[:5],
        sensitivity=sensitivity[:5],
        chart_data=chart_data,
        conclusion=conclusion,
        recommendation=" ".join(rec_parts) if rec_parts else "Stack-up is acceptable.",
    )
